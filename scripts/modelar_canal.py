# -*- coding: utf-8 -*-
"""Avaliacao do classificador de ``tem_canal_titular``.

ESTIMADOR
---------
Regressao logistica com correcao de Firth (scripts/firth.py) como estimador
primario. Tres atributos apresentam separacao quase completa, condicao sob a qual
a maxima verossimilhanca nao existe; a correcao de Firth produz estimativa finita
sem exigir hiperparametro. Ridge (L2) e arvores impulsionadas por gradiente
entram como verificacao: a primeira mostra que a conclusao independe da forma de
penalizacao; a segunda testa se a opcao por modelo interpretavel implica perda de
desempenho.

ESQUEMA DE AVALIACAO
--------------------
Validacao cruzada estratificada repetida, 5 particoes por 20 repeticoes. A
estratificacao considera conjuntamente o rotulo e o estrato amostral, de modo a
preservar as proporcoes de ambos em cada particao. A unidade de agrupamento e o
sitio; nao se agrupa por semelhanca textual, decisao fundamentada em duas razoes:
o modelo dispoe de nove parametros sobre atributos binarios, o que impossibilita
memorizacao de documento especifico, e os atributos de e-mail dependem do
endereco concreto de cada sitio, que varia mesmo entre sitios que compartilham
template.

SELECAO DE LIMIAR
-----------------
Os limiares correspondentes as revocacoes-alvo de 80%, 90% e 95% sobre a classe
de ausencia sao determinados exclusivamente nas particoes de treino e aplicados
as particoes de teste. Determinar o limiar sobre o teste constituiria vazamento e
inflaria as metricas operacionais.

CORRECAO DE VARIANCIA
---------------------
As particoes de treino de uma validacao cruzada repetida se sobrepoem, o que
torna as estimativas de desempenho correlacionadas e faz o erro-padrao ingenuo
subestimar a variancia. Adota-se o estimador de Nadeau e Bengio (2003):

    Var = (1/(k*r) + n_teste/n_treino) * s^2

com s^2 a variancia amostral entre particoes. Para cinco particoes o segundo
termo vale 1/4 e domina o primeiro, elevando o erro-padrao em cerca de cinco
vezes em relacao ao calculo ingenuo.

COMPARACAO CONTRA A LINHA DE BASE
---------------------------------
Teste de McNemar sobre as predicoes fora da particao, confrontando o modelo com o
detector por regra. O teste e conduzido por repeticao, situacao em que cada sitio
comparece uma unica vez, preservando a independencia das observacoes pareadas.
Reportam-se a mediana do valor-p e a proporcao de repeticoes com significancia,
em lugar de um valor unico.

Uso:
    python scripts/modelar_canal.py
    python scripts/modelar_canal.py --repeticoes 20 --particoes 5
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
from math import sqrt
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("firth", REPO / "scripts" / "firth.py")
_firth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_firth)

FEATS = ["F1_email_lgpd_proprio", "F2_email_lgpd_externo", "F3_email_generico_ancorado",
         "F4_subpagina_titular", "F5_contato_ancorado", "F6_telefone_ancorado",
         "F7_ancora_encarregado", "F8_ancora_direitos"]
REGEX_FEATS = ["F1_email_lgpd_proprio", "F4_subpagina_titular"]
ALVOS_REVOCACAO = [0.80, 0.90, 0.95]


# --------------------------------------------------------------------- metricas
def metricas(y, pred):
    y = np.asarray(y); pred = np.asarray(pred)
    vp = int(np.sum((y == 1) & (pred == 1))); vn = int(np.sum((y == 0) & (pred == 0)))
    fp = int(np.sum((y == 0) & (pred == 1))); fn = int(np.sum((y == 1) & (pred == 0)))
    sens = vp / (vp + fn) if vp + fn else 0.0
    esp = vn / (vn + fp) if vn + fp else 0.0
    p1 = vp / (vp + fp) if vp + fp else 0.0
    p0 = vn / (vn + fn) if vn + fn else 0.0
    f1_1 = 2 * p1 * sens / (p1 + sens) if p1 + sens else 0.0
    f1_0 = 2 * p0 * esp / (p0 + esp) if p0 + esp else 0.0
    den = sqrt((vp + fp) * (vp + fn) * (vn + fp) * (vn + fn))
    mcc = (vp * vn - fp * fn) / den if den else 0.0
    sinal = vn + fn
    return {"bal": (sens + esp) / 2, "macro_f1": (f1_0 + f1_1) / 2, "mcc": mcc,
            "sens": sens, "esp": esp, "taxa_sinal": sinal / len(y),
            "prec_aus": (vn / sinal) if sinal else 0.0}


def brier(y, prob):
    return float(np.mean((np.asarray(prob) - np.asarray(y)) ** 2))


def limiar_para_revocacao_ausencia(y_tr, p_tr, alvo):
    """Menor limiar que atinge a revocacao-alvo sobre a classe de ausencia.

    Sinaliza-se para revisao quando a probabilidade predita de haver canal fica
    ABAIXO do limiar. Elevar o limiar amplia a revocacao sobre a ausencia.
    """
    y_tr = np.asarray(y_tr); p_tr = np.asarray(p_tr)
    negativos = p_tr[y_tr == 0]
    if len(negativos) == 0:
        return 0.5
    return float(np.quantile(negativos, alvo))


# ------------------------------------------------------------------ estimadores
def ajusta_firth(Xtr, ytr, Xte):
    r = _firth.firth_logistic(Xtr, ytr)
    return _firth.prever_prob(Xte, r["beta"]), r["beta"]


def ajusta_ridge(Xtr, ytr, Xte):
    from sklearn.linear_model import LogisticRegression
    # penalizacao L2 e o comportamento padrao; declarar 'penalty' foi depreciado
    # em versoes recentes do scikit-learn. A forca fica em C, fixada a priori.
    m = LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs")
    m.fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1], np.concatenate([m.intercept_, m.coef_.ravel()])


def ajusta_gbdt(Xtr, ytr, Xte):
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1,
                                       max_depth=3, random_state=0)
    m.fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1], None


ESTIMADORES = {"Firth (primario)": ajusta_firth,
               "Ridge L2 (robustez)": ajusta_ridge,
               "GBDT (desafiante)": ajusta_gbdt}


# ------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="outputs/features_canal_N200.csv")
    ap.add_argument("--particoes", type=int, default=5)
    ap.add_argument("--repeticoes", type=int, default=20)
    ap.add_argument("--semente", type=int, default=20260719)
    ap.add_argument("--out", default="outputs/resultados_canal.csv")
    args = ap.parse_args()

    from sklearn.model_selection import RepeatedStratifiedKFold

    with (REPO / args.features).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    X = np.array([[int(r[f]) for f in FEATS] for r in R], dtype=float)
    y = np.array([int(r["y"]) for r in R])
    estrato = np.array([r.get("estrato", "") for r in R])
    regex = np.array([1 if any(r[f] == "1" for f in REGEX_FEATS) else 0 for r in R])
    # estratificacao conjunta de rotulo e estrato amostral
    chave = np.array([f"{a}_{b}" for a, b in zip(y, estrato)])

    print(f"sitios: {len(y)}  |  y=1: {int(y.sum())}  |  y=0: {int((1-y).sum())}")
    print(f"validacao cruzada: {args.particoes} particoes x {args.repeticoes} repeticoes")
    print(f"estratificacao conjunta rotulo x estrato: {len(set(chave))} celulas\n")

    rskf = RepeatedStratifiedKFold(n_splits=args.particoes,
                                   n_repeats=args.repeticoes,
                                   random_state=args.semente)
    por_est = {nome: {"bal": [], "macro_f1": [], "mcc": [], "sens": [], "esp": [],
                      "brier": [], **{f"nnr_{int(a*100)}": [] for a in ALVOS_REVOCACAO},
                      **{f"sinal_{int(a*100)}": [] for a in ALVOS_REVOCACAO},
                      **{f"prec_{int(a*100)}": [] for a in ALVOS_REVOCACAO}}
              for nome in ESTIMADORES}
    coefs = []
    # predicoes fora da particao, por repeticao, para o teste de McNemar
    oof = {nome: np.full((args.repeticoes, len(y)), -1) for nome in ESTIMADORES}

    for i, (itr, ite) in enumerate(rskf.split(X, chave)):
        rep = i // args.particoes
        for nome, ajusta in ESTIMADORES.items():
            prob, beta = ajusta(X[itr], y[itr], X[ite])
            pred = (prob >= 0.5).astype(int)
            m = metricas(y[ite], pred)
            for k in ("bal", "macro_f1", "mcc", "sens", "esp"):
                por_est[nome][k].append(m[k])
            por_est[nome]["brier"].append(brier(y[ite], prob))
            oof[nome][rep, ite] = pred
            if nome == "Firth (primario)" and beta is not None:
                coefs.append(beta)
            # leitura de triagem: limiar definido no treino
            prob_tr, _ = ajusta(X[itr], y[itr], X[itr])
            for alvo in ALVOS_REVOCACAO:
                lim = limiar_para_revocacao_ausencia(y[itr], prob_tr, alvo)
                pr = (prob >= lim).astype(int)
                mt = metricas(y[ite], pr)
                s = int(alvo * 100)
                por_est[nome][f"sinal_{s}"].append(mt["taxa_sinal"])
                por_est[nome][f"prec_{s}"].append(mt["prec_aus"])
                por_est[nome][f"nnr_{s}"].append(1 / mt["prec_aus"] if mt["prec_aus"] else np.nan)

    # ---- erro-padrao corrigido (Nadeau e Bengio, 2003) ----
    k, r = args.particoes, args.repeticoes
    n_te = len(y) / k
    n_tr = len(y) - n_te
    fator = (1.0 / (k * r)) + (n_te / n_tr)

    def media_ic(v):
        v = np.asarray([x for x in v if np.isfinite(x)])
        m = float(np.mean(v))
        ep = float(sqrt(fator * np.var(v, ddof=1)))
        return m, m - 1.96 * ep, m + 1.96 * ep

    print("=" * 100)
    print("DESEMPENHO  (media e IC 95% com variancia corrigida por Nadeau-Bengio)")
    print("=" * 100)
    print(f"  {'estimador':22}{'bal.acc':>18}{'macro-F1':>18}{'MCC':>18}{'Brier':>14}")
    linhas_csv = []
    for nome in ESTIMADORES:
        d = por_est[nome]
        b = media_ic(d["bal"]); f1 = media_ic(d["macro_f1"])
        mc = media_ic(d["mcc"]); br = media_ic(d["brier"])
        print(f"  {nome:22}{b[0]*100:7.1f} [{b[1]*100:4.1f},{b[2]*100:4.1f}]"
              f"{f1[0]*100:7.1f} [{f1[1]*100:4.1f},{f1[2]*100:4.1f}]"
              f"{mc[0]:8.3f} [{mc[1]:5.3f},{mc[2]:5.3f}]{br[0]:9.3f}")
        s = media_ic(d["sens"]); e = media_ic(d["esp"])
        print(f"  {'':22}sens {s[0]*100:5.1f}   esp {e[0]*100:5.1f}")
        linhas_csv.append({"estimador": nome, "bal_acc": b[0], "bal_ic_inf": b[1],
                           "bal_ic_sup": b[2], "macro_f1": f1[0], "mcc": mc[0],
                           "brier": br[0], "sens": s[0], "esp": e[0]})

    print("\n" + "=" * 100)
    print("TRIAGEM POR AUSENCIA  (limiar definido nas particoes de treino)")
    print("=" * 100)
    print(f"  {'estimador':22}{'revocacao':>11}{'sinalizado':>13}{'precisao':>11}{'NNR':>9}")
    for nome in ESTIMADORES:
        for alvo in ALVOS_REVOCACAO:
            s = int(alvo * 100)
            sn = media_ic(por_est[nome][f"sinal_{s}"])[0]
            pr = media_ic(por_est[nome][f"prec_{s}"])[0]
            nn = media_ic(por_est[nome][f"nnr_{s}"])[0]
            print(f"  {nome if alvo == ALVOS_REVOCACAO[0] else '':22}{s:>9}%"
                  f"{sn*100:12.1f}%{pr*100:10.1f}%{nn:9.2f}")

    # ---- McNemar contra o detector por regra ----
    print("\n" + "=" * 100)
    print("McNEMAR CONTRA O DETECTOR POR REGRA  (por repeticao)")
    print("=" * 100)
    from scipy.stats import binomtest
    for nome in ESTIMADORES:
        ps = []
        for rep in range(args.repeticoes):
            pr = oof[nome][rep]
            ok = pr >= 0
            b = int(np.sum((pr[ok] == y[ok]) & (regex[ok] != y[ok])))
            c = int(np.sum((pr[ok] != y[ok]) & (regex[ok] == y[ok])))
            if b + c:
                ps.append(binomtest(b, b + c, 0.5).pvalue)
        if ps:
            ps = np.array(ps)
            print(f"  {nome:22} p mediano = {np.median(ps):.2e}   "
                  f"repeticoes com p<0,05: {int(np.sum(ps < 0.05))}/{len(ps)}")

    # ---- coeficientes medios do estimador primario ----
    if coefs:
        C = np.mean(np.array(coefs), axis=0)
        print("\n" + "=" * 100)
        print("COEFICIENTES MEDIOS  (Firth; escala log-odds)")
        print("=" * 100)
        print(f"  {'intercepto':32}{C[0]:8.3f}")
        for nome_f, v in zip(FEATS, C[1:]):
            print(f"  {nome_f:32}{v:8.3f}")

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas_csv[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(linhas_csv)
    print(f"\nsaida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
