"""
VariableTest: tem_politica_privacidade.

Estrategia em duas camadas (decisao D7), refinada apos a piloto B4.

    1. Confia no fetcher para extracao de candidatos:
       ``evidence.subpage_selection["politica_privacidade"]`` (uniao pre+pos
       consentimento).
    2. Qualifica com discriminadores (refinamento B4):
         - Conteudo FORTE: subpagina baixada (>= min_size bytes) com >=
           min_keywords keywords distintas -> high. Qualifica sempre.
         - PDF: link de politica em PDF (.pdf) com path/titulo de politica ->
           medium.
         - Conteudo FRACO (1..min_keywords-1): conta so se o path/titulo do link
           for de politica (nao termo isolado).
         - Nao baixado e nao-PDF: NAO conta.
    3. Sem fallback por regex no HTML raiz (removido no refinamento B4).

Refinamento B4 (n=49): precisao 0,875 -> 0,966; recall 0,966; kappa 0,776 ->
0,913. (n=49: revalidar em held-out B8.)

v0.2.0 -> v0.2.1: CONFIG EXTERNA dos parametros de DADO (decisao B4 —
    externalizar dado, manter logica/regex no codigo). Vem de ``params``
    (carregados pelo orquestrador de config/rules/politica_privacidade.yaml):
    min_policy_size_bytes, min_keywords_for_high, policy_plausibility_keywords.
    O vocabulario de PATH (_POLICY_PATH_RX) e os padroes fracos sao REGEX e
    permanecem no codigo. Fallback para os *_DEFAULT se faltar (params vazio ==
    v0.2.0).

Fundamentacao:
    - Javed; Sajid (2024); Vorster; Da Veiga (2023).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar
from urllib.parse import urlparse

from privacyscope.core.interfaces import VariableTest
from privacyscope.core.types import RawEvidence, VariableResult, utc_now
from privacyscope.tests._helpers import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    confidence_to_float,
    safe_decode,
)
from privacyscope.tests._lexicon import POLICY_PLAUSIBILITY_KEYWORDS


# ---- DEFAULTS (fallback) — fonte editavel: config/rules/politica_privacidade.yaml ----
MIN_POLICY_SIZE_BYTES = 500
MIN_KEYWORDS_FOR_HIGH = 3

# LOGICA/REGEX (permanece no codigo):
_POLICY_PATH_RX = re.compile(
    r"(privacid|privacy|gdpr|lgpd|prote\w*[-_]?(?:de[-_]?)?dados|"
    r"dados[-_]?pessoais|polit\w*[-_]?de[-_]?dados)",
    re.IGNORECASE,
)
_WEAK_LINK_PATTERNS = frozenset({r"\bprivacidade\b", r"\bprivacy\b", r"\blgpd\b"})


def _is_pdf(url: str) -> bool:
    return url.lower().split("?")[0].split("#")[0].endswith(".pdf")


def _policy_like(url: str, matched_pattern: str | None) -> bool:
    path = urlparse(url).path or "/"
    if _POLICY_PATH_RX.search(path):
        return True
    if matched_pattern and matched_pattern not in _WEAK_LINK_PATTERNS:
        return True
    return False


class PoliticaPrivacidadeTest(VariableTest):
    """Detecta presenca de politica/aviso/termo de privacidade."""

    name: ClassVar[str] = "politica_privacidade"
    version: ClassVar[str] = "0.2.1"
    variable_name: ClassVar[str] = "tem_politica_privacidade"

    def evaluate(
        self,
        evidence: RawEvidence,
        params: dict[str, Any],
        *,
        protocol_version: str,
        run_id: str,
    ) -> VariableResult:
        params = params or {}
        try:
            min_size = int(params.get("min_policy_size_bytes", MIN_POLICY_SIZE_BYTES))
            if min_size < 1:
                min_size = MIN_POLICY_SIZE_BYTES
        except (TypeError, ValueError):
            min_size = MIN_POLICY_SIZE_BYTES
        try:
            kw_high = int(params.get("min_keywords_for_high", MIN_KEYWORDS_FOR_HIGH))
            if kw_high < 1:
                kw_high = MIN_KEYWORDS_FOR_HIGH
        except (TypeError, ValueError):
            kw_high = MIN_KEYWORDS_FOR_HIGH
        kw_list = params.get("policy_plausibility_keywords") or POLICY_PLAUSIBILITY_KEYWORDS
        keywords = [str(k).strip().lower() for k in kw_list if str(k).strip()]

        candidates = evidence.subpage_selection.get("politica_privacidade", [])

        value: bool = False
        confidence_label: str = CONFIDENCE_UNKNOWN
        source: str = "none"
        matched_url: str | None = None
        matched_pattern: str | None = None
        matched_against: str | None = None
        subpage_size: int | None = None
        keyword_hits: list[str] = []
        best_priority = 0

        for cand in candidates:
            url = cand.get("url", "")
            if not url:
                continue
            patt = cand.get("matched_pattern")
            policy_like = _policy_like(url, patt)

            if _is_pdf(url):
                if policy_like and best_priority < 2:
                    value = True
                    confidence_label = CONFIDENCE_MEDIUM
                    source = "subpage_selection+pdf_policy_link"
                    matched_url = url
                    matched_pattern = patt
                    matched_against = cand.get("matched_against")
                    subpage_size = None
                    keyword_hits = []
                    best_priority = 2
                continue

            body = self._find_body_for_url(evidence.html_pages, url)
            if body and len(body) >= min_size:
                text_lower = safe_decode(body).lower()
                hits = [kw for kw in keywords if kw in text_lower]
                if len(hits) >= kw_high:
                    value = True
                    confidence_label = CONFIDENCE_HIGH
                    source = "subpage_selection+content_qualified"
                    matched_url = url
                    matched_pattern = patt
                    matched_against = cand.get("matched_against")
                    subpage_size = len(body)
                    keyword_hits = hits[:10]
                    best_priority = 3
                    break
                elif hits:
                    if policy_like and best_priority < 1:
                        value = True
                        confidence_label = CONFIDENCE_MEDIUM
                        source = "subpage_selection+content_light_policy_link"
                        matched_url = url
                        matched_pattern = patt
                        matched_against = cand.get("matched_against")
                        subpage_size = len(body)
                        keyword_hits = hits
                        best_priority = 1
            # body ausente e nao-PDF: NAO conta.

        if not value:
            root = safe_decode(evidence.html_pages.get("/", b""))
            if root:
                confidence_label = CONFIDENCE_HIGH
                source = "no_match_any_source"
            else:
                confidence_label = CONFIDENCE_UNKNOWN
                source = "html_root_vazio"

        audit_trail: dict[str, Any] = {
            "source": source,
            "confidence_label": confidence_label,
            "matched_url": matched_url,
            "matched_pattern": matched_pattern,
            "matched_against": matched_against,
            "subpage_size_bytes": subpage_size,
            "subpage_keyword_hits": keyword_hits,
            "subpage_keyword_count": len(keyword_hits),
            "candidates_count": len(candidates),
            "min_policy_size_bytes": min_size,
            "min_keywords_for_high": kw_high,
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

    @staticmethod
    def _find_body_for_url(html_pages: dict[str, bytes], url: str) -> bytes | None:
        if url in html_pages:
            return html_pages[url]
        path = urlparse(url).path or "/"
        if path in html_pages:
            return html_pages[path]
        for key, body in html_pages.items():
            if key.endswith(path) or path.endswith(key):
                return body
        return None


__all__ = ["PoliticaPrivacidadeTest", "MIN_POLICY_SIZE_BYTES", "MIN_KEYWORDS_FOR_HIGH"]
