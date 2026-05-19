"""
VariableTest: tem_banner_cookies.

Detecta presença de banner informativo sobre uso de cookies na página
inicial. Estratégia híbrida (decisão D1):

    1. Vendor signatures (OneTrust, Cookiebot etc.) — sinal mais forte.
    2. Sinais estruturais (role="dialog", aria-modal, id/class com "cookie").
    3. Léxico PT-BR/EN ("cookie", "aceitar", "rastreamento").
    4. Reforço por consent_actions do Playwright (se disponível).

Fundamentação acadêmica:
    - Dabrowski et al. (2019): metodologia de detecção em larga escala.
    - Rasaii et al. (2023): análise multi-perspectiva de cookies.
    - ANPD Guia de Cookies (2023): caracterização de "comunicação prévia".
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

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


class BannerCookiesTest(VariableTest):
    """Detecta presença de banner de cookies na raiz."""

    name: ClassVar[str] = "banner_cookies"
    version: ClassVar[str] = "0.1.0"
    variable_name: ClassVar[str] = "tem_banner_cookies"

    def evaluate(
        self,
        evidence: RawEvidence,
        params: dict[str, Any],
        *,
        protocol_version: str,
        run_id: str,
    ) -> VariableResult:
        """Aplica detecção em camadas e devolve VariableResult."""
        del params  # MVP: sem params; futuras versões podem expor thresholds

        # 1) Texto da raiz — fonte primária
        root_bytes = evidence.html_pages.get("/", b"")
        text = safe_decode(root_bytes)

        # 2) Vendor signatures — alta confiança quando casa
        vendor_hits: list[dict] = []
        for vendor, patterns in VENDOR_SIGNATURES.items():
            for p in patterns:
                m = re.search(p, text, re.IGNORECASE)
                if m:
                    vendor_hits.append({"vendor": vendor, "matched_pattern": p})
                    break  # 1 hit por vendor é suficiente

        # 3) Sinais estruturais (role=dialog etc.)
        structural_hits: list[str] = []
        for p in COOKIE_STRUCTURAL_HINTS:
            if re.search(p, text, re.IGNORECASE):
                structural_hits.append(p)

        # 4) Léxico de cookies
        lexicon_hits: list[str] = []
        for p in COOKIE_LEXICON_PT_EN:
            if re.search(p, text, re.IGNORECASE):
                lexicon_hits.append(p)

        # 5) Sinal de reforço: consent_actions do Playwright
        # Considera "reforço" quando há ação efetiva de aceitar com success.
        consent_success_observed = any(
            a.get("phase") in ("accept", "consent")
            and a.get("success", False)
            for a in evidence.consent_actions
        )

        # ---- Decisão e confiança --------------------------------------
        # Hierarquia (do mais forte ao mais fraco):
        value: bool = False
        confidence_label: str = CONFIDENCE_UNKNOWN
        matched_via: str = "none"

        if not text:
            confidence_label = CONFIDENCE_UNKNOWN
            value = False
            matched_via = "html_vazio"
        elif vendor_hits:
            value = True
            matched_via = "vendor"
            confidence_label = (
                CONFIDENCE_HIGH if consent_success_observed or lexicon_hits
                else CONFIDENCE_HIGH  # vendor sozinho já é forte
            )
        elif structural_hits and lexicon_hits:
            value = True
            matched_via = "structural+lexicon"
            confidence_label = (
                CONFIDENCE_HIGH if consent_success_observed
                else CONFIDENCE_MEDIUM
            )
        elif structural_hits or lexicon_hits:
            value = True
            matched_via = "structural" if structural_hits else "lexicon"
            confidence_label = (
                CONFIDENCE_MEDIUM if consent_success_observed
                else CONFIDENCE_LOW
            )
        else:
            # Sem sinal — porém se consent_actions disparou, pode haver banner
            # invisível ao texto bruto (renderizado por JS após networkidle).
            if consent_success_observed:
                value = True
                matched_via = "consent_actions_only"
                confidence_label = CONFIDENCE_LOW
            else:
                value = False
                matched_via = "none"
                confidence_label = CONFIDENCE_HIGH  # alta confiança em "não tem"

        audit_trail: dict[str, Any] = {
            "matched_via": matched_via,
            "confidence_label": confidence_label,
            "vendor_hits": vendor_hits,
            "structural_hits": structural_hits,
            "lexicon_hits": lexicon_hits[:10],  # limita verbosidade
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


__all__ = ["BannerCookiesTest"]
