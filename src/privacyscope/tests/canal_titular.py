"""
VariableTest: tem_canal_titular.

Detecta presença de canal de atendimento ao titular dos dados (art. 18 LGPD).
Combina múltiplos sinais auditáveis, em ordem de confiança:

    1. **E-mail com prefixo LGPD whitelist** (dpo@, encarregado@, lgpd@,
       privacidade@, protecaodedados@) em qualquer página coletada. Sinal
       mais forte — alta confiança de canal específico para titular.

    2. **Subpágina `canal_titular`** baixada com conteúdo plausível
       (>= 500 bytes, contém âncora de "direitos do titular").
       Capturada pela categoria criada em ``fetchers/_subpage.py``.

    3. **Subpágina `encarregado`** baixada (DPO nominalmente identificado).

    4. **Âncoras textuais** ("DPO", "Encarregado", "Portal do Titular",
       "Seus Direitos", "Exercício de Direitos") no HTML raiz, mesmo sem
       e-mail nem subpágina explícita.

Mascaramento de e-mails: o ``audit_trail`` mantém o e-mail mascarado
(2 chars + asteriscos + domínio) conforme decisão D8. O HTML completo
permanece sem mascaramento na evidência bruta (chain of custody).

Fundamentação:
    - LGPD art. 18: direitos do titular dos dados pessoais.
    - LGPD art. 41: encarregado pelo tratamento de dados pessoais.
    - Res. CD/ANPD nº 1/2021: requisitos do processo fiscalizatório.
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
    EMAIL_REGEX,
    confidence_to_float,
    is_lgpd_email_prefix,
    mask_email,
    safe_decode,
)
from privacyscope.tests._lexicon import CANAL_TITULAR_ANCHORS


MIN_CANAL_SUBPAGE_BYTES = 500

# Keywords que confirmam que uma subpágina de canal_titular trata de
# exercício de direitos (não é um link genérico que casou por acaso).
CANAL_PLAUSIBILITY_KEYWORDS: tuple[str, ...] = (
    "titular",
    "direito",
    "lgpd",
    "exercer",
    "exercicio",
    "exercício",
    "encarregado",
    "dpo",
    "solicitacao",
    "solicitação",
    "requisicao",
    "requisição",
    "fale conosco",
)


class CanalTitularTest(VariableTest):
    """Detecta presença de canal de atendimento ao titular dos dados."""

    name: ClassVar[str] = "canal_titular"
    version: ClassVar[str] = "0.1.0"
    variable_name: ClassVar[str] = "tem_canal_titular"

    def evaluate(
        self,
        evidence: RawEvidence,
        params: dict[str, Any],
        *,
        protocol_version: str,
        run_id: str,
    ) -> VariableResult:
        del params

        # 1) Procura e-mails em TODAS as páginas coletadas (raiz + subpáginas).
        all_text = "\n".join(
            safe_decode(body) for body in evidence.html_pages.values() if body
        )

        lgpd_emails: list[str] = []
        generic_emails: list[str] = []
        if all_text:
            for raw_match in EMAIL_REGEX.findall(all_text):
                # EMAIL_REGEX usa grupo capturante — raw_match já é a string.
                email = raw_match if isinstance(raw_match, str) else raw_match[0]
                if is_lgpd_email_prefix(email):
                    lgpd_emails.append(email)
                else:
                    generic_emails.append(email)

        # Dedup preservando ordem
        lgpd_emails = list(dict.fromkeys(lgpd_emails))
        generic_emails = list(dict.fromkeys(generic_emails))

        # 2) Subpáginas: canal_titular E encarregado
        canal_candidates = evidence.subpage_selection.get("canal_titular", [])
        encarregado_candidates = evidence.subpage_selection.get("encarregado", [])

        # 3) Para cada candidato, verifica se foi baixado e plausível
        canal_titular_qualified = self._first_qualified_subpage(
            canal_candidates, evidence.html_pages
        )
        encarregado_qualified = self._first_qualified_subpage(
            encarregado_candidates, evidence.html_pages
        )

        # 4) Âncoras textuais no HTML raiz (independente das categorias acima)
        root_text = safe_decode(evidence.html_pages.get("/", b""))
        anchor_hits: list[str] = []
        for anchor in CANAL_TITULAR_ANCHORS:
            m = re.search(anchor, root_text, re.IGNORECASE)
            if m:
                anchor_hits.append(anchor)

        # ----- Decisão de confidence ---------------------------------------
        value: bool = False
        confidence_label: str = CONFIDENCE_UNKNOWN
        matched_via: list[str] = []

        if not root_text:
            confidence_label = CONFIDENCE_UNKNOWN
            matched_via = ["html_root_vazio"]
        else:
            # Sinal mais forte: email com prefixo whitelist
            if lgpd_emails:
                value = True
                matched_via.append("email_prefix_lgpd")
                confidence_label = CONFIDENCE_HIGH
            # Segundo mais forte: subpágina canal_titular baixada e plausível
            if canal_titular_qualified:
                value = True
                matched_via.append("subpage_canal_titular")
                if confidence_label != CONFIDENCE_HIGH:
                    confidence_label = CONFIDENCE_HIGH
            # Terceiro: subpágina encarregado baixada (DPO identificado)
            if encarregado_qualified:
                value = True
                matched_via.append("subpage_encarregado")
                if confidence_label not in (CONFIDENCE_HIGH,):
                    confidence_label = CONFIDENCE_HIGH
            # Quarto: âncora textual + e-mail genérico no mesmo escopo
            if not value and anchor_hits and generic_emails:
                value = True
                matched_via.append("anchor_text+generic_email")
                confidence_label = CONFIDENCE_MEDIUM
            # Quinto: só âncora textual
            if not value and anchor_hits:
                value = True
                matched_via.append("anchor_text_only")
                confidence_label = CONFIDENCE_LOW
            # Sexto: candidato de subpage existe mas não baixada
            if not value and (canal_candidates or encarregado_candidates):
                value = True
                matched_via.append("subpage_link_no_download")
                confidence_label = CONFIDENCE_MEDIUM
            # Nenhum sinal → não tem canal
            if not value:
                confidence_label = CONFIDENCE_HIGH  # "não tem" também é high
                matched_via = ["no_signal"]

        audit_trail: dict[str, Any] = {
            "matched_via": matched_via,
            "confidence_label": confidence_label,
            "lgpd_emails_masked": [mask_email(e) for e in lgpd_emails[:5]],
            "generic_emails_count": len(generic_emails),
            "canal_titular_candidates": len(canal_candidates),
            "canal_titular_qualified_url": (
                canal_titular_qualified["url"] if canal_titular_qualified else None
            ),
            "encarregado_candidates": len(encarregado_candidates),
            "encarregado_qualified_url": (
                encarregado_qualified["url"] if encarregado_qualified else None
            ),
            "anchor_hits": anchor_hits[:8],
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _first_qualified_subpage(
        candidates: list[dict],
        html_pages: dict[str, bytes],
    ) -> dict | None:
        """Devolve o primeiro candidato cuja subpágina foi baixada e tem
        tamanho mínimo + keyword plausível. Retorna None se nenhum qualifica.
        """
        from urllib.parse import urlparse

        for cand in candidates:
            url = cand.get("url", "")
            if not url:
                continue
            body: bytes | None = html_pages.get(url)
            if body is None:
                path = urlparse(url).path or "/"
                body = html_pages.get(path)
                if body is None:
                    for key, bd in html_pages.items():
                        if key.endswith(path) or path.endswith(key):
                            body = bd
                            break
            if body is None or len(body) < MIN_CANAL_SUBPAGE_BYTES:
                continue
            text_lower = safe_decode(body).lower()
            if any(kw in text_lower for kw in CANAL_PLAUSIBILITY_KEYWORDS):
                return {**cand, "_qualified_body_size": len(body)}
        return None


__all__ = ["CanalTitularTest", "CANAL_PLAUSIBILITY_KEYWORDS", "MIN_CANAL_SUBPAGE_BYTES"]
