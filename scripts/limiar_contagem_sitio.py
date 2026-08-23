# -*- coding: utf-8 -*-
"""Efeito do limiar de contagem sobre a decisao por sitio nas variaveis textuais.

POR QUE ESTE PROGRAMA EXISTE
----------------------------
O classificador decide SENTENCA a sentenca; o que chega ao analista e a decisao por
SITIO. A regra de agregacao em vigor marca o sitio como positivo quando ao menos uma
sentenca e sinalizada, o que equivale a fixar em um o limiar de contagem. O valor nao
foi escolhido por evidencia: e o que decorre de converter uma lista em booleano.

A consequencia e direcional e desfavoravel ao uso pretendido. A classe de interesse
declarada no trabalho e a AUSENCIA do sinal, porque o produto util e a reducao do
conjunto que exige exame humano. Um falso positivo de presenca e, do ponto de vista
dessa classe, um falso negativo: o sitio que nao divulga, mas que teve uma sentenca
espuria sinalizada, sai da fila e nao e examinado. Quanto menor o limiar, mais isso
acontece.

Este programa nao escolhe o limiar. Ele mede o que cada valor produz, para que a
escolha caiba a quem opera a triagem — que e quem conhece a razao entre esforco de
verificacao e cobertura que pode sustentar.

POR QUE A AVALIACAO E POR SITIO, E NAO POR SENTENCA
---------------------------------------------------
As metricas ja reportadas sao todas em nivel de sentenca. Elas descrevem o
classificador, nao o produto. A rotulagem de referencia dos 280 sitios traz rotulo
por SITIO para as tres variaveis, e e contra ele que a decisao agregada precisa ser
confrontada.

POPULACAO AVALIADA
------------------
Restringe-se aos sitios em que o anotador registrou politica com corpo avaliavel
(`status = text`). Duas exclusoes, ambas necessarias:

  Sitios sem politica. O anotador os rotula ZERO nas tres variaveis, por definicao;
  o arcabouco devolve NAO APLICAVEL, por forca da dependencia declarada. Nao sao a
  mesma coisa, e compara-los somaria ao acerto uma coincidencia que nenhum
  julgamento produziu.

  Sitios sem avaliabilidade. Sem texto nao ha o que decidir.

Reporta-se em separado, e nao se descarta em silencio, a divergencia entre o
anotador e o detector de politica: sitio que o anotador julgou dotado de texto e em
que o arcabouco nao detectou politica sai com NAO APLICAVEL e nao admite comparacao.

CONTAMINACAO
------------
As quinze politicas do conjunto de treino estao dentro dos 280 rotulados. A medida
principal sai sobre os sitios FORA delas; a lista de treino e derivada de
`outputs/segmentos_rotulados.csv`, e nao declarada a mao, de sorte que acompanha o
conjunto se ele mudar. Os sitios de treino sao reportados a parte, para que a
diferenca entre dentro e fora da amostra de ajuste fique visivel.

O QUE SE REPORTA
----------------
Por variavel e por limiar, a matriz de confusao completa em relacao a PRESENCA, e as
duas medidas da classe de interesse:

    revocacao da ausencia   VN / (VN + FP)   dos sitios que nao divulgam, quantos a
                                             triagem retem para exame
    precisao da ausencia    VN / (VN + FN)   dos sitios retidos, quantos de fato nao
                                             divulgam

Acompanha o coeficiente de Matthews, que e simetrico entre as classes e nao se deixa
enganar por prevalencia desequilibrada, e o tamanho da fila que cada limiar produz.

Os intervalos sao de Wilson. Em finalidade a classe negativa por sitio e pequena, e o
intervalo precisa acompanhar o ponto sob pena de sugerir precisao inexistente.

DISTRIBUICAO OBSERVADA
----------------------
Reporta-se ainda a distribuicao empirica do numero de sentencas sinalizadas nos
sitios que NAO divulgam. E ela, e nao suposicao de forma, que diz quanto ruido cada
documento produz.

Uso:
    python scripts/limiar_contagem_sitio.py
    python scripts/limiar_contagem_sitio.py --run-id <uuid> --limiares 1,2,3,5,10
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Nome da variavel no arcabouco -> nome da coluna na rotulagem de referencia.
VARIAVEIS = {
    "finalidade_especificada": "finalidade",
    "direitos_titular_explicados": "direitos_titular",
    "transf_internacional_divulgada": "transf_internacional",
}

Z = 1.96


# --------------------------------------------------------------------- medidas
def wilson(k: int, n: int, z: float = Z) -> tuple[float, float]:
    """Intervalo de Wilson para uma proporcao. Preferido a aproximacao normal
    porque nao ultrapassa os limites do intervalo unitario nem colapsa quando a
    contagem se aproxima de zero ou do total."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def matthews(vp: int, fp: int, fn: int, vn: int) -> float:
    num = vp * vn - fp * fn
    den = math.sqrt((vp + fp) * (vp + fn) * (vn + fp) * (vn + fn))
    return num / den if den else 0.0


