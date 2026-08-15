"""Preparo do texto de politica de privacidade, em seis etapas ordenadas.

Este modulo e a IMPLEMENTACAO CANONICA do procedimento descrito em
``docs/pipeline-segmentacao.md``. O programa de segmentacao que constroi o corpo
de treino o importa, e os plugins de classificacao o importam tambem: treino e
uso executam literalmente o mesmo codigo.

A inversao e deliberada. Enquanto o procedimento vivia no programa, o caminho de
inferencia teria de reimplementa-lo, e divergencia entre as duas implementacoes
nao se manifesta como falha — manifesta-se como queda de desempenho sem causa
aparente, porque o modelo recebe unidades de natureza distinta daquelas com que
aprendeu.

ETAPAS
------
1. Extracao em nivel de bloco a partir da marcacao de hipertexto.
2. Filtro de idioma, por subpagina.
3. Reconstrucao do texto extraido de PDF, que chega em linhas de diagramacao.
4. Divisao por sentenca, com guarda de abreviaturas.
5. Deduplicacao por sitio: de cada texto identico preserva-se uma ocorrencia.
6. Descarte de fragmento abaixo do comprimento minimo.

As etapas 5 e 6 nao alteram a lista de unidades: elas SELECIONAM indices. A
distincao importa porque a localizacao posicional de passagens transcritas, no
treino, exige o documento contiguo montado com a totalidade das unidades;
filtrar antes abriria lacunas.

PARAMETROS
----------
Os cinco parametros congelados foram fixados por inspecao e nao foram validados;
constituem limitacao declarada. O corte de repeticao, sexto parametro da
formulacao anterior e unico derivado do conjunto rotulado, deixou de existir com
a adocao da deduplicacao.

Nada aqui depende de conjunto de referencia externo: todas as etapas operam sobre
o documento sob analise, e por isso se aplicam sem alteracao a material novo.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable, Mapping, Sequence

__all__ = [
    "MIN_SEG", "MIN_IDIOMA", "RAZAO_IDIOMA", "REPET_PAGINA", "MAX_RECORRENTE",
    "PARAMETROS", "VERSAO_PREPARO",
    "Segmentacao", "segmenta", "indices_uteis",
    "extrai_blocos", "limpa", "normaliza", "em_portugues",
    "reconstroi_pdf", "divide_por_sentenca",
]

# ---------------------------------------------------------------- parametros
MIN_SEG = 20            # unidades menores sao fragmento de navegacao
MIN_IDIOMA = 400        # abaixo disso a deteccao de idioma nao e confiavel
RAZAO_IDIOMA = 1.4      # predominancia exigida para declarar outro idioma
REPET_PAGINA = 3        # ocorrencias que caracterizam cabecalho ou rodape de pagina
MAX_RECORRENTE = 150    # linha mais longa que isso nao e cabecalho, ainda que repita

PARAMETROS = {
    "MIN_SEG": MIN_SEG,
    "MIN_IDIOMA": MIN_IDIOMA,
    "RAZAO_IDIOMA": RAZAO_IDIOMA,
    "REPET_PAGINA": REPET_PAGINA,
    "MAX_RECORRENTE": MAX_RECORRENTE,
}

# Identifica o procedimento que produziu as unidades. Vai gravada no artefato de
# modelo e no registro de auditoria de cada resultado: preparo e coeficientes
# formam par, e trocar um sem o outro produz predicao plausivel e errada.
VERSAO_PREPARO = "1.0.0"

_MARCA = "\x01"   # limpa() ja removeu os caracteres de controle do texto, de modo
                  # que esta marca nao pode colidir com conteudo capturado
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

ABREVIACOES = ["art", "arts", "inc", "incs", "par", "cf", "ex", "pp", "pag", "pág",
               "fl", "fls", "cap", "caps", "sec", "seç", "ltda", "cia", "sr", "sra",
               "srs", "dr", "dra", "prof", "profa", "av", "etc", "vol", "ed", "org",
               "coord", "trad", "aprox", "obs", "ref", "min", "máx", "n", "no", "nº"]

# Vocabulos funcionais, cuja frequencia relativa identifica o idioma de forma
# robusta em texto longo, sem dependencia externa.
_VOC_EN = re.compile(r"\b(the|your|you|we|our|and|for|with|information|data|privacy|"
                     r"policy|personal|may|will|shall|that|this|which|use|are|is|to|of|"
                     r"in|on|by|from|any|such|these|been|have|has|does|do|not)\b", re.I)
_VOC_PT = re.compile(r"\b(o|a|os|as|de|da|do|dos|das|que|para|com|seu|sua|seus|suas|"
                     r"voc[êe]|n[óo]s|dados|informa[çc][õo]es|privacidade|pol[íi]tica|"
                     r"pode|podem|ser[áa]|em|ao|pelo|pela|nao|n[ãa]o|uma|um|seja)\b", re.I)

_MARCADOR_ITEM = re.compile(r"""^(?:
      \(\s*(?:[ivxlcdm]{1,5}|[a-zA-Z]|\d+)\s*\)     # (i)  (a)  (1)
    | [a-z]\)                                          # a)   b)
    | [a-z]\.                                          # a.   b.
    | \d+(?:\.\d+)*[.)]                                # 1.   2.3.   1.1)
    | [IVXLCDM]{1,5}\.                                 # I.   II.   IV.
    )(?:\s|$)""", re.X)


# ------------------------------------------------- etapa 1: extracao por bloco
class VisBloco(HTMLParser):
    """Texto visivel preservando fronteiras de bloco.

    Os elementos que o navegador renderiza como bloco encerram o trecho corrente.
    Sem isso, itens de lista consecutivos se fundem em segmento unico, e a
    enumeracao de direitos do artigo 18, tipicamente marcada em lista sem
    pontuacao final, perde as fronteiras.

    Os blocos sao acumulados em lista propria, e NUNCA delimitados por marcador
    inserido no texto: qualquer caractere escolhido como marcador pode ocorrer no
    conteudo capturado, e ao menos uma pagina da amostra traz byte nulo no texto.
    """

    # `html.parser` decide por si quais elementos tem conteudo de TEXTO PURO, e a
    # decisao variou entre versoes do CPython: as antigas comprehendem apenas
    # `script` e `style`; as recentes tambem `xmp`, `iframe`, `noembed` e
    # `noframes`. A diferenca e observavel no material coletado. Onde `iframe` e
    # tratado como texto puro, sua marcacao interna vira segmento — caso de
    # `<span class="fr-mk" style="display: none;">&nbsp;</span>`; onde nao e, a
    # marcacao e analisada como marcacao e apenas o texto interno comparece.
    #
    # Fixa-se o conjunto CLASSICO, que e o vigente quando o corpo de rotulagem foi
    # construido e marcado. A escolha e por compatibilidade com o material ja
    # julgado, e nao por merito: alterar o comportamento agora deslocaria os
    # segmentos sob os quais a marcacao exaustiva foi feita.
    #
    # Declarar o conjunto aqui e o que torna o preparo independente da versao
    # instalada. Sem isso, o mesmo material produz corpos distintos conforme o
    # ambiente, e o resumo criptografico do conjunto de treino deixa de
    # identificar coisa alguma.
    CDATA_CONTENT_ELEMENTS = ("script", "style")

    SKIP = {"script", "style", "noscript", "head", "svg", "path"}
    BLOCO = {"p", "div", "li", "br", "tr", "td", "th", "section", "article",
             "ul", "ol", "table", "blockquote", "dt", "dd", "form", "header",
             "footer", "nav", "main", "aside", "figure", "figcaption", "hr",
             "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.blocos: list[str] = []
        self._atual: list[str] = []
        self.skip = 0

    def _encerra(self):
        if self._atual:
            self.blocos.append(" ".join(self._atual))
            self._atual = []

    def handle_starttag(self, t, a):
        if t in self.SKIP:
            self.skip += 1
        if t in self.BLOCO:
            self._encerra()

    def handle_endtag(self, t):
        if t in self.SKIP and self.skip > 0:
            self.skip -= 1
        if t in self.BLOCO:
            self._encerra()

    def handle_data(self, d):
        if self.skip == 0:
            s = d.strip()
            if s:
                self._atual.append(s)

    def close(self):
        super().close()
        self._encerra()


def limpa(s: str) -> str:
    """Colapsa espaco em branco e remove caracteres de controle.

    Colapsa TODA a categoria de espaco em branco, quebra de linha inclusive. Em
    marcacao de hipertexto a quebra de linha no codigo-fonte e espaco em branco:
    apenas os elementos de bloco e a marca de quebra produzem separacao visual.
    Preserva-la equivaleria a tratar a indentacao do autor do sitio como estrutura
    do documento, e a divisao por sentenca converteria essa indentacao em fronteira
    de segmento. O defeito alcancava 2,9% dos blocos, em 33 de 70 sitios examinados.
    """
    return re.sub(r"\s+", " ", _CONTROLE.sub(" ", s)).strip()


def extrai_blocos(html_bytes: bytes) -> list[str]:
    """Blocos de texto visivel de uma subpagina. Nunca levanta."""
    p = VisBloco()
    try:
        p.feed(html_bytes.decode("utf-8", "ignore"))
        p.close()
    except Exception:
        pass
    return [x for x in (limpa(b) for b in p.blocos) if x]


def normaliza(s: str) -> str:
    """Forma de comparacao: sem acento, sem caixa, espaco colapsado."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).lower().strip()


