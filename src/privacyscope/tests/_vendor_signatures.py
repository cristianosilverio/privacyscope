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
        # 'data-domain-script' removido (refinamento B4): atributo do LOADER,
        # dispara mesmo sem o banner renderizar. Mantidos só sinais de container.
    ],
    "Cookiebot": [
        r'id\s*=\s*["\']CybotCookiebotDialog["\']',
        r'CybotCookiebotDialog',
        # 'data-cbid' removido (refinamento B4): atributo do LOADER do script.
    ],
    "QuantcastChoice": [
        r'class\s*=\s*["\'][^"\']*qc-cmp2-container[^"\']*["\']',
        r'id\s*=\s*["\']qc-cmp2-ui["\']',
        # '__tcfapi' removido (refinamento B4): nome de função da API IAB TCF,
        # presente em QUALQUER CMP do framework e mesmo sem banner exibido
        # (causou FP em riovagas.com.br na piloto).
    ],
    "CookieConsent": [
        # Biblioteca open-source bastante usada (cookieconsent.insites.com).
        r'id\s*=\s*["\']cookieconsent["\']',
        # 'cc-window' removido (refinamento B4): classe genérica que persiste no
        # DOM sem o banner renderizar (causou FP em gummy.com.br). Mantido
        # 'cc-banner', mais específico do container.
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
    "Cookieyes": [
        # CMP muito comum em WordPress BR. Assinatura restrita ao CONTAINER do
        # banner (cky-notice/cky-banner/cky-consent-container/overlay/modal),
        # evitando casar CSS/JS residual (cky-css, cky-js, cky-close__*) que
        # permanece no HTML sem banner exibido — testado contra a piloto B4,
        # onde a forma ampla 'cky-' gerava FP em riovagas/dedicacaodelta/poletto.
        r'class\s*=\s*["\'][^"\']*cky-(?:notice|banner|consent-container|overlay|modal)[^"\']*["\']',
    ],
    "Complianz": [
        # CMP muito comum em WordPress BR. Container do banner.
        r'id\s*=\s*["\']cmplz-cookiebanner-container["\']',
        r'class\s*=\s*["\'][^"\']*cmplz-cookiebanner[^"\']*["\']',
    ],
}


__all__ = ["VENDOR_SIGNATURES"]
