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
import re
import time
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from privacyscope.core.interfaces import PageFetcher
from privacyscope.core.types import Domain, RawEvidence, utc_now

logger = logging.getLogger(__name__)


# =============================================================================
# Constantes e defaults
# =============================================================================
DEFAULT_USER_AGENT = (
    "PrivacyScope/0.1.0 (research; +https://github.com/cristianosilverio/privacyscope)"
)

DEFAULT_MAX_RESPONSE_BYTES = 5_000_000  # 5 MB

#: Padrões default para detecção de subpáginas relevantes em sites institucionais BR.
#: Cada chave é uma categoria; cada valor é uma lista de regexes (case-insensitive)
#: que casa contra o texto OU o href de um <a>. O usuário pode sobrescrever via YAML
#: passando outro dict em params["subpage_categories"].
#:
#: Sobre o separador ``[\s_\-]*``: usado entre palavras-chave para casar tanto texto
#: visível (que usa espaços: "Política de Privacidade") quanto hrefs (que usam
#: hífens ou underscores: "politica-de-privacidade", "politica_de_privacidade").
#: \s sozinho NÃO cobre hífens, então usar ``\s*`` aqui falharia em todos os hrefs reais.
#:
#: TODO (refinamento pós-piloto): os defaults atuais são permissivos demais.
#: Smoke test em 17/05/2026 capturou false positives óbvios: "Denúncia de
#: descumprimento da LGPD" e "3ª Semana Serpro de Privacidade e Proteção de Dados"
#: foram classificados como politica_privacidade. Padrões com âncora fraca
#: (``\blgpd\b`` sozinho, ``prote\w*[\s_\-]*de[\s_\-]*dados`` sozinho) sobrematcham.
#: Refinar com base em rotulagem manual da piloto n=50. Ver docs/notas_de_refinamento.md.
DEFAULT_SUBPAGE_CATEGORIES: dict[str, list[str]] = {
    "politica_privacidade": [
        r"polit\w+[\s_\-]*de[\s_\-]*privacid",
        r"aviso[\s_\-]*de[\s_\-]*privacid",
        r"privacy[\s_\-]*policy",
        r"\blgpd\b",
        r"prote\w*[\s_\-]*de[\s_\-]*dados",
    ],
    "termos_uso": [
        r"termos[\s_\-]*de[\s_\-]*uso",
        r"termos[\s_\-]*de[\s_\-]*servic",
        r"terms[\s_\-]*of[\s_\-]*(use|service)",
        r"condi\w*[\s_\-]*de[\s_\-]*uso",
    ],
    "encarregado": [
        r"encarregad\w+",
        r"\bdpo\b",
        r"data[\s_\-]*protection[\s_\-]*officer",
        r"fale[\s_\-]*conosco.*lgpd",
        r"contato.*prote\w*[\s_\-]*de[\s_\-]*dados",
    ],
}


# =============================================================================
# Exceções
# =============================================================================
class FetchError(Exception):
    """Erro fatal durante coleta — sem evidência possível."""


class RobotsDisallowedError(FetchError):
    """robots.txt do site proíbe coleta da raiz pelo nosso User-Agent."""


