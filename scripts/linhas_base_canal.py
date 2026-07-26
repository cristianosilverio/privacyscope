# -*- coding: utf-8 -*-
"""Linhas de base para ``tem_canal_titular``.

O desempenho de um classificador so adquire significado quando confrontado com o
que se obtem sem modelo. Reportam-se tres referencias, em exigencia crescente:

  1. Classe majoritaria — piso absoluto, sem informacao.
  2. Detector por regra — F1 ou F4, correspondente a ``tests/canal_titular.py``.
     Constitui a comparacao central do trabalho.
  3. Melhor atributo isolado — se o conjunto completo nao o superar de forma
     defensavel, a engenharia de atributos nao se justifica.

As referencias 1 e 2 sao regras deterministicas definidas previamente, sem
ajuste; sua medida na amostra e estimativa nao enviesada. A referencia 3 decorre
de selecao conduzida sobre os mesmos dados e e, portanto, otimista. Os oito
atributos sao impressos individualmente e o melhor vem assinalado, de modo que o
valor seja lido como teto de referencia e nao como desempenho estimado.

Metricas. A manchete e simetrica — acuracia balanceada, macro-F1 e MCC —, o que
neutraliza a inversao da classe minoritaria entre as variaveis do protocolo.
Sensibilidade e especificidade acompanham separadamente. A acuracia simples nao
figura como metrica principal: sob desbalanceamento ela induz leitura equivocada.

Leitura de triagem. O framework destina-se a apoiar a etapa de Monitoramento, na
qual interessa localizar os sitios que nao divulgam. A classe-alvo operacional e,
portanto, a ausencia (y=0). Reportam-se a taxa de sinalizacao, a precisao sobre a
ausencia e o numero necessario a revisar (NNR = 1/precisao), que expressa quantos
sitios um analista examina para identificar uma lacuna efetiva.

Uso:
    python scripts/linhas_base_canal.py
"""
from __future__ import annotations

import argparse
import csv
from math import sqrt
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FEATS = ["F1_email_lgpd_proprio", "F2_email_lgpd_externo", "F3_email_generico_ancorado",
         "F4_subpagina_titular", "F5_contato_ancorado", "F6_telefone_ancorado",
         "F7_ancora_encarregado", "F8_ancora_direitos"]
REGEX_FEATS = ["F1_email_lgpd_proprio", "F4_subpagina_titular"]   # detector por regra


def matriz(y, pred):
    """(vp, vn, fp, fn) tomando y=1 como positivo."""
    vp = sum(1 for a, b in zip(y, pred) if a == 1 and b == 1)
    vn = sum(1 for a, b in zip(y, pred) if a == 0 and b == 0)
    fp = sum(1 for a, b in zip(y, pred) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y, pred) if a == 1 and b == 0)
    return vp, vn, fp, fn


def metricas(y, pred) -> dict:
    vp, vn, fp, fn = matriz(y, pred)
    sens = vp / (vp + fn) if (vp + fn) else 0.0          # revocacao da classe 1
    esp = vn / (vn + fp) if (vn + fp) else 0.0           # revocacao da classe 0
    bal = (sens + esp) / 2
    # F1 de cada classe -> macro
    p1 = vp / (vp + fp) if (vp + fp) else 0.0
    f1_1 = 2 * p1 * sens / (p1 + sens) if (p1 + sens) else 0.0
    p0 = vn / (vn + fn) if (vn + fn) else 0.0
    f1_0 = 2 * p0 * esp / (p0 + esp) if (p0 + esp) else 0.0
    macro_f1 = (f1_0 + f1_1) / 2
    den = sqrt((vp + fp) * (vp + fn) * (vn + fp) * (vn + fn))
    mcc = ((vp * vn - fp * fn) / den) if den else 0.0
    # Leitura de triagem: classe-alvo e a ausencia (y=0); sinalizado = predicao 0.
    sinal = vn + fn                                       # encaminhados a revisao
    prec_aus = vn / sinal if sinal else 0.0               # proporcao de lacunas efetivas
    nnr = (1 / prec_aus) if prec_aus else float("inf")
    return dict(sens=sens, esp=esp, bal=bal, macro_f1=macro_f1, mcc=mcc,
                acc=(vp + vn) / len(y), taxa_sinal=sinal / len(y),
                prec_aus=prec_aus, nnr=nnr, vp=vp, vn=vn, fp=fp, fn=fn)


