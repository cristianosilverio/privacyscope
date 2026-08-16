"""Renderizadores de saida: a sexta camada do arcabouco.

Cinco artefatos, tres formatos, quatro finalidades. A multiplicidade nao e
redundancia: quem tabula, quem prioriza, quem verifica e quem reprocessa querem
recortes diferentes do mesmo conjunto, e atender os quatro num arquivo so atende
mal a todos.

    csv             uma linha por sitio e variavel — o formato fiel ao
                    armazenamento, com os campos escalares do registro de
                    auditoria promovidos a coluna.
    csv_triagem     uma linha por sitio, uma coluna por variavel, ORDENADA por
                    nao conformidade — a fila de trabalho de quem prioriza, que
                    e o uso que a etapa de Monitoramento faz do instrumento.
    csv_evidencias  uma linha por SENTENCA sinalizada — a lista de trabalho de
                    quem confere. E o artefato que materializa o contrato de
                    triagem com verificacao humana.
    parquet         o formato longo, tipado, para reprocessamento analitico.
    json            estrutura aninhada por sitio, com o registro de auditoria
                    INTEGRO, inclusive as sentencas. E o unico que nao perde nada.

Todos carregam identificador da execucao, versao do protocolo e, quando o
resultado provem de classificacao, o resumo criptografico do artefato que o
produziu — sem o que a planilha que sai do arcabouco deixa de ser conferivel.
"""
from __future__ import annotations

import csv
import json
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any, ClassVar

from privacyscope.core.interfaces import OutputRenderer, ResultStore
from privacyscope.core.types import NAO_APLICAVEL, NAO_COLETADO
from privacyscope.outputs._comum import (
    COLUNAS_BASE, DERIVADAS, ESCALARES, coleta, densidade, destino, dominio,
    linha_plana, sentencas, trilha,
)


def _estado(valor) -> str:
    """Quatro estados, e nao dois.

    `nao_aplicavel` nao e ausencia de divulgacao: e ausencia de medicao, porque a
    precondicao da variavel nao se verificou. Reduzi-lo a `false` produziria
    indicador enviesado exatamente na direcao que o trabalho quer medir.

    `nao_coletado` e ainda mais distante de `false`: nao houve sitio a medir, seja
    porque a coleta falhou, seja porque a origem devolveu desafio anti-bot. O
    primeiro estado fala do sitio; o segundo, do instrumento.
    """
    if valor == NAO_COLETADO or valor == "nao_coletado":
        return NAO_COLETADO
    if valor == NAO_APLICAVEL or valor == "nao_aplicavel":
        return NAO_APLICAVEL
    return "true" if valor in (True, 1, "1", "true") else "false"


def _prioridade(d: dict) -> tuple:
    """Chave de ordenacao da triagem por NAO CONFORMIDADE.

    POR QUE NAO E A SOMA DOS SINAIS AUSENTES
    ----------------------------------------
    Ordenar pela contagem de `false` parece obvio e produz o oposto do pretendido. A
    dependencia declarada entre variaveis faz com que o sitio SEM politica tenha as
    tres variaveis textuais em `nao_aplicavel`, fora da contagem: o pior caso fica
    com teto de 3, ao passo que o sitio COM politica alcanca 4. Medido na coleta ao
    vivo de 15/08/2026: seis sitios com politica ficaram acima dos trinta e um sem
    politica, e um sitio sem banner, sem politica e sem canal do titular apareceu em
    setimo lugar.

    Contar `nao_aplicavel` como ausencia corrigiria a ordem e reintroduziria o vies
    que o ternario existe para remover, confundindo "nao divulgou" com "nao foi
    medido".

    O QUE ORDENA, ENTAO
    -------------------
    Ordem lexicografica ancorada no GRAFO DE DEPENDENCIAS declarado no protocolo,
    que e fato estrutural e nao juizo de gravidade:

    1. sitios com alguma variavel NAO COLETADA vao para o fim. Perfil incompleto nao
       se compara com perfil completo, e recoleta e outra fila que nao a de
       fiscalizacao. A coluna `motivo_nao_coleta` os identifica.
    2. numero de variaveis que ficaram SEM MEDICAO por precondicao nao satisfeita.
       Nao porque ausencia de politica seja mais grave, e sim porque ela IMPEDE a
       medicao de outras tres — consequencia declarada, e nao opiniao.
    3. numero de sinais medidos e ausentes.
    4. dominio, para que a ordem seja estavel entre execucoes.

    Nenhum peso por gravidade e arbitrado. Sustentar que banner vale mais ou menos
    que politica exigiria fonte que o trabalho nao tem, e seria a mesma arbitrariedade
    ja recusada na fixacao de limiar.
    """
    return (d.get("n_nao_coletado", 0) > 0,
            -d.get("n_nao_aplicavel", 0),
            -d.get("n_sinais_ausentes", 0),
            d.get("dominio", ""))


