# -*- coding: utf-8 -*-
"""Tabula uma execucao por estado, motivo e estrato.

A pergunta que a coleta ao vivo deixou nao e "quantos falharam", e sim de quem e a
falha. O arcabouco passou a distinguir tres responsaveis — o sitio, o instrumento e
o quadro amostral —, e esta tabela e a leitura correspondente.

Uso:
    python scripts/resumir_diagnostico.py data/diagnostico_20/results.sqlite \
        --lista protocols/diagnostico_20_lista.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from privacyscope.core.types import (                        # noqa: E402
    NAO_APLICAVEL, NAO_COLETADO, UNIDADE_INEXISTENTE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--lista", help="CSV com coluna `estrato`")
    ap.add_argument("--variavel", default="tem_politica_privacidade")
    ap.add_argument("--run-id")
    ap.add_argument("--dominio",
                    help="em vez da tabela, despeja a trilha de auditoria integral "
                         "das variaveis deste dominio; aceita fragmento do nome")
    args = ap.parse_args()

    con = sqlite3.connect(REPO / args.db if not Path(args.db).is_absolute() else args.db)
    rid = args.run_id
    if not rid:
        linha = con.execute("SELECT run_id FROM runs WHERE completed_at IS NOT NULL "
                            "ORDER BY started_at DESC LIMIT 1").fetchone()
        if not linha:
            print("nenhuma execucao concluida"); return 2
        rid = linha[0]

    if args.dominio:
        achou = False
        for u, v, val, aj in con.execute(
            "SELECT domain_url, variable_name, value, audit_trail_json "
            "FROM variables WHERE run_id = ? ORDER BY domain_url, variable_name",
            (rid,)
        ):
            if args.dominio.lower() not in u.lower():
                continue
            achou = True
            print(f"=== {u}  [{v}] = {str(val).strip(chr(34))}")
            try:
                trilha = json.loads(aj) if aj else {}
            except Exception:                                    # noqa: BLE001
                trilha = {"_ilegivel": aj}
            for k in sorted(trilha):
                texto = str(trilha[k])
                print(f"    {k:28s} {texto[:220]}")
            print()
        if not achou:
            print(f"nenhuma variavel de {args.dominio!r} na execucao {rid[:8]}")
        return 0

    estrato = {}
    if args.lista:
        with (REPO / args.lista).open(encoding="utf-8-sig", newline="") as fh:
            for l in csv.DictReader(fh, delimiter=";"):
                estrato[l["dominio"]] = l.get("estrato", "?")

    linhas = []
    for u, val, aj in con.execute(
        "SELECT domain_url, value, audit_trail_json FROM variables "
        "WHERE run_id = ? AND variable_name = ?", (rid, args.variavel)
    ):
        host = u.replace("https://", "").rstrip("/")
        a = json.loads(aj) if aj else {}
        v = str(val).strip('"')
        estado = ("medido" if v in ("True", "False", "true", "false", "1", "0")
                  else v)
        linhas.append((host, estrato.get(host, "?"), estado,
                       a.get("motivo_coleta") or a.get("motivo", "-"), v))

    print(f"execucao {rid[:8]} | variavel {args.variavel} | {len(linhas)} unidades\n")
    print(f"{'dominio':32s} {'estrato':14s} {'estado':22s} {'motivo':20s} valor")
    for h, e, est, m, v in sorted(linhas, key=lambda x: (x[2], x[1], x[0])):
        print(f"{h[:32]:32s} {e:14s} {est:22s} {m:20s} {v}")

    print()
    tot = collections.Counter(l[2] for l in linhas)
    for k, n in tot.most_common():
        print(f"   {k:24s} {n:3d}  ({n / len(linhas) * 100:4.1f}%)")
    print()
    print("estado x estrato:")
    cru = collections.Counter((l[1], l[2]) for l in linhas)
    for (e, est), n in sorted(cru.items()):
        print(f"   {e:14s} {est:24s} {n}")
    medidos = tot.get("medido", 0)
    inexistentes = tot.get(UNIDADE_INEXISTENTE, 0)
    denominador = len(linhas) - inexistentes
    if denominador:
        print()
        print(f"taxa de alcance: {medidos}/{denominador} = "
              f"{medidos / denominador * 100:.1f}%")
        print(f"   (denominador exclui {inexistentes} unidade(s) inexistente(s): "
              f"endereco que nao designa hospedeiro nao e sitio nao alcancado)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
