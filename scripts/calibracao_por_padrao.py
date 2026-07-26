# -*- coding: utf-8 -*-
"""Calibracao por padrao de atributos, e nao por faixa de probabilidade.

MOTIVACAO
---------
A curva de confiabilidade agrupa sitios por probabilidade predita. Quando duas
faixas vizinhas exibem previsao semelhante e frequencia observada oposta, duas
explicacoes competem e a curva nao as separa: pode ser corte arbitrario partindo
uma massa homogenea, caso em que a divergencia e ruido; ou pode ser que padroes
distintos de atributos recebam probabilidade parecida enquanto apresentam taxas
efetivamente diferentes, caso em que ha descalibracao real.

Agrupar pelo PADRAO DE ATRIBUTOS elimina a ambiguidade. Cada padrao e um vetor
binario de oito posicoes; sitios com o mesmo padrao recebem, num ajuste unico,
exatamente a mesma probabilidade. Comparar a probabilidade do padrao com a
frequencia observada entre os sitios que o exibem responde de forma direta se o
modelo erra sistematicamente em alguma configuracao.

A pergunta tem consequencia operacional: o limiar de triagem situa-se na regiao de
probabilidade intermediaria, de modo que descalibracao ali afeta diretamente quais
sitios seguem para exame humano.

Uso:
    python scripts/calibracao_por_padrao.py
    python scripts/calibracao_por_padrao.py --min-n 3
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("firth", REPO / "scripts" / "firth.py")
_firth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_firth)

FEATS = ["F1_email_lgpd_proprio", "F2_email_lgpd_externo", "F3_email_generico_ancorado",
         "F4_subpagina_titular", "F5_contato_ancorado", "F6_telefone_ancorado",
         "F7_ancora_encarregado", "F8_ancora_direitos"]
CURTO = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return 0.0, 1.0
    f = k / n; d = 1 + z * z / n
    c = (f + z * z / (2 * n)) / d
    h = z * np.sqrt(f * (1 - f) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="outputs/features_canal_N200.csv")
    ap.add_argument("--min-n", type=int, default=4,
                    help="tamanho minimo do padrao para avaliacao de calibracao")
    ap.add_argument("--out", default="outputs/calibracao_padroes.csv")
    args = ap.parse_args()

    with (REPO / args.features).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    X = np.array([[int(r[f]) for f in FEATS] for r in R], dtype=float)
    y = np.array([int(r["y"]) for r in R], dtype=float)

    beta = _firth.firth_logistic(X, y)["beta"]
    prob = _firth.prever_prob(X, beta)

    grupos = defaultdict(list)
    for i, linha in enumerate(X):
        grupos[tuple(int(v) for v in linha)].append(i)

    print(f"sitios: {len(y)}   padroes distintos observados: {len(grupos)}")
    print(f"padroes possiveis com oito atributos binarios: 256\n")

    linhas = []
    for pad, idx in grupos.items():
        idx = np.array(idx); n = len(idx)
        pos = int(y[idx].sum())
        p = float(prob[idx][0])
        fo = pos / n
        lo, hi = wilson(pos, n)
        linhas.append({"padrao": "".join(CURTO[j] for j, v in enumerate(pad) if v) or "(nenhum)",
                       "n": n, "positivos": pos, "prob_predita": p, "freq_observada": fo,
                       "ic_inf": lo, "ic_sup": hi, "desvio": fo - p,
                       "avaliavel": n >= args.min_n,
                       "compativel": (lo <= p <= hi) if n >= args.min_n else None})
    linhas.sort(key=lambda r: -r["n"])

    print("=" * 104)
    print(f"PADROES COM AO MENOS {args.min_n} SITIOS")
    print("=" * 104)
    print(f"  {'padrao':22}{'n':>5}{'pos':>5}{'previsto':>11}{'observado':>11}"
          f"{'IC 95%':>18}{'desvio':>9}  compat.")
    aval = [r for r in linhas if r["avaliavel"]]
    for r in aval:
        print(f"  {r['padrao']:22}{r['n']:>5}{r['positivos']:>5}{r['prob_predita']*100:>10.1f}%"
              f"{r['freq_observada']*100:>10.1f}%{r['ic_inf']*100:>11.1f}–{r['ic_sup']*100:<6.1f}"
              f"{r['desvio']*100:>+8.1f}   {'sim' if r['compativel'] else 'NAO'}")

    cobertos = sum(r["n"] for r in aval)
    print(f"\n  {len(aval)} padroes avaliaveis, cobrindo {cobertos} de {len(y)} sitios "
          f"({cobertos/len(y)*100:.0f}%)")
    incomp = [r for r in aval if not r["compativel"]]
    print(f"  padroes com previsao fora do intervalo observado: {len(incomp)}")

    print("\n" + "=" * 104)
    print("PADROES RAROS  (abaixo do minimo; listados sem julgamento de calibracao)")
    print("=" * 104)
    raros = [r for r in linhas if not r["avaliavel"]]
    print(f"  {len(raros)} padroes reunindo {sum(r['n'] for r in raros)} sitios")
    for r in raros[:12]:
        print(f"    {r['padrao']:22}{r['n']:>4} sitio(s), {r['positivos']} positivo(s), "
              f"previsto {r['prob_predita']*100:.1f}%")

    print("\n" + "=" * 104)
    print("REGIAO INTERMEDIARIA  (previsao entre 15% e 60%, onde se situa o limiar)")
    print("=" * 104)
    meio = [r for r in linhas if 0.15 <= r["prob_predita"] <= 0.60]
    n_meio = sum(r["n"] for r in meio); pos_meio = sum(r["positivos"] for r in meio)
    print(f"  {len(meio)} padroes, {n_meio} sitios, {pos_meio} positivos")
    if n_meio:
        p_med = sum(r["prob_predita"] * r["n"] for r in meio) / n_meio
        lo, hi = wilson(pos_meio, n_meio)
        print(f"  previsto medio {p_med*100:.1f}%   observado {pos_meio/n_meio*100:.1f}% "
              f"[{lo*100:.1f}–{hi*100:.1f}]   "
              f"{'compativel' if lo <= p_med <= hi else 'INCOMPATIVEL'}")
        print("\n  Se o agregado for compativel e os padroes individuais divergirem apenas")
        print("  em grupos pequenos, a divergencia observada na curva e ruido amostral.")
        print("  Se algum padrao com n razoavel divergir de forma consistente, ha")
        print("  descalibracao atribuivel a configuracao especifica de atributos.")

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(linhas)
    print(f"\nsaida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
