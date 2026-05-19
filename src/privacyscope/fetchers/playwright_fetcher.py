"""
PlaywrightFetcher — coleta multi-fase com Chromium headless.

Segundo plugin concreto de PageFetcher. Implementa as 5 fases definidas no
projeto para distinguir cookies pré-consent, pós-consent e (opcionalmente)
pós-revogação, gerando evidência regulatória sobre aderência aos artigos
7º e 8º da LGPD e às orientações da ANPD (2023) sobre cookies.

Fases:
    1) pre_consent       — captura cookies/screenshot ANTES de qualquer interação
    2) attempt_accept    — clica banner de consent (best-effort)
    3) post_consent      — recaptura após accept e novo networkidle
    4) attempt_revoke    — (opt-in) abre central de privacidade e rejeita
    5) post_revocation   — recaptura após revogação

Decisões arquiteturais:
    - Per-fetch browser launch: cada fetch instancia Playwright + Chromium
      novos, em processo separado. Garante zero vazamento de estado entre
      sites. Custo ~1s/site, defensável em banca trivialmente.
    - User-Agent híbrido: emula Chrome real (necessário para Playwright
      passar por anti-bot básico) + sufixo de identificação acadêmica.
    - Lazy loading: scroll programático após cada navegação, máximo de
      iterações configurável, para garantir DOM totalmente renderizado.
    - Subpáginas: extraídas via page.content() pós-consent (DOM maduro)
      usando extractor compartilhado em _subpage.py. Coleta de HTML das
      subpáginas no mesmo Playwright context (mantém estado de cookies).
    - Cookies: value mascarado (truncado + hash SHA-256 curto) para
      preservar análise sem armazenar identificadores potenciais.

Referências:
    - Rasaii et al. (2023): metodologia pre/post-consent
    - Dabrowski et al. (2019): cookies pós-GDPR
    - LGPD art. 7º, 8º §5º; ANPD Guia de Cookies (2023)
    - eMAG / Decreto 5.296/2004 / LBI: ARIA como sinal primário
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any, ClassVar
from urllib.parse import urlparse

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from privacyscope.core.interfaces import PageFetcher
from privacyscope.core.types import Domain, RawEvidence, utc_now
from privacyscope.fetchers._exceptions import (
    FetchError,
    NavigationFailedError,
)
from privacyscope.fetchers._subpage import (
    extract_subpage_candidates,
    validate_subpage_config,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constantes e defaults
# =============================================================================
#: User-Agent híbrido: Chrome real (passa anti-bot básico) + sufixo de
#: identificação acadêmica. Defensável: não enganamos servidores sobre o
#: navegador (é Chromium de verdade); identificamos o propósito de pesquisa.
DEFAULT_PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "PrivacyScope/0.1.0 (research; +https://github.com/cristianosilverio/privacyscope)"
)

DEFAULT_VIEWPORT = {"width": 1366, "height": 768}
DEFAULT_LOCALE = "pt-BR"

DEFAULT_NAVIGATION_TIMEOUT_MS = 30_000
DEFAULT_NETWORKIDLE_TIMEOUT_MS = 5_000
DEFAULT_CONSENT_CLICK_TIMEOUT_MS = 3_000
DEFAULT_SCROLL_MAX_ITERATIONS = 5
DEFAULT_SCROLL_WAIT_MS = 500
DEFAULT_REVOKE_INTERSTITIAL_MS = 1_500   # entre abrir centro e clicar rejeitar

#: Filtro default de tipos de recurso a registrar no network_log.
#: ``None`` = registrar tudo. Sobrescritível via params.
DEFAULT_NETWORK_LOG_RESOURCE_TYPES: list[str] | None = None

#: Detecção de banner de consent — configurável via protocol.yaml.
DEFAULT_CONSENT_BANNER_CONFIG: dict[str, list[str]] = {
    "banner_container_selectors": [
        "[role='dialog'][aria-modal='true']",
        "[role='alertdialog']",
        "[id*='cookie' i]",
        "[class*='cookie' i]",
        "[id*='consent' i]",
        "[class*='consent' i]",
        "[id*='lgpd' i]",
        "[class*='lgpd' i]",
        "[id*='gdpr' i]",
    ],
    "accept_button_selectors": [
        # ARIA primeiro (eMAG / LBI)
        "[aria-label*='aceitar' i]",
        "[aria-label*='accept' i]",
        "[aria-label*='concordo' i]",
        # Atributos comuns
        "button[id*='accept' i]",
        "button[class*='accept' i]",
        "[data-testid*='accept']",
        # Vendors específicos
        "#onetrust-accept-btn-handler",
    ],
    "accept_button_text_patterns": [
        r"^aceitar(\s+(todos|tudo))?$",
        r"^concordo$",
        r"^accept(\s+all)?$",
        r"^agree$",
        r"^ok$",
        r"^entendi$",
        r"^permitir(\s+todos)?$",
    ],
}

#: Detecção de central de privacidade (revoke flow) — configurável.
DEFAULT_PRIVACY_CENTER_CONFIG: dict[str, list[str]] = {
    "link_selectors": [
        "[aria-label*='preferenc' i]",
        "[aria-label*='configuraç' i]",
        "[aria-label*='gerenciar' i]",
        "a[href*='cookie']",
        "button[id*='preferenc' i]",
    ],
    "link_text_patterns": [
        r"(configuraç(ão|ões)?|prefer[eê]ncias?|gerenciar).*cookie",
        r"cookie.*(configuraç(ão|ões)?|prefer[eê]ncias?)",
        r"central\s*de\s*privacid",
        r"cookie\s*settings",
    ],
    "reject_button_selectors": [
        "[aria-label*='rejeitar' i]",
        "[aria-label*='reject' i]",
        "[aria-label*='recusar' i]",
        "button[id*='reject' i]",
    ],
    "reject_button_text_patterns": [
        r"^rejeitar(\s+(todos|tudo))?$",
        r"^reject\s+all$",
        r"^recusar(\s+(todos|tudo))?$",
        r"^salvar(\s+preferências?)?$",
    ],
}


# =============================================================================
# Helpers privados de módulo
# =============================================================================
def _mask_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    """Mascara o ``value`` do cookie preservando metadata + comparabilidade.

    Mantém: name, domain, path, expires, secure, httpOnly, sameSite.
    Transforma: value -> truncado primeiros 8 chars + "...".
    Adiciona: value_len (comprimento original), value_hash (SHA-256 hex[:16]).
    """
    raw = str(cookie.get("value", ""))
    return {
        **cookie,
        "value": raw[:8] + ("..." if len(raw) > 8 else ""),
        "value_len": len(raw),
        "value_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
    }


async def _ensure_full_render(
    page: Page,
    networkidle_timeout_ms: int,
    scroll_max_iter: int,
    scroll_wait_ms: int,
) -> None:
    """Força DOM completo — networkidle + scroll progressivo + networkidle final.

    Estratégia:
        1) Espera networkidle (timeout aceito sem propagar)
        2) Scroll-to-bottom progressivo, máx ``scroll_max_iter`` iterações.
           Quebra cedo quando altura do documento estabiliza.
        3) Aguarda novo networkidle (AJAX disparado pelo scroll)
        4) Volta para o topo (consistência para screenshot)
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=networkidle_timeout_ms)
    except PlaywrightTimeoutError:
        pass

    last_h = await page.evaluate("document.body.scrollHeight")
    for _ in range(scroll_max_iter):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(scroll_wait_ms)
        try:
            new_h = await page.evaluate("document.body.scrollHeight")
        except Exception:
            break
        if new_h == last_h:
            break
        last_h = new_h

    try:
        await page.wait_for_load_state("networkidle", timeout=networkidle_timeout_ms)
    except PlaywrightTimeoutError:
        pass

    try:
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(300)
    except Exception:
        pass


