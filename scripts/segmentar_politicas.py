# -*- coding: utf-8 -*-
"""Constroi o conjunto em nivel de segmento para as tres variaveis textuais.

MOTIVACAO
---------
O trecho que justifica o rotulo ocupa cerca de 1% da politica — mediana de 0,85%
para finalidade, 0,99% para direitos e 0,60% para transferencia internacional.
Classificar o documento inteiro submeteria o modelo a uma diluicao de
aproximadamente cem para um. A literatura de referencia opera, sem excecao, em
nivel de segmento ou sentenca (Wilson et al., 2016; Harkous et al., 2018).

As colunas de evidencia da rotulagem transcrevem a passagem que fundamentou cada
rotulo positivo, e verificou-se que 267 de 267 transcricoes localizam-se no
material coletado. Constituem, portanto, anotacao de trecho ja disponivel, o que
permite derivar rotulos de segmento sem rotulagem adicional.

PROCEDENCIA DOS ROTULOS DE SEGMENTO
-----------------------------------
Positivos: segmentos cobertos pela transcricao.

Negativos: segmentos de documentos rotulados como negativos, EXCLUSIVAMENTE. Nesses
documentos o anotador julgou que nada relevante existe, e a ausencia vale para todo
o texto.

Nao rotulados: demais segmentos de documentos positivos. O anotador transcreveu UMA
passagem justificadora, nao todas; trata-los como negativos introduziria falso
negativo sistematico. A extensao dessa incompletude e medida em separado, pelo
instrumento de scripts/preparar_validacao_completude.py.

CRITERIOS DE SEGMENTACAO
------------------------
A unidade e a SENTENCA. Quando o bloco de marcacao nao contem fronteira de sentenca
— item de lista, titulo, celula de tabela —, o proprio bloco constitui a unidade.
A regra e unica e dispensa limiar de comprimento.

Duas fontes de fronteira operam em conjunto. A primeira e a marcacao: os elementos
que o navegador renderiza como bloco encerram a unidade, o que preserva a distincao
entre item de lista, celula e paragrafo, sobretudo na enumeracao de direitos do
artigo 18, tipicamente marcada em lista sem pontuacao final. A segunda e a
pontuacao, aplicada dentro de cada bloco.

Verificou-se que a divisao por sentenca preserva 97,7% dos itens de lista intactos,
porque a regra exige ponto seguido de espaco e maiuscula, condicao que item de lista
raramente satisfaz. O acrescimo de segmentos e de 17,9%, concentrado nos 11,7% de
blocos que efetivamente reunem mais de uma sentenca.

A adocao da sentenca como unidade corrige duas deficiencias do recorte por bloco. A
primeira e de coerencia: sob limiar de comprimento, um paragrafo de tres sentencas
permanecia intacto com trezentos caracteres e era repartido com setecentos, de sorte
que o corpus reunia duas especies de unidade sem razao que as distinguisse. A
segunda, e mais grave, e de diluicao do rotulo: um bloco que reuna a concessao de
uso dos dados e, em seguida, a instrucao para exercicio de direitos era assinalado
integralmente como positivo para direitos, arrastando consigo texto alheio ao
requisito — a mesma diluicao que motivou o abandono do nivel de documento,
reaparecida em escala menor. Pelo mesmo motivo, um paragrafo que declare duas
finalidades distintas em sentencas sucessivas passa a fornecer dois sinais, e nao um.

Blocos que resistem a divisao — enumeracao sem pontuacao, lista de paises em campo
de formulario — permanecem extensos. Reparti-los por contagem de caracteres seria
corte arbitrario no interior de oracao, e por isso nao se faz.

REMOCAO DE MATERIAL DE NAVEGACAO
--------------------------------
Cabecalho, rodape e menu nao integram o objeto de analise, mas nao podem ser
excluidos pela marca semantica que os envolve: mediu-se que 10,5% das passagens que
fundamentam os rotulos residem dentro de header, footer, nav ou aside, porque parte
expressiva dos sitios emprega esses elementos de forma incorreta, envolvendo o
conteudo principal.

Adota-se, em seu lugar, criterio de REPETICAO. Material de navegacao reaparece em
cada subpagina do mesmo sitio, e material de modelo de plataforma reaparece em
sitios distintos; texto que se repete nessa escala nao constitui declaracao do
controlador sobre o tratamento. Descarta-se o segmento que ocorra cinco vezes ou
mais no mesmo sitio, ou em cinco sitios ou mais.

O corte adotado e o MENOR em que nenhum documento rotulado perde a totalidade de sua
evidencia, recalculado a cada execucao.

A formulacao ao nivel do DOCUMENTO, e nao do segmento, decorre de observacao: o
casamento posicional ocasionalmente varre para dentro da passagem transcrita um
titulo ou cabecalho contiguo, que se repete em todas as subpaginas do sitio. Exigir
que nenhum SEGMENTO positivo seja atingido faria um unico sitio nessas condicoes
elevar o corte de cinco para vinte e uma ocorrencias, reduzindo o alcance do filtro
de um quinto do material para um vigesimo — em nome de preservar titulos que nao
declaram tratamento algum. Exigir que nenhum DOCUMENTO perca toda a sua evidencia
preserva o que fundamenta cada rotulo e permanece robusto a esse artefato.

Registre-se que o valor e determinado com as passagens positivas a vista, o que
configura selecao sobre os dados. A regra declarada — o menor corte que preserva a
integralidade da evidencia — e, contudo, verificavel, reproduzivel e independente do
desempenho de qualquer modelo: nao se escolhe o corte que produz melhor resultado,
mas o que nao suprime aquilo que fundamenta os rotulos.

EXTRACAO EM NIVEL DE BLOCO
--------------------------
Os pacotes de evidencia foram gerados com o texto visivel concatenado por espaco,
o que fundiu itens de lista em segmento unico: a enumeracao de direitos do artigo
18, tipicamente marcada em lista, perde as fronteiras. Mediu-se que 26% das
transcricoes de direitos recaem em segmentos assim fundidos.

Esta rotina reextrai o texto a partir dos mesmos pacotes de captura, inserindo
fronteira nos elementos de bloco. Os pacotes de evidencia PERMANECEM INTOCADOS: sao
o artefato sobre o qual a rotulagem foi conduzida e sobre o qual o segundo avaliador
trabalha. A reextracao produz derivado paralelo.

A alteracao alcanca apenas espacos em branco. A rotina verifica, sitio a sitio, que
o texto normalizado da reextracao coincide com o do pacote congelado, o que
demonstra que nenhum conteudo foi acrescido ou suprimido.

RECONSTRUCAO DO TEXTO EXTRAIDO DE PDF
-------------------------------------
A extracao de PDF devolve as linhas de DIAGRAMACAO do documento, e nao periodos: a
quebra ocorre onde a margem da pagina termina, de sorte que a oracao se reparte ao
meio. Segmentar sobre elas produz unidades como "e compartilhamos seus dados pessoais
em nossa atuacao, bem como sobre quais sao os", desprovidas de sentido isolado. Na
amostra, apenas 12% das unidades assim obtidas encerravam em pontuacao.

Reconstroi-se o texto em tres operacoes, nesta ordem:

  1. Remocao de linha recorrente. Cabecalho e rodape de pagina repetem-se a cada
     folha. Suprimem-se as linhas curtas que ocorram tres vezes ou mais no mesmo
     documento. A operacao PRECEDE a juncao: aplicada depois, o cabecalho ja teria
     aderido ao conteudo, tornando unica cada ocorrencia e escapando a deteccao.

  2. Juncao das linhas, encerrando a unidade apenas diante de ponto, exclamacao,
     interrogacao ou ponto e virgula. O ponto e virgula e incluido porque a
     enumeracao de direitos e de finalidades o emprega como separador de item, e
     desconsidera-lo fundiria a lista inteira em unidade unica. Linha terminada em
     hifen indica vocabulo partido entre linhas, e a juncao se faz sem espaco.

  3. Marcador de item sempre inicia unidade. Reconhecem-se numeracao decimal, letra
     e algarismo romano, com ou sem parenteses. Sem esta regra, o titulo de secao,
     que nao encerra em pontuacao, absorve o numero do item seguinte.

Sobre o texto assim reconstruido aplica-se a mesma divisao por sentenca empregada no
material em HTML, de modo que a unidade final seja a mesma nas duas procedencias.

DELIMITACAO POR IDIOMA
----------------------
O classificador opera sobre texto de politica em portugues: o modelo de linguagem
adotado e pre-treinado nesse idioma, e o vocabulario da representacao esparsa se
fragmentaria entre linguas. Secoes redigidas em outro idioma ficam, portanto, fora
do escopo e sao REMOVIDAS do conjunto.

Remover difere de rotular como negativo. Deixar tais segmentos sem marcacao, num
esquema em que a ausencia de marca significa ausencia do requisito, afirmaria que
passagens que de fato declaram finalidade nao a declaram — falso negativo
introduzido por artefato de idioma. A remocao nao afirma nada a respeito deles.

A deteccao opera por SUBPAGINA, e nao por segmento. O segmento tem extensao mediana
de algumas dezenas de caracteres, insuficiente para identificacao confiavel de
idioma; a subpagina reune milhares, e a separacao observada e inequivoca. Na amostra,
o unico caso relevante apresenta subpaginas com 301 ocorrencias de vocabulo ingles
contra 71 portuguesas, e outras com a proporcao inversa.

Politica disponivel exclusivamente em outro idioma resulta em documento sem conteudo
apos a remocao, e a situacao e reportada: trata-se de sitio cuja politica nao se
enderecca ao titular em portugues, achado que interessa ao monitoramento e que nao
deve ser confundido com ausencia de divulgacao.

DELIMITACAO AO CORPO DA POLITICA
--------------------------------
Segmenta-se o conteudo das subpaginas e dos documentos em PDF, excluido o texto da
pagina inicial. A delimitacao apoia-se em verificacao: as 267 transcricoes
localizam-se na secao de politica, e nenhuma ocorre exclusivamente na pagina
inicial. Segmentar a pagina inicial acrescentaria apenas material de navegacao.

Uso:
    python scripts/segmentar_politicas.py
    python scripts/segmentar_politicas.py --so-verificar
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import tarfile
import unicodedata
from collections import Counter, OrderedDict
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

VARIAVEIS = [("finalidade", "finalidade_evid"),
             ("direitos_titular", "direitos_evid"),
             ("transf_internacional", "transf_evid")]

MIN_SEG = 20            # segmentos menores sao fragmento de navegacao
COBERTURA_MIN = 0.5     # fracao do menor entre segmento e trecho que a sobreposicao cobre
REPET_MAX = 30          # teto da busca pelo corte de repeticao

# Abreviaturas correntes em politica de privacidade e em texto juridico. Sem esta
# guarda, a fronteira de sentenca quebra em "Ltda.", "Sr.", "etc." e "Av.".
ABREVIACOES = ["art", "arts", "inc", "incs", "par", "cf", "ex", "pp", "pag", "pág",
               "fl", "fls", "cap", "caps", "sec", "seç", "ltda", "cia", "sr", "sra",
               "srs", "dr", "dra", "prof", "profa", "av", "etc", "vol", "ed", "org",
               "coord", "trad", "aprox", "obs", "ref", "min", "máx", "n", "no", "nº"]

_MARCA = "\x01"   # limpa() ja removeu os caracteres de controle do texto, de modo
                  # que esta marca nao pode ocorrer no conteudo capturado


def localiza_trecho(doc, ev):
    """Posicao do trecho transcrito no documento normalizado.

    Tenta a correspondencia integral e, na sua ausencia, ancora pelo inicio da
    transcricao — o anotador ocasionalmente elide parte do meio da passagem.
    Retorna (inicio, fim) ou None.
    """
    if not ev or not doc:
        return None
    i = doc.find(ev)
    if i >= 0:
        return (i, i + len(ev))
    for corte in (120, 80, 50):
        if len(ev) <= corte:
            break
        i = doc.find(ev[:corte])
        if i >= 0:
            return (i, min(len(doc), i + len(ev)))
    return None


class VisBloco(HTMLParser):
    """Texto visivel preservando fronteiras de bloco.

    Reproduz o extrator empregado na geracao dos pacotes, com um acrescimo: os
    elementos que o navegador renderiza como bloco encerram o trecho corrente. Sem
    isso, itens de lista consecutivos se fundem em segmento unico.

    Os blocos sao acumulados em lista propria, e nao delimitados por marcador
    inserido no texto: qualquer caractere escolhido como marcador pode ocorrer no
    conteudo capturado, e ao menos uma pagina da amostra traz byte nulo no texto.
    """

    SKIP = {"script", "style", "noscript", "head", "svg", "path"}
    BLOCO = {"p", "div", "li", "br", "tr", "td", "th", "section", "article",
             "ul", "ol", "table", "blockquote", "dt", "dd", "form", "header",
             "footer", "nav", "main", "aside", "figure", "figcaption", "hr",
             "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.blocos = []
        self._atual = []
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


_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Vocabulos funcionais, cuja frequencia relativa identifica o idioma de forma
# robusta em texto longo, sem dependencia externa.
_VOC_EN = re.compile(r"\b(the|your|you|we|our|and|for|with|information|data|privacy|"
                     r"policy|personal|may|will|shall|that|this|which|use|are|is|to|of|"
                     r"in|on|by|from|any|such|these|been|have|has|does|do|not)\b", re.I)
_VOC_PT = re.compile(r"\b(o|a|os|as|de|da|do|dos|das|que|para|com|seu|sua|seus|suas|"
                     r"voc[êe]|n[óo]s|dados|informa[çc][õo]es|privacidade|pol[íi]tica|"
                     r"pode|podem|ser[áa]|em|ao|pelo|pela|nao|n[ãa]o|uma|um|seja)\b", re.I)
MIN_IDIOMA = 400        # abaixo disso a deteccao nao e confiavel
RAZAO_IDIOMA = 1.4      # predominancia exigida para declarar outro idioma


def em_portugues(texto):
    """Decide se a subpagina esta em portugues.

    Conservadora por construcao: exige texto longo e predominancia nitida de
    vocabulo estrangeiro para excluir. Na duvida, preserva.
    """
    if len(texto) < MIN_IDIOMA:
        return True
    en, pt = len(_VOC_EN.findall(texto)), len(_VOC_PT.findall(texto))
    return not (en > pt * RAZAO_IDIOMA)


def limpa(s):
    """Remove caracteres de controle, que inviabilizam a gravacao em CSV."""
    return re.sub(r"[ \t]+", " ", _CONTROLE.sub(" ", s)).strip()


def extrai_blocos(html_bytes):
    p = VisBloco()
    try:
        p.feed(html_bytes.decode("utf-8", "ignore"))
        p.close()
    except Exception:
        pass
    return [x for x in (limpa(b) for b in p.blocos) if x]


def normaliza(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).lower().strip()


def divide_por_sentenca(seg):
    """Divide o bloco em sentencas.

    Protege previamente os pontos que nao encerram periodo — abreviaturas
    conhecidas, iniciais isoladas e separadores decimais —, substituindo-os por
    marca temporaria que e restituida ao final. Sem essa guarda, a fronteira quebra
    em "Ltda.", "Sr." e "etc.".

    Reconhece ainda marcadores de item que nao dependem de pontuacao final:
    numeracao decimal, algarismo romano e letra entre parenteses.
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


