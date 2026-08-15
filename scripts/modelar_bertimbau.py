# -*- coding: utf-8 -*-
"""Confronto entre a representacao densa do BERTimbau e a esparsa, e contra a regra.

O QUE ESTE PROGRAMA ISOLA
-------------------------
Estimador, particao, procedimento de escolha do limiar, leque de regularizacao e
metrica sao os mesmos empregados na representacao esparsa. A unica coisa que difere e
a representacao: no lugar dos n-gramas ponderados, o vetor de 768 dimensoes produzido
pelo codificador congelado. Diferenca observada e atribuivel a representacao, e nao a
alguma folga de ajuste concedida a um dos lados.

Duas assimetrias remanescentes, declaradas porque nao foram eliminadas:

  A representacao esparsa e ajustada dentro de cada particao de treino, ao passo que o
  codificador foi pre-treinado sobre material externo. Nao ha vazamento do material de
  teste, porque o pre-treinamento nao viu os rotulos nem foi conduzido para esta
  tarefa, mas as duas representacoes nao consumiram a mesma quantidade de informacao.

  O vetor denso e normalizado por linha em norma L2, o mesmo que a representacao
  esparsa faz. A normalizacao e por observacao, e portanto nao transporta informacao
  entre particoes; padronizar por coluna transportaria, e exigiria estimar media e
  desvio dentro da dobra.

REGRA DE DECISAO, FIXADA ANTES DA EXECUCAO
------------------------------------------
Adota-se o preditor mais complexo apenas quando o intervalo pareado da diferenca de
coeficiente de Matthews EXCLUI zero. Empate resolve pelo mais simples, na ordem regra,
representacao esparsa, representacao densa.

A regra e declarada antes de conhecer os valores porque, com tres preditores e tres
variaveis sobre os mesmos quinze documentos, escolher o vencedor depois de ve-lo e
reportar a metrica dele produz estimativa otimista. E o mesmo vicio que se recusou ao
fixar a granularidade, quando se descartou treinar as duas alternativas e ficar com a
melhor.

Precisao e revocacao sao reportadas ao lado da metrica de decisao. O coeficiente de
Matthews e simetrico e desconhece que o contrato de saida do arcabouco e triagem com
verificacao humana; sob esse contrato, dois preditores de coeficiente equivalente mas
pontos de operacao distintos NAO sao equivalentes, e a escolha final considera qual
ponto serve ao uso.

A agregacao por [CLS] entra como VERIFICACAO DE ROBUSTEZ e nao e elegivel pela regra
de selecao: admiti-la como alternativa a escolher acrescentaria comparacoes sobre o
mesmo material, que e exatamente o que a regra existe para conter.

Uso:
    python scripts/extrair_vetores_bertimbau.py
    python scripts/modelar_textuais.py            # grava as predicoes da esparsa
    python scripts/modelar_bertimbau.py
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("lb", REPO / "scripts" / "linhas_base_textuais.py")
_lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lb)

VARIAVEIS = _lb.VARIAVEIS
ROTULO = _lb.ROTULO
GRADE_C = [0.01, 0.1, 1.0, 10.0, 80.0, 100.0, 150.0, 300.0, 1000.0]


def normaliza_linhas(X):
    n = np.linalg.norm(X, axis=1, keepdims=True)
    return X / np.maximum(n, 1e-12)


def ajusta(Xtr, ytr, Xte, C):
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(C=C, max_iter=3000, solver="liblinear")
    m.fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1]


def seleciona_interno(X, y, grupos, semente=0):
    """Escolhe conjuntamente a forca da regularizacao e o limiar de decisao.

    Reproduz o procedimento da representacao esparsa, inclusive a semente da particao
    interna, de modo que a comparacao nao seja contaminada por diferenca de sorteio.
    """
    unicos = np.unique(grupos)
    rng = np.random.default_rng(semente)
    dobras = np.array_split(rng.permutation(unicos), min(3, len(unicos)))
    melhor = (-2.0, GRADE_C[0], 0.5)
    for C in GRADE_C:
        prob = np.zeros(len(y))
        for d in dobras:
            te = np.isin(grupos, d)
            if te.all() or not te.any():
                continue
            prob[te] = ajusta(X[~te], y[~te], X[te], C)
        for c in np.quantile(prob, np.arange(0.50, 0.999, 0.02)):
            mm = _lb.metricas(y, (prob >= c).astype(int))
            if mm["mcc"] > melhor[0]:
                melhor = (mm["mcc"], C, float(c))
    return melhor[1], melhor[2]


def avalia(X, y, grupos):
    """Avaliacao deixando um documento de fora, com selecao aninhada por dobra."""
    prob = np.zeros(len(y))
    pred = np.zeros(len(y), dtype=int)
    escolhidos = []
    for g in np.unique(grupos):
        tr, te = grupos != g, grupos == g
        Cg, lim = seleciona_interno(X[tr], y[tr], grupos[tr])
        p = ajusta(X[tr], y[tr], X[te], Cg)
        prob[te] = p
        pred[te] = (p >= lim).astype(int)
        escolhidos.append(Cg)
    return prob, pred, escolhidos


def reamostra_multipla(y, grupos, preditores, n, rng):
    """Reamostragem por agrupamento com TODOS os preditores na mesma reamostra.

    Devolve o coeficiente de Matthews de cada preditor e a diferenca de cada par
    ordenado. Extrair todos os pares da mesma reamostra preserva o pareamento: se cada
    par fosse reamostrado por conta propria, as diferencas deixariam de ser mutuamente
    consistentes, e A superar B e B superar C poderia conviver com C superar A.
    """
    unicos = np.unique(grupos)
    indices = {g: np.where(grupos == g)[0] for g in unicos}
    vals = [[] for _ in preditores]
    pares = {(i, j): [] for i in range(len(preditores))
             for j in range(len(preditores)) if i < j}
    for _ in range(n):
        sorteio = rng.integers(0, len(unicos), len(unicos))
        sel = np.concatenate([indices[unicos[k]] for k in sorteio])
        ms = [_lb.metricas(y[sel], p[sel])["mcc"] for p in preditores]
        for i, m in enumerate(ms):
            vals[i].append(m)
        for (i, j) in pares:
            pares[(i, j)].append(ms[j] - ms[i])
    return vals, pares


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpo", default="outputs/segmentos_rotulados.csv")
    ap.add_argument("--vetores", default="outputs/vetores_bertimbau.npz")
    ap.add_argument("--oof", default="outputs/oof_textuais.csv")
    ap.add_argument("--out", default="outputs/modelo_bertimbau.csv")
    ap.add_argument("--reamostras", type=int, default=2000)
    ap.add_argument("--semente", type=int, default=20260811)
    ap.add_argument("--variavel", choices=VARIAVEIS, default=None)
    args = ap.parse_args()

    with (REPO / args.corpo).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    z = np.load(REPO / args.vetores, allow_pickle=False)

    # Alinhamento: a ordem das linhas e o unico vinculo entre vetor e rotulo. Conferir
    # e barato; usar vetores desalinhados produz resultado plausivel e falso, que
    # nenhuma metrica adiante denuncia.
    assert len(z["site_id"]) == len(R), "vetores e corpo tem tamanhos distintos"
    for i, r in enumerate(R):
        assert z["site_id"][i] == r["site_id"] and z["segmento_id"][i] == r["segmento_id"], \
            f"desalinhamento na linha {i}: {z['site_id'][i]} vs {r['site_id']}"

    with (REPO / args.oof).open(encoding="utf-8", newline="") as fh:
        O = list(csv.DictReader(fh, delimiter=";"))
    esparsa = {(o["variavel"], o["site_id"], o["segmento_id"]): int(o["pred"]) for o in O}
    faltam = sorted({v for v in VARIAVEIS} - {o["variavel"] for o in O})
    if faltam:
        print(f"ERRO: {args.oof} nao cobre {', '.join(faltam)}.")
        print("Reexecute scripts/modelar_textuais.py sem --variavel.")
        return 1

    sitios = sorted({r["site_id"] for r in R})
    idx = {s: i for i, s in enumerate(sitios)}
    grupos = np.array([idx[r["site_id"]] for r in R])
    rng = np.random.default_rng(args.semente)

    Xm = normaliza_linhas(z["media"].astype(np.float64))
    Xc = normaliza_linhas(z["cls"].astype(np.float64))
    print(f"corpo: {len(R):,} segmentos, {len(sitios)} politicas")
    print(f"vetores: {z['modelo']}, {Xm.shape[1]} dimensoes, teto {z['max_len']} subpalavras")
    print(f"estimador: regressao logistica L2, C e limiar por particao interna agrupada")
    print(f"regra de decisao: adota-se o mais complexo so quando o IC pareado exclui zero\n")

    NOMES = ["regra do codebook", "TF-IDF + L2", "BERTimbau media + L2",
             "BERTimbau [CLS] + L2 (robustez)"]
    linhas = []
    for v in ([args.variavel] if args.variavel else VARIAVEIS):
        y = np.array([int(r[v]) for r in R])
        regra = np.array([_lb.aplica_regra(r["texto"], v) for r in R])
        tfidf = np.array([esparsa[(v, r["site_id"], r["segmento_id"])] for r in R])
        prob_m, pred_m, esc_m = avalia(Xm, y, grupos)
        prob_c, pred_c, _ = avalia(Xc, y, grupos)

        print("=" * 104)
        print(f"{ROTULO[v]}   positivos: {int(y.sum())}   "
              f"proporcao 1 : {int((1 - y).sum() / max(y.sum(), 1))}")
        print(f"  C escolhido nas particoes internas (media): "
              + ", ".join(f"{c} em {n} de {len(sitios)}"
                          for c, n in sorted(Counter(esc_m).items())))
        print("=" * 104)
        print(f"  {'':32}{'MCC':>8}{'IC 95%':>18}{'prec':>9}{'rev':>8}"
              f"{'F1+':>8}{'AP':>8}{'VP':>6}{'FP':>7}{'FN':>6}")

        preditores = [regra, tfidf, pred_m, pred_c]
        escores = [None, None, prob_m, prob_c]
        vals, pares = reamostra_multipla(y, grupos, preditores, args.reamostras, rng)
        for i, nome in enumerate(NOMES):
            m = _lb.metricas(y, preditores[i])
            a = _lb.precisao_media(y, escores[i]) if escores[i] is not None else float("nan")
            atxt = f"{a * 100:6.1f}%" if a == a else "     —"
            lo, hi = np.percentile(vals[i], [2.5, 97.5])
            print(f"  {nome:32}{m['mcc']:8.3f}   [{lo:6.3f}, {hi:6.3f}]"
                  f"{m['prec'] * 100:8.1f}%{m['rev'] * 100:7.1f}%{m['f1_pos'] * 100:7.1f}%"
                  f"{atxt:>8}{m['vp']:6}{m['fp']:7}{m['fn']:6}")
            linhas.append({"variavel": v, "modelo": nome, **m, "ap": a,
                           "mcc_ic_inf": lo, "mcc_ic_sup": hi})

        print(f"\n  COMPARACOES PAREADAS")
        for (i, j), d in pares.items():
            if j == 3 or i == 3:
                continue  # a robustez nao entra na regra de selecao
            d = np.asarray(d)
            lo, hi = np.percentile(d, [2.5, 97.5])
            obs = _lb.metricas(y, preditores[j])["mcc"] - _lb.metricas(y, preditores[i])["mcc"]
            vered = ("supera" if lo > 0 else "e superado" if hi < 0 else "indistinguivel")
            print(f"    {NOMES[j]:32} menos {NOMES[i]:22}"
                  f"{obs:+8.3f}  [{lo:+.3f}, {hi:+.3f}]  {vered}")
            linhas.append({"variavel": v, "modelo": f"diferenca: {NOMES[j]} - {NOMES[i]}",
                           "mcc": obs, "mcc_ic_inf": lo, "mcc_ic_sup": hi,
                           "veredito": vered})

        # A regra de selecao aplicada, sem juizo posterior. A escada e percorrida um
        # degrau por vez, e cada degrau tem de superar o OCUPANTE do degrau anterior,
        # e nao um preditor qualquer: superar uma alternativa que ja foi descartada
        # nao e razao para adotar o mais complexo. Assim formulada, a escada e
        # monotona e nao admite ciclo entre os tres.
        supera = lambda d: bool(np.percentile(np.asarray(d), 2.5) > 0)
        ocupante = 1 if supera(pares[(0, 1)]) else 0
        if supera(pares[(ocupante, 2)]):
            ocupante = 2
        escolha = NOMES[ocupante]
        print(f"\n    SOB A REGRA DECLARADA -> {escolha}")
        print(f"    Ponto de operacao a considerar contra o contrato de triagem:")
        for i, nome in enumerate(NOMES[:3]):
            m = _lb.metricas(y, preditores[i])
            print(f"      {nome:32} sinaliza {m['vp'] + m['fp']:5} segmentos, "
                  f"{m['vp']:4} certos, deixa passar {m['fn']:4}")
        linhas.append({"variavel": v, "modelo": "escolha sob a regra declarada",
                       "veredito": escolha})
        print()

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    campos = []
    for l in linhas:
        for k in l:
            if k not in campos:
                campos.append(k)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=";", restval="")
        w.writeheader(); w.writerows(linhas)
    print(f"saida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