class ResponseTooLargeError(FetchError):
    """Resposta excedeu max_response_bytes."""


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

        cats = params.get("subpage_categories", DEFAULT_SUBPAGE_CATEGORIES)
        if not isinstance(cats, dict):
            raise ValueError("subpage_categories deve ser dict[str, list[str]]")
        validated_cats: dict[str, list[str]] = {}
        for cat, patterns in cats.items():
            if not isinstance(cat, str) or not cat:
                raise ValueError(f"chave de categoria deve ser string não-vazia; recebido: {cat!r}")
            if not isinstance(patterns, list):
                raise ValueError(f"patterns para '{cat}' deve ser lista de strings de regex")
            for p in patterns:
                if not isinstance(p, str):
                    raise ValueError(f"pattern em '{cat}' deve ser str; recebido: {p!r}")
                try:
                    re.compile(p, re.IGNORECASE)
                except re.error as e:
                    raise ValueError(f"regex inválido em '{cat}': {p!r}: {e}") from e
            validated_cats[cat] = list(patterns)
        cfg["subpage_categories"] = validated_cats

        cfg["max_per_category"] = params.get("max_per_category", 1)
        if not isinstance(cfg["max_per_category"], int) or cfg["max_per_category"] < 1:
            raise ValueError("max_per_category deve ser inteiro >= 1")

        cfg["max_total_subpages"] = params.get("max_total_subpages", 5)
        if not isinstance(cfg["max_total_subpages"], int) or cfg["max_total_subpages"] < 0:
            raise ValueError("max_total_subpages deve ser inteiro >= 0")

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
    # Extração de subpáginas
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_subpage_candidates(
        html: bytes,
        base_url: str,
        categories: dict[str, list[str]],
        max_per_category: int,
        max_total: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """Encontra subpáginas candidatas no HTML raiz e devolve auditoria por categoria.

        Retorno (estrutura compatível com RawEvidence.subpage_selection):
            {categoria: [{url, matched_pattern, matched_against, snippet}, ...], ...}

        Cada <a> contribui para no máximo uma categoria. Categorias sem matches
        são omitidas do retorno.
        """
        if max_total == 0:
            return {}

        soup = BeautifulSoup(html, "lxml")
        compiled = {
            cat: [re.compile(p, re.IGNORECASE) for p in patterns]
            for cat, patterns in categories.items()
        }

        result: dict[str, list[dict[str, Any]]] = {cat: [] for cat in categories}
        seen_urls: set[str] = set()
        total = 0

        for a in soup.find_all("a", href=True):
            if total >= max_total:
                break
            href = str(a["href"]).strip()
            text = (a.get_text() or "").strip()
            aria_label = str(a.get("aria-label", "")).strip()
            title_attr = str(a.get("title", "")).strip()
            if not href:
                continue

            # Ordem de inspeção (importante para o audit_trail):
            #   1) text        — o que humano vê
            #   2) aria-label  — o que assistive tech "vê" (WCAG / eMAG / LBI)
            #   3) title       — tooltip
            #   4) href        — URL/path
            # Sites com acessibilidade decente (gov.br, grandes empresas) frequentemente
            # têm ícones/links com texto vago mas aria-label explícito.
            inspection_order = [
                ("text",       text,       text.lower()),
                ("aria-label", aria_label, aria_label.lower()),
                ("title",      title_attr, title_attr.lower()),
                ("href",       href,       href.lower()),
            ]

            for cat, regexes in compiled.items():
                if len(result[cat]) >= max_per_category:
                    continue
                matched_pattern: str | None = None
                matched_against: str | None = None
                snippet_source: str = ""

                for source_name, source_raw, source_lower in inspection_order:
                    if not source_lower:
                        continue
                    for rx in regexes:
                        if rx.search(source_lower):
                            matched_pattern = rx.pattern
                            matched_against = source_name
                            snippet_source = source_raw
                            break
                    if matched_pattern is not None:
                        break

                if matched_pattern is None:
                    continue

                full_url = urljoin(base_url, href)
                if not full_url.startswith(("http://", "https://")):
                    continue
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                result[cat].append({
                    "url": full_url,
                    "matched_pattern": matched_pattern,
                    "matched_against": matched_against,
                    "snippet": snippet_source[:120],
                })
                total += 1
                break  # cada <a> casa em no máximo uma categoria

        # Omite categorias vazias
        return {cat: items for cat, items in result.items() if items}

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
            subpage_selection = self._extract_subpage_candidates(
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
    "DEFAULT_USER_AGENT",
    "FetchError",
    "RobotsDisallowedError",
    "ResponseTooLargeError",
]
