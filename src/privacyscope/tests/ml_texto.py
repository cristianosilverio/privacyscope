"""VariableTests das tres variaveis textuais, por classificacao supervisionada.

VARIAVEIS
---------
    finalidade_especificada          artefato `finalidade`
    direitos_titular_explicados      artefato `direitos_titular`
    transf_internacional_divulgada   artefato `transf_internacional`

Uma implementacao, tres subclasses. Cada subclasse existe apenas para declarar o
nome do plugin, o nome da variavel produzida e o artefato correspondente: o
orquestrador resolve nome -> classe e instancia sem argumentos, de sorte que a
identidade da variavel tem de estar na classe, e nao em parametro.

CLASSIFICACAO POR SENTENCA, SAIDA POR SITIO
-------------------------------------------
O classificador decide SENTENCA a sentenca. O que o arcabouco devolve por sitio e
outra coisa, e o contrato foi fixado assim:

    value          presenca de ao menos uma sentenca sinalizada
    confidence     maior probabilidade entre as sinalizadas
    audit_trail    contagem, denominador, limiar, as sentencas de maior escore,
                   identidade do artefato, versao do preparo e cobertura

A leitura binaria e a agregacao trivial da contagem — pô-la em `value` contrariaria
o tipo declarado no protocolo sem acrescentar informacao, uma vez que a contagem
permanece disponivel. O denominador acompanha porque contagem bruta nao e comparavel
entre sitios: politica de tres mil segmentos e outra de cem, ambas com cinco
sentencas sinalizadas, nao dizem a mesma coisa.

O arcabouco nao arbitra o que cinco sentencas significam em lugar de uma. Ele
relata, e a decisao fica com quem consome — que e o que preserva a distincao entre
evidencia tecnica observavel e juizo de conformidade.

MATERIAL SUBMETIDO
------------------
Subpaginas e documentos em PDF, EXCLUIDA a pagina inicial e a captura anterior ao
consentimento. A exclusao reproduz o material sobre o qual o modelo foi ajustado:
as transcricoes de referencia localizam-se na secao de politica, e nenhuma ocorre
exclusivamente na pagina inicial, de modo que submete-la acrescentaria apenas
material de navegacao — de natureza distinta da que o modelo aprendeu.

O preparo e o da biblioteca, o mesmo do treino, sem reimplementacao.

IDENTIDADE DO ARTEFATO
----------------------
O protocolo declara `modelo_file` e `modelo_sha256`. O artefato e lido UMA VEZ e
reaproveitado; identidade divergente interrompe a execucao em vez de produzir
resultado atribuido a um modelo que nao foi o empregado.

EXTRAPOLACAO
------------
A lista de sitios de quem executa o arcabouco nao e a lista de treino. Quando a
cobertura de vocabulario do documento fica abaixo do quantil inferior observado no
treino, o resultado sai marcado: a predicao ali e extrapolacao, e a marca e o que
impede a degradacao de passar despercebida.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

from privacyscope.core.interfaces import VariableTest
from privacyscope.core.types import RawEvidence, VariableResult
from privacyscope.models.artefato import Artefato, le
from privacyscope.text.segmentacao import segmenta

logger = logging.getLogger(__name__)

PAGINAS_EXCLUIDAS = frozenset({"/", "/__pre_consent"})
N_SENTENCAS_PADRAO = 10      # teto de sentencas gravadas no registro de auditoria


class MLTextoTest(VariableTest):
    """Base das tres variaveis textuais. Nao se registra diretamente."""

    version: ClassVar[str] = "1.0.0"
    name: ClassVar[str] = ""
    variable_name: ClassVar[str] = ""
    variavel_artefato: ClassVar[str] = ""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], Artefato] = {}

    # ------------------------------------------------------------- artefato
    def _artefato(self, params: dict[str, Any]) -> Artefato:
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
            a = le(p, esperado or None)
            if a.variavel != self.variavel_artefato:
                raise ValueError(
                    f"{self.name}: o artefato {p.name} declara a variavel "
                    f"{a.variavel!r}, e este teste produz {self.variavel_artefato!r}. "
                    f"Artefato trocado no protocolo.")
            if not esperado:
                logger.warning(
                    "%s: `modelo_sha256` nao declarado no protocolo; a identidade "
                    "do artefato nao sera conferida (encontrado: %s)",
                    self.name, a.sha256)
            self._cache[chave] = a
        return self._cache[chave]

    # -------------------------------------------------------------- material
    @staticmethod
    def _paginas(evidence: RawEvidence) -> dict[str, bytes]:
        return {k: v for k, v in (evidence.html_pages or {}).items()
                if k not in PAGINAS_EXCLUIDAS and v}

    @staticmethod
    def _textos_pdf(evidence: RawEvidence) -> tuple[list[str], list[str]]:
        """Texto de cada PDF e o metodo pelo qual foi obtido."""
        textos, metodos = [], []
        for dados in (evidence.pdf_documents or {}).values():
            if not dados:
                continue
            try:
                from privacyscope.fetchers._pdf import extract_pdf_text
                texto, metodo = extract_pdf_text(dados)
            except Exception as e:                       # noqa: BLE001
                logger.warning("falha ao extrair PDF: %s", e)
                texto, metodo = "", "erro"
            if texto:
                textos.append(texto)
            metodos.append(metodo)
        return textos, metodos

    # -------------------------------------------------------------- avaliacao
    def evaluate(self, evidence: RawEvidence, params: dict[str, Any], *,
                 protocol_version: str, run_id: str) -> VariableResult:
        from datetime import datetime, timezone

        artefato = self._artefato(params)
        teto = int(params.get("n_sentencas_auditoria", N_SENTENCAS_PADRAO))
        # Sufixo declarado no protocolo, para quando dois regimes da mesma variavel
        # convivem no mesmo run. A camada de resultados tem chave unica por nome, e
        # sem o sufixo um sobrescreveria o outro em silencio.
        sufixo = params.get("variavel_sufixo", "")

        paginas = self._paginas(evidence)
        textos_pdf, metodos_pdf = self._textos_pdf(evidence)
        preparo = segmenta(paginas, textos_pdf)
        segmentos = preparo.segmentos

        trilha: dict[str, Any] = {
            **artefato.descricao(),
            "n_segmentos_avaliados": len(segmentos),
            "n_subpaginas": len(paginas),
            "n_pdf": len(textos_pdf),
            "metodos_pdf": metodos_pdf,
            "subpaginas_outro_idioma": list(preparo.subpaginas_removidas),
            "preparo_parametros": dict(preparo.parametros),
        }

        if not segmentos:
            # Ausencia de conteudo avaliavel NAO e ausencia de divulgacao. Politica
            # existente apenas em idioma estrangeiro cai aqui, e o motivo vai
            # registrado para que a leitura a jusante nao as confunda.
            # Ja se sabe que nao restou segmento. Se alguma subpagina foi removida
            # pelo filtro de idioma, o documento existe e nao se enderecca ao
            # titular em portugues; se nenhuma foi, simplesmente nao ha texto.
            trilha["motivo"] = ("politica_outro_idioma"
                               if preparo.subpaginas_removidas
                               else "sem_texto_avaliavel")
            trilha["n_sentencas_sinalizadas"] = 0
            trilha["sentencas"] = []
            return self._resultado(evidence, False, 0.0, trilha, sufixo,
                                   protocol_version, run_id, datetime.now(timezone.utc))

        prob, sinal = artefato.decide(segmentos)
        indices = [i for i, s in enumerate(sinal) if s]
        indices.sort(key=lambda i: -prob[i])

        # A cobertura e do documento inteiro, e nao por sentenca: a pergunta e se
        # ESTE material se parece com aquele em que o modelo foi ajustado.
        cobertura = artefato.cobertura(" ".join(segmentos))
        trilha.update({
            "n_sentencas_sinalizadas": len(indices),
            "limiar": artefato.limiar,
            "cobertura_vocabulario": round(float(cobertura), 4),
            "extrapolacao": bool(artefato.em_extrapolacao(cobertura)),
            "sentencas": [{"posicao": int(preparo.uteis[i]),
                           "escore": round(float(prob[i]), 4),
                           "texto": segmentos[i]} for i in indices[:teto]],
        })
        if len(indices) > teto:
            trilha["sentencas_omitidas"] = len(indices) - teto

        valor = bool(indices)
        confianca = float(prob[indices[0]]) if indices else float(prob.max())
        return self._resultado(evidence, valor, confianca, trilha, sufixo,
                               protocol_version, run_id, datetime.now(timezone.utc))

    def _resultado(self, evidence, valor, confianca, trilha, sufixo,
                   protocol_version, run_id, agora) -> VariableResult:
        return VariableResult(
            domain_url=evidence.domain.url,
            variable_name=f"{self.variable_name}{sufixo}",
            value=valor,
            confidence=max(0.0, min(1.0, float(confianca))),
            audit_trail=trilha,
            protocol_version=protocol_version,
            plugin_version=self.version,
            run_id=run_id,
            timestamp_utc=agora)


class FinalidadeEspecificadaTest(MLTextoTest):
    name: ClassVar[str] = "finalidade_especificada"
    variable_name: ClassVar[str] = "finalidade_especificada"
    variavel_artefato: ClassVar[str] = "finalidade"


class DireitosTitularExplicadosTest(MLTextoTest):
    name: ClassVar[str] = "direitos_titular_explicados"
    variable_name: ClassVar[str] = "direitos_titular_explicados"
    variavel_artefato: ClassVar[str] = "direitos_titular"


class TransfInternacionalDivulgadaTest(MLTextoTest):
    name: ClassVar[str] = "transf_internacional_divulgada"
    variable_name: ClassVar[str] = "transf_internacional_divulgada"
    variavel_artefato: ClassVar[str] = "transf_internacional"
