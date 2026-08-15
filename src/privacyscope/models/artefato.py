"""Artefato de modelo: gravacao, leitura, conferencia e aplicacao.

POR QUE ESTE MODULO EXISTE
--------------------------
Um classificador ajustado e objeto de natureza distinta da configuracao de regra.
A configuracao externaliza conhecimento de dominio para que seja ajustavel a mao,
com auditoria; o artefato de modelo tambem e externalizado e versionado, mas NAO e
ajustavel: editar o vocabulario sem reajustar os coeficientes rompe o pareamento
entre os dois e produz predicao plausivel e errada, que nenhuma verificacao a
jusante acusa. O artefato se substitui como unidade, e a unidade tem identidade
criptografica propria.

POR QUE NAO `pickle` NEM `joblib`
---------------------------------
Tres razoes, e nenhuma delas e estilistica. A serializacao por `pickle` amarra o
artefato a versao da biblioteca que o gravou, de sorte que atualizar o ambiente
pode torna-lo ilegivel ou, pior, legivel com semantica alterada; executa codigo
arbitrario na leitura, o que e inaceitavel em arquivo que se pretende conferivel
por terceiro; e nao e inspecionavel, de modo que ninguem pode olhar o conteudo sem
executa-lo.

Adota-se formato de arranjos numericos com metadados em notacao de objetos. O
arquivo e um recipiente de dados, nao de codigo.

POR QUE A VETORIZACAO E PROPRIA
-------------------------------
A representacao esparsa e reconstituida aqui, e nao pela biblioteca de aprendizado
que a ajustou. A razao e a mesma que afasta `pickle`: a inferencia nao pode depender
da versao de uma biblioteca externa. O procedimento e curto, integralmente
especificado e verificavel — `tests_unit/test_artefato.py` confronta esta
implementacao com a da biblioteca sobre o corpo real e exige coincidencia.

O QUE O ARTEFATO CARREGA
------------------------
Alem dos coeficientes, tres conjuntos de metadados sem os quais ele nao cumpre a
funcao:

  PROVENIENCIA — resumo criptografico do conjunto de treino e versao do preparo de
  texto. O artefato nao carrega o corpo, e carrega a impressao digital dele: e o
  que permite verificar que dois artefatos vieram do mesmo material sem dispor do
  material. Preparo e coeficientes formam par; trocar um sem o outro e defeito
  silencioso.

  OPERACAO — o limiar de decisao, apurado em particao interna e nao arbitrado na
  inferencia.

  COBERTURA — distribuicao da fracao de termos conhecidos observada no treino. A
  lista de sitios de quem executa o arcabouco nao e a lista de treino; documento
  cuja cobertura fique muito abaixo da tipica esta em regiao de extrapolacao, e o
  resultado sai marcado em lugar de sair calado.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

__all__ = ["Artefato", "ArtefatoCanal", "ArtefatoCorrompido", "grava",
           "grava_canal", "le", "le_canal", "resumo_arquivo", "resumo_texto",
           "VERSAO_FORMATO"]

VERSAO_FORMATO = "1"

# Reproduz o padrao de tokenizacao da representacao esparsa empregada no ajuste:
# sequencias de dois ou mais caracteres de palavra. Vocabulos de uma letra sao
# descartados, conduta que a biblioteca de aprendizado adota por omissao e que aqui
# se declara.
_TOKEN = re.compile(r"(?u)\b\w\w+\b")


class ArtefatoCorrompido(RuntimeError):
    """Resumo criptografico do arquivo diverge do declarado.

    Interrompe a execucao deliberadamente. Prosseguir com artefato cuja identidade
    nao confere produziria resultados atribuidos a um modelo que nao foi o
    empregado, e a trilha de auditoria registraria informacao falsa.
    """


def resumo_arquivo(caminho: Path | str) -> str:
    """Resumo SHA-256 dos bytes do arquivo, em blocos."""
    h = hashlib.sha256()
    with Path(caminho).open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def resumo_texto(partes: Iterable[str]) -> str:
    """Resumo SHA-256 de uma sequencia de textos, com separador inequivoco.

    O separador e caractere que a limpeza do preparo remove do conteudo, de sorte
    que nao possa ocorrer dentro de uma parte e produzir colisao entre sequencias
    distintas.
    """
    h = hashlib.sha256()
    for p in partes:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


@dataclass(frozen=True)
class Artefato:
    """Modelo ajustado, com proveniencia e ponto de operacao.

    Attributes:
        variavel: nome da variavel tecnica que este artefato decide.
        vocabulario: termo -> indice de coluna.
        idf: peso documental de cada coluna.
        coeficientes: peso de cada coluna no escore.
        intercepto: termo constante do escore.
        limiar: probabilidade a partir da qual a sentenca e sinalizada.
        regularizacao: forca da regularizacao empregada no ajuste. Nao participa da
            inferencia; e proveniencia, e permite reproduzir o ajuste de origem.
        ngramas: extensao minima e maxima das sequencias de vocabulos.
        minusculas: se o texto e minusculizado antes da tokenizacao.
        sublinear_tf: se a frequencia recebe escalonamento logaritmico.
        preparo_versao: versao do preparo de texto que produziu o treino.
        preparo_parametros: parametros congelados daquele preparo.
        corpo_sha256: resumo do conjunto de treino.
        cobertura_treino: quantis da fracao de termos conhecidos no treino.
        ajustado_em: instante do ajuste, em tempo universal coordenado.
        gerado_por: programa que produziu o artefato.
        sha256: resumo do arquivo de origem; preenchido na leitura.
    """

    variavel: str
    vocabulario: Mapping[str, int]
    idf: np.ndarray
    coeficientes: np.ndarray
    intercepto: float
    limiar: float
    regularizacao: float = 0.0
    ngramas: tuple[int, int] = (1, 3)
    minusculas: bool = True
    sublinear_tf: bool = True
    preparo_versao: str = ""
    preparo_parametros: Mapping[str, float] = None  # type: ignore[assignment]
    corpo_sha256: str = ""
    cobertura_treino: Mapping[str, float] = None    # type: ignore[assignment]
    ajustado_em: str = ""
    gerado_por: str = ""
    sha256: str = ""

    # ------------------------------------------------------------- vetorizacao
    def termos(self, texto: str) -> list[str]:
        """Sequencias de vocabulos extraidas do texto, com repeticao."""
        if self.minusculas:
            texto = texto.lower()
        toks = _TOKEN.findall(texto)
        n_min, n_max = self.ngramas
        saida: list[str] = []
        if n_min <= 1 <= n_max:
            saida.extend(toks)
        for n in range(max(n_min, 2), n_max + 1):
            saida.extend(" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1))
        return saida

    def cobertura(self, texto: str) -> float:
        """Fracao das sequencias do texto presentes no vocabulario do treino.

        Mede a distancia entre o material sob analise e aquele com que o modelo
        aprendeu. Documento muito abaixo da cobertura tipica esta em extrapolacao,
        e o resultado deve sair marcado.
        """
        t = self.termos(texto)
        if not t:
            return 0.0
        return sum(1 for x in t if x in self.vocabulario) / len(t)

    def vetoriza(self, textos: Sequence[str]) -> np.ndarray:
        """Matriz densa de frequencia ponderada, normalizada por linha.

        Densa por escolha: a inferencia opera sobre dezenas a centenas de sentencas
        por sitio, e a economia da representacao esparsa nao compensa a dependencia
        adicional. Para conjuntos maiores, o escore por lote resolve.
        """
        n_col = len(self.idf)
        X = np.zeros((len(textos), n_col), dtype=np.float64)
        for i, texto in enumerate(textos):
            contagem: dict[int, int] = {}
            for termo in self.termos(texto):
                j = self.vocabulario.get(termo)
                if j is not None:
                    contagem[j] = contagem.get(j, 0) + 1
            for j, c in contagem.items():
                tf = 1.0 + math.log(c) if self.sublinear_tf else float(c)
                X[i, j] = tf * self.idf[j]
            norma = math.sqrt(float(np.dot(X[i], X[i])))
            if norma > 0:
                X[i] /= norma
        return X

    # ---------------------------------------------------------------- decisao
    def probabilidades(self, textos: Sequence[str]) -> np.ndarray:
        """Probabilidade da classe positiva para cada texto."""
        if not len(textos):
            return np.zeros(0, dtype=np.float64)
        eta = self.vetoriza(textos) @ self.coeficientes + self.intercepto
        return _sigmoide(eta)

    def decide(self, textos: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
        """Probabilidades e decisao binaria sob o limiar do artefato."""
        p = self.probabilidades(textos)
        return p, (p >= self.limiar)

    # ------------------------------------------------------------- descricao
    def descricao(self) -> dict:
        """Metadados para o registro de auditoria de cada resultado."""
        return {
            "variavel": self.variavel,
            "modelo_sha256": self.sha256,
            "preparo_versao": self.preparo_versao,
            "corpo_sha256": self.corpo_sha256,
            "limiar": self.limiar,
            "regularizacao": self.regularizacao,
            "n_atributos": int(len(self.idf)),
            "ajustado_em": self.ajustado_em,
        }

    def em_extrapolacao(self, cobertura: float) -> bool:
        """Cobertura abaixo do quantil inferior observado no treino."""
        piso = (self.cobertura_treino or {}).get("p05")
        return piso is not None and cobertura < piso


def _sigmoide(eta: np.ndarray) -> np.ndarray:
    """Estavel nos dois ramos: `exp` de argumento positivo grande transborda."""
    eta = np.asarray(eta, dtype=float)
    saida = np.empty_like(eta)
    pos = eta >= 0
    saida[pos] = 1.0 / (1.0 + np.exp(-eta[pos]))
    e = np.exp(eta[~pos])
    saida[~pos] = e / (1.0 + e)
    return saida


def grava(caminho: Path | str, *, variavel: str, vocabulario: Mapping[str, int],
          idf: Sequence[float], coeficientes: Sequence[float], intercepto: float,
          limiar: float, regularizacao: float = 0.0,
          ngramas: tuple[int, int] = (1, 3),
          minusculas: bool = True, sublinear_tf: bool = True,
          preparo_versao: str = "", preparo_parametros: Mapping | None = None,
          corpo_sha256: str = "", cobertura_treino: Mapping | None = None,
          gerado_por: str = "") -> str:
    """Grava o artefato e devolve o resumo criptografico do arquivo.

    O vocabulario e gravado como sequencia ordenada pelo indice de coluna, e nao
    como mapeamento: a ordem e o proprio indice, e grava-la explicitamente evita
    que a leitura dependa da ordem de iteracao de um dicionario.
    """
    idf = np.asarray(idf, dtype=np.float64)
    coeficientes = np.asarray(coeficientes, dtype=np.float64)
    if not (len(idf) == len(coeficientes) == len(vocabulario)):
        raise ValueError(f"dimensoes incompativeis: vocabulario {len(vocabulario)}, "
                         f"idf {len(idf)}, coeficientes {len(coeficientes)}")
    # A validacao PRECEDE a montagem: indice fora do intervalo levantaria erro de
    # atribuicao, cuja mensagem nao diz o que esta errado nem como corrigir.
    indices = sorted(vocabulario.values())
    if indices != list(range(len(vocabulario))):
        faltando = sorted(set(range(len(vocabulario))) - set(indices))[:5]
        raise ValueError(
            f"indices do vocabulario nao formam intervalo contiguo de 0 a "
            f"{len(vocabulario) - 1}; ausentes, entre outros: {faltando}")
    termos = [""] * len(vocabulario)
    for termo, j in vocabulario.items():
        termos[j] = termo

    meta = {
        "versao_formato": VERSAO_FORMATO,
        "tipo": "texto_esparso",
        "variavel": variavel,
        "intercepto": float(intercepto),
        "limiar": float(limiar),
        "regularizacao": float(regularizacao),
        "ngramas": list(ngramas),
        "minusculas": bool(minusculas),
        "sublinear_tf": bool(sublinear_tf),
        "preparo_versao": preparo_versao,
        "preparo_parametros": dict(preparo_parametros or {}),
        "corpo_sha256": corpo_sha256,
        "cobertura_treino": dict(cobertura_treino or {}),
        "ajustado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gerado_por": gerado_por,
    }
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        caminho,
        metadados=np.array(json.dumps(meta, ensure_ascii=False, sort_keys=True)),
        termos=np.array(termos, dtype=object),
        idf=idf, coeficientes=coeficientes)
    return resumo_arquivo(caminho)


def le(caminho: Path | str, sha256_esperado: str | None = None) -> Artefato:
    """Le o artefato e confere a identidade quando ela e declarada.

    A conferencia precede a leitura do conteudo. Artefato cuja identidade nao
    confere nao e lido pela metade: a execucao para.
    """
    caminho = Path(caminho)
    sha = resumo_arquivo(caminho)
    if sha256_esperado and sha != sha256_esperado:
        raise ArtefatoCorrompido(
            f"o artefato {caminho.name} nao corresponde ao declarado.\n"
            f"  declarado no protocolo: {sha256_esperado}\n"
            f"  encontrado no arquivo : {sha}\n"
            f"Substitua o artefato ou atualize o protocolo — o arcabouco nao "
            f"prossegue com modelo de identidade incerta.")

    # O tipo e conferido ANTES dos arranjos: ler primeiro produziria erro de chave
    # ausente, cuja mensagem nao diz que o artefato e de outra especie.
    with np.load(caminho, allow_pickle=True) as z:
        meta = json.loads(str(z["metadados"]))
        # Artefatos gravados antes da distincao de tipo nao trazem o campo; a
        # ausencia significa representacao esparsa, entao o unico tipo existente.
        if meta.get("tipo", "texto_esparso") != "texto_esparso":
            raise ArtefatoCorrompido(
                f"o artefato e do tipo {meta.get('tipo')!r}; este leitor espera "
                f"'texto_esparso'. Artefato trocado no protocolo.")
        termos = [str(t) for t in z["termos"]]
        idf = np.asarray(z["idf"], dtype=np.float64)
        coef = np.asarray(z["coeficientes"], dtype=np.float64)
    if meta.get("versao_formato") != VERSAO_FORMATO:
        raise ArtefatoCorrompido(
            f"versao de formato {meta.get('versao_formato')!r} desconhecida; "
            f"esta implementacao le a versao {VERSAO_FORMATO!r}")

    return Artefato(
        variavel=meta["variavel"],
        vocabulario={t: j for j, t in enumerate(termos)},
        idf=idf, coeficientes=coef,
        intercepto=float(meta["intercepto"]), limiar=float(meta["limiar"]),
        regularizacao=float(meta.get("regularizacao", 0.0)),
        ngramas=tuple(meta.get("ngramas", (1, 3))),
        minusculas=bool(meta.get("minusculas", True)),
        sublinear_tf=bool(meta.get("sublinear_tf", True)),
        preparo_versao=meta.get("preparo_versao", ""),
        preparo_parametros=meta.get("preparo_parametros", {}),
        corpo_sha256=meta.get("corpo_sha256", ""),
        cobertura_treino=meta.get("cobertura_treino", {}),
        ajustado_em=meta.get("ajustado_em", ""),
        gerado_por=meta.get("gerado_por", ""),
        sha256=sha)


# ===========================================================================
# Modelo sobre atributos estruturados — o classificador do canal do titular
# ===========================================================================
@dataclass(frozen=True)
class ArtefatoCanal:
    """Estimador sobre atributos binarios, ajustado por verossimilhanca penalizada.

    Difere do artefato de representacao esparsa em natureza, e nao apenas em
    tamanho: nao ha vocabulario nem ponderacao documental, e a entrada e um
    conjunto nomeado de atributos extraidos por procedimento proprio. O que se
    conserva e o essencial — identidade criptografica, proveniencia e ausencia de
    objeto serializado.

    A ORDEM DOS ATRIBUTOS E O RISCO PRINCIPAL. Coeficientes atribuidos a colunas
    trocadas produzem probabilidade plausivel e errada, e nenhuma verificacao a
    jusante acusa. Por isso a inferencia nao recebe vetor: recebe um MAPEAMENTO
    nome -> valor, e a ordenacao e feita aqui, contra os nomes gravados.
    """

    variavel: str
    atributos: tuple[str, ...]
    coeficientes: np.ndarray
    intercepto: float
    limiar: float = 0.5
    extrator_versao: str = ""
    extrator_parametros: Mapping[str, float] = None   # type: ignore[assignment]
    corpo_sha256: str = ""
    n_observacoes: int = 0
    ajustado_em: str = ""
    gerado_por: str = ""
    sha256: str = ""

    def vetoriza(self, atributos: Mapping[str, float]) -> np.ndarray:
        """Ordena os atributos conforme os nomes gravados, e recusa o que faltar."""
        faltando = [a for a in self.atributos if a not in atributos]
        if faltando:
            raise ValueError(
                f"atributos ausentes para {self.variavel}: {faltando}. O extrator "
                f"e o artefato precisam ser da mesma versao.")
        return np.array([float(atributos[a]) for a in self.atributos], dtype=float)

    def probabilidade(self, atributos: Mapping[str, float]) -> float:
        eta = float(np.dot(self.vetoriza(atributos), self.coeficientes) + self.intercepto)
        return float(_sigmoide(np.array([eta]))[0])

    def decide(self, atributos: Mapping[str, float]) -> tuple[float, bool]:
        p = self.probabilidade(atributos)
        return p, p >= self.limiar

    def descricao(self) -> dict:
        return {"variavel": self.variavel, "modelo_sha256": self.sha256,
                "extrator_versao": self.extrator_versao,
                "corpo_sha256": self.corpo_sha256, "limiar": self.limiar,
                "n_atributos": len(self.atributos),
                "n_observacoes": self.n_observacoes,
                "ajustado_em": self.ajustado_em}


def grava_canal(caminho: Path | str, *, variavel: str, atributos: Sequence[str],
                coeficientes: Sequence[float], intercepto: float,
                limiar: float = 0.5, extrator_versao: str = "",
                extrator_parametros: Mapping | None = None,
                corpo_sha256: str = "", n_observacoes: int = 0,
                gerado_por: str = "") -> str:
    coeficientes = np.asarray(coeficientes, dtype=np.float64)
    if len(atributos) != len(coeficientes):
        raise ValueError(f"dimensoes incompativeis: {len(atributos)} atributos, "
                         f"{len(coeficientes)} coeficientes")
    if len(set(atributos)) != len(atributos):
        raise ValueError("nomes de atributo repetidos; a ordenacao ficaria ambigua")
    meta = {
        "versao_formato": VERSAO_FORMATO,
        "tipo": "canal_estruturado",
        "variavel": variavel,
        "intercepto": float(intercepto),
        "limiar": float(limiar),
        "extrator_versao": extrator_versao,
        "extrator_parametros": dict(extrator_parametros or {}),
        "corpo_sha256": corpo_sha256,
        "n_observacoes": int(n_observacoes),
        "ajustado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gerado_por": gerado_por,
    }
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        caminho,
        metadados=np.array(json.dumps(meta, ensure_ascii=False, sort_keys=True)),
        atributos=np.array(list(atributos), dtype=object),
        coeficientes=coeficientes)
    return resumo_arquivo(caminho)


def le_canal(caminho: Path | str, sha256_esperado: str | None = None) -> ArtefatoCanal:
    caminho = Path(caminho)
    sha = resumo_arquivo(caminho)
    if sha256_esperado and sha != sha256_esperado:
        raise ArtefatoCorrompido(
            f"o artefato {caminho.name} nao corresponde ao declarado.\n"
            f"  declarado no protocolo: {sha256_esperado}\n"
            f"  encontrado no arquivo : {sha}\n"
            f"Substitua o artefato ou atualize o protocolo — o arcabouco nao "
            f"prossegue com modelo de identidade incerta.")
    with np.load(caminho, allow_pickle=True) as z:
        meta = json.loads(str(z["metadados"]))
        if meta.get("tipo") != "canal_estruturado":
            raise ArtefatoCorrompido(
                f"o artefato e do tipo {meta.get('tipo', 'texto_esparso')!r}; este "
                f"leitor espera 'canal_estruturado'. Artefato trocado no protocolo.")
        atributos = tuple(str(a) for a in z["atributos"])
        coef = np.asarray(z["coeficientes"], dtype=np.float64)
    return ArtefatoCanal(
        variavel=meta["variavel"], atributos=atributos, coeficientes=coef,
        intercepto=float(meta["intercepto"]), limiar=float(meta["limiar"]),
        extrator_versao=meta.get("extrator_versao", ""),
        extrator_parametros=meta.get("extrator_parametros", {}),
        corpo_sha256=meta.get("corpo_sha256", ""),
        n_observacoes=int(meta.get("n_observacoes", 0)),
        ajustado_em=meta.get("ajustado_em", ""),
        gerado_por=meta.get("gerado_por", ""), sha256=sha)
