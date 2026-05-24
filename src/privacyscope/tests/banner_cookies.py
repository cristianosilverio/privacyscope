"""
VariableTest: tem_banner_cookies.

Detecta presenca de banner informativo sobre uso de cookies na pagina
inicial. Estrategia hibrida (decisao D1), refinada em duas etapas apos a
piloto B4 com base na rotulagem manual cega dos 49 sites.

Hierarquia de decisao (do mais forte ao mais fraco):

    1. Vendor signature em ELEMENTO VISIVEL (OneTrust, Cookiebot, Cookieyes,
       Complianz etc.) - sinal mais forte.
    2. Acao de consentimento efetiva do Playwright (clique de aceite) - sinal
       empiricamente sem falsos positivos na piloto.
    3. Container NOMEADO VISIVEL (id/class com cookie|consent|lgpd|privacid|
       privacy|gdpr) cujo subtree contem termo do lexico de cookies.
    4. Vendor detectado apenas por dominio de loader (termly.io, truste.com) -
       fallback fraco (script presente, renderizacao nao confirmada).

Refinamento pos-piloto B4:
    v0.1.0 -> v0.2.0: o gatilho deixou de aceitar lexico solto e estrutura
        generica (role="dialog"); passou a exigir container nomeado + lexico.
        Precisao 0,564 -> 0,833; kappa 0,327 -> 0,750.
    v0.2.0 -> v0.3.0: FILTRO DE VISIBILIDADE via DOM (BeautifulSoup): ignora
        elementos nao-visuais (script/style/...) e elementos ocultos (no
        proprio no ou em ancestral). Piloto B4: precisao 1,000; recall 0,909;
        F1 0,952; kappa 0,915 (zero FP, sem novos FN; n=49 -> revalidar).
    v0.3.0 -> v0.3.1: CONFIG EXTERNA dos parametros de DADO (decisao B4:
        externalizar dado, manter logica/regex no codigo). Vem de ``params``
        (carregados pelo orquestrador de config/rules/banner_cookies.yaml):
        max_ancestor_depth, nonvisual_tags, vendor_text_only e container_vocab
        (palavras do container). Lexico, assinaturas de vendor e classes-ocultas
        sao REGEX e permanecem no codigo. Se um parametro faltar, usa o
        respectivo *_DEFAULT (fallback a prova de falha; params vazio == v0.3.0).

Fundamentacao academica:
    - Dabrowski et al. (2019); Rasaii et al. (2023); ANPD Guia de Cookies (2023).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from bs4 import BeautifulSoup

from privacyscope.core.interfaces import VariableTest
from privacyscope.core.types import RawEvidence, VariableResult, utc_now
from privacyscope.tests._helpers import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    confidence_to_float,
    safe_decode,
)
from privacyscope.tests._lexicon import (
    COOKIE_LEXICON_PT_EN,
    COOKIE_STRUCTURAL_HINTS,
)
from privacyscope.tests._vendor_signatures import VENDOR_SIGNATURES


# ---- DEFAULTS (fallback) — fonte editavel: config/rules/banner_cookies.yaml ----
# DADO (externalizavel):
NONVISUAL_TAGS = frozenset(
    {"script", "style", "link", "meta", "noscript", "template", "head", "title", "base"}
)
_VENDOR_TEXT_ONLY = ("termly.io", "truste.com")
_MAX_ANCESTOR_DEPTH = 6
_CONTAINER_VOCAB = ("cookie", "consent", "lgpd", "privacid", "privacidade", "privacy", "gdpr")

# LOGICA/REGEX (permanece no codigo):
_CONTAINER_VOCAB_RX = re.compile("(?:" + "|".join(_CONTAINER_VOCAB) + ")", re.IGNORECASE)
_HIDE_CLASS_RX = re.compile(
    r"(?:^|\s)(?:cc-invisible|[a-z0-9_]+-invisible|invisible|hidden|is-hidden|"
    r"d-none|sr-only|visually-hidden)(?:\s|$)",
    re.IGNORECASE,
)
_VENDOR_COMPILED: list[tuple[str, "re.Pattern"]] = [
    (vendor, re.compile(p, re.IGNORECASE))
    for vendor, patterns in VENDOR_SIGNATURES.items()
    for p in patterns
]
_LEXICON_COMPILED: list["re.Pattern"] = [
    re.compile(p, re.IGNORECASE) for p in COOKIE_LEXICON_PT_EN
]


def _build_container_rx(vocab) -> "re.Pattern":
    words = [str(w).strip() for w in vocab if str(w).strip()]
    if not words:
        return _CONTAINER_VOCAB_RX
    return re.compile("(?:" + "|".join(words) + ")", re.IGNORECASE)


def _element_hidden(el, max_depth: int = _MAX_ANCESTOR_DEPTH) -> bool:
    """True se o elemento (ou um ancestral ate max_depth) esta oculto.

    Cobre ocultacao declarada no HTML capturado: style inline (display:none /
    visibility:hidden / opacity:0), atributo ``hidden``, ``aria-hidden="true"``
    e classes de ocultacao. Limitacao: nao resolve ocultacao via CSS de folha
    externa (sem marca no proprio HTML).
    """
    node = el
    depth = 0
    while node is not None and getattr(node, "name", None) and depth < max_depth:
        style = str(node.get("style") or "").lower().replace(" ", "")
        if "display:none" in style or "visibility:hidden" in style or "opacity:0" in style:
            return True
        if node.has_attr("hidden"):
            return True
        if str(node.get("aria-hidden", "")).lower() == "true":
            return True
        classes = node.get("class") or []
        if classes and _HIDE_CLASS_RX.search(" ".join(classes)):
            return True
        node = node.parent
        depth += 1
    return False


def _attr_string(el) -> str:
    """Reconstroi ``id="..." class="..."`` para casar assinaturas de vendor."""
    parts = []
    el_id = el.get("id")
    if el_id:
        parts.append('id="' + str(el_id) + '"')
    el_cls = el.get("class")
    if el_cls:
        parts.append('class="' + " ".join(el_cls) + '"')
    return " ".join(parts)


def _match_vendor_element(attr: str):
    """Devolve o nome do vendor cuja assinatura casa o atributo, ou None."""
    if not attr:
        return None
    for vendor, rx in _VENDOR_COMPILED:
        if rx.search(attr):
            return vendor
    return None


class BannerCookiesTest(VariableTest):
    """Detecta presenca de banner de cookies na raiz."""

    name: ClassVar[str] = "banner_cookies"
    version: ClassVar[str] = "0.3.1"
    variable_name: ClassVar[str] = "tem_banner_cookies"

    def evaluate(
        self,
        evidence: RawEvidence,
        params: dict[str, Any],
        *,
        protocol_version: str,
        run_id: str,
    ) -> VariableResult:
        """Aplica deteccao em camadas (com filtro de visibilidade) e devolve VariableResult."""
        params = params or {}
        # ---- parametros de DADO (params -> fallback default) ----
        try:
            max_depth = int(params.get("max_ancestor_depth", _MAX_ANCESTOR_DEPTH))
            if max_depth < 1:
                max_depth = _MAX_ANCESTOR_DEPTH
        except (TypeError, ValueError):
            max_depth = _MAX_ANCESTOR_DEPTH
        nonvisual = frozenset(params.get("nonvisual_tags") or NONVISUAL_TAGS)
        vendor_text_only = tuple(params.get("vendor_text_only") or _VENDOR_TEXT_ONLY)
        container_rx = _build_container_rx(params.get("container_vocab") or _CONTAINER_VOCAB)

        root_bytes = evidence.html_pages.get("/", b"")
        text = safe_decode(root_bytes)

        # Sinais textuais apenas para AUDITORIA (nao decidem).
        lexicon_hits: list[str] = [
            p for p in COOKIE_LEXICON_PT_EN if re.search(p, text, re.IGNORECASE)
        ]
        structural_hits: list[str] = [
            p for p in COOKIE_STRUCTURAL_HINTS if re.search(p, text, re.IGNORECASE)
        ]

        consent_success_observed = any(
            a.get("phase") in ("accept", "consent") and a.get("success", False)
            for a in evidence.consent_actions
        )

        # --- Varredura do DOM com filtro de visibilidade ---
        vendor_hits: list[dict] = []
        vendor_visible = False
        container_visible = False
        matched_snippet = None
        visible_candidates = 0
        hidden_candidates = 0
        parse_error = False

        if text:
            try:
                soup = BeautifulSoup(text, "lxml")
            except Exception:  # pragma: no cover - fallback defensivo
                soup = None
                parse_error = True

            if soup is not None:
                for el in soup.find_all(True):
                    if el.name in nonvisual:
                        continue
                    ic = (str(el.get("id") or "") + " " + " ".join(el.get("class") or [])).strip()
                    if not ic:
                        continue
                    is_container = bool(container_rx.search(ic))
                    vendor_name = _match_vendor_element(_attr_string(el))
                    if not (is_container or vendor_name):
                        continue
                    if _element_hidden(el, max_depth):
                        hidden_candidates += 1
                        continue
                    visible_candidates += 1
                    if vendor_name and not vendor_visible:
                        vendor_visible = True
                        vendor_hits.append({"vendor": vendor_name, "visible": True})
                        if matched_snippet is None:
                            matched_snippet = re.sub(r"\s+", " ", ic)[:120]
                    if is_container and not container_visible:
                        sub = str(el)
                        if any(rx.search(sub) for rx in _LEXICON_COMPILED):
                            container_visible = True
                            if matched_snippet is None:
                                matched_snippet = re.sub(r"\s+", " ", ic)[:120]

        vendor_text_loader = bool(text) and any(d in text.lower() for d in vendor_text_only)

        # ---- Decisao e confianca ----
        value: bool = False
        confidence_label: str = CONFIDENCE_UNKNOWN
        matched_via: str = "none"

        if not text:
            value = False
            confidence_label = CONFIDENCE_UNKNOWN
            matched_via = "html_vazio"
        elif vendor_visible:
            value = True
            confidence_label = CONFIDENCE_HIGH
            matched_via = "vendor"
        elif consent_success_observed:
            value = True
            confidence_label = CONFIDENCE_HIGH
            matched_via = "consent_actions"
        elif container_visible:
            value = True
            confidence_label = CONFIDENCE_MEDIUM
            matched_via = "container+lexicon"
        elif vendor_text_loader:
            value = True
            confidence_label = CONFIDENCE_LOW
            matched_via = "vendor_loader"
        else:
            value = False
            confidence_label = CONFIDENCE_HIGH
            matched_via = "none"

        audit_trail: dict[str, Any] = {
            "matched_via": matched_via,
            "confidence_label": confidence_label,
            "vendor_hits": vendor_hits,
            "vendor_text_loader": vendor_text_loader,
            "container_visible": container_visible,
            "matched_snippet": matched_snippet,
            "visible_candidates": visible_candidates,
            "hidden_candidates": hidden_candidates,
            "parse_error": parse_error,
            "max_ancestor_depth": max_depth,
            "structural_hits": structural_hits,
            "lexicon_hits": lexicon_hits[:10],
            "lexicon_hit_count": len(lexicon_hits),
            "consent_success_observed": consent_success_observed,
            "consent_actions_count": len(evidence.consent_actions),
            "html_root_bytes": len(root_bytes),
            "fetcher_used": evidence.fetcher_name,
        }

        return VariableResult(
            domain_url=evidence.domain.url,
            variable_name=self.variable_name,
            value=value,
            confidence=confidence_to_float(confidence_label),
            audit_trail=audit_trail,
            protocol_version=protocol_version,
            plugin_version=self.version,
            run_id=run_id,
            timestamp_utc=utc_now(),
        )


__all__ = ["BannerCookiesTest", "NONVISUAL_TAGS"]