class CsvLongo(OutputRenderer):
    """Uma linha por sitio e variavel."""

    name: ClassVar[str] = "csv"
    version: ClassVar[str] = "1.0.0"

    def render(self, store: ResultStore, params: dict[str, Any]) -> Path:
        R = coleta(store, params)
        alvo = destino(params, "data/results/resultados.csv")
        campos = list(COLUNAS_BASE) + list(ESCALARES) + list(DERIVADAS)
        with alvo.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=campos, delimiter=";", restval="")
            w.writeheader()
            for r in R:
                w.writerow(linha_plana(r))
        return alvo.resolve()


class CsvTriagem(OutputRenderer):
    """Uma linha por sitio, uma coluna por variavel, ORDENADA por nao conformidade.

    O nome diz o proposito, e nao a forma. Enquanto era apenas a versao larga do
    formato longo, o nome anterior (`csv_largo`) fazia par com `csv` no vocabulario
    corrente de dados.
    Deixou de fazer quando ganhou ordenacao por nao conformidade e coluna de
    prioridade: passou a ser duas coisas, e o nome dizia so uma.
    """

    name: ClassVar[str] = "csv_triagem"
    version: ClassVar[str] = "1.0.0"

    def render(self, store: ResultStore, params: dict[str, Any]) -> Path:
        R = coleta(store, params)
        alvo = destino(params, "data/results/resultados_triagem.csv")

        variaveis = sorted({r.variable_name for r in R})
        por_sitio: dict[str, dict[str, Any]] = OrderedDict()
        for r in R:
            d = por_sitio.setdefault(dominio(r.domain_url), {
                "dominio": dominio(r.domain_url), "domain_url": r.domain_url,
                "run_id": r.run_id, "protocol_version": r.protocol_version})
            at = trilha(r)
            d[r.variable_name] = _estado(r.value)
            d[f"{r.variable_name}__confianca"] = round(float(r.confidence), 4)
            # Contagem, denominador e densidade acompanham o valor binario porque a
            # triagem ORDENA, e o binario satura em variaveis de alta prevalencia:
            # em finalidade ele responde "sim" para toda politica com texto, ao passo
            # que a densidade preserva ordenacao. Nenhum limiar e arbitrado aqui — a
            # ordenacao dispensa corte, e escolher um contra a rotulagem de referencia
            # seria ajustar parametro sobre o conjunto de afericao.
            if at.get("n_segmentos_avaliados") is not None:
                d[f"{r.variable_name}__n_sentencas"] = at.get("n_sentencas_sinalizadas")
                d[f"{r.variable_name}__n_segmentos"] = at.get("n_segmentos_avaliados")
                d[f"{r.variable_name}__densidade"] = densidade(at)
            if at.get("extrapolacao"):
                d["extrapolacao"] = "true"
            if at.get("coletado") is False:
                # Prefere a causa RAIZ. `dependencia_nao_coletada` e consequencia, e
                # deixa-la sobrescrever o motivo original esconderia por que a coluna
                # ficou vazia — que e a pergunta que quem le a triagem faz.
                m = at.get("motivo", "desconhecido")
                atual = d.get("motivo_nao_coleta", "")
                if not atual or (atual == "dependencia_nao_coletada"
                                 and m != "dependencia_nao_coletada"):
                    d["motivo_nao_coleta"] = m

        # A contagem de sinais AUSENTES e o que ordena a triagem: a etapa de
        # Monitoramento prioriza por ausencia de evidencia de transparencia, e
        # deixar o leitor somar colunas a mao seria transferir-lhe trabalho.
        for d in por_sitio.values():
            d.setdefault("extrapolacao", "false")
            # Ausencia de sinal conta apenas o que foi MEDIDO e deu falso. Somar
            # `nao_aplicavel` aqui confundiria "nao divulgou" com "nao foi medido",
            # e a ordenacao da triagem passaria a priorizar sitios sem politica.
            d["n_sinais_ausentes"] = sum(1 for v in variaveis if d.get(v) == "false")
            d["n_nao_aplicavel"] = sum(1 for v in variaveis
                                       if d.get(v) == NAO_APLICAVEL)
            # Taxa de alcance e parte do resultado. Sitio nao coletado que sumisse da
            # saida sairia do numerador e do denominador ao mesmo tempo, e a proporcao
            # resultante responderia a pergunta errada: prevalencia entre os alcancados,
            # e nao entre os amostrados.
            d["n_nao_coletado"] = sum(1 for v in variaveis
                                      if d.get(v) == NAO_COLETADO)
            d["motivo_nao_coleta"] = d.get("motivo_nao_coleta", "")
            d["n_variaveis_apuradas"] = sum(1 for v in variaveis
                                            if d.get(v) in ("true", "false"))

        com_contagem = sorted({v for d in por_sitio.values() for v in variaveis
                               if f"{v}__n_segmentos" in d})
        campos = (["ordem_triagem", "dominio", "n_sinais_ausentes",
                   "n_variaveis_apuradas", "n_nao_aplicavel", "n_nao_coletado",
                   "motivo_nao_coleta"]
                  + variaveis + [f"{v}__confianca" for v in variaveis]
                  + [c for v in com_contagem
                     for c in (f"{v}__n_sentencas", f"{v}__n_segmentos",
                               f"{v}__densidade")]
                  + ["extrapolacao", "domain_url", "run_id", "protocol_version"])
        linhas = sorted(por_sitio.values(), key=_prioridade)
        for i, d in enumerate(linhas, 1):
            d["ordem_triagem"] = i
        with alvo.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=campos, delimiter=";", restval="")
            w.writeheader()
            w.writerows(linhas)
        return alvo.resolve()


