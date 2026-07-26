# -*- coding: utf-8 -*-
"""Extracao da matriz de atributos de ``tem_canal_titular`` a partir da evidencia.

Oito atributos binarios, derivados do texto da evidencia coletada:

  F1 email_lgpd_dominio_proprio  prefixo de privacidade no dominio do sitio
  F2 email_lgpd_dominio_externo  prefixo de privacidade em dominio de grupo
  F3 email_generico_ancorado     e-mail sem prefixo, proximo a ancora de direitos
  F4 subpagina_titular           subpagina de canal/encarregado plausivel
  F5 contato_ancorado            formulario ou link ancorado a direitos
  F6 telefone_ancorado           telefone proximo a ancora
  F7 ancora_encarregado          mencao a Encarregado/DPO
  F8 ancora_direitos             mencao a exercicio de direitos

F7 e F8 sao binarias e nao contagens. A escolha e empirica: testados os cortes de
contagem de 1 a 14, o corte otimo e >=1, identico a binarizacao, com ganho nulo
em acuracia balanceada. A contagem bruta e ainda confundida pelo comprimento do
documento — uma politica extensa menciona mais vezes por ser extensa —, de modo
que mediria extensao textual em vez do construto.

F1 e F4 correspondem aos sinais do detector por regra do framework
(``tests/canal_titular.py``). O conjunto contem, portanto, a linha de base como
caso particular. Trata-se de modelos aninhados, o que torna a comparacao por
McNemar um teste direto sobre o ganho dos sinais adicionais.

A janela de proximidade e fixada em 200 caracteres, ordem de grandeza de um
paragrafo. O valor e definido previamente a avaliacao; as execucoes com 100 e 400
destinam-se a verificacao de robustez, nao a selecao — selecionar a janela pelo
desempenho equivaleria a ajustar hiperparametro sobre a amostra inteira.

Excluem-se do conjunto o ``stratum``, por constituir atalho de taxa-base e proxy
da fonte amostral, e ``plataforma_externa_dsr``, presente em apenas tres casos, o
que o tornaria quase constante e instavel.

Os atributos derivam exclusivamente do texto da evidencia. O campo ``canal_forma``
nao entra como insumo; seu uso restringe-se a auditoria do extrator, conduzida em
``auditar_features_canal.py``.

A evidencia lida compreende o HTML armazenado (raiz e subpaginas) e o texto dos
PDFs de politica, incluindo os obtidos por ``enriquecer_pdfs_b9.py``, de modo a
corresponder ao material que sustentou a rotulagem manual.

Uso:
    python scripts/extrair_features_canal.py --janela 200
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
import tarfile
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "b9" / "raw"
ENRICH = REPO / "data" / "b9" / "pdf_enrichment"

EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:com|com\.br|br|gov\.br|org|org\.br|edu|edu\.br|net|net\.br))\b",
    re.IGNORECASE)
PREFIXOS_LGPD = ("dpo", "encarregado", "encarregada", "privacidade", "lgpd",
                 "protecaodedados", "protecao.dados", "protecao_dados", "meusdados")
BLOCKLIST = frozenset({
    "cloudflare.com", "cloudfront.net", "akamai.com", "akamaihd.net", "fastly.com",
    "amazonaws.com", "wordpress.com", "automattic.com", "shopify.com", "wix.com",
    "wixpress.com", "squarespace.com", "hubspot.com", "zendesk.com", "salesforce.com",
    "google.com", "gstatic.com", "adobe.com", "sentry.io", "example.com",
})
ANC_ENCARREGADO = re.compile(r"\bencarregad[oa]\b|\bdpo\b|data\s+protection\s+officer", re.I)
ANC_DIREITOS = re.compile(
    r"portal\s+do\s+titular|central\s+do\s+titular|canal\s+do\s+titular|seus\s+direitos"
    r"|direitos\s+do\s+titular|exerc\w+\s+(?:de\s+|seus\s+)?direitos|requisi\w+\s+lgpd"
    r"|solicita\w+\s+lgpd|titular\s+dos\s+dados", re.I)
ANC_QUALQUER = re.compile(f"({ANC_ENCARREGADO.pattern})|({ANC_DIREITOS.pattern})", re.I)
TEL_RE = re.compile(r"tel:[+0-9()\s.\-]{8,}|\(?\d{2}\)?\s?\d{4,5}[\-\s.]?\d{4}")
PLAUSIBILIDADE = ("titular", "direito", "lgpd", "exercer", "exercicio", "exercício",
                  "encarregado", "dpo", "solicitacao", "solicitação", "requisicao",
                  "requisição", "fale conosco")
MIN_SUBPAGE_BYTES = 500


class _Vis(HTMLParser):
    SKIP = {"script", "style", "noscript", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buf, self.skip = [], 0

    def handle_starttag(self, t, a):
        if t in self.SKIP:
            self.skip += 1

    def handle_endtag(self, t):
        if t in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, d):
        if not self.skip and d.strip():
            self.buf.append(d.strip())


def visivel(html: str) -> str:
    p = _Vis()
    try:
        p.feed(html)
    except Exception:
        pass
    return re.sub(r"\s+", " ", " ".join(p.buf))


def dominio_base(url: str) -> str:
    d = re.sub(r"^https?://", "", (url or "")).split("/")[0].lower()
    return d[4:] if d.startswith("www.") else d


def mesmo_dominio(email_dom: str, site_dom: str) -> bool:
    e, s = email_dom.lower().strip(), site_dom.lower().strip()
    return e == s or e.endswith("." + s) or s.endswith("." + e)


def eh_provedor(dom: str) -> bool:
    d = dom.lower()
    return any(d == p or d.endswith("." + p) for p in BLOCKLIST)


def posicoes_ancora(texto: str) -> list:
    """Posicoes das ancoras no texto, calculadas uma unica vez por corpus.
    O recalculo por ocorrencia domina o tempo em documentos extensos."""
    return [m.start() for m in ANC_QUALQUER.finditer(texto)]


def perto_pos(anc, alvo_re, texto: str, janela: int) -> bool:
    """True se alguma ocorrencia de alvo_re dista <= janela caracteres de uma
    ancora. A busca binaria sobre as posicoes ordenadas evita varredura linear."""
    if not anc:
        return False
    import bisect
    for m in alvo_re.finditer(texto):
        p = m.start()
        i = bisect.bisect_left(anc, p)
        for j in (i - 1, i):
            if 0 <= j < len(anc) and abs(p - anc[j]) <= janela:
                return True
    return False


def carregar(tar_path: Path):
    """Le o tarball (modo leitura). Devolve (html_bruto, texto_visivel, subpage_selection)."""
    htmls, meta = [], {}
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in tf.getmembers():
            n = m.name
            if n.endswith("/html_root.html") or ("/html_subpages/" in n and n.endswith(".html")):
                try:
                    htmls.append(tf.extractfile(m).read().decode("utf-8", "ignore"))
                except Exception:
                    pass
            elif n.endswith("/meta.json"):
                try:
                    meta = json.load(tf.extractfile(m))
                except Exception:
                    pass
            elif "/pdf_documents/" in n and n.endswith(".pdf"):
                pass  # bytes; texto vem do enriquecimento
    html = "\n".join(htmls)
    return html, visivel(html), (meta.get("subpage_selection") or {})


def texto_pdf(host: str) -> str:
    d = ENRICH / host
    if not d.is_dir():
        return ""
    partes = []
    for t in sorted(d.glob("*.txt")):
        try:
            partes.append(t.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    return re.sub(r"\s+", " ", " ".join(partes))


def extrair(host: str, url: str, tar_path: Path, janela: int) -> dict:
    html, vis, subsel = carregar(tar_path)
    vis_total = (vis + " " + texto_pdf(host)).strip()
    sdom = dominio_base(url)

    emails = {e.lower() for e in EMAIL_RE.findall(vis_total)} | {e.lower() for e in EMAIL_RE.findall(html)}
    f1 = f2 = 0
    genericos = []
    for e in emails:
        user, dom = e.split("@", 1)
        if eh_provedor(dom):
            continue
        if any(user.startswith(p) for p in PREFIXOS_LGPD):
            if mesmo_dominio(dom, sdom):
                f1 = 1
            else:
                f2 = 1
        else:
            genericos.append(e)

    anc_vis = posicoes_ancora(vis_total)
    f3 = 0
    if genericos:
        # alternancia unica com todos os enderecos, para uma so varredura
        alt = re.compile("|".join(re.escape(e) for e in genericos[:60]), re.I)
        f3 = 1 if perto_pos(anc_vis, alt, vis_total, janela) else 0

    f4 = 0
    for cat in ("canal_titular", "encarregado"):
        for item in (subsel.get(cat) or []):
            f4 = 1
    if f4 and not any(k in vis_total.lower() for k in PLAUSIBILIDADE):
        f4 = 0
    if f4 and len(html) < MIN_SUBPAGE_BYTES:
        f4 = 0

    # F5: <form> ou <a> cujo texto casa ancora de direitos
    f5 = 0
    htm = html[:2_000_000]          # teto de tamanho: portais extensos degradam a regex
    anc_html = posicoes_ancora(htm)
    if perto_pos(anc_html, re.compile(r"<form\b", re.I), htm, janela):
        f5 = 1
    if not f5:
        for m in re.finditer(r"<a\b[^>]{0,400}>([^<]{0,120})</a>", htm, re.I):
            if ANC_DIREITOS.search(m.group(1) or "") and not re.search(
                    r'href="(mailto:|tel:)', m.group(0), re.I):
                f5 = 1
                break

    f6 = 1 if perto_pos(anc_vis, TEL_RE, vis_total, janela) else 0
    f7 = 1 if ANC_ENCARREGADO.search(vis_total) else 0
    f8 = 1 if ANC_DIREITOS.search(vis_total) else 0
    return dict(F1_email_lgpd_proprio=f1, F2_email_lgpd_externo=f2, F3_email_generico_ancorado=f3,
                F4_subpagina_titular=f4, F5_contato_ancorado=f5, F6_telefone_ancorado=f6,
                F7_ancora_encarregado=f7, F8_ancora_direitos=f8)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--janela", type=int, default=200)
    ap.add_argument("--rotulos", default="rotulagem_b9.csv")
    ap.add_argument("--out", default="outputs/features_canal_N200.csv",
                    help="artefato gerado; a convencao do projeto e outputs/")
    ap.add_argument("--offset", type=int, default=0,
                    help="indice inicial, para execucao em blocos")
    ap.add_argument("--limit", type=int, default=0,
                    help="processa no maximo N sitios (0 = todos)")
    args = ap.parse_args()

    with open(REPO / args.rotulos, encoding="utf-8-sig", newline="") as fh:
        rot = list(csv.DictReader(fh, delimiter=";"))
    alvo = {(r["site_id"] or "").strip(): r for r in rot
            if (r.get("tem_canal_titular") or "").strip() in ("0", "1")}
    man = {}
    for l in (RAW / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            e = json.loads(l)
            man[dominio_base(e["domain_url"])] = e

    itens = sorted(alvo.items())
    if args.offset or args.limit:
        itens = itens[args.offset: (args.offset + args.limit) if args.limit else None]
    linhas, faltando = [], []
    for host, r in itens:
        e = man.get(dominio_base("http://" + host)) or man.get(host)
        if not e:
            faltando.append(host); continue
        tp = RAW / e["tar_filename"]
        if not tp.exists():
            faltando.append(host); continue
        try:
            f = extrair(host, e["domain_url"], tp, args.janela)
        except Exception as ex:
            print(f"  [ERRO] {host}: {type(ex).__name__}"); faltando.append(host); continue
        f.update(site_id=host, estrato=(r.get("estrato") or "").strip(),
                 y=int((r["tem_canal_titular"]).strip()))
        linhas.append(f)

    cols = ["site_id", "estrato", "y"] + [f"F{i}_" + n for i, n in enumerate(
        ["email_lgpd_proprio", "email_lgpd_externo", "email_generico_ancorado", "subpagina_titular",
         "contato_ancorado", "telefone_ancorado", "ancora_encarregado", "ancora_direitos"], start=1)]
    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    novo = not out.exists() or args.offset == 0
    with out.open("w" if novo else "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
        if novo:
            w.writeheader()
        w.writerows(linhas)
    print(f"janela N={args.janela} | sitios={len(linhas)} | sem evidencia={len(faltando)}")
    print(f"saida: {out}")
    if faltando:
        print("  faltando:", faltando[:10])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
