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

DEDUPLICACAO POR SITIO
----------------------
Cabecalho, rodape e menu nao integram o objeto de analise, mas nao podem ser
excluidos pela marca semantica que os envolve: mediu-se que 10,5% das passagens que
fundamentam os rotulos residem dentro de header, footer, nav ou aside, porque parte
expressiva dos sitios emprega esses elementos de forma incorreta, envolvendo o
conteudo principal.

Adota-se, em seu lugar, DEDUPLICACAO: de cada texto identico dentro do mesmo sitio
preserva-se uma ocorrencia e descartam-se as demais. Nao ha remocao por repeticao, e
nao ha parametro de corte.

A formulacao anterior descartava toda ocorrencia de texto que comparecesse cinco
vezes ou mais no mesmo sitio, ou em cinco sitios distintos. Tres razoes a
inviabilizaram, e as tres foram apuradas por medicao:

  O problema que o filtro enderecava e DUPLICACAO, e nao presenca. A mesma frase
  contada dezenas de vezes distorce a proporcao de classes, a ponderacao pelo inverso
  da frequencia documental e — o que mais importa — as proprias metricas: como as
  copias residem no mesmo documento, e a particao e por documento, a decisao do modelo
  sobre uma unica sentenca comparece varias vezes no conjunto reunido. Preservar uma
  copia resolve a duplicacao sem suprimir texto algum.

  O criterio entre sitios removia declaracao junto com cromo de plataforma. Sete
  segmentos portadores de evidencia foram descartados exclusivamente por ele, e o
  titulo "Transferencia internacional de dados" sobreviveu por comparecer em quatro
  sitios, a um passo do corte. Politica copiada de modelo continua sendo declaracao do
  controlador que a publicou.

  O criterio entre sitios acoplava o resultado de cada sitio a composicao da execucao:
  o mesmo documento produzia conjuntos distintos conforme quem mais estivesse na
  rodada. A deduplicacao e estritamente intra-sitio e nao tem essa dependencia.

A consequencia e que material de navegacao passa a integrar o conjunto, uma vez por
sitio. Isso e deliberado. O descarte de fragmentos abaixo do comprimento minimo ja
suprime o cromo mais curto, e o que resta e exatamente o que o arcabouco encontrara em
operacao — de modo que o classificador aprende a rejeita-lo no treino, em vez de
encontra-lo pela primeira vez em campo. Preparo do treino e preparo do uso passam a
coincidir, o que a formulacao anterior nao permitia: a contagem entre sitios nao e
computavel sobre um sitio isolado.

Quando ocorrencias do mesmo texto divergem quanto ao rotulo derivado do casamento
posicional, a sobrevivente recebe o rotulo POSITIVO. A divergencia decorre de o
intervalo da transcricao cobrir uma ocorrencia e nao as outras; descartar a positiva
suprimiria evidencia por acidente de posicao.

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
import os
import glob
import json
import os
import re
import sys
import tarfile
import unicodedata
from collections import Counter, OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

# O preparo do texto tem implementacao canonica na biblioteca. Este programa apenas
# a alimenta com o material congelado e cruza o resultado com a rotulagem manual.
# Reimplementa-lo aqui faria treino e inferencia executarem codigo distinto para a
# mesma finalidade, divergencia que nao se manifesta como falha e sim como queda de
# desempenho sem causa aparente.
from privacyscope.text.segmentacao import (            # noqa: E402
    MIN_SEG, normaliza, reconstroi_pdf, segmenta,
)

VARIAVEIS = [("finalidade", "finalidade_evid"),
             ("direitos_titular", "direitos_evid"),
             ("transf_internacional", "transf_evid")]

COBERTURA_MIN = 0.5     # fracao do menor entre segmento e trecho que a sobreposicao cobre

# Abreviaturas correntes em politica de privacidade e em texto juridico. Sem esta
# guarda, a fronteira de sentenca quebra em "Ltda.", "Sr.", "etc." e "Av.".

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


