# -*- coding: utf-8 -*-
"""Lista as unidades declaradas em um protocolo que nao produziram resultado.

POR QUE ESTE PROGRAMA EXISTE
----------------------------
Ate a correcao de 16/08/2026, dominio que falhava na coleta sumia: nao entrava em
saida alguma e so existia como linha de log. Some do numerador e do denominador ao
mesmo tempo, de sorte que qualquer proporcao calculada sobre o resultado responde a
uma pergunta que ninguem fez — a prevalencia entre os sitios alcancados, e nao entre
os amostrados. Na coleta ao vivo de 15/08/2026 isso foi 20 de 100.

Execucoes posteriores a correcao gravam a unidade perdida com motivo classificado.
Este programa serve as ANTERIORES, cujo registro nao tem essa informacao: reconstroi
o conjunto por diferenca entre o declarado e o apurado, e produz a lista em formato
que a fonte `csv` le, para que a reexecucao apure as causas como DADO.

O QUE ELE DISTINGUE
-------------------
Nunca coletado (ausente do manifesto de evidencia) e coletado sem analise (presente
no manifesto e ausente do resultado). As causas sao distintas e os remedios tambem:
o primeiro e falha de coleta, o segundo e falha de analise sobre evidencia integra.

ESTRATO
-------
A coluna `estrato` acompanha a lista porque a pergunta de interesse nao e quantos
falharam, e sim se algum estrato falha mais. Classificar depois, a mao, sobre a
lista ja reduzida, convidaria a classificar olhando o resultado.

Uso:
    python scripts/listar_sem_coleta.py protocols/aovivo.yaml \
        --db data/aovivo/results.sqlite --saida protocols/diagnostico_20_lista.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

# Sufixos de dominio reservados a administracao publica no registro .br.
SUFIXOS_GOV = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br", ".tc.br")


def estrato(host: str) -> str:
    return "governamental" if host.endswith(SUFIXOS_GOV) else "outro"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("protocolo")
    ap.add_argument("--db", help="banco de resultados; padrao e o do protocolo")
    ap.add_argument("--run-id", help="execucao a considerar; padrao e a mais recente concluida")
    ap.add_argument("--saida", required=True, help="CSV a gerar")
    ap.add_argument("--ranques", default="protocols/aovivo_amostra.csv",
                    help="CSV do quadro original, de onde se herda o ranque")
    args = ap.parse_args()

    p = REPO / args.protocolo if not Path(args.protocolo).is_absolute() else Path(args.protocolo)
    proto = yaml.safe_load(p.read_text(encoding="utf-8"))
    declarados = [u.replace("https://", "").replace("http://", "").rstrip("/")
                  for u in (proto.get("override_domains") or [])]
    if not declarados:
        print("ERRO: este programa opera sobre protocolo com `override_domains`.")
        return 2

    db = Path(args.db) if args.db else REPO / proto["result_store"]["params"]["db_path"]
    if not db.is_absolute():
        db = REPO / db
    con = sqlite3.connect(db)
    rid = args.run_id
    if not rid:
        linha = con.execute("SELECT run_id FROM runs WHERE completed_at IS NOT NULL "
                            "ORDER BY started_at DESC LIMIT 1").fetchone()
        if not linha:
            print(f"ERRO: nenhuma execucao concluida em {db}")
            return 2
        rid = linha[0]
    apurados = {u.replace("https://", "").rstrip("/") for (u,) in con.execute(
        "SELECT DISTINCT domain_url FROM variables WHERE run_id = ?", (rid,))}

    repo_base = REPO / proto["repository"]["params"]["base_path"]
    manifesto = repo_base / "raw" / "manifest.jsonl"
    coletados: set[str] = set()
    if manifesto.exists():
        for linha in manifesto.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                try:
                    coletados.add(json.loads(linha)["domain_url"]
                                  .replace("https://", "").rstrip("/"))
                except Exception:                                  # noqa: BLE001
                    pass

    # Ranque herdado do quadro original: perde-lo tornaria a lista nao rastreavel
    # ate a lista de popularidade que a originou.
    ranque: dict[str, str] = {}
    q = REPO / args.ranques
    if q.is_file():
        with q.open(encoding="utf-8-sig", newline="") as fh:
            amostra = fh.read(8192); fh.seek(0)
            delim = ";" if amostra.count(";") > amostra.count(",") else ","
            for linha in csv.DictReader(fh, delimiter=delim):
                d = (linha.get("dominio") or "").strip().lower()
                if d:
                    ranque[d] = (linha.get("rank_tranco") or "").strip()

    faltam = [d for d in declarados if d not in apurados]
    sem_evidencia = [d for d in faltam if d not in coletados]
    com_evidencia = [d for d in faltam if d in coletados]

    saida = REPO / args.saida
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["ordem", "rank_tranco", "dominio", "url", "estrato", "situacao"])
        for i, d in enumerate(faltam, 1):
            w.writerow([i, ranque.get(d, ""), d, f"https://{d}", estrato(d),
                        "sem_evidencia" if d in sem_evidencia else "sem_analise"])

    print(f"protocolo      : {p.name}")
    print(f"execucao       : {rid}")
    print(f"declarados     : {len(declarados)}")
    print(f"com resultado  : {len(apurados)}")
    print(f"sem resultado  : {len(faltam)}")
    print(f"  nunca coletados            : {len(sem_evidencia)}")
    print(f"  coletados e nao analisados : {len(com_evidencia)}")
    gov = sum(1 for d in faltam if estrato(d) == "governamental")
    gov_tot = sum(1 for d in declarados if estrato(d) == "governamental")
    if gov_tot:
        print(f"  governamentais             : {gov} de {gov_tot} "
              f"({gov / gov_tot * 100:.1f}% do estrato)")
    print(f"lista          : {saida.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
