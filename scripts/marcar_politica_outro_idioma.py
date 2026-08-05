# -*- coding: utf-8 -*-
"""Atribui status proprio ao sitio cuja politica so existe em idioma estrangeiro.

O escopo do classificador e o texto de politica em portugues. Sitio cuja politica
esteja redigida exclusivamente em outro idioma nao constitui ausencia de politica —
ha politica — nem politica que omita o requisito — o requisito pode estar declarado.
Confundi-lo com qualquer das duas categorias distorceria o panorama de prevalencia.

Atribui-se, por isso, o status `politica_outro_idioma`, que o retira do conjunto de
modelagem e o preserva como categoria propria, reportavel.

A deteccao reproduz o criterio empregado na segmentacao: identifica-se o idioma por
subpagina, e assinala-se o sitio cujas subpaginas de politica sejam todas
estrangeiras. A decisao final cabe ao anotador; a rotina apenas relaciona os
candidatos e, quando autorizada, aplica a alteracao.

Uso:
    python scripts/marcar_politica_outro_idioma.py                # apenas relaciona
    python scripts/marcar_politica_outro_idioma.py --aplicar      # grava
"""
from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import json
import os
import shutil
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("seg", REPO / "scripts" / "segmentar_politicas.py")
_seg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotulagem", default="rotulagem_b9.csv")
    ap.add_argument("--tarballs", default="data/b9/raw")
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    caminho = REPO / args.rotulagem
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        leitor = csv.DictReader(fh, delimiter=";")
        campos = leitor.fieldnames
        R = list(leitor)

    tars = {os.path.basename(p).split("__")[-1].replace(".tar.gz", ""): p
            for p in glob.glob(str(REPO / args.tarballs / "*.tar.gz"))}

    candidatos = []
    for r in R:
        if r.get("status") != "text":
            continue
        tar = tars.get(r["site_id"])
        if not tar:
            continue
        pt = est = 0
        try:
            with tarfile.open(tar, "r:gz") as tf:
                idx = {}
                for m in tf.getmembers():
                    if m.name.endswith("/html_subpages/_index.json"):
                        try:
                            idx = json.load(tf.extractfile(m))
                        except Exception:
                            pass
                for m in tf.getmembers():
                    if "/html_subpages/" not in m.name or not m.name.endswith(".html"):
                        continue
                    base = os.path.basename(m.name)[:-5]
                    if idx.get(base, base) == "/__pre_consent":
                        continue
                    txt = " ".join(_seg.extrai_blocos(tf.extractfile(m).read()))
                    if len(txt) < _seg.MIN_IDIOMA:
                        continue
                    if _seg.em_portugues(txt):
                        pt += 1
                    else:
                        est += 1
        except Exception as e:
            print(f"  falha ao ler {r['site_id']}: {e}")
            continue
        if est and not pt:
            candidatos.append((r, est))

    print(f"sitios com status 'text': {sum(1 for r in R if r.get('status') == 'text')}")
    print(f"candidatos a 'politica_outro_idioma': {len(candidatos)}\n")
    for r, est in candidatos:
        ev = next((r.get(k) for k in ("finalidade_evid", "direitos_evid", "transf_evid")
                   if (r.get(k) or "").strip()), "")
        print(f"  {r['site_id']:30} {est} subpagina(s) de politica, nenhuma em portugues")
        if ev:
            print(f"     evidencia transcrita: {' '.join(ev.split())[:96]}")

    if not args.aplicar:
        print("\n  modo de relacao: nada foi gravado. Use --aplicar para efetivar.")
        return 0

    if not candidatos:
        print("\n  nenhum candidato; nada a fazer.")
        return 0

    shutil.copy2(caminho, str(caminho) + ".bak_idioma")
    alvo = {r["site_id"] for r, _ in candidatos}
    for r in R:
        if r["site_id"] in alvo:
            r["status"] = "politica_outro_idioma"
    with caminho.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=";")
        w.writeheader(); w.writerows(R)
    print(f"\n  status alterado em {len(alvo)} sitio(s); copia de seguranca em "
          f"{caminho.name}.bak_idioma")
    print("  Replicar a alteracao na planilha de trabalho.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