class CsvEvidencias(OutputRenderer):
    """Uma linha por sentenca sinalizada. Lista de trabalho da verificacao."""

    name: ClassVar[str] = "csv_evidencias"
    version: ClassVar[str] = "1.0.0"

    def render(self, store: ResultStore, params: dict[str, Any]) -> Path:
        R = coleta(store, params)
        alvo = destino(params, "data/results/evidencias.csv")
        campos = ["dominio", "variable_name", "posicao", "escore", "texto",
                  "limiar", "n_sentencas_sinalizadas", "sentencas_omitidas",
                  "extrapolacao", "modelo_sha256", "run_id"]
        with alvo.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=campos, delimiter=";", restval="",
                               quoting=csv.QUOTE_ALL)
            w.writeheader()
            for r in R:
                at = trilha(r)
                for s in sentencas(r):
                    w.writerow({
                        "dominio": dominio(r.domain_url),
                        "variable_name": r.variable_name,
                        "posicao": s.get("posicao"), "escore": s.get("escore"),
                        # A quebra de linha nao sobrevive a leitura por planilha;
                        # o preparo ja colapsa espaco, mas a guarda e barata.
                        "texto": " ".join(str(s.get("texto", "")).split()),
                        "limiar": at.get("limiar"),
                        "n_sentencas_sinalizadas": at.get("n_sentencas_sinalizadas"),
                        "sentencas_omitidas": at.get("sentencas_omitidas", 0),
                        "extrapolacao": "true" if at.get("extrapolacao") else "false",
                        "modelo_sha256": at.get("modelo_sha256", ""),
                        "run_id": r.run_id})
        return alvo.resolve()