def pct(x: float) -> str:
    return "n/d" if x != x else f"{x * 100:.1f}"


# ----------------------------------------------------------------- leitura
def hospedeiro(url: str) -> str:
    return (url.replace("https://", "").replace("http://", "")
            .rstrip("/").lower())


def valor_bruto(v) -> str:
    """A camada de resultados grava booleano sem aspas e estado como cadeia em
    notacao de objetos. Ambas as formas chegam aqui."""
    s = str(v).strip().strip('"').lower()
    return s


def le_rotulos(caminho: Path) -> dict[str, dict]:
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        return {r["site_id"]: r for r in csv.DictReader(fh, delimiter=";")}


def le_treino(caminho: Path) -> set[str]:
    if not caminho.exists():
        return set()
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        return {r["site_id"] for r in csv.DictReader(fh, delimiter=";")}


def escolhe_execucao(con: sqlite3.Connection, pedido: str | None) -> str:
    linhas = list(con.execute("select run_id, started_at from runs order by started_at"))
    if not linhas:
        sys.exit("ERRO: o banco nao registra execucao alguma.")
    if pedido:
        ids = [r[0] for r in linhas]
        if pedido not in ids:
            sys.exit(f"ERRO: execucao {pedido} ausente do banco. Disponiveis: {ids}")
        return pedido
    if len(linhas) > 1:
        print(f"AVISO: o banco tem {len(linhas)} execucoes; adota-se a mais recente.")
        for rid, ts in linhas:
            print(f"        {rid}  {ts}")
    return linhas[-1][0]


def le_predicoes(con: sqlite3.Connection, run_id: str, variavel: str) -> dict[str, dict]:
    saida: dict[str, dict] = {}
    consulta = ("select domain_url, value, audit_trail_json from variables "
                "where run_id = ? and variable_name = ?")
    for url, valor, trilha_json in con.execute(consulta, (run_id, variavel)):
        t = json.loads(trilha_json) if trilha_json else {}
        saida[hospedeiro(url)] = {
            "estado": valor_bruto(valor),
            "n_sinalizadas": t.get("n_sentencas_sinalizadas"),
            "n_segmentos": t.get("n_segmentos_avaliados"),
            "extrapolacao": t.get("extrapolacao"),
            "motivo": t.get("motivo", ""),
            "modelo_sha256": t.get("modelo_sha256", ""),
        }
    return saida


