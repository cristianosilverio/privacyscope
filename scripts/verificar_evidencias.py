# -*- coding: utf-8 -*-
"""Verificacao de ancoragem das citacoes de evidencia na rotulagem.

O protocolo de anotacao determina que a rotulagem incida sobre o snapshot
coletado, nunca sobre o sitio ao vivo. Um campo ``*_evid`` cujo texto nao conste
da evidencia indica rotulo formado a partir de material externo ao snapshot, o
que retira do gabarito o lastro no conteudo que o modelo processara.

O procedimento identificou o caso de ``pm.pr.gov.br``, cuja coleta retornou 403
Forbidden — evidencia de 351 caracteres, sem conteudo — enquanto a citacao
registrada mencionava a Resolucao SEAP n 12.099/2026, texto ausente do snapshot.
A linha foi reclassificada para NA conforme P3 e K5.

Metodo. Cada citacao e normalizada (minusculas, remocao de acentos, colapso de
espacos) e confrontada com o pacote de evidencia igualmente normalizado. A busca
emprega fragmentos do inicio, do meio e do fim da citacao, tolerando truncamento
nas bordas decorrente do copia-e-cola. A ocorrencia de um fragmento basta para
considerar a citacao ancorada.

Interpretacao. Ausencia de correspondencia nao implica erro de rotulagem. Tres
causas sao possiveis: rotulo formado sobre o sitio ao vivo; parafrase em lugar de
transcricao literal; ou regeneracao do pacote posterior a rotulagem, situacao
verificada nos sitios enriquecidos por PDF, em que o texto mudou de posicao.
Somente a primeira compromete o gabarito.

O script nao altera a rotulagem. Produz outputs/verificacao_evidencias.csv.

Uso:
    python scripts/verificar_evidencias.py
"""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACOTES_PADRAO = Path(
    r"C:\Users\Cristiano.Silverio\OneDrive - LGPD2U\Treinamentos\ESALQ\TCC\Rotulagem\evidencia_b9")

CAMPOS = ["canal_evid", "finalidade_evid", "direitos_evid", "transf_evid"]


def normaliza(t: str) -> str:
    """Minusculas, sem acentos e com espacos colapsados, para comparacao robusta."""
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def fragmentos(cit: str, tam: int) -> list:
    """Fragmentos de inicio, meio e fim, tolerantes a truncamento nas bordas."""
    if len(cit) <= tam:
        return [cit] if cit else []
    meio = (len(cit) - tam) // 2
    return [cit[:tam], cit[meio:meio + tam], cit[-tam:]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotulos", default="rotulagem_b9.csv")
    ap.add_argument("--pacotes", default=str(PACOTES_PADRAO))
    ap.add_argument("--min-frag", type=int, default=50,
                    help="tamanho do fragmento buscado, em caracteres normalizados")
    ap.add_argument("--out", default="outputs/verificacao_evidencias.csv")
    args = ap.parse_args()

    pac = Path(args.pacotes)
    if not pac.is_dir():
        print(f"ERRO: pasta de pacotes nao encontrada: {pac}")
        print("      passe o caminho com --pacotes")
        return 2

    with (REPO / args.rotulos).open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))

    linhas, sem_pacote = [], 0
    for r in rows:
        host = (r.get("site_id") or "").strip()
        cits = {c: (r.get(c) or "").strip() for c in CAMPOS}
        if not any(cits.values()):
            continue
        p = pac / f"{host}.txt"
        if not p.exists():
            sem_pacote += 1
            continue
        evid_norm = normaliza(p.read_text(encoding="utf-8", errors="ignore"))
        for campo, cit in cits.items():
            if not cit:
                continue
            cn = normaliza(cit)
            frs = fragmentos(cn, args.min_frag)
            achou = any(f and f in evid_norm for f in frs)
            linhas.append({
                "site_id": host,
                "estrato": (r.get("estrato") or "").strip(),
                "status": (r.get("status") or "").strip(),
                "campo": campo,
                "ancorado": "SIM" if achou else "NAO",
                "chars_citacao": len(cn),
                "chars_evidencia": len(evid_norm),
                "citacao": cit[:160],
            })

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(linhas)

    nao = [l for l in linhas if l["ancorado"] == "NAO"]
    sites = sorted({l["site_id"] for l in nao})
    print(f"citacoes verificadas: {len(linhas)}   (sitios sem pacote: {sem_pacote})")
    print(f"ancoradas na evidencia: {len(linhas)-len(nao)} "
          f"({(len(linhas)-len(nao))/len(linhas)*100:.1f}%)")
    print(f"NAO encontradas: {len(nao)}  em {len(sites)} sitio(s)")
    print(f"\nsaida: {out}")
    if nao:
        print("\ncitacoes sem correspondencia na evidencia:")
        for l in nao[:40]:
            print(f"  {l['site_id']:28.28} {l['campo']:16} evid={l['chars_evidencia']:>7}c "
                  f"| {l['citacao'][:70]}")
    print("\nA ausencia de correspondencia admite tres causas: rotulo formado sobre o")
    print("sitio ao vivo, parafrase em lugar de transcricao, ou regeneracao do pacote")
    print("posterior a rotulagem. Apenas a primeira compromete o gabarito.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