# --------------------------------------------------- etapa 2: filtro de idioma
def em_portugues(texto: str) -> bool:
    """Decide se a subpagina esta em portugues.

    Conservadora por construcao: exige texto longo e predominancia nitida de
    vocabulo estrangeiro para excluir. Na duvida, preserva. Opera por SUBPAGINA,
    nunca por segmento: o segmento tem extensao mediana de algumas dezenas de
    caracteres, insuficiente para identificacao confiavel.
    """
    if len(texto) < MIN_IDIOMA:
        return True
    en, pt = len(_VOC_EN.findall(texto)), len(_VOC_PT.findall(texto))
    return not (en > pt * RAZAO_IDIOMA)


# ------------------------------------------------ etapa 3: reconstrucao de PDF
def reconstroi_pdf(linhas: Iterable[str]) -> list[str]:
    """Reconstitui periodos a partir das linhas de diagramacao do PDF.

    A extracao de PDF devolve as linhas onde a margem da pagina termina, e nao
    periodos: sem esta etapa, apenas 12% das unidades encerram em pontuacao.

    Tres operacoes, NESTA ORDEM. A supressao de linha recorrente precede a juncao
    porque, aplicada depois, o cabecalho ja teria aderido ao conteudo, tornando
    unica cada ocorrencia e escapando a deteccao.
    """
    linhas = list(linhas)
    ocorr = Counter(linhas)
    uteis = [l for l in linhas
             if ocorr[l] < REPET_PAGINA or len(l) > MAX_RECORRENTE]
    fim = re.compile(r"[.!?;]\s*$")
    saida, buf = [], ""
    for t in uteis:
        if buf and _MARCADOR_ITEM.match(t):
            saida.append(buf); buf = ""
        if buf:
            buf = buf[:-1] + t if buf.endswith("-") else buf + " " + t
        else:
            buf = t
        # marcador isolado nao encerra unidade: aguarda o conteudo que o segue
        if fim.search(buf) and not _MARCADOR_ITEM.fullmatch(buf.strip()):
            saida.append(buf); buf = ""
    if buf:
        saida.append(buf)
    return [x for x in (limpa(x) for x in saida) if x]


