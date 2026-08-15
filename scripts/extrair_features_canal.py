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
sys.path.insert(0, str(REPO / "src"))

# A extracao tem implementacao canonica na biblioteca. Este programa apenas le o
# material congelado e cruza o resultado com a rotulagem. Reimplementa-la aqui faria
# treino e inferencia executarem codigo distinto para a mesma finalidade.
from privacyscope.features.canal_titular import (          # noqa: E402
    ATRIBUTOS, JANELA_PADRAO, dominio_base, extrai_atributos, visivel,
)

RAW = REPO / "data" / "b9" / "raw"
ENRICH = REPO / "data" / "b9" / "pdf_enrichment"
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
    """Le o material congelado e delega a extracao a biblioteca."""
    html, _vis, subsel = carregar(tar_path)
    return extrai_atributos(html, url=url, subpage_selection=subsel,
                            texto_pdf=texto_pdf(host), janela=janela)


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
