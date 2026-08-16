"""CoorteReexameSource — dominios selecionados por resultado de execucao anterior.

POR QUE ESTA FONTE EXISTE
-------------------------
O art. 19 da Resolucao CD/ANPD n. 1/2021 estabelece ciclo anual de monitoramento, e
o art. 20 exige que o Relatorio de Ciclo avalie o que se fez e direcione o ciclo
seguinte. Reexaminar quem apresentou ausencia de sinal e, literalmente, o que a norma
descreve — e ate aqui a unica via era enumerar dominios a mao no protocolo.

A demanda ja existia antes de a fonte existir: `protocols/b7_recollect.yaml` e
exatamente isso, resolvido por transcricao manual.

O QUE ELA NAO E
---------------
**Nao e amostra probabilistica.** E CENSO DE UMA CONDICAO: devolve todos os dominios
que satisfazem o criterio declarado, e nao um sorteio deles. Estimar prevalencia
sobre o resultado de uma coorte assim seria erro grosseiro — a coorte foi definida
justamente pela variavel que se pretenderia estimar.

O uso legitimo e outro: verificar se a condicao persiste, medir mudanca entre ciclos,
e concentrar esforco de verificacao humana onde ha sinal. A leitura e longitudinal,
sobre os mesmos sitios, e nao transversal sobre a populacao.

CRITERIOS
---------
    valor          o resultado da variavel iguala o declarado — inclusive
                   `nao_aplicavel`, que seleciona os sitios em que a medicao nao
                   pode ser feita, tipicamente por ausencia de politica detectada
    extrapolacao   o registro de auditoria marcou o documento como fora da
                   distribuicao em que o modelo foi ajustado
    sem_resultado  o dominio consta da execucao mas a variavel nao foi apurada,
                   o que em regra indica falha de coleta
    mudanca        o valor difere entre DUAS execucoes sobre o mesmo dominio. E a
                   condicao que materializa o ciclo do art. 20, que exige do
                   Relatorio avaliar o que se fez e direcionar o seguinte: as duas
                   listas que interessam sao quem regularizou e quem regrediu.
                   Sem `variavel`, considera qualquer uma; com ela, so aquela.
                   Sem identificadores de execucao, compara as duas mais recentes.
                   So entram execucoes CONCLUIDAS.

Uso no protocolo:

    sources:
      - name: coorte_reexame
        params:
          db_path: data/padrao/results.sqlite
          run_id: 06c0905b-...        # opcional; padrao e a execucao mais recente
          variavel: tem_politica_privacidade
          valor: false
          limite: 300                 # opcional
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, ClassVar, Iterator

from privacyscope.core.interfaces import SampleSource
from privacyscope.core.types import (
    ESTADOS_INDETERMINADOS, NAO_APLICAVEL, Domain)
from privacyscope.sources.csv_lista import normaliza_host, sufixo

logger = logging.getLogger(__name__)

CRITERIOS = ("valor", "extrapolacao", "sem_resultado", "mudanca")


class CoorteInvalidaError(ValueError):
    """Banco ausente, execucao inexistente ou criterio mal declarado."""


class CoorteReexameSource(SampleSource):
    """Dominios de execucao anterior que satisfazem um criterio declarado."""

    name: ClassVar[str] = "coorte_reexame"
    version: ClassVar[str] = "1.0.0"

    def list_domains(self, params: dict[str, Any]) -> Iterator[Domain]:
        caminho = params.get("db_path")
        if not caminho:
            raise CoorteInvalidaError(
                "CoorteReexameSource exige params['db_path'] com o banco de "
                "resultados da execucao anterior.")
        p = Path(caminho)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[3] / caminho
        if not p.is_file():
            raise CoorteInvalidaError(f"banco de resultados nao encontrado: {p}")

        criterio = self._criterio(params)
        variavel = params.get("variavel")
        # `mudanca` dispensa a variavel: sem ela, qualquer diferenca conta. Nos
        # demais criterios a coorte se define por uma variavel e uma condicao sobre
        # ela, e omiti-la tornaria a selecao indeterminada.
        if not variavel and criterio != "mudanca":
            raise CoorteInvalidaError(
                "CoorteReexameSource exige params['variavel']: a coorte se define "
                "por uma variavel e uma condicao sobre ela.")
        limite = params.get("limite")

        recentes = self._execucoes(p)
        if not recentes:
            raise CoorteInvalidaError(
                f"nenhuma execucao CONCLUIDA em {p}. Execucao em curso ou "
                f"interrompida nao define coorte: o que ela ainda nao alcancou "
                f"seria lido como ausencia de sinal.")
        run_id = params.get("run_id") or recentes[0]
        anterior = params.get("run_id_anterior")
        if criterio == "mudanca" and not anterior:
            candidatas = [r for r in recentes if r != run_id]
            if not candidatas:
                raise CoorteInvalidaError(
                    f"o criterio `mudanca` compara DUAS execucoes concluidas, e "
                    f"{p.name} tem apenas uma. Rode o protocolo outra vez sobre o "
                    f"mesmo conjunto antes de reexaminar por diferenca.")
            anterior = candidatas[0]

        # A leitura passa pela INTERFACE do armazenamento, e nao pela tabela. O
        # armazenamento serializa o valor em notacao de objetos — booleano vira
        # `true`, cadeia vira `"nao_aplicavel"` com aspas —, e ler a coluna crua
        # obrigaria esta fonte a conhecer aquela convencao. Conhecimento duplicado
        # de serializacao e defeito silencioso a espera de uma mudanca de formato.
        from privacyscope.core.plugin_registry import resolve as _resolve
        loja = _resolve("result_stores", "sqlite")(db_path=str(p))
        try:
            hosts = self._seleciona(loja, run_id, variavel, criterio, params,
                                    anterior=anterior)
        finally:
            loja.close()

        if limite:
            hosts = hosts[: int(limite)]
        logger.info("CoorteReexameSource: %d dominios de %s, criterio %s, "
                    "execucao %s%s, variavel %s", len(hosts), p.name, criterio,
                    run_id[:8], f" contra {anterior[:8]}" if anterior else "",
                    variavel or "(qualquer)")
        if not hosts:
            logger.warning(
                "CoorteReexameSource: a coorte saiu VAZIA. Confira a variavel e o "
                "criterio: coorte vazia executa sem coletar nada e encerra sem aviso.")
        for h in hosts:
            yield Domain(url=f"https://{h}", tld=sufixo(h),
                         source_name=self.name, rank=None, stratum=None)

    # ------------------------------------------------------------------
    @staticmethod
    def _criterio(params: dict[str, Any]) -> str:
        declarados = [c for c in CRITERIOS if c in params]
        if len(declarados) > 1:
            raise CoorteInvalidaError(
                f"declare UM criterio, e nao {declarados}: combinar dois tornaria "
                f"a definicao da coorte ambigua.")
        return declarados[0] if declarados else "valor"

    @staticmethod
    def _execucoes(caminho: Path) -> list[str]:
        """A tabela de execucoes nao tem interface propria; le-se direto.

        Aqui a leitura crua e admissivel porque nao envolve serializacao de valor:
        o identificador e o instante sao texto em ambos os lados.
        """
        con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        try:
            # So execucoes CONCLUIDAS. Definir coorte sobre execucao em curso
            # confunde o que ainda nao foi coletado com o que foi coletado e nao
            # apurou sinal — e, na comparacao entre execucoes, marcaria como
            # mudanca todo dominio que a execucao nova ainda nao alcancou.
            return [r[0] for r in con.execute(
                "SELECT run_id FROM runs WHERE completed_at IS NOT NULL "
                "ORDER BY started_at DESC")]
        finally:
            con.close()

    @staticmethod
    def _seleciona(loja, run_id: str, variavel: str, criterio: str,
                   params: dict[str, Any], anterior: str | None = None) -> list[str]:
        todos = list(loja.query({"run_id": run_id}))

        if criterio == "mudanca":
            def mapa(rid):
                return {(r.domain_url, r.variable_name): r.value
                        for r in loja.query({"run_id": rid})
                        if not variavel or r.variable_name == variavel}
            atual, antes = mapa(run_id), mapa(anterior)
            # So entram dominios apurados nas DUAS execucoes: variavel ausente de um
            # lado e falha de coleta, e trata-la como mudanca confundiria instabilidade
            # do detector com instabilidade da coleta.
            comuns = set(atual) & set(antes)
            mudaram = {u for (u, _v) in comuns
                       if not _igual(atual[(u, _v)], antes[(u, _v)])}
            return sorted(normaliza_host(u) for u in mudaram)

        if criterio == "sem_resultado":
            # Dominios da execucao que nao registraram esta variavel. Em regra e
            # falha de coleta: o sitio entrou na amostra e nao produziu evidencia.
            presentes = {r.domain_url for r in todos}
            com = {r.domain_url for r in todos if r.variable_name == variavel}
            return sorted(normaliza_host(u) for u in (presentes - com))

        da_variavel = [r for r in todos if r.variable_name == variavel]
        if criterio == "extrapolacao":
            return [normaliza_host(r.domain_url) for r in da_variavel
                    if (r.audit_trail or {}).get("extrapolacao")]

        alvo = params.get("valor")
        if alvo is None:
            # A mensagem enumera os estados a partir do modulo de tipos, e nao de
            # uma lista escrita a mao: o quarto estado nasceu depois desta mensagem,
            # e ela continuou anunciando tres por meses.
            estados = ", ".join(["true", "false"] + [repr(e) for e in ESTADOS_INDETERMINADOS])
            raise CoorteInvalidaError(
                f"o criterio `valor` exige params['valor']: {estados}.")
        return [normaliza_host(r.domain_url) for r in da_variavel
                if _igual(r.value, alvo)]


def _igual(valor: Any, alvo: Any) -> bool:
    """Compara o valor ja desserializado com o declarado no protocolo.

    O protocolo traz booleano do YAML ou cadeia; o armazenamento devolve o tipo
    original. A comparacao por texto normalizado cobre as tres saidas possiveis sem
    depender de qual das duas pontas escolheu que representacao.
    """
    if isinstance(valor, bool) and isinstance(alvo, bool):
        return valor is alvo
    return str(valor).strip().lower() == str(alvo).strip().lower()
