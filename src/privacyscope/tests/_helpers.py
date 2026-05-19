"""
Utilitários compartilhados entre VariableTests.

Funções e constantes que aparecem em mais de um teste — extraídas para
manter cada teste focado na lógica específica da variável que apura.
"""

from __future__ import annotations

import re
from typing import Optional


# -----------------------------------------------------------------------
# Confidence labels e mapping para float (contrato VariableResult.confidence)
# -----------------------------------------------------------------------
# VariableResult.confidence é float em [0,1] (modelos ML retornam
# probabilidade direta). Testes determinísticos usam labels semânticas que
# são mapeadas para valores fixos. A label vai para audit_trail; o float vai
# para o campo VariableResult.confidence.
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNKNOWN = "unknown"
CONFIDENCE_LEVELS = (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_UNKNOWN,
)

_CONFIDENCE_FLOAT_MAP = {
    CONFIDENCE_HIGH: 0.95,
    CONFIDENCE_MEDIUM: 0.65,
    CONFIDENCE_LOW: 0.35,
    CONFIDENCE_UNKNOWN: 0.0,
}


def confidence_to_float(label: str) -> float:
    """Mapeia label semântica para float compatível com VariableResult.confidence.

    Raises:
        ValueError: se label não estiver em CONFIDENCE_LEVELS.
    """
    if label not in _CONFIDENCE_FLOAT_MAP:
        raise ValueError(
            f"confidence label desconhecida: {label!r}. Use uma de: {CONFIDENCE_LEVELS}"
        )
    return _CONFIDENCE_FLOAT_MAP[label]


# -----------------------------------------------------------------------
# Decodificação segura de HTML em bytes
# -----------------------------------------------------------------------
def safe_decode(content: bytes, max_bytes: int = 5_000_000) -> str:
    """Decodifica bytes para str com fallback robusto.

    Tenta utf-8 (mais comum em sites brasileiros), depois latin-1 como
    fallback (alguns sites legados). Trunca a ``max_bytes`` para evitar
    custo excessivo em páginas anormalmente grandes.
    """
    if not content:
        return ""
    if len(content) > max_bytes:
        content = content[:max_bytes]
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


# -----------------------------------------------------------------------
# Match com contexto — usado para evidence_snippet
# -----------------------------------------------------------------------
def match_with_context(
    pattern: str,
    text: str,
    *,
    context_chars: int = 120,
    flags: int = re.IGNORECASE,
) -> Optional[dict]:
    """Procura ``pattern`` em ``text`` e devolve match + snippet evidencial.

    Returns:
        None se nenhum match. Caso contrário::

            {
                "matched_pattern": pattern,
                "position": int,             # offset no texto
                "snippet": str,              # até 240 chars centrados no match
                "match_text": str,           # o que casou exatamente
            }

    O ``snippet`` tem até ``2 * context_chars`` caracteres e é o que vai
    para ``VariableResult.evidence_snippet`` — auditável visualmente em
    qualquer ferramenta (Excel, IDE, browser).
    """
    if not text or not pattern:
        return None
    m = re.search(pattern, text, flags)
    if not m:
        return None
    start = max(0, m.start() - context_chars)
    end = min(len(text), m.end() + context_chars)
    snippet = text[start:end]
    # Compacta whitespace para snippet ficar legível em coluna de tabela
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return {
        "matched_pattern": pattern,
        "position": m.start(),
        "snippet": snippet[:240],
        "match_text": m.group(0),
    }


# -----------------------------------------------------------------------
# Mascaramento de e-mail — convenção: 2 chars + asteriscos + domínio
# -----------------------------------------------------------------------
def mask_email(email: str) -> str:
    """Mascara e-mail mantendo 2 primeiros chars do username e domínio.

    Exemplos::

        mask_email("dpo@example.com.br")        -> "dp***@example.com.br"
        mask_email("e@example.com")             -> "e***@example.com"
        mask_email("contato@ipt.br")            -> "co***@ipt.br"

    Notes:
        - E-mails do encarregado são por LGPD art. 41 publicamente
          disponibilizados; o mascaramento aqui é convenção do framework
          para preservar evidência sem expor literal em exports tabulares.
        - O HTML completo permanece no tar.gz da evidência bruta, sem
          mascaramento — auditoria forense preservada.
    """
    if "@" not in email:
        return email
    user, _, domain = email.partition("@")
    if len(user) <= 2:
        return f"{user}***@{domain}"
    return f"{user[:2]}***@{domain}"


# -----------------------------------------------------------------------
# Regex de e-mail — uso geral nos testes
# -----------------------------------------------------------------------
# Padrão deliberadamente conservador: aceita TLDs comuns no Brasil.
# Evita capturar @example.com em código JS que não corresponde a contato real.
EMAIL_REGEX = re.compile(
    r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:com|com\.br|br|gov\.br|org|org\.br|edu|edu\.br|net|net\.br))\b",
    re.IGNORECASE,
)


# Prefixos de username que indicam canal LGPD/proteção de dados.
EMAIL_PREFIXES_LGPD = (
    "dpo",
    "encarregado",
    "encarregada",
    "privacidade",
    "lgpd",
    "protecaodedados",
    "protecao.dados",
    "protecao_dados",
    "dataprotection",
    "data.protection",
)


def is_lgpd_email_prefix(email: str) -> bool:
    """True se o username do e-mail começa com prefixo típico LGPD."""
    user = email.split("@", 1)[0].lower()
    return any(user.startswith(p) for p in EMAIL_PREFIXES_LGPD)


__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "CONFIDENCE_UNKNOWN",
    "CONFIDENCE_LEVELS",
    "confidence_to_float",
    "safe_decode",
    "match_with_context",
    "mask_email",
    "EMAIL_REGEX",
    "EMAIL_PREFIXES_LGPD",
    "is_lgpd_email_prefix",
]
