"""
Assinaturas dos principais Consent Management Platforms (CMPs).

Cada CMP comercial usa IDs, classes e estruturas DOM identificáveis. Detectar
uma dessas assinaturas é evidência forte de banner de cookies — concede
``confidence_level: high`` ao ``banner_cookies`` VariableTest, mesmo sem
match léxico explícito (alguns CMPs renderizam texto via i18n após carga).

Manter este arquivo separado de ``_lexicon.py`` permite:

    - Atualizar vendors sem mexer no vocabulário geral.
    - Banca verificar quais CMPs o framework reconhece nominalmente.

Vendors selecionados por presença documentada no mercado brasileiro
(Pantelic et al., 2022; Rasaii et al., 2023; observação direta em sites
``.gov.br`` e ``.com.br``).
"""

from __future__ import annotations


VENDOR_SIGNATURES: dict[str, list[str]] = {
    "OneTrust": [
        r'id\s*=\s*["\']onetrust-banner-sdk["\']',
        r'id\s*=\s*["\']onetrust-consent-sdk["\']',
        r'class\s*=\s*["\'][^"\']*optanon-alert-box-wrapper[^"\']*["\']',
        r'data-domain-script',
    ],
    "Cookiebot": [
        r'id\s*=\s*["\']CybotCookiebotDialog["\']',
        r'CybotCookiebotDialog',
        r'data-cbid',
    ],
    "QuantcastChoice": [
        r'class\s*=\s*["\'][^"\']*qc-cmp2-container[^"\']*["\']',
        r'id\s*=\s*["\']qc-cmp2-ui["\']',
        r'__tcfapi',
    ],
    "CookieConsent": [
        # Biblioteca open-source bastante usada (cookieconsent.insites.com).
        r'id\s*=\s*["\']cookieconsent["\']',
        r'class\s*=\s*["\'][^"\']*cc-window[^"\']*["\']',
        r'class\s*=\s*["\'][^"\']*cc-banner[^"\']*["\']',
    ],
    "Termly": [
        r'termly\.io',
        r'id\s*=\s*["\']termly-code-snippet-support["\']',
    ],
    "TrustArc": [
        r'id\s*=\s*["\']truste-consent-track["\']',
        r'truste\.com',
    ],
    "Klaro": [
        # Library OSS popular em sites .gov europeus e brasileiros.
        r'id\s*=\s*["\']klaro["\']',
        r'class\s*=\s*["\'][^"\']*klaro[^"\']*["\']',
    ],
    "Osano": [
        r'osano-cm-window',
        r'class\s*=\s*["\'][^"\']*osano[^"\']*["\']',
    ],
}


__all__ = ["VENDOR_SIGNATURES"]
