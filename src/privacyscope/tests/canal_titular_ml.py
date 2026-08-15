"""VariableTest de ``tem_canal_titular`` por classificacao supervisionada.

ACRESCENTA, NAO SUBSTITUI
-------------------------
O detector por regra permanece registrado sob ``canal_titular`` e continua
executavel. Os resultados do trabalho reportam os DOIS regimes para esta variavel —
o determinístico como linha de base declarada, o supervisionado como desfecho —, e
o arcabouco tem de poder produzir ambos, sob declaracao no protocolo. Substituir um
pelo outro impediria a comparacao que o trabalho reivindica.

O ESTIMADOR
-----------
Regressao logistica com correcao de Firth, implementada pelo autor. A correcao se
impos por medicao: tres dos oito atributos nao apresentam contraexemplo na classe
negativa, situacao de separacao quase completa em que a maxima verossimilhanca nao
existe — o coeficiente diverge e leva junto a calibracao, a estabilidade entre
particoes e a interpretacao.

A inferencia aqui NAO reajusta nada. Ela aplica os coeficientes gravados, e a
correcao de Firth pertence ao ajuste, nao ao uso.

MATERIAL SUBMETIDO
------------------
O sitio inteiro — pagina inicial inclusive — mais o texto dos documentos em PDF. A
diferenca em relacao as variaveis textuais e do construto: o canal de atendimento
nao e propriedade do texto da politica e pode ser divulgado em pagina de contato.

A ORDEM DA CONCATENACAO
-----------------------
Os atributos de proximidade dependem de distancia em caracteres, de sorte que a
ordem em que as paginas se concatenam pode, nas emendas, criar ou desfazer uma
vizinhanca. A ordem adotada e declarada: pagina inicial primeiro, subpaginas em
seguida, ordenadas pela chave. A coincidencia com a matriz que sustentou o ajuste e
verificada sobre material real em scripts/verificar_item.py.

SAIDA
-----
    value          presenca de canal de atendimento ao titular
    confidence     probabilidade estimada
    audit_trail    os oito atributos com seus valores, o limiar, a identidade do
                   artefato e a versao do extrator

Diferente das variaveis textuais, aqui nao ha sentencas a exibir: o que fundamenta
a decisao sao os atributos, e sao eles que vao para a conferencia humana.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

from privacyscope.core.interfaces import VariableTest
from privacyscope.core.types import RawEvidence, VariableResult
from privacyscope.features.canal_titular import (
    ATRIBUTOS, JANELA_PADRAO, VERSAO_EXTRATOR, extrai_atributos,
)
from privacyscope.models.artefato import ArtefatoCanal, le_canal

logger = logging.getLogger(__name__)


class CanalTitularMLTest(VariableTest):
    """Canal do titular por classificacao supervisionada."""

    name: ClassVar[str] = "canal_titular_ml"
    version: ClassVar[str] = "1.0.0"
    variable_name: ClassVar[str] = "tem_canal_titular"

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], ArtefatoCanal] = {}

    def _artefato(self, params: dict[str, Any]) -> ArtefatoCanal:
        caminho = params.get("modelo_file")
        if not caminho:
            raise ValueError(
                f"{self.name}: o protocolo nao declara `modelo_file`. Sem o "
                f"artefato nao ha inferencia, e adivinhar o caminho produziria "
                f"resultado atribuido a modelo indeterminado.")
        esperado = params.get("modelo_sha256") or ""
        chave = (str(caminho), esperado)
        if chave not in self._cache:
            p = Path(caminho)
            if not p.is_absolute():
                p = Path(__file__).resolve().parents[3] / caminho
            a = le_canal(p, esperado or None)
            if a.variavel != self.variable_name:
                raise ValueError(
                    f"{self.name}: o artefato {p.name} declara a variavel "
                    f"{a.variavel!r}, e este teste produz {self.variable_name!r}. "
                    f"Artefato trocado no protocolo.")
            if a.extrator_versao and a.extrator_versao != VERSAO_EXTRATOR:
                raise ValueError(
                    f"{self.name}: o artefato foi ajustado sobre atributos da "
                    f"versao {a.extrator_versao!r}, e o extrator instalado e "
                    f"{VERSAO_EXTRATOR!r}. Extrator e coeficientes formam par; "
                    f"aplicar um sobre o outro produz predicao plausivel e errada.")
            if not esperado:
                logger.warning(
                    "%s: `modelo_sha256` nao declarado; a identidade do artefato "
                    "nao sera conferida (encontrado: %s)", self.name, a.sha256)
            self._cache[chave] = a
        return self._cache[chave]

    @staticmethod
    def html_concatenado(evidence: RawEvidence) -> str:
        """Pagina inicial primeiro, subpaginas ordenadas pela chave.

        A ordem e declarada porque os atributos de proximidade dependem de
        distancia em caracteres: nas emendas entre paginas, ordem distinta pode
        criar ou desfazer uma vizinhanca.
        """
        paginas = evidence.html_pages or {}
        chaves = (["/"] if "/" in paginas else []) + sorted(k for k in paginas if k != "/")
        return "\n".join(paginas[k].decode("utf-8", "ignore") for k in chaves
                         if paginas.get(k))

    @staticmethod
    def texto_pdf(evidence: RawEvidence) -> str:
        import re
        partes = []
        for dados in (evidence.pdf_documents or {}).values():
            if not dados:
                continue
            try:
                from privacyscope.fetchers._pdf import extract_pdf_text
                texto, _ = extract_pdf_text(dados)
            except Exception as e:                       # noqa: BLE001
                logger.warning("falha ao extrair PDF: %s", e)
                texto = ""
            if texto:
                partes.append(texto)
        return re.sub(r"\s+", " ", " ".join(partes))

    def evaluate(self, evidence: RawEvidence, params: dict[str, Any], *,
                 protocol_version: str, run_id: str) -> VariableResult:
        from datetime import datetime, timezone

        artefato = self._artefato(params)
        janela = int(artefato.extrator_parametros.get("janela", JANELA_PADRAO))

        html = self.html_concatenado(evidence)
        atributos = extrai_atributos(
            html, url=evidence.domain.url,
            subpage_selection=(evidence.subpage_selection or {}),
            texto_pdf=self.texto_pdf(evidence), janela=janela)

        prob, sinal = artefato.decide(atributos)
        trilha: dict[str, Any] = {
            **artefato.descricao(),
            "atributos": {a: int(atributos[a]) for a in ATRIBUTOS},
            "janela": janela,
            "n_subpaginas": len(evidence.html_pages or {}),
            "n_pdf": len(evidence.pdf_documents or {}),
            "extrator_parametros": dict(artefato.extrator_parametros or {}),
        }
        return VariableResult(
            domain_url=evidence.domain.url,
            variable_name=self.variable_name,
            value=bool(sinal),
            confidence=max(0.0, min(1.0, float(prob))),
            audit_trail=trilha,
            protocol_version=protocol_version,
            plugin_version=self.version,
            run_id=run_id,
            timestamp_utc=datetime.now(timezone.utc))
