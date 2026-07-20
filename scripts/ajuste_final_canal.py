# -*- coding: utf-8 -*-
"""Ajuste final do classificador de ``tem_canal_titular`` sobre a amostra inteira.

PROPOSITO
---------
Produz a equacao publicavel e a inferencia por coeficiente. Difere de
scripts/modelar_canal.py, que estima DESEMPENHO por validacao cruzada. Sao
finalidades distintas e nao intercambiaveis:

  - o desempenho provem exclusivamente da validacao cruzada, que avalia cada
    sitio por um modelo que nao o utilizou no ajuste;
  - a equacao e os intervalos provem deste ajuste unico sobre os 207 sitios,
    porque media de coeficientes ao longo das particoes nao equivale ao ajuste
    sobre os dados completos.

Nenhuma metrica de acerto e emitida aqui. Metrica calculada sobre a mesma amostra
usada no ajuste e otimista por construcao, e reporta-la ao lado dos coeficientes
convidaria a confusao entre as duas finalidades.

INFERENCIA
----------
Intervalos por perfil da verossimilhanca penalizada e testes da razao de
verossimilhancas, conforme Heinze e Schemper (2002). O erro-padrao de Wald e
exibido apenas para evidenciar a divergencia nos coeficientes sob separacao, onde
o intervalo simetrico nao se sustenta.

Nao se aplica correcao para multiplicidade aos oito coeficientes. A hipotese
central do trabalho — superioridade sobre o detector por regra — e avaliada por
um unico teste de McNemar em scripts/modelar_canal.py; os coeficientes cumprem
papel descritivo, de leitura da contribuicao de cada sinal. A ausencia de
correcao e declarada no texto.

INTERPRETACAO DO INTERCEPTO
---------------------------
O intercepto reflete a composicao da amostra rotulada, cuja prevalencia de
ausencia e de 50,7%, e nao a prevalencia populacional. As probabilidades preditas
estao calibradas para essa amostra. A estimativa populacional de prevalencia
provem do detector automatico com correcao de Rogan-Gladen sobre a amostra
integral, procedimento independente deste ajuste.

Uso:
    python scripts/ajuste_final_canal.py
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
from math import exp
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("firth", REPO / "scripts" / "firth.py")
_firth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_firth)

FEATS = ["F1_email_lgpd_proprio", "F2_email_lgpd_externo", "F3_email_generico_ancorado",
         "F4_subpagina_titular", "F5_contato_ancorado", "F6_telefone_ancorado",
         "F7_ancora_encarregado", "F8_ancora_direitos"]


def formata_p(p):
    return "<1e-16" if p < 1e-16 else f"{p:.2e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="outputs/features_canal_N200.csv")
    ap.add_argument("--nivel", type=float, default=0.95)
    ap.add_argument("--out", default="outputs/coeficientes_canal.csv")
    args = ap.parse_args()

    with (REPO / args.features).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    X = np.array([[int(r[f]) for f in FEATS] for r in R], dtype=float)
    y = np.array([int(r["y"]) for r in R], dtype=float)

    ajuste = _firth.firth_logistic(X, y)
    beta = ajuste["beta"]
    ep = _firth.erro_padrao_wald(X, y, beta)
    z = 1.959963984540054                       # quantil normal de duas caudas

    print(f"sitios: {len(y)}   com canal: {int(y.sum())}   sem canal: {int((1-y).sum())}")
    print(f"convergiu: {ajuste['convergiu']} em {ajuste['iteracoes']} iteracoes")
    print(f"log-verossimilhanca penalizada: {ajuste['loglik_penalizada']:.4f}\n")

    # ocorrencias de cada atributo, para dimensionar a precisao das estimativas
    print("=" * 104)
    print(f"COEFICIENTES  (perfil da verossimilhanca penalizada, {args.nivel:.0%})")
    print("=" * 104)
    print(f"  {'termo':28}{'ocorr':>7}{'beta':>9}{'RC':>10}"
          f"{'IC perfil':>22}{'p (TRV)':>12}{'IC Wald':>20}")

    linhas = []
    nomes = ["intercepto"] + FEATS
    for j, nome in enumerate(nomes):
        ic = _firth.ic_perfil(X, y, j, nivel=args.nivel)
        trv = _firth.razao_verossimilhanca_penalizada(X, y, j)
        ocorr = "" if j == 0 else f"{int(X[:, j-1].sum())}"
        rc = exp(beta[j]) if abs(beta[j]) < 700 else float("inf")
        wald = f"[{beta[j]-z*ep[j]:6.2f},{beta[j]+z*ep[j]:6.2f}]"
        print(f"  {nome:28}{ocorr:>7}{beta[j]:9.3f}{rc:10.2f}"
              f"   [{ic['inferior']:7.3f},{ic['superior']:7.3f}]"
              f"{formata_p(trv['p']):>12}{wald:>20}")
        linhas.append({"termo": nome, "ocorrencias": ocorr, "beta": beta[j],
                       "razao_chances": rc, "ic_inferior": ic["inferior"],
                       "ic_superior": ic["superior"], "identificado": ic["identificado"],
                       "qui2": trv["qui2"], "p": trv["p"],
                       "ep_wald": ep[j], "assimetria_ic": (ic["superior"] - beta[j])
                       / (beta[j] - ic["inferior"]) if beta[j] > ic["inferior"] else float("nan")})

    print("\n" + "=" * 104)
    print("EQUACAO")
    print("=" * 104)
    termos = [f"{beta[0]:.3f}"] + [
        f"{'+' if beta[j+1] >= 0 else '-'} {abs(beta[j+1]):.3f}*{f}"
        for j, f in enumerate(FEATS)]
    print("  ln(p/(1-p)) = " + " ".join(termos))
    print(f"\n  sem nenhum atributo: p = {1/(1+exp(-beta[0]))*100:.1f}%")
    print(f"  limiar de 0,5 exige soma dos atributos ativos acima de {-beta[0]:.3f}")

    print("\n" + "=" * 104)
    print("ADVERTENCIAS DE LEITURA")
    print("=" * 104)
    print("  Desempenho nao e reportado aqui; provem da validacao cruzada.")
    print("  Coeficientes com poucas ocorrencias sustentam intervalo largo e nao")
    print("  autorizam leitura substantiva; conferir a coluna de ocorrencias.")

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(linhas)
    print(f"\nsaida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
