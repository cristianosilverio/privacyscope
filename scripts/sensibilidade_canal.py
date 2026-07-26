# -*- coding: utf-8 -*-
"""Analise de sensibilidade: modelo reduzido do canal do titular.

NATUREZA DESTA ANALISE
----------------------
O conjunto de oito atributos foi declarado antes da observacao de qualquer
resultado, pelo mesmo principio que fixou a janela de 200 caracteres. Tres deles
— subpagina do titular, contato ancorado e telefone ancorado — reuniram entre
onze e treze ocorrencias e produziram intervalos que cruzam o zero.

Retira-los com base nesses valores constituiria selecao conduzida sobre os mesmos
dados que sustentam a estimativa de desempenho, e contaminaria os resultados da
validacao cruzada, obtidos com os oito atributos. Esta rotina NAO promove o
modelo reduzido a principal: verifica se a conclusao do trabalho — a superioridade
sobre o detector por regra — sobrevive a retirada dos atributos imprecisos.

O desfecho informativo e a ESTABILIDADE. Diferenca desprezivel indica que a
conclusao nao depende dos tres atributos; diferenca substancial indicaria que
eles carregam sinal que os intervalos amplos nao revelaram, e o achado seria a
propria imprecisao, nao a irrelevancia.

Uso:
    python scripts/sensibilidade_canal.py
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
from math import sqrt, exp
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("firth", REPO / "scripts" / "firth.py")
_firth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_firth)

COMPLETO = ["F1_email_lgpd_proprio", "F2_email_lgpd_externo", "F3_email_generico_ancorado",
            "F4_subpagina_titular", "F5_contato_ancorado", "F6_telefone_ancorado",
            "F7_ancora_encarregado", "F8_ancora_direitos"]
RETIRADOS = ["F4_subpagina_titular", "F5_contato_ancorado", "F6_telefone_ancorado"]
REDUZIDO = [f for f in COMPLETO if f not in RETIRADOS]
REGEX = ["F1_email_lgpd_proprio", "F4_subpagina_titular"]


def metricas(y, pred):
    y = np.asarray(y); pred = np.asarray(pred)
    vp = int(np.sum((y == 1) & (pred == 1))); vn = int(np.sum((y == 0) & (pred == 0)))
    fp = int(np.sum((y == 0) & (pred == 1))); fn = int(np.sum((y == 1) & (pred == 0)))
    sens = vp / (vp + fn) if vp + fn else 0.0
    esp = vn / (vn + fp) if vn + fp else 0.0
    p1 = vp / (vp + fp) if vp + fp else 0.0
    p0 = vn / (vn + fn) if vn + fn else 0.0
    f1 = 2 * p1 * sens / (p1 + sens) if p1 + sens else 0.0
    f0 = 2 * p0 * esp / (p0 + esp) if p0 + esp else 0.0
    den = sqrt((vp + fp) * (vp + fn) * (vn + fp) * (vn + fn))
    return {"bal": (sens + esp) / 2, "macro_f1": (f0 + f1) / 2,
            "mcc": (vp * vn - fp * fn) / den if den else 0.0, "sens": sens, "esp": esp}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="outputs/features_canal_N200.csv")
    ap.add_argument("--particoes", type=int, default=5)
    ap.add_argument("--repeticoes", type=int, default=20)
    ap.add_argument("--semente", type=int, default=20260719)
    ap.add_argument("--out", default="outputs/sensibilidade_canal.csv")
    args = ap.parse_args()

    from sklearn.model_selection import RepeatedStratifiedKFold
    from scipy.stats import binomtest

    with (REPO / args.features).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    y = np.array([int(r["y"]) for r in R])
    estrato = np.array([r.get("estrato", "") for r in R])
    chave = np.array([f"{a}_{b}" for a, b in zip(y, estrato)])
    regex = np.array([1 if any(r[f] == "1" for f in REGEX) else 0 for r in R])
    X = {"completo": np.array([[int(r[f]) for f in COMPLETO] for r in R], dtype=float),
         "reduzido": np.array([[int(r[f]) for f in REDUZIDO] for r in R], dtype=float)}

    print(f"sitios: {len(y)}   com canal: {int(y.sum())}   sem canal: {int((1-y).sum())}")
    print(f"modelo completo: {len(COMPLETO)} atributos   EPV = {int(y.sum())/(len(COMPLETO)+1):.1f}")
    print(f"modelo reduzido: {len(REDUZIDO)} atributos   EPV = {int(y.sum())/(len(REDUZIDO)+1):.1f}")
    print(f"retirados: {', '.join(RETIRADOS)}\n")

    rskf = RepeatedStratifiedKFold(n_splits=args.particoes, n_repeats=args.repeticoes,
                                   random_state=args.semente)
    acc = {k: {m: [] for m in ("bal", "macro_f1", "mcc", "sens", "esp")} for k in X}
    oof = {k: np.full((args.repeticoes, len(y)), -1) for k in X}

    for i, (itr, ite) in enumerate(rskf.split(X["completo"], chave)):
        rep = i // args.particoes
        for nome, M in X.items():
            beta = _firth.firth_logistic(M[itr], y[itr])["beta"]
            pred = (_firth.prever_prob(M[ite], beta) >= 0.5).astype(int)
            m = metricas(y[ite], pred)
            for k in acc[nome]:
                acc[nome][k].append(m[k])
            oof[nome][rep, ite] = pred

    k, r = args.particoes, args.repeticoes
    fator = (1.0 / (k * r)) + ((len(y) / k) / (len(y) - len(y) / k))

    def resume(v):
        v = np.asarray(v); m = float(np.mean(v))
        return m, 1.96 * sqrt(fator * np.var(v, ddof=1))

    print("=" * 92)
    print("DESEMPENHO  (media e margem de 95% com variancia corrigida)")
    print("=" * 92)
    print(f"  {'modelo':14}{'bal.acc':>20}{'macro-F1':>16}{'MCC':>18}{'sens':>8}{'esp':>8}")
    linhas = []
    for nome in ("completo", "reduzido"):
        b = resume(acc[nome]["bal"]); f = resume(acc[nome]["macro_f1"])
        c = resume(acc[nome]["mcc"]); s = resume(acc[nome]["sens"]); e = resume(acc[nome]["esp"])
        print(f"  {nome:14}{b[0]*100:8.1f} ± {b[1]*100:4.1f}{f[0]*100:11.1f} ± {f[1]*100:4.1f}"
              f"{c[0]:12.3f} ± {c[1]:5.3f}{s[0]*100:8.1f}{e[0]*100:8.1f}")
        linhas.append({"modelo": nome, "n_atributos": len(COMPLETO if nome == "completo" else REDUZIDO),
                       "bal_acc": b[0], "margem": b[1], "macro_f1": f[0], "mcc": c[0],
                       "sens": s[0], "esp": e[0]})

    dif_b = np.mean(acc["completo"]["bal"]) - np.mean(acc["reduzido"]["bal"])
    dif_m = np.mean(acc["completo"]["mcc"]) - np.mean(acc["reduzido"]["mcc"])
    print(f"\n  diferenca completo menos reduzido: {dif_b*100:+.2f} pp de acuracia balanceada, "
          f"{dif_m:+.4f} de MCC")

    print("\n" + "=" * 92)
    print("McNEMAR")
    print("=" * 92)
    def mcnemar(pa, pb):
        ps = []
        for rep in range(args.repeticoes):
            a, b = pa[rep], pb[rep]
            ok = a >= 0
            n01 = int(np.sum((a[ok] == y[ok]) & (b[ok] != y[ok])))
            n10 = int(np.sum((a[ok] != y[ok]) & (b[ok] == y[ok])))
            if n01 + n10:
                ps.append(binomtest(n01, n01 + n10, 0.5).pvalue)
        return np.array(ps) if ps else np.array([1.0])

    for nome in ("completo", "reduzido"):
        p = mcnemar(oof[nome], np.tile(regex, (args.repeticoes, 1)))
        print(f"  {nome:10} contra o detector por regra: p mediano = {np.median(p):.2e}   "
              f"repeticoes com p<0,05: {int(np.sum(p < 0.05))}/{len(p)}")
    p = mcnemar(oof["completo"], oof["reduzido"])
    print(f"  completo contra reduzido:            p mediano = {np.median(p):.3f}   "
          f"repeticoes com p<0,05: {int(np.sum(p < 0.05))}/{len(p)}")

    print("\n" + "=" * 92)
    print("COEFICIENTES DO MODELO REDUZIDO  (ajuste sobre a amostra integral)")
    print("=" * 92)
    beta = _firth.firth_logistic(X["reduzido"], y)["beta"]
    print(f"  {'termo':28}{'beta':>9}{'RC':>10}{'IC 95% (perfil)':>24}{'p':>11}")
    for j, nome in enumerate(["intercepto"] + REDUZIDO):
        ic = _firth.ic_perfil(X["reduzido"], y, j)
        trv = _firth.razao_verossimilhanca_penalizada(X["reduzido"], y, j)
        rc = exp(beta[j]) if abs(beta[j]) < 700 else float("inf")
        print(f"  {nome:28}{beta[j]:9.3f}{rc:10.2f}"
              f"   [{ic['inferior']:7.3f},{ic['superior']:7.3f}]{trv['p']:11.2e}")

    print("\n" + "=" * 92)
    print("LEITURA")
    print("=" * 92)
    if abs(dif_b) < 0.02 and np.median(mcnemar(oof['completo'], oof['reduzido'])) > 0.05:
        print("  Os dois modelos sao indistinguiveis. A conclusao do trabalho nao depende dos")
        print("  tres atributos imprecisos. O modelo completo permanece como principal, por ter")
        print("  sido declarado antes da observacao dos resultados.")
    else:
        print("  Os modelos divergem. Convem examinar se os atributos retirados carregam sinal")
        print("  que os intervalos amplos nao revelaram.")

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(linhas)
    print(f"\nsaida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
