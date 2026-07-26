# -*- coding: utf-8 -*-
"""Auditoria da engenharia de atributos de ``tem_canal_titular``.

A auditoria antecede o treinamento e verifica se os atributos extraidos
automaticamente alcancam os sinais registrados na rotulagem manual. Responde a
tres questoes:

  1. Cada atributo discrimina? (prevalencia por classe e lift)
  2. O extrator dispara onde a forma foi registrada? (alinhamento)
  3. Quantos positivos permanecem inalcancaveis? (teto de revocacao)

Os atributos derivam do texto da evidencia; o campo ``canal_forma`` nao integra o
conjunto de entrada do modelo. Seu uso aqui e exclusivamente de auditoria.
Empregar as formas como atributo implicaria prever o rotulo a partir de um
derivado do proprio rotulo, e o desempenho resultante careceria de sentido.

Interpretacao da secao 2. Uma taxa baixa de alinhamento nao caracteriza defeito
de implementacao. Os dois criterios divergem por construcao: a rotulagem aplicou
criterio semantico — se o contato constitui canal do Encarregado do controlador —
enquanto o atributo aplica criterio sintatico — se ha prefixo de privacidade no
dominio proprio. A divergencia e, em si, resultado do trabalho.

Dois casos ilustram o padrao na coleta b9. Em ``planalto.gov.br`` o Encarregado
responde por ``encarregado.lgpd@presidencia.gov.br``: em orgaos publicos o
contato costuma residir no dominio do orgao-pai, o que a rotulagem tratou como
controlador e o extrator classifica como dominio externo (F2). Em
``realoficial.com.br`` o contato e ``antonio@realoficial.com.br``, sem prefixo de
privacidade, situacao coberta por F3 e nao por F1.

Por essa razao a secao 2 distingue "nao disparou o par" de "perda real", esta
ultima definida como ausencia de qualquer um dos oito atributos. Apenas a
segunda representa sinal perdido.

Uso:
    python scripts/auditar_features_canal.py
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FEATS = [
    "F1_email_lgpd_proprio", "F2_email_lgpd_externo", "F3_email_generico_ancorado",
    "F4_subpagina_titular", "F5_contato_ancorado", "F6_telefone_ancorado",
    "F7_ancora_encarregado", "F8_ancora_direitos",
]

# Correspondencia nominal entre forma registrada e atributo. Uso restrito a auditoria.
PARES = [
    ("forma:email_lgpd_controlador",  "F1_email_lgpd_proprio"),
    ("forma:email_grupo_controlador", "F2_email_lgpd_externo"),
    ("forma:email_generico_rotulado", "F3_email_generico_ancorado"),
    ("forma:subpagina_canal_titular", "F4_subpagina_titular"),
    ("forma:subpagina_encarregado",   "F4_subpagina_titular"),
    ("forma:formulario_direitos",     "F5_contato_ancorado"),
    ("forma:telefone_encarregado",    "F6_telefone_ancorado"),
]

# Sinais cobertos pelo detector por regra. A linha de base fica aninhada no
# conjunto, o que sustenta a comparacao por McNemar entre modelos aninhados.
REGEX_FEATS = ["F1_email_lgpd_proprio", "F4_subpagina_titular"]


def nz(v) -> str:
    return (v or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="outputs/features_canal_N200.csv")
    ap.add_argument("--rotulos", default="rotulagem_b9.csv")
    args = ap.parse_args()

    with (REPO / args.features).open(encoding="utf-8", newline="") as fh:
        F = {r["site_id"]: r for r in csv.DictReader(fh, delimiter=";")}
    with (REPO / args.rotulos).open(encoding="utf-8-sig", newline="") as fh:
        R = {nz(r["site_id"]): r for r in csv.DictReader(fh, delimiter=";")}

    pos = [h for h in F if F[h]["y"] == "1"]
    neg = [h for h in F if F[h]["y"] == "0"]
    print(f"sitios: {len(F)}  |  positivos: {len(pos)}  |  negativos: {len(neg)}")

    # ---------------------------------------------------------------- 1
    print("\n" + "=" * 76)
    print("1. PREVALENCIA POR CLASSE E LIFT")
    print("   lift = P(atributo | y=1) / P(atributo | y=0). 'inf' = nunca aparece")
    print("   em negativo, ou seja, atributo de especificidade perfeita na amostra.")
    print("=" * 76)
    print(f"{'atributo':32}{'y=0':>16}{'y=1':>16}{'lift':>9}")
    for f in FEATS:
        a = sum(1 for h in neg if F[h][f] == "1")
        b = sum(1 for h in pos if F[h][f] == "1")
        lift = (b / len(pos)) / (a / len(neg)) if a else float("inf")
        ls = "  inf" if lift == float("inf") else f"{lift:5.1f}x"
        print(f"{f:32}{a:>5}/{len(neg)} ({a/len(neg)*100:4.1f}%)"
              f"{b:>5}/{len(pos)} ({b/len(pos)*100:4.1f}%){ls:>9}")

    # ---------------------------------------------------------------- 2
    print("\n" + "=" * 76)
    print("2. ALINHAMENTO ENTRE CRITERIO SINTATICO E FORMA REGISTRADA")
    print("=" * 76)
    for forma, feat in PARES:
        alvo = [h for h in F if nz(R.get(h, {}).get(forma)) == "1"]
        if not alvo:
            print(f"\n{forma}  (nenhum caso na amostra)")
            continue
        miss = [h for h in alvo if F[h][feat] == "0"]
        perdidos = [h for h in miss if all(F[h][f] == "0" for f in FEATS)]
        salvos = len(miss) - len(perdidos)
        print(f"\n{forma}  (n={len(alvo)})  ->  {feat}")
        print(f"   par disparou ............ {len(alvo)-len(miss):3}  ({(len(alvo)-len(miss))/len(alvo)*100:5.1f}%)")
        print(f"   nao disparou ............ {len(miss):3}"
              f"   dos quais capturados por OUTRO atributo: {salvos}")
        print(f"   PERDA REAL (zero atrib.). {len(perdidos):3}")
        if perdidos:
            print(f"      {', '.join(perdidos)}")

    # ---------------------------------------------------------------- 3
    print("\n" + "=" * 76)
    print("3. TETO DE REVOCACAO")
    print("=" * 76)
    sem = [h for h in pos if all(F[h][f] == "0" for f in FEATS)]
    reg = [h for h in pos if any(F[h][f] == "1" for f in REGEX_FEATS)]
    ruido = [h for h in neg if any(F[h][f] == "1" for f in FEATS)]
    print(f"  conjunto dos 8 atributos ..... {(1-len(sem)/len(pos))*100:5.1f}%   "
          f"({len(pos)-len(sem)}/{len(pos)} positivos alcancaveis)")
    print(f"  detector por regra (F1+F4) ... {len(reg)/len(pos)*100:5.1f}%   ({len(reg)}/{len(pos)})")
    print(f"  ganho do conjunto ............ {((1-len(sem)/len(pos)) - len(reg)/len(pos))*100:+5.1f} pontos percentuais")
    print(f"\n  ruido: negativos com algum atributo ... {len(ruido)/len(neg)*100:5.1f}% ({len(ruido)}/{len(neg)})")
    print(f"  positivos INALCANCAVEIS (teto declarado): {len(sem)}")
    for h in sem:
        formas = [k.split(":")[1] for k in R.get(h, {})
                  if k.startswith("forma:") and nz(R[h][k]) == "1"]
        print(f"      {h:32.32} formas rotuladas: {formas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