def secoes_pdf_do_pacote(texto):
    """Secoes de politica em PDF no pacote congelado, sem reconstituir.

    Devolve o texto bruto de cada secao; a reconstrucao em periodos cabe a
    biblioteca, que a aplica identicamente no treino e na inferencia.
    """
    return [m.group(1) for m in
            re.finditer(r"^\[POLITICA EM PDF[^\]]*\][^\n]*\n(.*?)(?=^\[|\Z)",
                        texto, re.M | re.S)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotulagem", default="rotulagem_b9.csv")
    ap.add_argument("--tcc", default=os.environ.get("PRIVACYSCOPE_TCC"),
                    help="pasta do TCC com os pacotes congelados; na ausencia do "
                         "argumento adota-se a variavel de ambiente PRIVACYSCOPE_TCC")
    ap.add_argument("--sem-pdf", action="store_true",
                    help="segmenta apenas o HTML, dispensando os pacotes congelados")
    ap.add_argument("--tarballs", default="data/b9/raw")
    ap.add_argument("--so-verificar", action="store_true",
                    help="confere a identidade de conteudo e encerra")
    ap.add_argument("--manter-duplicatas", action="store_true",
                    help="preserva as copias, marcadas na coluna `duplicata`")
    ap.add_argument("--out", default="outputs/segmentos_textuais.csv")
    args = ap.parse_args()

    # O texto de politica publicada em PDF provem dos pacotes congelados, e nao dos
    # tarballs. Sem a pasta do TCC o ramo de PDF simplesmente nao executa, e a
    # ausencia nao se manifesta como falha: o programa encerra com codigo zero
    # tendo descartado, em silencio, a politica inteira dos sitios que so publicam
    # em PDF. Prosseguir sem esse material passa a exigir declaracao explicita.
    if not args.tcc and not args.sem_pdf:
        print("ERRO: a pasta do TCC nao foi informada.")
        print("  Sem ela o texto das politicas em PDF fica de fora, e a conferencia")
        print("  de identidade do conteudo nao e exercida.")
        print("  Informe --tcc, ou defina a variavel de ambiente:")
        print("    PowerShell:  $env:PRIVACYSCOPE_TCC = \"C:\\caminho\\TCC\"")
        print("    bash:        export PRIVACYSCOPE_TCC=/caminho/TCC")
        print("  Para segmentar deliberadamente sem os PDF, use --sem-pdf.")
        return 2
    if args.sem_pdf:
        args.tcc = None
        print("AVISO: --sem-pdf declarado. O texto das politicas em PDF fica de fora")
        print("  e a conferencia de identidade do conteudo nao sera exercida.\n")

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

        # Indexa-se pelo NOME DO ARQUIVO, que e unico; o rotulo de origem serve ao
        # relatorio, e dois arquivos podem compartilha-lo.
        paginas, rotulo_de = OrderedDict(), {}
        tar = tars.get(sitio)
        if tar:
            try:
                o = carrega_tarball(tar)
                idx = o["index"]
                for chave in sorted(o["subs"]):
                    base = chave[:-5] if chave.endswith(".html") else chave
                    rotulo = idx.get(base, base)
                    if rotulo == "/__pre_consent":
                        continue
                    paginas[chave] = o["subs"][chave]
                    rotulo_de[chave] = rotulo
            except Exception as e:
                print(f"  falha ao ler {sitio}: {e}")
        else:
            sem_tar += 1

        preparo = segmenta(paginas, secoes_pdf_do_pacote(pacote) if pacote else ())
        integrais = list(preparo.blocos_integrais)
        for chave in preparo.subpaginas_removidas:
            outro_idioma.append((sitio, rotulo_de.get(chave, chave)))

        # A verificacao confronta subpaginas com subpaginas, antes de qualquer
        # descarte: o material em PDF provem do proprio pacote e sua identidade e
        # trivial, ao passo que o descarte de fragmentos curtos suprimiria palavras
        # e faria divergir uma extracao correta. Emprega-se o conjunto INTEGRAL,
        # anterior ao filtro de idioma, porque a conferencia afere a fidelidade da
        # extracao, e nao as exclusoes deliberadas que a sucedem.
        if pacote and integrais:
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

        # Mantem-se a totalidade dos segmentos para a localizacao, de modo que o
        # documento normalizado permaneca contiguo; o descarte de fragmentos curtos
        # abriria lacunas e impediria a correspondencia de trechos que as atravessam.
        finais = list(preparo.unidades)

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

    # Deduplicacao por sitio. Preserva-se a PRIMEIRA ocorrencia de cada texto no
    # sitio, e descartam-se as demais. A escolha da primeira e arbitraria e
    # inconsequente — os segmentos sao independentes e nao carregam contexto —, mas
    # precisa ser declarada e determinista para que a reexecucao reproduza o conjunto.
    from collections import defaultdict
    grupos = defaultdict(list)
    for l in linhas:
        grupos[(l["site_id"], l["variavel"], l["texto"])].append(l)

    # Rotulo da sobrevivente: positivo se QUALQUER copia o for. Copias do mesmo texto
    # podem divergir porque o intervalo da transcricao cobre uma ocorrencia e nao as
    # outras; preservar a negativa suprimiria evidencia por acidente de posicao.
    def consolida(g):
        alvo = next((x for x in g if x["y"] == 1), None)
        if alvo is None:
            alvo = next((x for x in g if x["y"] == ""), g[0])
        prim = g[0]
        prim["y"] = alvo["y"]
        return prim

    com_evidencia_antes = {(l["site_id"], l["variavel"]) for l in linhas if l["y"] == 1}
    sobreviventes = {id(consolida(g)) for g in grupos.values()}
    duplicatas = [l for l in linhas if id(l) not in sobreviventes]
    dup_pos = sum(1 for l in duplicatas if l["y"] == 1)
    divergentes = sum(1 for g in grupos.values()
                      if len({x["y"] for x in g}) > 1)

    if args.manter_duplicatas:
        for l in linhas:
            l["duplicata"] = 0 if id(l) in sobreviventes else 1
    else:
        linhas = [l for l in linhas if id(l) in sobreviventes]

    por_doc = defaultdict(list)
    for l in linhas:
        if l["y"] == 1:
            por_doc[(l["site_id"], l["variavel"])].append(l)

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
    if ident_ok + ident_dif == 0:
        print("  ATENCAO: a conferencia nao foi exercida em sitio algum. O texto")
        print("  reextraido NAO foi confrontado contra o pacote congelado nesta")
        print("  execucao, e a fidelidade da extracao fica sem verificacao.")
    if not args.so_verificar:
        print(f"transcricoes localizadas no documento: {loc_ok}   nao localizadas: {loc_falha}")
        n_por_var = max(1, len(VARIAVEIS))
        print(f"deduplicacao por sitio: {len(duplicatas)//n_por_var} copias descartadas "
              f"por variavel"
              + ("  (preservadas por --manter-duplicatas)" if args.manter_duplicatas
                 else ""))
        print(f"  copias que portavam evidencia: {dup_pos//n_por_var} "
              f"(preservadas na sobrevivente)")
        print(f"  textos cujas copias divergiam quanto ao rotulo: "
              f"{divergentes//n_por_var}")
        depois = {(l["site_id"], l["variavel"]) for l in linhas if l["y"] == 1}
        zerados = sorted(com_evidencia_antes - depois)
        print(f"  documentos que perderam toda a evidencia: {len(zerados)}"
              + (f"   ATENCAO: a deduplicacao nao pode produzir isso; "
                 f"a consolidacao do rotulo falhou em {zerados[:3]}"
                 if zerados else "   (nenhum, como esperado)"))
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