# =============================================================================
# PlaywrightFetcher
# =============================================================================
class PlaywrightFetcher(PageFetcher):
    """Coleta multi-fase com Chromium headless. Implementa PageFetcher (camada 2).

    Cada fetch lança Playwright + browser novos (processo separado), garantindo
    isolamento absoluto entre sites coletados.
    """

    name: ClassVar[str] = "playwright"
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        default_user_agent: str | None = None,
        headless: bool = True,
    ) -> None:
        self.default_user_agent = default_user_agent or DEFAULT_PLAYWRIGHT_USER_AGENT
        self.headless = headless

    # ------------------------------------------------------------------
    # Validação de params
    # ------------------------------------------------------------------
    def _validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve defaults + validação. Levanta ValueError em params inválidos.

        Subpáginas validadas via ``validate_subpage_config`` (compartilhado).
        Banners e privacy center validados localmente.
        """
        cfg: dict[str, Any] = {}

        cfg["user_agent"] = params.get("user_agent", self.default_user_agent)
        if not isinstance(cfg["user_agent"], str) or not cfg["user_agent"]:
            raise ValueError("user_agent deve ser string não-vazia")

        for key, default in (
            ("navigation_timeout_ms", DEFAULT_NAVIGATION_TIMEOUT_MS),
            ("networkidle_timeout_ms", DEFAULT_NETWORKIDLE_TIMEOUT_MS),
            ("consent_click_timeout_ms", DEFAULT_CONSENT_CLICK_TIMEOUT_MS),
            ("scroll_wait_ms", DEFAULT_SCROLL_WAIT_MS),
            ("revoke_interstitial_ms", DEFAULT_REVOKE_INTERSTITIAL_MS),
        ):
            cfg[key] = params.get(key, default)
            if not isinstance(cfg[key], int) or cfg[key] < 0:
                raise ValueError(f"{key} deve ser inteiro >= 0")

        cfg["scroll_max_iterations"] = params.get(
            "scroll_max_iterations", DEFAULT_SCROLL_MAX_ITERATIONS
        )
        if not isinstance(cfg["scroll_max_iterations"], int) or cfg["scroll_max_iterations"] < 0:
            raise ValueError("scroll_max_iterations deve ser inteiro >= 0")

        cfg["phase_screenshots"] = params.get("phase_screenshots", True)
        if not isinstance(cfg["phase_screenshots"], bool):
            raise ValueError("phase_screenshots deve ser bool")

        cfg["revoke_after_consent"] = params.get("revoke_after_consent", False)
        if not isinstance(cfg["revoke_after_consent"], bool):
            raise ValueError("revoke_after_consent deve ser bool")

        # Banner config — merge com defaults
        banner = params.get("consent_banner", {})
        if not isinstance(banner, dict):
            raise ValueError("consent_banner deve ser dict")
        merged_banner = {**DEFAULT_CONSENT_BANNER_CONFIG, **banner}
        self._validate_selector_pattern_dict(merged_banner, "consent_banner",
                                             ["banner_container_selectors",
                                              "accept_button_selectors",
                                              "accept_button_text_patterns"])
        cfg["consent_banner"] = merged_banner

        # Privacy center config — merge com defaults
        privacy = params.get("privacy_center", {})
        if not isinstance(privacy, dict):
            raise ValueError("privacy_center deve ser dict")
        merged_privacy = {**DEFAULT_PRIVACY_CENTER_CONFIG, **privacy}
        self._validate_selector_pattern_dict(merged_privacy, "privacy_center",
                                             ["link_selectors", "link_text_patterns",
                                              "reject_button_selectors",
                                              "reject_button_text_patterns"])
        cfg["privacy_center"] = merged_privacy

        # Network log filter
        nl_types = params.get("network_log_resource_types", DEFAULT_NETWORK_LOG_RESOURCE_TYPES)
        if nl_types is not None:
            if not isinstance(nl_types, list) or not all(isinstance(t, str) for t in nl_types):
                raise ValueError("network_log_resource_types deve ser None ou list[str]")
        cfg["network_log_resource_types"] = nl_types

        # Subpáginas — delega
        cats, mpc, mts = validate_subpage_config(params)
        cfg["subpage_categories"] = cats
        cfg["max_per_category"] = mpc
        cfg["max_total_subpages"] = mts

        return cfg

    @staticmethod
    def _validate_selector_pattern_dict(d: dict, top_name: str, required_keys: list[str]) -> None:
        """Valida que d tem as chaves esperadas, todas list[str], regexes compilam."""
        for k in required_keys:
            if k not in d:
                raise ValueError(f"{top_name}.{k} ausente")
            v = d[k]
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise ValueError(f"{top_name}.{k} deve ser list[str]")
            if k.endswith("_text_patterns"):
                for p in v:
                    try:
                        re.compile(p, re.IGNORECASE)
                    except re.error as e:
                        raise ValueError(f"regex inválido em {top_name}.{k}: {p!r}: {e}") from e

    # ------------------------------------------------------------------
    # Capturas (chamadas por fase)
    # ------------------------------------------------------------------
    async def _capture_cookies(self, context: BrowserContext) -> list[dict[str, Any]]:
        raw = await context.cookies()
        return [_mask_cookie(c) for c in raw]

    async def _capture_screenshot(self, page: Page, enabled: bool) -> bytes | None:
        if not enabled:
            return None
        try:
            return await page.screenshot(full_page=True, type="png", timeout=10_000)
        except (PlaywrightTimeoutError, Exception) as e:
            logger.debug("screenshot falhou: %s", e)
            return None

    # ------------------------------------------------------------------
    # FASES
    # ------------------------------------------------------------------
    async def _phase_pre_consent(
        self, page: Page, context: BrowserContext, domain: Domain, cfg: dict
    ) -> tuple[list[dict], bytes | None]:
        """Navega + render completo + captura cookies/screenshot ANTES de interação."""
        try:
            await page.goto(
                domain.url,
                wait_until="domcontentloaded",
                timeout=cfg["navigation_timeout_ms"],
            )
        except PlaywrightTimeoutError as e:
            raise NavigationFailedError(f"timeout em goto({domain.url}): {e}") from e
        except Exception as e:
            raise NavigationFailedError(f"falha em goto({domain.url}): {e}") from e

        await _ensure_full_render(
            page,
            cfg["networkidle_timeout_ms"],
            cfg["scroll_max_iterations"],
            cfg["scroll_wait_ms"],
        )
        cookies = await self._capture_cookies(context)
        screenshot = await self._capture_screenshot(page, cfg["phase_screenshots"])
        return cookies, screenshot

    async def _phase_attempt_accept(self, page: Page, cfg: dict) -> dict[str, Any]:
        """Tenta clicar botão de aceitar do banner. Nunca propaga exceção."""
        t0 = time.perf_counter()
        action: dict[str, Any] = {
            "phase": "accept",
            "attempted": False,
            "success": False,
            "method": None,
            "selector_used": None,
            "button_text": None,
            "snippet": None,
            "duration_ms": 0,
            "error": None,
        }
        banner_cfg = cfg["consent_banner"]
        click_timeout = cfg["consent_click_timeout_ms"]

        try:
            # 1) CSS selectors
            for sel in banner_cfg["accept_button_selectors"]:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=500):
                        action["attempted"] = True
                        try:
                            btn_text = await loc.text_content(timeout=500)
                        except Exception:
                            btn_text = None
                        try:
                            snippet = await loc.evaluate("el => el.outerHTML")
                        except Exception:
                            snippet = None
                        action["selector_used"] = sel
                        action["button_text"] = (btn_text or "")[:80]
                        action["snippet"] = (snippet or "")[:200]
                        await loc.click(timeout=click_timeout)
                        action["success"] = True
                        action["method"] = "css_selector"
                        break
                except (PlaywrightTimeoutError, Exception) as e:
                    logger.debug("accept sel %s nao casou: %s", sel, e)
                    continue

            # 2) Text patterns (fallback)
            if not action["success"]:
                for pattern in banner_cfg["accept_button_text_patterns"]:
                    try:
                        loc = page.get_by_role("button").filter(
                            has_text=re.compile(pattern, re.IGNORECASE)
                        ).first
                        if await loc.is_visible(timeout=500):
                            action["attempted"] = True
                            btn_text = await loc.text_content(timeout=500)
                            action["selector_used"] = f"role=button + text=~/{pattern}/i"
                            action["button_text"] = (btn_text or "")[:80]
                            await loc.click(timeout=click_timeout)
                            action["success"] = True
                            action["method"] = "text_pattern"
                            break
                    except (PlaywrightTimeoutError, Exception):
                        continue
        except Exception as e:
            action["error"] = f"{type(e).__name__}: {e}"
        finally:
            action["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return action

    async def _phase_post_consent(
        self, page: Page, context: BrowserContext, cfg: dict
    ) -> tuple[list[dict], bytes | None]:
        """Espera estabilização pós-accept e recaptura."""
        await _ensure_full_render(
            page,
            cfg["networkidle_timeout_ms"],
            cfg["scroll_max_iterations"],
            cfg["scroll_wait_ms"],
        )
        cookies = await self._capture_cookies(context)
        screenshot = await self._capture_screenshot(page, cfg["phase_screenshots"])
        return cookies, screenshot

    async def _phase_attempt_revoke(self, page: Page, cfg: dict) -> dict[str, Any]:
        """Pipeline em 2 cliques: abrir central de privacidade + rejeitar."""
        t0 = time.perf_counter()
        action: dict[str, Any] = {
            "phase": "revoke",
            "attempted": False,
            "success": False,
            "center_opened": False,
            "reject_clicked": False,
            "method_center": None,
            "method_reject": None,
            "selector_used_center": None,
            "selector_used_reject": None,
            "duration_ms": 0,
            "error": None,
        }
        pc = cfg["privacy_center"]
        click_timeout = cfg["consent_click_timeout_ms"]

        try:
            # (a) Abrir central
            for sel in pc["link_selectors"]:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=500):
                        action["attempted"] = True
                        action["selector_used_center"] = sel
                        action["method_center"] = "css_selector"
                        await loc.click(timeout=click_timeout)
                        action["center_opened"] = True
                        break
                except (PlaywrightTimeoutError, Exception):
                    continue
            if not action["center_opened"]:
                for pattern in pc["link_text_patterns"]:
                    try:
                        loc = page.get_by_text(
                            re.compile(pattern, re.IGNORECASE)
                        ).first
                        if await loc.is_visible(timeout=500):
                            action["attempted"] = True
                            action["selector_used_center"] = f"text=~/{pattern}/i"
                            action["method_center"] = "text_pattern"
                            await loc.click(timeout=click_timeout)
                            action["center_opened"] = True
                            break
                    except (PlaywrightTimeoutError, Exception):
                        continue

            if not action["center_opened"]:
                return action  # sem central, sem revoke possível

            # Espera modal/página da central renderizar
            await page.wait_for_timeout(cfg["revoke_interstitial_ms"])

            # (b) Clicar rejeitar
            for sel in pc["reject_button_selectors"]:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=500):
                        action["selector_used_reject"] = sel
                        action["method_reject"] = "css_selector"
                        await loc.click(timeout=click_timeout)
                        action["reject_clicked"] = True
                        break
                except (PlaywrightTimeoutError, Exception):
                    continue
            if not action["reject_clicked"]:
                for pattern in pc["reject_button_text_patterns"]:
                    try:
                        loc = page.get_by_role("button").filter(
                            has_text=re.compile(pattern, re.IGNORECASE)
                        ).first
                        if await loc.is_visible(timeout=500):
                            action["selector_used_reject"] = f"role=button + text=~/{pattern}/i"
                            action["method_reject"] = "text_pattern"
                            await loc.click(timeout=click_timeout)
                            action["reject_clicked"] = True
                            break
                    except (PlaywrightTimeoutError, Exception):
                        continue

            action["success"] = action["center_opened"] and action["reject_clicked"]
        except Exception as e:
            action["error"] = f"{type(e).__name__}: {e}"
        finally:
            action["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return action

    async def _phase_post_revoke(
        self, page: Page, context: BrowserContext, cfg: dict
    ) -> tuple[list[dict], bytes | None]:
        """Recaptura após revoke (mesma lógica de post_consent)."""
        return await self._phase_post_consent(page, context, cfg)

    # ------------------------------------------------------------------
    # Extração de subpáginas + coleta no mesmo context
    # ------------------------------------------------------------------
    async def _extract_subpages_from_page(
        self, page: Page, base_url: str, cfg: dict
    ) -> dict[str, list[dict[str, Any]]]:
        """page.content() -> HTML pós-render -> extractor compartilhado."""
        html = await page.content()
        return extract_subpage_candidates(
            html.encode("utf-8"),
            base_url=base_url,
            categories=cfg["subpage_categories"],
            max_per_category=cfg["max_per_category"],
            max_total=cfg["max_total_subpages"],
        )

    async def _fetch_subpages_in_context(
        self,
        page: Page,
        subpage_selection: dict[str, list[dict]],
        cfg: dict,
    ) -> tuple[dict[str, bytes], dict[str, dict[str, str]], list[dict], list[str]]:
        """Navega cada subpágina no MESMO context (mantém cookies pós-consent)."""
        html_pages: dict[str, bytes] = {}
        headers_by_url: dict[str, dict[str, str]] = {}
        network_entries: list[dict] = []
        errors: list[str] = []

        for cat, items in subpage_selection.items():
            for item in items:
                sub_url = item["url"]
                t0 = time.perf_counter()
                try:
                    response = await page.goto(
                        sub_url,
                        wait_until="domcontentloaded",
                        timeout=cfg["navigation_timeout_ms"],
                    )
                    await _ensure_full_render(
                        page,
                        cfg["networkidle_timeout_ms"],
                        cfg["scroll_max_iterations"],
                        cfg["scroll_wait_ms"],
                    )
                    html = await page.content()
                    path = urlparse(sub_url).path or f"/__sub_{cat}"
                    if path == "/":
                        path = f"/__sub_{cat}"
                    html_pages[path] = html.encode("utf-8")
                    if response is not None:
                        headers_by_url[sub_url] = dict(response.headers)
                        network_entries.append({
                            "url": sub_url,
                            "method": "GET",
                            "status": response.status,
                            "size_bytes": len(html_pages[path]),
                            "duration_ms": int((time.perf_counter() - t0) * 1000),
                            "content_type": response.headers.get("content-type", ""),
                            "category": cat,
                        })
                except (PlaywrightTimeoutError, Exception) as e:
                    errors.append(
                        f"subpagina {sub_url}: {type(e).__name__}: {e}"
                    )
        return html_pages, headers_by_url, network_entries, errors

    # ------------------------------------------------------------------
    # ORQUESTRAÇÃO PRINCIPAL — fetch()
    # ------------------------------------------------------------------
    async def fetch(self, domain: Domain, params: dict[str, Any]) -> RawEvidence:
        """Cada call: Playwright + browser + context novos. Isolamento absoluto."""
        cfg = self._validate_params(params)

        errors: list[str] = []
        network_log: list[dict] = []
        headers_by_url: dict[str, dict[str, str]] = {}
        html_pages: dict[str, bytes] = {}
        consent_actions: list[dict] = []
        phase_screenshots: dict[str, bytes] = {}
        cookies_pre: list[dict] = []
        cookies_post: list[dict] = []
        cookies_post_revoke: list[dict] = []
        subpage_selection: dict[str, list[dict]] = {}

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            try:
                context = await browser.new_context(
                    locale=DEFAULT_LOCALE,
                    viewport=DEFAULT_VIEWPORT,
                    user_agent=cfg["user_agent"],
                    ignore_https_errors=False,
                )

                # Network log via listeners — captura TODAS as requisições.
                # Filtro opcional por resource_type controlado em cfg.
                pending: dict[str, float] = {}
                rtypes_filter = cfg["network_log_resource_types"]

                def on_request(req):
                    pending[req.url] = time.perf_counter()

                def on_response(resp):
                    try:
                        if rtypes_filter is not None and resp.request.resource_type not in rtypes_filter:
                            return
                        start = pending.pop(resp.url, None)
                        duration_ms = (
                            int((time.perf_counter() - start) * 1000) if start else None
                        )
                        network_log.append({
                            "url": resp.url,
                            "method": resp.request.method,
                            "status": resp.status,
                            "resource_type": resp.request.resource_type,
                            "duration_ms": duration_ms,
                            "content_type": resp.headers.get("content-type", ""),
                        })
                    except Exception as e:
                        logger.debug("network listener error: %s", e)

                context.on("request", on_request)
                context.on("response", on_response)

                page = await context.new_page()

                # === FASE 1 — Pre-consent ===
                cookies_pre, scr_pre = await self._phase_pre_consent(
                    page, context, domain, cfg
                )
                if scr_pre:
                    phase_screenshots["pre_consent"] = scr_pre

                # === FASE 2 — Tentar accept ===
                accept_action = await self._phase_attempt_accept(page, cfg)
                consent_actions.append(accept_action)

                # === FASE 3 — Post-consent ===
                cookies_post, scr_post = await self._phase_post_consent(
                    page, context, cfg
                )
                if scr_post:
                    phase_screenshots["post_consent"] = scr_post

                # === HTML da raiz (pós-consent — DOM mais maduro) ===
                root_html = await page.content()
                html_pages["/"] = root_html.encode("utf-8")

                # === Extração de subpáginas pós-consent ===
                subpage_selection = await self._extract_subpages_from_page(
                    page, domain.url, cfg
                )

                # === Coleta das subpáginas no mesmo context ===
                sub_html, sub_headers, sub_net, sub_errors = (
                    await self._fetch_subpages_in_context(
                        page, subpage_selection, cfg
                    )
                )
                html_pages.update(sub_html)
                headers_by_url.update(sub_headers)
                # network_log de subpáginas vai junto via listener acima

                errors.extend(sub_errors)

                # === FASE 4-5 — Revoke (opt-in) ===
                if cfg["revoke_after_consent"]:
                    # Voltar para a raiz para reabrir central de privacidade
                    try:
                        await page.goto(
                            domain.url,
                            wait_until="domcontentloaded",
                            timeout=cfg["navigation_timeout_ms"],
                        )
                        await _ensure_full_render(
                            page,
                            cfg["networkidle_timeout_ms"],
                            cfg["scroll_max_iterations"],
                            cfg["scroll_wait_ms"],
                        )
                    except Exception as e:
                        errors.append(f"revoke pre-nav: {type(e).__name__}: {e}")

                    revoke_action = await self._phase_attempt_revoke(page, cfg)
                    consent_actions.append(revoke_action)
                    cookies_post_revoke, scr_revoke = await self._phase_post_revoke(
                        page, context, cfg
                    )
                    if scr_revoke:
                        phase_screenshots["post_revocation"] = scr_revoke

                await context.close()
            finally:
                await browser.close()

        # Screenshot "principal" = último estado capturado.
        main_screenshot = phase_screenshots.get(
            "post_revocation", phase_screenshots.get("post_consent")
        )

        return RawEvidence(
            domain=domain,
            html_pages=html_pages,
            cookies=cookies_post if cookies_post else cookies_pre,
            cookies_pre_consent=cookies_pre,
            cookies_post_consent=cookies_post,
            cookies_post_revocation=cookies_post_revoke,
            consent_actions=consent_actions,
            headers=headers_by_url,
            screenshot=main_screenshot,
            phase_screenshots=phase_screenshots,
            network_log=network_log,
            subpage_selection=subpage_selection,
            fetcher_name=self.name,
            timestamp_utc=utc_now(),
            errors=errors,
        )


__all__ = [
    "PlaywrightFetcher",
    "DEFAULT_PLAYWRIGHT_USER_AGENT",
    "DEFAULT_CONSENT_BANNER_CONFIG",
    "DEFAULT_PRIVACY_CENTER_CONFIG",
]