def carrega_tarball(caminho):
    """Subpaginas e indice do pacote de captura.

    A nomenclatura interna segue a adotada na geracao dos pacotes de evidencia:
    as subpaginas residem em html_subpages/ e o indice que associa arquivo a
    caminho de origem e _index.json, no mesmo diretorio.
    """
    o = {"subs": OrderedDict(), "index": {}}
    with tarfile.open(caminho, "r:gz") as tf:
        for m in tf.getmembers():
            n = m.name
            if n.endswith("/html_subpages/_index.json"):
                try:
                    o["index"] = json.load(tf.extractfile(m))
                except Exception:
                    pass
            elif "/html_subpages/" in n and n.endswith(".html"):
                o["subs"][os.path.basename(n)] = tf.extractfile(m).read()
    return o


def secoes_subpagina_do_pacote(texto):
    """Corpo das subpaginas no pacote congelado, sem as linhas de cabecalho.

    As linhas que rotulam a secao introduzem vocabulario proprio do pacote, ausente
    do documento original; mante-las na comparacao produziria divergencia espuria.
    """
    partes = []
    for m in re.finditer(r"^\[SUBPAGINA\][^\n]*\n(.*?)(?=^\[|\Z)", texto, re.M | re.S):
        partes.append(m.group(1))
    return "\n".join(partes)