def linhas_de_pdf(texto: str) -> list[str]:
    """Linhas nao vazias do texto extraido de um PDF, prontas para reconstrucao."""
    return [l.strip() for l in (texto or "").split("\n") if l.strip()]


# --------------------------------------------- etapa 4: divisao por sentenca
def divide_por_sentenca(seg: str) -> list[str]:
    """Divide o bloco em sentencas.

    Protege previamente os pontos que nao encerram periodo — abreviaturas
    correntes em texto juridico, iniciais isoladas e separadores decimais —,
    substituindo-os por marca temporaria restituida ao final. Sem essa guarda, a
    fronteira quebra em "Ltda.", "Sr." e "etc.".

    Quando o bloco nao contem fronteira de sentenca — item de lista, titulo,
    celula de tabela —, o proprio bloco constitui a unidade. A regra e unica e
    dispensa limiar de comprimento.
    """
    prot = seg
    for a in ABREVIACOES:
        prot = re.sub(r"\b(" + re.escape(a) + r")\.", r"\1" + _MARCA, prot, flags=re.I)
    prot = re.sub(r"\b([A-ZÀ-Ú])\.", r"\1" + _MARCA, prot)      # inicial isolada
    prot = re.sub(r"(\d)\.(?=\d)", r"\1" + _MARCA, prot)        # 13.709, 1.1
    t = re.sub(r"(?<=[.!?;:])\s+(?=[A-ZÀ-Ú])", "\n", prot)
    t = re.sub(r"\s+(?=\d+(?:" + _MARCA + r"\d+)*[).]\s+[A-ZÀ-Ú])", "\n", t)
    # marcadores de item entre parenteses: (i), (ii), (a), (IV)
    t = re.sub(r"\s+(?=\((?:[IVXivx]{1,5}|[A-Za-z])\)\s)", "\n", t)
    return [x.replace(_MARCA, ".").strip() for x in t.split("\n") if x.strip()]


# ------------------------------------------ etapas 5 e 6: selecao de indices
def indices_uteis(unidades: Sequence[str]) -> list[int]:
    """Indices das unidades que sobrevivem a deduplicacao e ao comprimento minimo.

    Deduplicacao por sitio: de cada texto identico preserva-se a PRIMEIRA
    ocorrencia. A escolha da primeira e arbitraria e inconsequente — as unidades
    sao independentes e nao carregam contexto —, mas precisa ser declarada e
    determinista para que a reexecucao reproduza o conjunto.

    Devolve INDICES, e nao textos: o documento contiguo empregado para localizar
    passagens transcritas e montado com a totalidade das unidades, e filtrar antes
    abriria lacunas.
    """
    vistos: set[str] = set()
    saida: list[int] = []
    for i, u in enumerate(unidades):
        if len(u) < MIN_SEG:
            continue
        if u in vistos:
            continue
        vistos.add(u)
        saida.append(i)
    return saida


