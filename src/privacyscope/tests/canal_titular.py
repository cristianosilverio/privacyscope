"""
VariableTest: tem_canal_titular.

Detecta presenca de canal de atendimento ao titular dos dados (art. 18 LGPD),
com foco no contato do Encarregado (art. 41 LGPD; Res. CD/ANPD nr 18/2024, que
exige a divulgacao da IDENTIDADE e do CONTATO do Encarregado). Sinais:

    1. **E-mail com prefixo LGPD** (dpo@, encarregado@, lgpd@, privacidade@,
       protecaodedados@) em qualquer pagina coletada, DESDE QUE o dominio do
       e-mail nao seja de um provedor de infraestrutura/SaaS (blocklist).
    2. **Subpagina `canal_titular`** baixada e plausivel.
    3. **Subpagina `encarregado`** baixada e plausivel.

Refinamento pos-piloto B4 (criterio do Encarregado):
    - E-mail GENERICO nao conta (o whitelist de prefixos ja garante isso).
    - Removidas branches que davam TRUE sem contato especifico.
    - Filtro controlador-vs-processador: e-mail de DPO em dominio de provedor
      (ex.: dpo@cloudflare.com) e descartado.

CONFIG EXTERNA (decisao B4 — externalizar DADO, manter LOGICA no codigo):
    Os parametros de DADO (provider_email_blocklist, canal_plausibility_keywords,
    min_subpage_bytes) vem de ``params`` (carregados pelo orquestrador a partir
    de ``config/rules/canal_titular.yaml`` declarado no protocolo). As regex e o
    fluxo de decisao permanecem no codigo. Se um parametro faltar em params, usa
    o respectivo *_DEFAULT abaixo (fallback a prova de falha). A fonte do
    blocklist e seu hash vao para o audit_trail (rastreabilidade do run).

    LIMITACAO do blocklist e abordagem IDEAL (allowlist por controlador) estao
    documentadas em config/rules/canal_titular.yaml e no TCC (trabalho futuro).
    Os valores hardcoded de fallback foram DERIVADOS na piloto B4 (n=49) — sao
    de desenvolvimento, a validar em amostra held-out (B8) e, no que for
    aprendivel, superados por classificador supervisionado (B9).

Fundamentacao:
    - LGPD art. 18; art. 41 e Res. CD/ANPD nr 18/2024 (identidade e contato do
      Encarregado).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, ClassVar
from urllib.parse import urlparse

from privacyscope.core.interfaces import VariableTest
from privacyscope.core.types import RawEvidence, VariableResult, utc_now
from privacyscope.tests._helpers import (
    CONFIDENCE_HIGH,
    CONFIDENCE_UNKNOWN,
    EMAIL_REGEX,
    confidence_to_float,
    is_lgpd_email_prefix,
    mask_email,
    safe_decode,
)
from privacyscope.tests._lexicon import CANAL_TITULAR_ANCHORS


# Fallbacks (a prova de falha) — a fonte editavel e config/rules/canal_titular.yaml.
MIN_CANAL_SUBPAGE_BYTES_DEFAULT = 500

CANAL_PLAUSIBILITY_KEYWORDS_DEFAULT: tuple[str, ...] = (
    "titular", "direito", "lgpd", "exercer", "exercicio", "exercício",
    "encarregado", "dpo", "solicitacao", "solicitação", "requisicao",
    "requisição", "fale conosco",
)

PROVIDER_EMAIL_BLOCKLIST_DEFAULT: frozenset[str] = frozenset({
    "cloudflare.com", "cloudfront.net", "akamai.com", "akamaihd.net",
    "fastly.com", "amazonaws.com", "wordpress.com", "automattic.com",
    "shopify.com", "wix.com", "wixpress.com", "squarespace.com",
    "hubspot.com", "zendesk.com", "salesforce.com",
})

# Compat: nomes historicos exportados (apontam para os defaults).
MIN_CANAL_SUBPAGE_BYTES = MIN_CANAL_SUBPAGE_BYTES_DEFAULT
CANAL_PLAUSIBILITY_KEYWORDS = CANAL_PLAUSIBILITY_KEYWORDS_DEFAULT
PROVIDER_EMAIL_BLOCKLIST = PROVIDER_EMAIL_BLOCKLIST_DEFAULT


def _normalize_set(items) -> frozenset[str]:
    return frozenset(str(x).strip().lower() for x in items if str(x).strip())


def _resolve_blocklist(params: dict[str, Any]) -> tuple[frozenset[str], str]:
    inline = params.get("provider_email_blocklist")
    if isinstance(inline, (list, tuple, set)) and inline:
        return _normalize_set(inline), "params"
    return PROVIDER_EMAIL_BLOCKLIST_DEFAULT, "default-hardcoded"


def _resolve_keywords(params: dict[str, Any]) -> tuple[str, ...]:
    kw = params.get("canal_plausibility_keywords")
    if isinstance(kw, (list, tuple)) and kw:
        return tuple(str(x).strip().lower() for x in kw if str(x).strip())
    return CANAL_PLAUSIBILITY_KEYWORDS_DEFAULT


def _resolve_min_bytes(params: dict[str, Any]) -> int:
    try:
        v = int(params.get("min_subpage_bytes", MIN_CANAL_SUBPAGE_BYTES_DEFAULT))
        return v if v > 0 else MIN_CANAL_SUBPAGE_BYTES_DEFAULT
    except (TypeError, ValueError):
        return MIN_CANAL_SUBPAGE_BYTES_DEFAULT


def _is_provider_email(email: str, blocklist: frozenset[str]) -> bool:
    dom = email.split("@")[-1].lower().strip()
    return any(dom == p or dom.endswith("." + p) for p in blocklist)


class CanalTitularTest(VariableTest):
    """Detecta presenca de canal de atendimento ao titular dos dados."""

    name: ClassVar[str] = "canal_titular"
    version: ClassVar[str] = "0.2.2"
    variable_name: ClassVar[str] = "tem_canal_titular"

    def evaluate(
        self,
        evidence: RawEvidence,
        params: dict[str, Any],
        *,
        protocol_version: str,
        run_id: str,
    ) -> VariableResult:
        params = params or {}
        blocklist, bl_source = _resolve_blocklist(params)
        keywords = _resolve_keywords(params)
        min_bytes = _resolve_min_bytes(params)
        bl_sha = hashlib.sha256("\n".join(sorted(blocklist)).encode("utf-8")).hexdigest()[:12]

        # 1) E-mails em TODAS as paginas coletadas (raiz + subpaginas).
        all_text = "\n".join(
            safe_decode(body) for body in evidence.html_pages.values() if body
        )
        lgpd_emails: list[str] = []
        provider_emails: list[str] = []
        generic_emails: list[str] = []
        if all_text:
            for raw_match in EMAIL_REGEX.findall(all_text):
                email = raw_match if isinstance(raw_match, str) else raw_match[0]
                if is_lgpd_email_prefix(email):
                    if _is_provider_email(email, blocklist):
                        provider_emails.append(email)
                    else:
                        lgpd_emails.append(email)
                else:
                    generic_emails.append(email)
        lgpd_emails = list(dict.fromkeys(lgpd_emails))
        provider_emails = list(dict.fromkeys(provider_emails))
        generic_emails = list(dict.fromkeys(generic_emails))

        # 2) Subpaginas dedicadas
        canal_candidates = evidence.subpage_selection.get("canal_titular", [])
        encarregado_candidates = evidence.subpage_selection.get("encarregado", [])
        canal_titular_qualified = self._first_qualified_subpage(
            canal_candidates, evidence.html_pages, min_bytes, keywords
        )
        encarregado_qualified = self._first_qualified_subpage(
            encarregado_candidates, evidence.html_pages, min_bytes, keywords
        )

        # 3) Ancoras textuais — apenas AUDITORIA (nao decidem).
        root_text = safe_decode(evidence.html_pages.get("/", b""))
        anchor_hits: list[str] = [
            a for a in CANAL_TITULAR_ANCHORS if re.search(a, root_text, re.IGNORECASE)
        ]

        # ----- Decisao: exige CONTATO ESPECIFICO do Encarregado -------------
        value: bool = False
        confidence_label: str = CONFIDENCE_UNKNOWN
        matched_via: list[str] = []
        if not root_text:
            confidence_label = CONFIDENCE_UNKNOWN
            matched_via = ["html_root_vazio"]
        else:
            if lgpd_emails:
                value = True
                matched_via.append("email_prefix_lgpd")
                confidence_label = CONFIDENCE_HIGH
            if canal_titular_qualified:
                value = True
                matched_via.append("subpage_canal_titular")
                confidence_label = CONFIDENCE_HIGH
            if encarregado_qualified:
                value = True
                matched_via.append("subpage_encarregado")
                confidence_label = CONFIDENCE_HIGH
            if not value:
                confidence_label = CONFIDENCE_HIGH
                matched_via = ["no_signal"]

        audit_trail: dict[str, Any] = {
            "matched_via": matched_via,
            "confidence_label": confidence_label,
            "lgpd_emails_masked": [mask_email(e) for e in lgpd_emails[:5]],
            "provider_emails_masked": [mask_email(e) for e in provider_emails[:5]],
            "generic_emails_count": len(generic_emails),
            "provider_blocklist_source": bl_source,
            "provider_blocklist_count": len(blocklist),
            "provider_blocklist_sha": bl_sha,
            "min_subpage_bytes": min_bytes,
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
    @staticmethod
    def _first_qualified_subpage(
        candidates: list[dict],
        html_pages: dict[str, bytes],
        min_bytes: int,
        keywords: tuple[str, ...],
    ) -> dict | None:
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
            if body is None or len(body) < min_bytes:
                continue
            text_lower = safe_decode(body).lower()
            if any(kw in text_lower for kw in keywords):
                return {**cand, "_qualified_body_size": len(body)}
        return None


__all__ = [
    "CanalTitularTest",
    "CANAL_PLAUSIBILITY_KEYWORDS_DEFAULT",
    "MIN_CANAL_SUBPAGE_BYTES_DEFAULT",
    "PROVIDER_EMAIL_BLOCKLIST_DEFAULT",
]
