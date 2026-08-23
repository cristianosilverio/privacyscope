"""Teto comparativo por representacao densa. NAO habilitado por omissao.

POR QUE ESTE PLUGIN EXISTE E NAO E O MECANISMO
-----------------------------------------------
O teto mede quanta folga a representacao esparsa deixa. Nao e o mecanismo do
arcabouco, e a razao e de desenho e nao de desempenho: o objeto do trabalho e a
construcao do instrumento, e o modelo pre-treinado e artefato de terceiro cujo
conteudo nao se examina.

Tres consequencias praticas, que sustentam a decisao de nao habilita-lo:

  CUSTO  O codificador processa cerca de oito segmentos por segundo em processador
  comum. A amostra dimensionada em 384 sitios rende algo perto de cento e sete mil
  segmentos, o que significa proximo de quatro horas por execucao. A representacao
  esparsa faz o mesmo volume em segundos.

  INTEGRIDADE  Os pesos nao acompanham o repositorio. Um arcabouco que promete
  recomputacao sobre evidencia congelada nao deve obte-los pela rede durante a
  execucao, e por isso o caminho local e a conduta declarada.

  COLISAO  Este plugin produz as MESMAS variaveis que a representacao esparsa. A
  camada de resultados tem chave unica por nome de variavel, de sorte que executar
  os dois no mesmo run sobrescreveria um com o outro. Para compara-los lado a lado,
  declare `variavel_sufixo` no protocolo.

IDENTIDADE DO CODIFICADOR
-------------------------
O artefato carrega a cabeca ajustada e o resumo criptografico do codificador,
cobrindo pesos E TOKENIZADOR — vocabulario de subpalavras distinto produz entrada
distinta para os mesmos pesos.

O diretorio local vem de `codificador_dir` no protocolo, e o resumo e conferido na
carga. Na ausencia do caminho, o codificador e resolvido pelo nome e a conferencia
se faz sobre o que a resolucao devolver, com AVISO — a conduta conveniente
permanece possivel, mas nunca silenciosa.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

from privacyscope.core.interfaces import VariableTest
from privacyscope.core.types import RawEvidence, VariableResult
from privacyscope.models.artefato import ArtefatoDenso, le_denso
from privacyscope.tests.ml_texto import (LIMIAR_CONTAGEM_PADRAO, MLTextoTest,
                                          N_SENTENCAS_PADRAO)
from privacyscope.text.segmentacao import segmenta

logger = logging.getLogger(__name__)


class BertimbauTest(VariableTest):
    """Base do teto comparativo. Nao se registra diretamente."""

    version: ClassVar[str] = "1.0.0"
    name: ClassVar[str] = ""
    variable_name: ClassVar[str] = ""
    variavel_artefato: ClassVar[str] = ""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], ArtefatoDenso] = {}
        self._codificador = None

    # -------------------------------------------------------------- artefato
    def _artefato(self, params: dict[str, Any]) -> ArtefatoDenso:
        caminho = params.get("modelo_file")
        if not caminho:
            raise ValueError(f"{self.name}: o protocolo nao declara `modelo_file`.")
        esperado = params.get("modelo_sha256") or ""
        chave = (str(caminho), esperado)
        if chave not in self._cache:
            p = Path(caminho)
            if not p.is_absolute():
                p = Path(__file__).resolve().parents[3] / caminho
            a = le_denso(p, esperado or None)
            if a.variavel != self.variavel_artefato:
                raise ValueError(
                    f"{self.name}: o artefato declara {a.variavel!r} e este teste "
                    f"produz {self.variavel_artefato!r}. Artefato trocado no protocolo.")
            self._cache[chave] = a
        return self._cache[chave]

    # ----------------------------------------------------------- codificador
    def _carrega_codificador(self, artefato: ArtefatoDenso, params: dict[str, Any]):
        """Tokenizador e pesos, conferidos contra a identidade do artefato."""
        if self._codificador is not None:
            return self._codificador
        try:
            import torch                                     # noqa: F401
            from transformers import AutoModel, AutoTokenizer
        except ImportError as e:
            raise RuntimeError(
                f"{self.name}: o teto comparativo exige as dependencias opcionais. "
                "Instale as dependencias opcionais com: "
                "pip install -e '.[ml-advanced]'") from e

        origem = params.get("codificador_dir")
        if origem:
            artefato.confere_codificador(origem)
        else:
            origem = artefato.codificador
            logger.warning(
                "%s: `codificador_dir` nao declarado; o codificador sera resolvido "
                "pelo nome %r, o que envolve resolucao remota e escapa a cadeia de "
                "custodia. Declare o caminho local para conferencia de identidade.",
                self.name, origem)

        import torch
        tok = AutoTokenizer.from_pretrained(origem)
        modelo = AutoModel.from_pretrained(origem)
        modelo.eval()
        self._codificador = (tok, modelo, torch)
        return self._codificador

    def _vetores(self, textos, artefato, params):
        """Media das posicoes ponderada pela mascara, ou a posicao de classificacao.

        A mascara zera o preenchimento antes da soma: sem isso, o vetor de um
        segmento curto dependeria de com quem ele foi agrupado no lote.
        """
        import numpy as np
        tok, modelo, torch = self._carrega_codificador(artefato, params)
        lote = int(params.get("lote", 32))
        saida = np.zeros((len(textos), len(artefato.coeficientes)), dtype=np.float64)
        with torch.no_grad():
            for i in range(0, len(textos), lote):
                bloco = textos[i:i + lote]
                ent = tok(bloco, padding=True, truncation=True,
                          max_length=artefato.max_len, return_tensors="pt")
                h = modelo(**ent).last_hidden_state
                if artefato.agregacao == "cls":
                    v = h[:, 0, :]
                else:
                    m = ent["attention_mask"].unsqueeze(-1).to(h.dtype)
                    v = (h * m).sum(1) / m.sum(1)
                saida[i:i + len(bloco)] = v.cpu().numpy()
        return saida

    # -------------------------------------------------------------- avaliacao
    def evaluate(self, evidence: RawEvidence, params: dict[str, Any], *,
                 protocol_version: str, run_id: str) -> VariableResult:
        from datetime import datetime, timezone

        artefato = self._artefato(params)
        teto = int(params.get("n_sentencas_auditoria", N_SENTENCAS_PADRAO))
        # O teto so e teto se agregar como o mecanismo que ele mede. Limiar de
        # contagem distinto entre os dois tornaria a comparacao por sitio incomparavel.
        limiar_contagem = int(params.get("limiar_contagem", LIMIAR_CONTAGEM_PADRAO))
        sufixo = params.get("variavel_sufixo", "")

        preparo = segmenta(MLTextoTest._paginas(evidence),
                           MLTextoTest._textos_pdf(evidence)[0])
        segmentos = preparo.segmentos
        trilha: dict[str, Any] = {
            **artefato.descricao(),
            "n_segmentos_avaliados": len(segmentos),
            "subpaginas_outro_idioma": list(preparo.subpaginas_removidas),
            "limiar_contagem": limiar_contagem,
            "teto_comparativo": True,
        }
        agora = datetime.now(timezone.utc)

        if not segmentos:
            trilha["motivo"] = ("politica_outro_idioma"
                                if preparo.subpaginas_removidas else "sem_texto_avaliavel")
            trilha["n_sentencas_sinalizadas"] = 0
            trilha["sentencas"] = []
            return self._resultado(evidence, False, 0.0, trilha, sufixo,
                                   protocol_version, run_id, agora)

        prob, sinal = artefato.decide(self._vetores(segmentos, artefato, params))
        indices = sorted((i for i, s in enumerate(sinal) if s), key=lambda i: -prob[i])
        trilha.update({
            "n_sentencas_sinalizadas": len(indices),
            "sentencas": [{"posicao": int(preparo.uteis[i]),
                           "escore": round(float(prob[i]), 4),
                           "texto": segmentos[i]} for i in indices[:teto]],
        })
        if len(indices) > teto:
            trilha["sentencas_omitidas"] = len(indices) - teto
        confianca = float(prob[indices[0]]) if indices else float(prob.max())
        return self._resultado(evidence, len(indices) >= limiar_contagem, confianca, trilha, sufixo,
                               protocol_version, run_id, agora)

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


class FinalidadeDensaTest(BertimbauTest):
    name: ClassVar[str] = "finalidade_especificada_densa"
    variable_name: ClassVar[str] = "finalidade_especificada"
    variavel_artefato: ClassVar[str] = "finalidade"


class DireitosDensaTest(BertimbauTest):
    name: ClassVar[str] = "direitos_titular_explicados_densa"
    variable_name: ClassVar[str] = "direitos_titular_explicados"
    variavel_artefato: ClassVar[str] = "direitos_titular"


class TransfDensaTest(BertimbauTest):
    name: ClassVar[str] = "transf_internacional_divulgada_densa"
    variable_name: ClassVar[str] = "transf_internacional_divulgada"
    variavel_artefato: ClassVar[str] = "transf_internacional"
