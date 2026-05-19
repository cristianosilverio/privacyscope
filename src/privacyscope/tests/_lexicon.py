"""
Léxico compartilhado dos VariableTests determinísticos.

Reúne padrões regex e palavras-chave usados na detecção de cookies, política
de privacidade e canal do titular. Centralizar este vocabulário num arquivo
único permite:

    - Refinamento por amostra empírica (após piloto B4) sem caçar regex
      em arquivos espalhados.
    - Auditabilidade pela banca: "que palavras o framework procurou para
      decidir que tem política?" — resposta é este arquivo.
    - Garantia de coerência: HttpFetcher (em ``_subpage.py``) e
      VariableTests usam os mesmos termos.

Padrões em regex usam ``[\\s_\\-]*`` como separador para casar variantes
"politica-de-privacidade", "politica_de_privacidade", "Política de Privacidade".
"""

from __future__ import annotations


# =============================================================================
# Termos genéricos de cookies (banner_cookies)
# =============================================================================
COOKIE_LEXICON_PT_EN: list[str] = [
    # PT-BR
    r"\bcookies?\b",
    r"rastreamento",
    r"experi\w+\s+de\s+navega\w+",
    r"consentimento",
    r"continuar\s+navegando",
    r"aceitar\s+(todos?|cookies)",
    r"concordo",
    r"permitir\s+cookies",
    # EN
    r"accept\s+cookies",
    r"cookie\s+(banner|notice|consent|preferences)",
    r"we\s+use\s+cookies",
]

# Sinais estruturais de banner (atributos/aria/role tipicamente usados).
COOKIE_STRUCTURAL_HINTS: list[str] = [
    r'role\s*=\s*["\']dialog["\']',
    r'aria-modal\s*=\s*["\']true["\']',
    r'aria-label[^>]*(cookie|consent|privacidad)',
    r'id\s*=\s*["\'][^"\']*cookie[^"\']*["\']',
    r'class\s*=\s*["\'][^"\']*cookie[^"\']*["\']',
]


# =============================================================================
# Keywords de plausibilidade para qualificar página de política
# =============================================================================
# Usadas pelo tem_politica_privacidade para distinguir uma política real de
# uma página que apenas menciona "LGPD" (e.g., denúncia, evento, notícia).
# Critério: ``confidence_level: high`` exige >= 3 keywords distintas.
POLICY_PLAUSIBILITY_KEYWORDS: list[str] = [
    "lgpd",
    "lei geral de proteção de dados",
    "lei nº 13.709",
    "13.709",
    "base legal",
    "bases legais",
    "finalidade",
    "compartilhamento",
    "retenção",
    "retencao",
    "titular dos dados",
    "titular dos seus dados",
    "encarregado",
    "anpd",
    "autoridade nacional",
    "direitos do titular",
    "consentimento",
    "tratamento de dados",
    "dados pessoais",
    "transferência internacional",
    "transferencia internacional",
]


# =============================================================================
# Âncoras textuais para canal do titular
# =============================================================================
# Termos que indicam existência de canal de exercício de direitos (art. 18
# LGPD), além das categorias do _subpage.py.
CANAL_TITULAR_ANCHORS: list[str] = [
    r"\bencarregad[oa]\b",
    r"\bdpo\b",
    r"data\s+protection\s+officer",
    r"portal\s+do\s+titular",
    r"central\s+do\s+titular",
    r"canal\s+do\s+titular",
    r"seus\s+direitos",
    r"direitos\s+do\s+titular",
    r"exerc\w+\s+de\s+direitos",
    r"requisi\w+\s+lgpd",
    r"solicita\w+\s+lgpd",
    r"fale\s+conosco.{0,30}lgpd",
    r"contato.{0,30}prote\w+\s+de\s+dados",
]


__all__ = [
    "COOKIE_LEXICON_PT_EN",
    "COOKIE_STRUCTURAL_HINTS",
    "POLICY_PLAUSIBILITY_KEYWORDS",
    "CANAL_TITULAR_ANCHORS",
]