# ----------------------------------------------------------------- principal
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="data/simulacao/analista.sqlite")
    ap.add_argument("--run-id", default=None, help="execucao a considerar; na omissao, a mais recente")
    ap.add_argument("--rotulos", default="rotulagem_b9.csv")
    ap.add_argument("--treino", default="outputs/segmentos_rotulados.csv")
    ap.add_argument("--limiares", default="1,2,3,4,5,7,10")
    ap.add_argument("--out", default="outputs/limiar_contagem_sitio.csv")
    ap.add_argument("--out-detalhe", default="outputs/limiar_contagem_sitio_detalhe.csv")
    a = ap.parse_args()

    limiares = [int(x) for x in a.limiares.split(",") if x.strip()]
    banco = REPO / a.banco
    if not banco.exists():
        sys.exit(f"ERRO: banco ausente em {banco}")

    rot = le_rotulos(REPO / a.rotulos)
    treino = le_treino(REPO / a.treino)
    con = sqlite3.connect(banco)
    run_id = escolhe_execucao(con, a.run_id)

    print("=" * 96)
    print("EFEITO DO LIMIAR DE CONTAGEM SOBRE A DECISAO POR SITIO")
    print("=" * 96)
    print(f"banco      : {banco}")
    print(f"execucao   : {run_id}")
    print(f"rotulagem  : {a.rotulos}  ({len(rot)} sitios)")
    print(f"treino     : {a.treino}  ({len(treino)} politicas)")
    print(f"limiares   : {limiares}")
    print()

    linhas_saida: list[dict] = []
    linhas_detalhe: list[dict] = []

    for variavel, coluna in VARIAVEIS.items():
        pred = le_predicoes(con, run_id, variavel)
        if not pred:
            print(f"AVISO: {variavel} ausente da execucao {run_id}; variavel ignorada.\n")
            continue

        shas = {p["modelo_sha256"] for p in pred.values() if p["modelo_sha256"]}

        # --- funil de elegibilidade, contado e reportado ---
        com_texto = [s for s, r in rot.items() if r.get("status") == "text"]
        sem_par = [s for s in com_texto if s not in pred]
        pareados = [s for s in com_texto if s in pred]
        sem_medicao = [s for s in pareados
                       if pred[s]["estado"] in ("nao_aplicavel", "nao_coletado",
                                                "unidade_inexistente")]
        avaliaveis = [s for s in pareados if s not in set(sem_medicao)]
        sem_rotulo = [s for s in avaliaveis if rot[s].get(coluna) not in ("0", "1")]
        avaliaveis = [s for s in avaliaveis if s not in set(sem_rotulo)]
        dentro = [s for s in avaliaveis if s in treino]
        fora = [s for s in avaliaveis if s not in treino]

        print("=" * 96)
        print(f"{variavel}   (coluna de referencia: {coluna})")
        print("-" * 96)
        print(f"  sitios com politica em texto na rotulagem      : {len(com_texto)}")
        if sem_par:
            print(f"  sem correspondencia na execucao               : {len(sem_par)}  {sem_par[:4]}")
        if sem_medicao:
            print(f"  sem medicao (precondicao ou coleta)           : {len(sem_medicao)}"
                  f"   <- divergencia entre anotador e detector de politica")
        if sem_rotulo:
            print(f"  sem rotulo utilizavel na referencia           : {len(sem_rotulo)}")
        print(f"  avaliaveis                                    : {len(avaliaveis)}")
        print(f"    dentro do conjunto de treino                : {len(dentro)}")
        print(f"    FORA do conjunto de treino  (base principal): {len(fora)}")
        if len(shas) > 1:
            print(f"  ATENCAO: {len(shas)} artefatos distintos na mesma execucao")
        print()

        for s in avaliaveis:
            p = pred[s]
            linhas_detalhe.append({
                "variavel": variavel, "site_id": s,
                "estrato": rot[s].get("estrato", ""),
                "no_treino": int(s in treino),
                "rotulo": rot[s][coluna],
                "n_sinalizadas": p["n_sinalizadas"],
                "n_segmentos": p["n_segmentos"],
                "estado_arcabouco": p["estado"],
                "extrapolacao": p["extrapolacao"],
                "incerto": rot[s].get(f"{coluna.split('_')[0]}_incerto", ""),
            })

        for rotulo_base, conjunto in (("fora do treino", fora), ("no treino", dentro)):
            if not conjunto:
                continue
            pos = sum(1 for s in conjunto if rot[s][coluna] == "1")
            neg = len(conjunto) - pos
            print(f"  --- {rotulo_base}: n = {len(conjunto)}, "
                  f"divulgam = {pos}, NAO divulgam = {neg} "
                  f"(prevalencia {pos / len(conjunto) * 100:.1f}%) ---")

            if neg == 0:
                print("      classe negativa vazia; nenhuma medida da ausencia e definivel.\n")
                continue

            # distribuicao observada do ruido nos sitios que NAO divulgam
            ruido = sorted(pred[s]["n_sinalizadas"] or 0
                           for s in conjunto if rot[s][coluna] == "0")
            com_ruido = sum(1 for x in ruido if x >= 1)
            print(f"      sentencas sinalizadas nos {neg} que NAO divulgam: "
                  f"min {ruido[0]}, mediana {ruido[len(ruido) // 2]}, max {ruido[-1]}; "
                  f"com ao menos uma: {com_ruido} ({com_ruido / neg * 100:.1f}%)")
            print(f"      distribuicao: {dict(sorted(Counter(ruido).items()))}")
            print()

            cab = (f"      {'c':>3} {'VP':>4} {'FP':>4} {'FN':>4} {'VN':>4} "
                   f"{'rev.aus':>9} {'IC 95%':>15} {'prec.aus':>9} {'IC 95%':>15} "
                   f"{'MCC':>7} {'fila':>6}")
            print(cab)
            print("      " + "-" * (len(cab) - 6))
            for c in limiares:
                vp = fp = fn = vn = 0
                for s in conjunto:
                    n = pred[s]["n_sinalizadas"] or 0
                    previsto = 1 if n >= c else 0
                    real = 1 if rot[s][coluna] == "1" else 0
                    if real and previsto:
                        vp += 1
                    elif not real and previsto:
                        fp += 1
                    elif real and not previsto:
                        fn += 1
                    else:
                        vn += 1
                rev = vn / (vn + fp) if (vn + fp) else float("nan")
                pre = vn / (vn + fn) if (vn + fn) else float("nan")
                rlo, rhi = wilson(vn, vn + fp)
                plo, phi = wilson(vn, vn + fn) if (vn + fn) else (float("nan"),) * 2
                fila = vn + fn
                print(f"      {c:>3} {vp:>4} {fp:>4} {fn:>4} {vn:>4} "
                      f"{pct(rev):>9} {'[' + pct(rlo) + '; ' + pct(rhi) + ']':>15} "
                      f"{pct(pre):>9} {'[' + pct(plo) + '; ' + pct(phi) + ']':>15} "
                      f"{matthews(vp, fp, fn, vn):>7.3f} {fila:>6}")
                linhas_saida.append({
                    "variavel": variavel, "conjunto": rotulo_base, "limiar": c,
                    "n": len(conjunto), "divulgam": pos, "nao_divulgam": neg,
                    "VP": vp, "FP": fp, "FN": fn, "VN": vn,
                    "revocacao_ausencia": round(rev, 4),
                    "rev_ic_inf": round(rlo, 4), "rev_ic_sup": round(rhi, 4),
                    "precisao_ausencia": round(pre, 4) if pre == pre else "",
                    "prec_ic_inf": round(plo, 4) if plo == plo else "",
                    "prec_ic_sup": round(phi, 4) if phi == phi else "",
                    "matthews": round(matthews(vp, fp, fn, vn), 4),
                    "tamanho_da_fila": fila,
                    "run_id": run_id,
                })
            print()

    if not linhas_saida:
        sys.exit("ERRO: nenhuma variavel produziu resultado. Confira --run-id e --banco.")

    alvo = REPO / a.out
    alvo.parent.mkdir(parents=True, exist_ok=True)
    with alvo.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas_saida[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(linhas_saida)

    alvo_d = REPO / a.out_detalhe
    with alvo_d.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas_detalhe[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(linhas_detalhe)

    print("=" * 96)
    print(f"gravado: {alvo}")
    print(f"gravado: {alvo_d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
