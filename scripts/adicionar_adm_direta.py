# -*- coding: utf-8 -*-
"""Insercao da variavel analitica ``adm_direta`` no arquivo de rotulagem.

A estratificacao amostral foi operacionalizada pelo sufixo ``.gov.br``, criterio
verificavel e fixado previamente ao sorteio. A rotulagem evidenciou que orgaos da
administracao publica direta empregam tambem outros sufixos institucionais
(.jus.br, .mp.br, .def.br, .leg.br), de modo que alguns sitios dessa natureza
foram sorteados no estrato empresarial.

Reetiquetar o ``estrato`` comprometeria a inferencia baseada no desenho amostral:
tais sitios foram selecionados sob a probabilidade de inclusao do estrato
empresarial, da qual derivam os pesos de reponderacao. Mantem-se, por isso, duas
variaveis distintas:

  ``estrato``    amostral; permanece conforme o sorteio e governa a ponderacao.
  ``adm_direta`` analitica; sustenta as comparacoes substantivas entre dominios.

O procedimento corresponde a estimacao por dominio (Cochran, 1977).

Universidades federais recebem ``nao``, por integrarem a administracao indireta —
autarquias e fundacoes — e nao a direta. A denominacao ``adm_direta`` foi adotada
precisamente para que essa classificacao seja factualmente correta, ao contrario
de um par publico/privado, que qualificaria uma universidade federal como
privada.

A variavel e derivada por regra a partir do ``site_id``, nao constituindo
julgamento de anotador, e pode ser regenerada a qualquer momento. A operacao e
idempotente.

Uso:
    python scripts/adicionar_adm_direta.py
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import Counter
from pathlib import Path

# Sufixos institucionais de orgaos da administracao publica direta.
#   .gov.br  Executivo (Uniao, estados, municipios)
#   .jus.br  Poder Judiciario
#   .mp.br   Ministerio Publico
#   .def.br  Defensoria Publica
#   .leg.br  Poder Legislativo
ADM_DIRETA = re.compile(r"\.(gov|jus|mp|def|leg)\.br$", re.IGNORECASE)


def classifica(site_id: str) -> str:
    return "sim" if ADM_DIRETA.search((site_id or "").strip()) else "nao"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="rotulagem_b9.csv")
    args = ap.parse_args()
    p = Path(args.csv)
    if not p.exists():
        print(f"ERRO: {p} nao encontrado")
        return 2

    with p.open(encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh, delimiter=";")
        rows = list(rd)
        cols = list(rd.fieldnames or [])

    # a coluna e posicionada apos 'estrato', por afinidade semantica
    if "adm_direta" not in cols:
        i = cols.index("estrato") + 1 if "estrato" in cols else len(cols)
        cols.insert(i, "adm_direta")

    for r in rows:
        r["adm_direta"] = classifica(r.get("site_id", ""))

    shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
    with p.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)

    # relatorio
    tab = Counter((r.get("estrato", "").strip(), r["adm_direta"]) for r in rows)
    print(f"Linhas: {len(rows)} | colunas: {len(cols)}")
    print("\nestrato (amostral) x adm_direta (analitica):")
    for (e, a), n in sorted(tab.items()):
        print(f"   estrato={e:5} adm_direta={a:4} -> {n:4}")
    div = [r["site_id"] for r in rows
           if (r.get("estrato", "").strip() == "corp") and r["adm_direta"] == "sim"]
    print(f"\nSitios de administracao direta sorteados no estrato empresarial: {len(div)}")
    for s in div:
        print("   ", s)
    print("\n(o estrato permanece conforme o sorteio; os pesos nao se alteram)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
