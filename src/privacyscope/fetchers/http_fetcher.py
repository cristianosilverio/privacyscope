"""
HttpFetcher — coleta HTTP simples, sem renderização JavaScript.

Primeira tentativa do FallbackChain. Adequado para sites com conteúdo
servido em HTML estático. Sites que dependem de SPA escalonam para o
PlaywrightFetcher.

Funcionalidades:
    - GET assíncrono via httpx.AsyncClient
    - Coleta da página raiz + subpáginas candidatas (configuráveis)
    - Captura de cookies via Set-Cookie HTTP (não captura cookies setados
      por document.cookie em JavaScript — limitação intrínseca)
    - Respeito a robots.txt por default (configurável)
    - Extração de subpáginas por regex contra texto OU href dos links
    - Auditoria completa: cada subpágina selecionada registra qual regex
      disparou e contra qual atributo (text|href), com snippet evidencial

Referências:
    - Le Pochat et al. (2019): User-Agent identificável de pesquisa
    - Dabrowski et al. (2019): coleta de cookies em larga escala
    - RFC 9309: Robots Exclusion Protocol
"""

from __future__ import annotations

import asyncio
import http.cookies as http_cookies
import logging
import time
from typing import Any, ClassVar
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from privacyscope.core.interfaces import PageFetcher
from privacyscope.core.types import Domain, RawEvidence, utc_now
from privacyscope.fetchers._exceptions import (
    FetchError,
    ResponseTooLargeError,
    RobotsDisallowedError,
)
from privacyscope.fetchers._subpage import (
    DEFAULT_SUBPAGE_CATEGORIES,
    extract_subpage_candidates,
    validate_subpage_config,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constantes e defaults
# =============================================================================
DEFAULT_HTTP_USER_AGENT = (
    "PrivacyScope/0.1.0 (research; +https://github.com/cristianosilverio/privacyscope)"
)
# Alias para retrocompat. Novos códigos devem usar DEFAULT_HTTP_USER_AGENT.
DEFAULT_USER_AGENT = DEFAULT_HTTP_USER_AGENT

DEFAULT_MAX_RESPONSE_BYTES = 5_000_000  # 5 MB

# DEFAULT_SUBPAGE_CATEGORIES vem de privacyscope.fetchers._subpage e é
# reexportado abaixo para retrocompatibilidade. Centralizar em _subpage permite
# que HttpFetcher e PlaywrightFetcher compartilhem a mesma definição e que
# refinamentos pós-piloto afetem os dois fetchers de uma vez só.


# Exceções importadas de privacyscope.fetchers._exceptions (compartilhadas).
# Reexportadas no __all__ para retrocompatibilidade.


# =============================================================================
# HttpFetcher
# =============================================================================
class HttpFetcher(PageFetcher):
    """Coleta HTTP simples (sem JS).

    Implementa PageFetcher (camada 2). Usado como primeira tentativa do
    FallbackChain por ser ~10x mais rápido que coletas com navegador headless.
    """

    name: ClassVar[str] = "http_simples"
    version: ClassVar[str] = "0.1.0"

    def __init__(self, default_user_agent: str | None = None) -> None:
        self.default_user_agent = default_user_agent or DEFAULT_USER_AGENT

    # ------------------------------------------------------------------
    # Validação de params
    # ------------------------------------------------------------------
    def _validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve defaults e valida params do protocolo. Levanta ValueError em falha."""
        cfg: dict[str, Any] = {}

        cfg["user_agent"] = params.get("user_agent", self.default_user_agent)
        if not isinstance(cfg["user_agent"], str) or not cfg["user_agent"]:
            raise ValueError("user_agent deve ser string não-vazia")

        for key, default in (("connect_timeout_s", 10.0), ("read_timeout_s", 30.0)):
            cfg[key] = params.get(key, default)
            if not isinstance(cfg[key], (int, float)) or cfg[key] <= 0:
                raise ValueError(f"{key} deve ser número positivo")

        cfg["max_redirects"] = params.get("max_redirects", 5)
        if not isinstance(cfg["max_redirects"], int) or cfg["max_redirects"] < 0:
            raise ValueError("max_redirects deve ser inteiro >= 0")

        cfg["max_response_bytes"] = params.get("max_response_bytes", DEFAULT_MAX_RESPONSE_BYTES)
        if not isinstance(cfg["max_response_bytes"], int) or cfg["max_response_bytes"] < 1024:
            raise ValueError("max_response_bytes deve ser inteiro >= 1024")

        cfg["respect_robots_txt"] = params.get("respect_robots_txt", True)
        if not isinstance(cfg["respect_robots_txt"], bool):
            raise ValueError("respect_robots_txt deve ser bool")

        # Validação de subpage_categories, max_per_category, max_total_subpages
        # delegada ao módulo compartilhado fetchers/_subpage.py — mesma lógica
        # consumida pelo PlaywrightFetcher.
        cats, mpc, mts = validate_subpage_config(params)
        cfg["subpage_categories"] = cats
        cfg["max_per_category"] = mpc
        cfg["max_total_subpages"] = mts

        return cfg

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------
    @staticmethod
    async def _load_robots(
        base_url: str, user_agent: str, timeout_s: float
    ) -> tuple[RobotFileParser | None, str | None]:
        """Baixa e parseia /robots.txt do host. Retorna (parser, msg_erro_opcional).

        Convenção RFC 9309: 404 ou indisponível = sem restrição; 401/403 = totalmente
        proibido (registramos como nota mas não bloqueamos por completo, deixando a
        decisão fina ao can_fetch chamado depois).
        """
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s, follow_redirects=True, headers={"User-Agent": user_agent}
            ) as client:
                resp = await client.get(robots_url)
            if resp.status_code == 200:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                return parser, None
            if resp.status_code in (401, 403):
                # Tratar como acesso restrito a robots; conservador.
                parser = RobotFileParser()
                parser.parse(["User-agent: *", "Disallow: /"])
                return parser, f"robots.txt {robots_url}: status {resp.status_code} (interpretado como Disallow:/)"
            if resp.status_code == 404:
                return None, None
            return None, f"robots.txt {robots_url}: status {resp.status_code} (ignorado)"
        except httpx.HTTPError as e:
            return None, f"robots.txt {robots_url}: {type(e).__name__}: {e} (ignorado)"

    # ------------------------------------------------------------------
    # Extração de cookies HTTP
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_set_cookies(response_headers: httpx.Headers) -> list[dict[str, Any]]:
        """Parseia cabeçalhos Set-Cookie e devolve lista de dicts."""
        cookies: list[dict[str, Any]] = []
        for raw in response_headers.get_list("set-cookie"):
            sc = http_cookies.SimpleCookie()
            try:
                sc.load(raw)
            except http_cookies.CookieError as e:
                logger.debug("Set-Cookie inválido ignorado: %s (%s)", raw[:120], e)
                continue
            for name, morsel in sc.items():
                cookies.append({
                    "name": name,
                    "value": morsel.value,
                    "domain": morsel["domain"],
                    "path": morsel["path"] or "/",
                    "expires": morsel["expires"],
                    "max_age": morsel["max-age"],
                    "secure": bool(morsel["secure"]),
                    "httpOnly": bool(morsel["httponly"]),
                    "sameSite": morsel["samesite"] if "samesite" in morsel else "",
                })
        return cookies

    # ------------------------------------------------------------------
    # Coleta de uma URL individual
    # ------------------------------------------------------------------
    async def _fetch_one(
        self, client: httpx.AsyncClient, url: str, max_bytes: int
    ) -> tuple[bytes, dict[str, str], list[dict[str, Any]], dict[str, Any]]:
        """GET único; devolve (body, headers, cookies_set, network_log_entry).

        Levanta ResponseTooLargeError ou httpx.HTTPError em falha.
        """
        t0 = time.perf_counter()
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()

            content_length_header = resp.headers.get("content-length")
            if content_length_header:
                try:
                    if int(content_length_header) > max_bytes:
                        raise ResponseTooLargeError(
                            f"{url}: content-length={content_length_header} > max={max_bytes}"
                        )
                except ValueError:
                    pass  # content-length malformado, deixa a checagem dinâmica abaixo decidir

            buf = bytearray()
            async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise ResponseTooLargeError(
                        f"{url}: resposta excedeu {max_bytes} bytes durante streaming"
                    )

            body = bytes(buf)
            headers = {k: v for k, v in resp.headers.items()}
            status = resp.status_code
            set_cookies = self._extract_set_cookies(resp.headers)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        net_entry = {
            "url": url,
            "method": "GET",
            "status": status,
            "size_bytes": len(body),
            "duration_ms": duration_ms,
            "content_type": headers.get("content-type", ""),
        }
        return body, headers, set_cookies, net_entry

    # ------------------------------------------------------------------
    # Implementação principal: fetch(domain, params) -> RawEvidence
    # ------------------------------------------------------------------
    async def fetch(self, domain: Domain, params: dict[str, Any]) -> RawEvidence:
        cfg = self._validate_params(params)

        errors: list[str] = []
        network_log: list[dict[str, Any]] = []
        headers_by_url: dict[str, dict[str, str]] = {}
        html_pages: dict[str, bytes] = {}
        all_cookies: list[dict[str, Any]] = []
        subpage_selection: dict[str, list[dict[str, Any]]] = {}

        # 1) robots.txt
        robot_parser: RobotFileParser | None = None
        if cfg["respect_robots_txt"]:
            robot_parser, robots_msg = await self._load_robots(
                domain.url, cfg["user_agent"], cfg["read_timeout_s"]
            )
            if robots_msg:
                errors.append(robots_msg)
            if robot_parser is not None and not robot_parser.can_fetch(
                cfg["user_agent"], domain.url
            ):
                raise RobotsDisallowedError(
                    f"robots.txt proíbe coleta de {domain.url} pelo UA {cfg['user_agent']!r}"
                )

        # 2) Cliente HTTP
        timeout = httpx.Timeout(
            connect=cfg["connect_timeout_s"],
            read=cfg["read_timeout_s"],
            write=10.0,
            pool=10.0,
        )
        client_headers = {
            "User-Agent": cfg["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(
            timeout=timeout,
            max_redirects=cfg["max_redirects"],
            follow_redirects=True,
            headers=client_headers,
        ) as client:
            # 3) Coleta da raiz (falha aqui é fatal)
            try:
                root_body, root_headers, root_cookies, root_net = await self._fetch_one(
                    client, domain.url, cfg["max_response_bytes"]
                )
            except httpx.HTTPError as e:
                raise FetchError(f"falha ao coletar raiz {domain.url}: {type(e).__name__}: {e}") from e

            html_pages["/"] = root_body
            headers_by_url[domain.url] = root_headers
            all_cookies.extend(root_cookies)
            network_log.append(root_net)

            # 4) Extração de subpáginas candidatas
            subpage_selection = extract_subpage_candidates(
                root_body,
                domain.url,
                cfg["subpage_categories"],
                cfg["max_per_category"],
                cfg["max_total_subpages"],
            )

            # 5) Filtrar por robots.txt e preparar fetches concorrentes
            jobs: list[tuple[str, str]] = []  # (category, url)
            for cat, items in subpage_selection.items():
                for item in items:
                    sub_url = item["url"]
                    if robot_parser is not None and not robot_parser.can_fetch(
                        cfg["user_agent"], sub_url
                    ):
                        errors.append(f"robots.txt proíbe subpágina {sub_url}")
                        continue
                    jobs.append((cat, sub_url))

            # 6) Fetch concorrente das subpáginas
            if jobs:
                results = await asyncio.gather(
                    *[self._fetch_one(client, url, cfg["max_response_bytes"]) for _, url in jobs],
                    return_exceptions=True,
                )
                for (cat, sub_url), result in zip(jobs, results):
                    if isinstance(result, BaseException):
                        errors.append(
                            f"subpagina {sub_url}: {type(result).__name__}: {result}"
                        )
                        continue
                    sub_body, sub_headers, sub_cookies, sub_net = result
                    sub_path = urlparse(sub_url).path or "/"
                    # Evita colisão com a raiz se subpath também for "/"
                    if sub_path == "/":
                        sub_path = f"/__sub_{cat}"
                    html_pages[sub_path] = sub_body
                    headers_by_url[sub_url] = sub_headers
                    all_cookies.extend(sub_cookies)
                    network_log.append(sub_net)

        # 7) RawEvidence consolidada
        return RawEvidence(
            domain=domain,
            html_pages=html_pages,
            cookies=all_cookies,
            headers=headers_by_url,
            screenshot=None,
            network_log=network_log,
            subpage_selection=subpage_selection,
            fetcher_name=self.name,
            timestamp_utc=utc_now(),
            errors=errors,
        )


__all__ = [
    "HttpFetcher",
    "DEFAULT_SUBPAGE_CATEGORIES",
    "DEFAULT_HTTP_USER_AGENT",
    "DEFAULT_USER_AGENT",
    "FetchError",
    "RobotsDisallowedError",
    "ResponseTooLargeError",
]