# ------------------------------------------------------------- orquestracao
@dataclass(frozen=True)
class Segmentacao:
    """Resultado do preparo de um documento.

    Attributes:
        unidades: todas as sentencas, na ordem, ANTES da selecao. E sobre esta
            lista que os indices de ``uteis`` se referem, e e com ela que se monta
            o documento contiguo.
        uteis: indices das unidades que sobrevivem a deduplicacao e ao
            comprimento minimo.
        blocos_integrais: blocos de todas as subpaginas, ANTES do filtro de
            idioma. A conferencia de fidelidade da extracao contra o pacote
            congelado emprega este conjunto, porque afere a extracao e nao as
            exclusoes deliberadas que a sucedem.
        subpaginas_removidas: chaves das subpaginas descartadas pelo filtro de
            idioma. Documento cujas subpaginas sejam todas estrangeiras resulta
            vazio, situacao que o consumidor deve reportar com status proprio e
            NAO confundir com ausencia de politica.
        versao_preparo: identifica o procedimento; vai para o registro de auditoria.
        parametros: valores congelados em vigor nesta execucao.
    """

    unidades: tuple[str, ...]
    uteis: tuple[int, ...]
    subpaginas_removidas: tuple[str, ...] = ()
    blocos_integrais: tuple[str, ...] = ()
    versao_preparo: str = VERSAO_PREPARO
    parametros: Mapping[str, float] = field(default_factory=lambda: dict(PARAMETROS))

    @property
    def segmentos(self) -> list[str]:
        """Unidades efetivamente submetidas ao classificador."""
        return [self.unidades[i] for i in self.uteis]

    def documento_contiguo(self) -> tuple[str, list[tuple[int, int] | None]]:
        """Documento normalizado e o intervalo de caracteres de cada unidade.

        Emprega a TOTALIDADE das unidades, inclusive as descartadas na selecao,
        de sorte que o texto permaneca contiguo e a correspondencia de trechos que
        atravessam uma unidade curta continue possivel.
        """
        partes: list[str] = []
        intervalos: list[tuple[int, int] | None] = [None] * len(self.unidades)
        pos = 0
        for i, seg in enumerate(self.unidades):
            ns = normaliza(seg)
            if not ns:
                continue
            if partes:
                pos += 1                       # separador
            intervalos[i] = (pos, pos + len(ns))
            partes.append(ns)
            pos += len(ns)
        return " ".join(partes), intervalos


def segmenta(paginas: Mapping[str, bytes] | None = None,
             textos_pdf: Sequence[str] = (),
             *, filtrar_idioma: bool = True) -> Segmentacao:
    """Aplica as seis etapas a um documento.

    Args:
        paginas: subpaginas em marcacao de hipertexto, chave -> bytes. A ordem do
            mapeamento e preservada e determina a ordem das unidades.
        textos_pdf: texto ja extraido de cada documento em PDF, um item por
            documento. A extracao a partir dos bytes e atribuicao da camada de
            coleta, que combina camada de texto e reconhecimento optico; aqui
            recebe-se o resultado dela.
        filtrar_idioma: quando falso, preserva subpaginas em outro idioma. Reservado
            a auditoria; a operacao normal filtra.

    Returns:
        Segmentacao. A pagina inicial NAO deve ser incluida em ``paginas``: as 267
        transcricoes de referencia localizam-se na secao de politica, e nenhuma
        ocorre exclusivamente na pagina inicial, de modo que segmenta-la
        acrescentaria apenas material de navegacao.
    """
    blocos: list[str] = []
    integrais: list[str] = []
    removidas: list[str] = []
    for chave, html in (paginas or {}).items():
        b = extrai_blocos(html)
        integrais.extend(b)
        if filtrar_idioma and not em_portugues(" ".join(b)):
            removidas.append(chave)
            continue
        blocos.extend(b)
    for texto in textos_pdf:
        blocos.extend(reconstroi_pdf(linhas_de_pdf(texto)))

    unidades: list[str] = []
    for b in blocos:
        unidades.extend(divide_por_sentenca(b))
    return Segmentacao(unidades=tuple(unidades),
                       uteis=tuple(indices_uteis(unidades)),
                       subpaginas_removidas=tuple(removidas),
                       blocos_integrais=tuple(integrais))