class ParquetLongo(OutputRenderer):
    """Formato longo tipado, para reprocessamento analitico."""

    name: ClassVar[str] = "parquet"
    version: ClassVar[str] = "1.0.0"

    def render(self, store: ResultStore, params: dict[str, Any]) -> Path:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as e:                              # pragma: no cover
            raise RuntimeError(
                "o renderizador parquet exige pyarrow; instale com "
                "pip install -e . (pyarrow consta das dependencias do pacote)") from e
        R = coleta(store, params)
        alvo = destino(params, "data/results/resultados.parquet")
        linhas = [linha_plana(r) for r in R]
        campos = list(COLUNAS_BASE) + list(ESCALARES) + list(DERIVADAS)
        colunas = {c: [l.get(c, "") for l in linhas] for c in campos}

        # A tipagem e DECLARADA, nunca inferida. Colunas do registro de auditoria
        # so existem para as variaveis supervisionadas, de sorte que ficam vazias
        # nas demais; sob inferencia, o tipo passaria a depender de qual variavel
        # aparece primeiro, e o esquema do arquivo variaria entre execucoes.
        REAIS = ("confidence", "limiar", "cobertura_vocabulario",
                 "densidade_sinalizacao")
        INTEIROS = ("n_sentencas_sinalizadas", "n_segmentos_avaliados")

        def _real(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        def _inteiro(x):
            try:
                return int(float(x))
            except (TypeError, ValueError):
                return None

        arranjos = {}
        for c in campos:
            if c in REAIS:
                arranjos[c] = pa.array([_real(x) for x in colunas[c]], type=pa.float64())
            elif c in INTEIROS:
                arranjos[c] = pa.array([_inteiro(x) for x in colunas[c]], type=pa.int64())
            else:
                arranjos[c] = pa.array([None if x == "" else str(x) for x in colunas[c]],
                                       type=pa.string())
        pq.write_table(pa.table(arranjos), alvo)
        return alvo.resolve()


class JsonEvidencia(OutputRenderer):
    """Estrutura aninhada por sitio, com o registro de auditoria integro."""

    name: ClassVar[str] = "json"
    version: ClassVar[str] = "1.0.0"

    def render(self, store: ResultStore, params: dict[str, Any]) -> Path:
        R = coleta(store, params)
        alvo = destino(params, "data/results/resultados.json")

        sitios: dict[str, dict[str, Any]] = OrderedDict()
        modelos: dict[str, str] = {}
        for r in R:
            at = trilha(r)
            d = sitios.setdefault(dominio(r.domain_url),
                                  {"dominio": dominio(r.domain_url),
                                   "domain_url": r.domain_url, "variaveis": {}})
            d["variaveis"][r.variable_name] = {
                "valor": _estado(r.value),
                "confianca": round(float(r.confidence), 6),
                "densidade_sinalizacao": densidade(at),
                "plugin_version": r.plugin_version,
                "auditoria": at}
            if at.get("modelo_sha256"):
                modelos[r.variable_name] = at["modelo_sha256"]

        # O cabecalho reune, num lugar so, o que identifica a execucao inteira:
        # sem ele o leitor teria de percorrer todos os sitios para descobrir sob
        # que protocolo e com que modelos o conjunto foi produzido.
        cabecalho = {
            "run_id": R[0].run_id if R else None,
            "protocol_version": R[0].protocol_version if R else None,
            "n_sitios": len(sitios),
            "n_resultados": len(R),
            "modelos": modelos,
        }
        with alvo.open("w", encoding="utf-8") as fh:
            json.dump({"execucao": cabecalho, "sitios": list(sitios.values())},
                      fh, ensure_ascii=False, indent=2)
        return alvo.resolve()