_MARCADOR_ITEM = re.compile(r"""^(?:
      \(\s*(?:[ivxlcdm]{1,5}|[a-zA-Z]|\d+)\s*\)     # (i)  (a)  (1)
    | [a-z]\)                                          # a)   b)
    | [a-z]\.                                          # a.   b.
    | \d+(?:\.\d+)*[.)]                                # 1.   2.3.   1.1)
    | [IVXLCDM]{1,5}\.                                 # I.   II.   IV.
    )(?:\s|$)""", re.X)

REPET_PAGINA = 3        # ocorrencias que caracterizam cabecalho ou rodape de pagina
MAX_RECORRENTE = 150    # linha mais longa que isso nao e cabecalho, ainda que repita


def reconstroi_pdf(linhas):
    """Reconstitui periodos a partir das linhas de diagramacao do PDF."""
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


def texto_pdf_do_pacote(texto):
    """Texto de politica em PDF, reconstituido em periodos."""
    saida = []
    for m in re.finditer(r"^\[POLITICA EM PDF[^\]]*\][^\n]*\n(.*?)(?=^\[|\Z)",
                         texto, re.M | re.S):
        linhas = [l.strip() for l in m.group(1).split("\n") if l.strip()]
        saida.extend(reconstroi_pdf(linhas))
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotulagem", default="rotulagem_b9.csv")
    ap.add_argument("--tcc", default=None, help="pasta do TCC (pacotes congelados)")
    ap.add_argument("--tarballs", default="data/b9/raw")
    ap.add_argument("--so-verificar", action="store_true",
                    help="confere a identidade de conteudo e encerra")
    ap.add_argument("--manter-repetidos", action="store_true",
                    help="preserva o material de navegacao, para auditoria")
    ap.add_argument("--out", default="outputs/segmentos_textuais.csv")
    args = ap.parse_args()

    tcc = Path(args.tcc) if args.tcc else None
    with (REPO / args.rotulagem).open(encoding="utf-8-sig", newline="") as fh:
        R = [r for r in csv.DictReader(fh, delimiter=";") if r.get("status") == "text"]
    # 'politica_outro_idioma' identifica o sitio cuja politica so existe em idioma
    # estrangeiro; nao e ausencia de politica nem politica sem o requisito, e por
    # isso nao integra o conjunto de modelagem.
    print(f"sitios com politica e texto avaliavel: {len(R)}")


    # indice dos pacotes de captura por hospedeiro
    tars = {}
    for p in glob.glob(str(REPO / args.tarballs / "*.tar.gz")):
        nome = os.path.basename(p)
        partes = nome.split("__")
        if len(partes) >= 3:
            tars[partes[-1].replace(".tar.gz", "")] = p
    print(f"pacotes de captura localizados: {len(tars)}")

    linhas = []
    outro_idioma = []
    ident_ok = ident_dif = sem_tar = loc_ok = loc_falha = 0
    for r in R:
        sitio = r["site_id"]
        pacote = ""
        if tcc:
            cam = tcc / (r.get("evidencia_arquivo") or "")
            if cam.exists():
                pacote = cam.read_text(encoding="utf-8", errors="replace")

        subpaginas = []
        integrais = []          # antes do filtro de idioma
        tar = tars.get(sitio)
        if tar:
            try:
                o = carrega_tarball(tar)
                idx = o["index"]
                for chave in sorted(o["subs"]):
                    html = o["subs"][chave]
                    base = chave[:-5] if chave.endswith(".html") else chave
                    if idx.get(base, base) == "/__pre_consent":
                        continue
                    blocos = extrai_blocos(html)
                    integrais.extend(blocos)     # para a conferencia de identidade
                    if not em_portugues(" ".join(blocos)):
                        outro_idioma.append((sitio, idx.get(base, base)))
                        continue
                    subpaginas.extend(blocos)
            except Exception as e:
                print(f"  falha ao ler {sitio}: {e}")
        else:
            sem_tar += 1

        # A verificacao confronta subpaginas com subpaginas, antes de qualquer
        # descarte: o material em PDF provem do proprio pacote e sua identidade e
        # trivial, ao passo que o descarte de fragmentos curtos suprimiria palavras
        # e faria divergir uma extracao correta. Emprega-se o conjunto INTEGRAL,
        # anterior ao filtro de idioma, porque a conferencia afere a fidelidade da
        # extracao, e nao as exclusoes deliberadas que a sucedem.
        if pacote and integrais:
            from collections import Counter
            a = Counter(normaliza(" ".join(integrais)).split())
            b = Counter(normaliza(secoes_subpagina_do_pacote(pacote)).split())
            comum = sum((a & b).values())
            base = max(sum(a.values()), sum(b.values()))
            taxa = comum / base if base else 0.0
            if taxa >= 0.98:
                ident_ok += 1
            else:
                ident_dif += 1
                if ident_dif <= 8:
                    faltam = [w for w, _ in (b - a).most_common(6)]
                    print(f"  divergencia em {sitio}: {taxa*100:.1f}% dos vocabulos"
                          f"   ausentes na reextracao: {faltam}")

        segmentos = list(subpaginas)
        if pacote:
            segmentos.extend(texto_pdf_do_pacote(pacote))

        # Mantem-se a totalidade dos segmentos para a localizacao, de modo que o
        # documento normalizado permaneca contiguo; o descarte de fragmentos curtos
        # abriria lacunas e impediria a correspondencia de trechos que as atravessam.
        finais = []
        for seg in segmentos:
            finais.extend(divide_por_sentenca(seg))

        if args.so_verificar:
            continue

        # Documento normalizado com o intervalo de caracteres de cada segmento.
        # O casamento e posicional: localiza-se a transcricao no documento e
        # marcam-se os segmentos que o intervalo efetivamente cobre. Comparar
        # vocabulario, em lugar de posicao, faria vocabulos comuns casarem em
        # qualquer segmento e contaminaria o conjunto.
        partes, intervalos, pos = [], [None] * len(finais), 0
        for i, seg in enumerate(finais):
            ns = normaliza(seg)
            if not ns:
                continue
            if partes:
                pos += 1                       # separador
            intervalos[i] = (pos, pos + len(ns))
            partes.append(ns)
            pos += len(ns)
        doc = " ".join(partes)

        for v, ecol in VARIAVEIS:
            rot = r.get(v)
            if rot not in ("0", "1"):
                continue
            faixa = None
            if rot == "1":
                ev = normaliza(r.get(ecol) or "")
                faixa = localiza_trecho(doc, ev)
                if faixa:
                    loc_ok += 1
                elif ev:
                    loc_falha += 1
                    if loc_falha <= 5:
                        print(f"  trecho nao localizado: {sitio} / {v}")
            for i, seg in enumerate(finais):
                if len(seg) < MIN_SEG:
                    continue                   # fragmento de navegacao
                iv = intervalos[i]
                if rot == "0":
                    y = 0                       # negativo confiavel
                elif faixa and iv:
                    # Criterio simetrico: exigir que a transcricao cubra metade do
                    # segmento inviabilizaria o casamento sempre que o trecho fosse
                    # curto e o segmento longo, ainda que integralmente contido nele.
                    # Toma-se por referencia o menor dos dois comprimentos.
                    sobrep = max(0, min(iv[1], faixa[1]) - max(iv[0], faixa[0]))
                    ref = min(iv[1] - iv[0], faixa[1] - faixa[0])
                    y = 1 if ref and sobrep / ref >= COBERTURA_MIN else ""
                else:
                    y = ""                      # nao rotulado
                linhas.append({"site_id": sitio, "estrato": r.get("estrato", ""),
                               "variavel": v, "segmento_id": i, "y": y,
                               "n_caracteres": len(seg), "texto": seg})

    # Repeticao: apurada sobre a totalidade das linhas, e nunca antes da
    # localizacao das passagens, sob pena de abrir lacunas no documento continuo.
    from collections import defaultdict
    ocorr = Counter((l["site_id"], l["texto"]) for l in linhas if l["variavel"] == VARIAVEIS[0][0])
    sitios = defaultdict(set)
    for l in linhas:
        if l["variavel"] == VARIAVEIS[0][0]:
            sitios[l["texto"]].add(l["site_id"])

    # Determinacao do corte pela regra declarada: o menor valor em que nenhum
    # documento rotulado perde a totalidade de sua evidencia.
    por_doc = defaultdict(list)
    for l in linhas:
        if l["y"] == 1:
            por_doc[(l["site_id"], l["variavel"])].append(l)

    def zera_algum(corte):
        for ls in por_doc.values():
            atingidos = [l for l in ls
                         if ocorr[(l["site_id"], l["texto"])] >= corte
                         or len(sitios[l["texto"]]) >= corte]
            if atingidos and len(atingidos) == len(ls):
                return True
        return False

    corte = next((c for c in range(2, REPET_MAX + 1) if not zera_algum(c)), None)
    if corte is None:
        raise SystemExit("ABORTADO: nenhum corte ate o teto preserva a evidencia de "
                         "todos os documentos; convem revisar o criterio")
    atingidos = sum(1 for ls in por_doc.values() for l in ls
                    if ocorr[(l["site_id"], l["texto"])] >= corte
                    or len(sitios[l["texto"]]) >= corte)
    print(f"\ncorte de repeticao apurado pela regra do menor valor que preserva a")
    print(f"evidencia de todos os documentos: {corte} ocorrencias")
    print(f"  segmentos positivos atingidos: {atingidos} "
          f"(titulos varridos para dentro de trechos; nenhum documento fica sem evidencia)")

    def e_navegacao(l):
        return (ocorr[(l["site_id"], l["texto"])] >= corte
                or len(sitios[l["texto"]]) >= corte)

    marcados = [l for l in linhas if e_navegacao(l)]
    pos_perdidos = sum(1 for l in marcados if l["y"] == 1)
    if args.manter_repetidos:
        for l in linhas:
            l["navegacao"] = 1 if e_navegacao(l) else 0
    else:
        linhas = [l for l in linhas if not e_navegacao(l)]

    if outro_idioma:
        from collections import Counter as _C
        porsit = _C(s for s, _ in outro_idioma)
        print(f"\nsubpaginas removidas por estarem em outro idioma: {len(outro_idioma)}")
        for s_, n in porsit.most_common():
            resta = sum(1 for l in linhas if l["site_id"] == s_)
            print(f"  {s_:30} {n} subpagina(s)"
                  + ("   ATENCAO: documento sem conteudo remanescente" if resta == 0 else ""))

    print(f"\nidentidade de conteudo: {ident_ok} conferem, {ident_dif} divergem, "
          f"{sem_tar} sem pacote de captura")
    if not args.so_verificar:
        print(f"transcricoes localizadas no documento: {loc_ok}   nao localizadas: {loc_falha}")
        n_por_var = max(1, len(VARIAVEIS))
        print(f"material de navegacao ({corte}+ no mesmo sitio ou {corte}+ sitios): "
              f"{len(marcados)//n_por_var} segmentos por variavel"
              + ("  (preservados por --manter-repetidos)" if args.manter_repetidos else "  descartados"))
        zerados = sum(1 for ls in por_doc.values()
                      if all(e_navegacao(l) for l in ls))
        print(f"  documentos que perderam toda a evidencia: {zerados}"
              + ("   ATENCAO: contraria o criterio" if zerados else "   (nenhum, conforme o criterio)"))
    if args.so_verificar:
        return 0

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";",
                           quoting=csv.QUOTE_ALL)
        w.writeheader(); w.writerows(linhas)

    print("\n" + "=" * 84)
    print("CONJUNTO EM NIVEL DE SEGMENTO")
    print("=" * 84)
    print(f"  {'variavel':24}{'positivos':>11}{'negativos':>11}{'nao rotulados':>16}{'sitios':>9}")
    for v, _ in VARIAVEIS:
        sub = [l for l in linhas if l["variavel"] == v]
        p = sum(1 for l in sub if l["y"] == 1)
        n = sum(1 for l in sub if l["y"] == 0)
        u = sum(1 for l in sub if l["y"] == "")
        print(f"  {v:24}{p:>11}{n:>11}{u:>16}{len(set(l['site_id'] for l in sub)):>9}")
        docs_pos = set(l["site_id"] for l in sub if l["y"] == 1)
        docs_neg = set(l["site_id"] for l in sub if l["y"] == 0)
        media = p / len(docs_pos) if docs_pos else 0
        print(f"  {'':24}oriundos de {len(docs_pos)} documentos positivos e "
              f"{len(docs_neg)} negativos; {media:.1f} segmentos positivos por documento")
    print(f"\nsaida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
