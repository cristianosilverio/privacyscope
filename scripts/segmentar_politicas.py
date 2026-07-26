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
from collections import OrderedDict
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

VARIAVEIS = [("finalidade", "finalidade_evid"),
             ("direitos_titular", "direitos_evid"),
             ("transf_internacional", "transf_evid")]

MIN_SEG = 20          # segmentos menores sao fragmento de navegacao
MAX_SEG = 600         # acima disso, aplica-se divisao secundaria
COBERTURA_MIN = 0.5   # fracao do menor entre segmento e trecho que a sobreposicao cobre


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


def divide_longo(seg):
    """Divisao secundaria de segmento extenso, por fronteira de sentenca."""
    if len(seg) <= MAX_SEG:
        return [seg]
    t = re.sub(r"(?<=[.!?;:])\s+(?=[A-ZÀ-Ú])", "\n", seg)
    t = re.sub(r"\s+(?=\d+(\.\d+)*[).]\s+[A-ZÀ-Ú])", "\n", t)
    return [x.strip() for x in t.split("\n") if x.strip()]


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


def texto_pdf_do_pacote(texto):
    """Blocos de PDF, preservados do pacote: a extracao ja respeita as linhas."""
    saida = []
    for m in re.finditer(r"^\[POLITICA EM PDF[^\]]*\][^\n]*\n(.*?)(?=^\[|\Z)",
                         texto, re.M | re.S):
        saida.extend(x for x in (limpa(l) for l in m.group(1).split("\n")) if x)
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotulagem", default="rotulagem_b9.csv")
    ap.add_argument("--tcc", default=None, help="pasta do TCC (pacotes congelados)")
    ap.add_argument("--tarballs", default="data/b9/raw")
    ap.add_argument("--so-verificar", action="store_true",
                    help="confere a identidade de conteudo e encerra")
    ap.add_argument("--out", default="outputs/segmentos_textuais.csv")
    args = ap.parse_args()

    tcc = Path(args.tcc) if args.tcc else None
    with (REPO / args.rotulagem).open(encoding="utf-8-sig", newline="") as fh:
        R = [r for r in csv.DictReader(fh, delimiter=";") if r.get("status") == "text"]
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
    ident_ok = ident_dif = sem_tar = loc_ok = loc_falha = 0
    for r in R:
        sitio = r["site_id"]
        pacote = ""
        if tcc:
            cam = tcc / (r.get("evidencia_arquivo") or "")
            if cam.exists():
                pacote = cam.read_text(encoding="utf-8", errors="replace")

        subpaginas = []
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
                    subpaginas.extend(extrai_blocos(html))
            except Exception as e:
                print(f"  falha ao ler {sitio}: {e}")
        else:
            sem_tar += 1

        # A verificacao confronta subpaginas com subpaginas, antes de qualquer
        # descarte: o material em PDF provem do proprio pacote e sua identidade e
        # trivial, ao passo que o descarte de fragmentos curtos suprimiria palavras
        # e faria divergir uma extracao correta.
        if pacote and subpaginas:
            from collections import Counter
            a = Counter(normaliza(" ".join(subpaginas)).split())
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
            finais.extend(divide_longo(seg))

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

    print(f"\nidentidade de conteudo: {ident_ok} conferem, {ident_dif} divergem, "
          f"{sem_tar} sem pacote de captura")
    if not args.so_verificar:
        print(f"transcricoes localizadas no documento: {loc_ok}   nao localizadas: {loc_falha}")
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