def linha(nome, m, marca=""):
    nnr = "inf" if m["nnr"] == float("inf") else f"{m['nnr']:.2f}"
    print(f"  {nome:34}{m['bal']*100:7.1f}{m['macro_f1']*100:9.1f}{m['mcc']:8.3f}"
          f"{m['sens']*100:8.1f}{m['esp']*100:8.1f}   {m['taxa_sinal']*100:5.1f}%"
          f"{m['prec_aus']*100:8.1f}%{nnr:>7}  {marca}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="outputs/features_canal_N200.csv")
    args = ap.parse_args()

    with (REPO / args.features).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    y = [int(r["y"]) for r in R]
    n1, n0 = sum(y), len(y) - sum(y)
    print(f"sitios: {len(y)}  |  com canal (y=1): {n1}  |  sem canal (y=0): {n0}")
    print(f"prevalencia da AUSENCIA (alvo da triagem): {n0/len(y)*100:.1f}%")
    print(f"teto de trabalho poupado (classificador perfeito): {(1-n0/len(y))*100:.1f}%")

    cab = (f"\n  {'linha de base':34}{'bal.acc':>7}{'macroF1':>9}{'MCC':>8}"
           f"{'sens':>8}{'esp':>8}{'sinaliz':>9}{'prec.aus':>9}{'NNR':>7}")
    print("\n" + "=" * 108)
    print("LINHAS DE BASE" + " " * 34 + "|-------- manchete --------|  |--- triagem (ausencia) ---|")
    print("=" * 108 + cab)
    print("  " + "-" * 104)

    # 1) classe majoritaria
    maj = 1 if n1 >= n0 else 0
    linha("1. classe majoritaria", metricas(y, [maj] * len(y)),
          "<- piso absoluto")

    # 2) detector por regra (F1 ou F4)
    pred_rx = [1 if any(r[f] == "1" for f in REGEX_FEATS) else 0 for r in R]
    m_rx = metricas(y, pred_rx)
    linha("2. detector por regra (F1 ou F4)", m_rx, "<- referencia central")

    # 3) cada atributo isolado
    print("  " + "-" * 104)
    melhor, m_melhor = None, None
    for f in FEATS:
        pred = [1 if r[f] == "1" else 0 for r in R]
        m = metricas(y, pred)
        if m_melhor is None or m["bal"] > m_melhor["bal"]:
            melhor, m_melhor = f, m
        linha(f"3. so {f}", m)
    print("  " + "-" * 104)
    linha(f">>> melhor atributo isolado: {melhor.split('_')[0]}", m_melhor,
          "<- OTIMISTA (selecao)")

    print("\n" + "=" * 108)
    print("COMO LER")
    print("=" * 108)
    print(f"  Referencia central: linha 2 (bal.acc {m_rx['bal']*100:.1f}%, MCC {m_rx['mcc']:.3f}).")
    print(f"  O conjunto completo deve superar tambem a linha 3 ({melhor.split('_')[0]}, "
          f"bal.acc {m_melhor['bal']*100:.1f}%), sob pena de nao se justificar.")
    print("  'sinaliz' = fracao do corpus mandada a revisao humana; 'prec.aus' = quantos")
    print("  desses sao lacuna real; NNR = sitios revisados por lacuna encontrada.")
    print("\n  A linha 3 e otimista: o melhor atributo foi selecionado sobre os mesmos")
    print("  dados. As linhas 1 e 2 sao regras previas, sem ajuste, e constituem")
    print("  estimativas nao enviesadas ainda que medidas na amostra.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
