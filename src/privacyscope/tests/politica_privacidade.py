"""
VariableTest: tem_politica_privacidade.

Estratégia em duas camadas (decisão D7):

    1. **Confia no fetcher** para extração inicial de candidatos: consulta
       ``evidence.subpage_selection["politica_privacidade"]`` (já populado por
       ``fetchers/_subpage.py`` com 11 padrões cobrindo "política", "aviso",
       "notificação", "declaração", "portal", "central" de privacidade).

    2. **Qualifica a evidência** com filtros próprios para reduzir falsos
       positivos:
         - Subpágina foi efetivamente baixada (``html_pages[url]`` existe)?
         - Conteúdo plausível (>= 500 bytes)?
         - Contém >= 3 keywords distintas de LGPD/privacidade?

       Mitigação direta do falso positivo documentado em
       ``docs/notas_de_refinamento.md`` item 1 ("Denúncia LGPD" no anpd
       caindo em política — uma página de denúncia tem poucas keywords
       estruturais de política, ficando em ``confidence_level: low``).

    3. **Fallback** quando subpage_selection vazio: regex em ``html_root``
       buscando link explícito.

Fundamentação:
    - Javed; Sajid (2024): systematic review de literatura sobre políticas
      de privacidade — define termos canônicos para detecção textual.
    - Vorster; Da Veiga (2023): guidelines para análise estrutural de
      políticas de privacidade em sites comerciais.
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
from privacyscope.tests._lexicon import POLICY_PLAUSIBILITY_KEYWORDS


# Threshold mínimo de bytes para considerar uma página de política plausível.
# Páginas reais costumam ter milhares de bytes; 500 é piso conservador para
# detectar shells SPA ou redirects mal formados.
MIN_POLICY_SIZE_BYTES = 500

# Mínimo de keywords distintas para confidence high.
MIN_KEYWORDS_FOR_HIGH = 3


class PoliticaPrivacidadeTest(VariableTest):
    """Detecta presença de política/aviso/termo de privacidade."""

    name: ClassVar[str] = "politica_privacidade"
    version: ClassVar[str] = "0.1.0"
    variable_name: ClassVar[str] = "tem_politica_privacidade"

    def evaluate(
        self,
        evidence: RawEvidence,
        params: dict[str, Any],
        *,
        protocol_version: str,
        run_id: str,
    ) -> VariableResult:
        del params  # MVP: sem params customizáveis

        # 1) Consulta subpage_selection (fonte primária)
        candidates = evidence.subpage_selection.get("politica_privacidade", [])

        value: bool = False
        confidence_label: str = CONFIDENCE_UNKNOWN
        source: str = "none"
        matched_url: str | None = None
        matched_pattern: str | None = None
        matched_against: str | None = None
        subpage_size: int | None = None
        keyword_hits: list[str] = []

        if candidates:
            # Há pelo menos um candidato — tenta qualificar
            for cand in candidates:
                url = cand.get("url", "")
                if not url:
                    continue
                # Procura HTML correspondente em html_pages.
                # _subpage.py guarda URLs absolutas; html_pages tem paths
                # (e.g. "/politica-privacidade"). Tenta ambas as formas.
                body = self._find_body_for_url(evidence.html_pages, url)
                if body and len(body) >= MIN_POLICY_SIZE_BYTES:
                    text_lower = safe_decode(body).lower()
                    hits = [kw for kw in POLICY_PLAUSIBILITY_KEYWORDS if kw in text_lower]
                    if len(hits) >= MIN_KEYWORDS_FOR_HIGH:
                        value = True
                        confidence_label = CONFIDENCE_HIGH
                        source = "subpage_selection+content_qualified"
                        matched_url = url
                        matched_pattern = cand.get("matched_pattern")
                        matched_against = cand.get("matched_against")
                        subpage_size = len(body)
                        keyword_hits = hits[:10]
                        break
                    elif hits:
                        # Página existe, alguma keyword bate, mas não atinge 3
                        if confidence_label == CONFIDENCE_UNKNOWN:
                            value = True
                            confidence_label = CONFIDENCE_MEDIUM
                            source = "subpage_selection+content_weak"
                            matched_url = url
                            matched_pattern = cand.get("matched_pattern")
                            matched_against = cand.get("matched_against")
                            subpage_size = len(body)
                            keyword_hits = hits
                else:
                    # Link existe mas página não baixada (HTTP error, robots)
                    if confidence_label == CONFIDENCE_UNKNOWN:
                        value = True
                        confidence_label = CONFIDENCE_MEDIUM
                        source = "subpage_selection+page_not_downloaded"
                        matched_url = url
                        matched_pattern = cand.get("matched_pattern")
                        matched_against = cand.get("matched_against")

        # 2) Fallback: regex no HTML raiz se nada qualificou
        if not value:
            root = safe_decode(evidence.html_pages.get("/", b""))
            if root:
                # Procura link com texto "política/aviso/termo + privacidade/dados"
                m = re.search(
                    r"(polit\w+|aviso|termo|notifica\w+|declara\w+)[\s_\-]*de[\s_\-]*(privacid\w+|dados\s+pessoais)",
                    root,
                    re.IGNORECASE,
                )
                if m:
                    value = True
                    confidence_label = CONFIDENCE_LOW
                    source = "html_root_regex_fallback"
                    matched_pattern = m.group(0)[:80]
                    matched_against = "html_root"
                else:
                    confidence_label = CONFIDENCE_HIGH  # "não tem" também é high
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
    # Helpers internos
    # ------------------------------------------------------------------
    @staticmethod
    def _find_body_for_url(
        html_pages: dict[str, bytes], url: str
    ) -> bytes | None:
        """Tenta resolver bytes da subpágina pela URL absoluta.

        html_pages tem como chave o path interno (sem domínio). Estratégia:
            1. Tenta a URL absoluta diretamente (caso o fetcher armazene assim).
            2. Extrai o path da URL e busca por correspondência exata.
            3. Busca por sufixo (caso a chave seja path sem barra inicial).
        """
        if url in html_pages:
            return html_pages[url]
        # Extrai path
        from urllib.parse import urlparse
        path = urlparse(url).path or "/"
        if path in html_pages:
            return html_pages[path]
        # Tenta sufixo (chaves podem ter normalizações diferentes)
        for key, body in html_pages.items():
            if key.endswith(path) or path.endswith(key):
                return body
        return None


__all__ = ["PoliticaPrivacidadeTest", "MIN_POLICY_SIZE_BYTES", "MIN_KEYWORDS_FOR_HIGH"]
