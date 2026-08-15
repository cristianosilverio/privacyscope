# -*- coding: utf-8 -*-
"""Classificador supervisionado das tres variaveis textuais, em nivel de sentenca.

REPRESENTACAO
-------------
Frequencia de termo ponderada pelo inverso da frequencia documental, sobre n-gramas
de uma a tres palavras. Tres decisoes merecem registro:

  Minusculizacao. Reduz a esparsidade do vocabulario, o que importa com o numero de
  positivos disponivel. A caixa carrega sinal — "Encarregado" e "Titular" sao termos
  que a lei capitaliza, e nomes de paises e provedores indicam transferencia —, mas
  esse sinal e recuperavel pelos proprios n-gramas.

  Ausencia de remocao de palavras vazias. A ponderacao pelo inverso da frequencia
  documental ja rebaixa termos ubiquos, e lista manual duplicaria a funcao de modo
  pior. Sobretudo, as palavras vazias sao portadoras aqui: "nao compartilhamos",
  "sem o consentimento", "salvo quando". A negacao inverte o sentido sem alterar as
  palavras de conteudo, e suprimi-la comprometeria a distincao que mais importa.

  N-gramas ate tres palavras, pela mesma razao: e o alcance necessario para capturar
  "nao compartilhamos com terceiros" como unidade.

Emprega-se escalonamento logaritmico da frequencia e normalizacao L2, que atenua o
efeito de comprimento do segmento.

ESTIMADOR
---------
Regressao logistica com penalizacao L2. A correcao de Firth, adotada no classificador
do canal, NAO se aplica: sua penalizacao depende do determinante da matriz de
informacao, singular quando os atributos superam as observacoes, e o vocabulario aqui
alcanca milhares de dimensoes. O argumento que motivou Firth — ausencia de
hiperparametro — nao se sustenta em alta dimensao esparsa, onde alguma regularizacao
e inevitavel; e a propria penalizacao trata a separacao que Firth enderecava.

A forca da regularizacao e escolhida por SELECAO ANINHADA, em particao interna
agrupada sobre as politicas de treino, dentre um leque declarado. Nenhum valor do
material de teste participa da escolha.

Cogitou-se fixa-la a priori no valor padrao da biblioteca, sob o argumento de que a
selecao aninhada seria ruidosa com quinze grupos e de que uma analise de
sensibilidade cobriria a objecao de arbitrariedade. A analise de sensibilidade
desautorizou o argumento: o coeficiente de Matthews da transferencia internacional
varia de 0,370 a 0,700 conforme o valor adotado, e o dos direitos de 0,584 a 0,706.
Sob variacao dessa magnitude, fixar o parametro nao e conduta conservadora — e
sorteio, e a conclusao a respeito de qual classificador supera a regra passaria a
depender de escolha alheia aos dados. O ruido da selecao aninhada e preferivel.

ESQUEMA DE AVALIACAO
--------------------
Particao agrupada por sitio, deixando um documento de fora. O vetorizador e ajustado
EXCLUSIVAMENTE sobre as particoes de treino: ajusta-lo sobre o conjunto completo
vazaria o vocabulario do material de teste.

O limiar de decisao provem de particao interna, tambem agrupada, sobre as politicas de
treino. Apura-lo sobre as predicoes de treino seria otimista, uma vez que o modelo
regularizado separa bem o material a que foi ajustado.

As metricas sao apuradas uma vez sobre as predicoes reunidas, e a incerteza provem de
reamostragem por agrupamento sobre os quinze DOCUMENTOS (Efron, 1979; Field e Welsh,
2007). Reamostrar segmentos trataria como independentes unidades que compartilham
autoria e redacao; a pergunta que se responde e se o desempenho se transfere a outras
politicas, e essa e variabilidade de documento.

O adversario e a REGRA, e nao a classe majoritaria. Duas comparacoes sao reportadas,
porque respondem a perguntas distintas e podem divergir:

  TESTE DE McNEMAR (1947) — afere se os dois classificadores incorrem na mesma taxa de
  erro. Sob desequilibrio acentuado o erro e dominado pela classe majoritaria, de
  sorte que o teste favorece o preditor conservador. Nao esta errado: responde quem
  erra menos no total.

  DIFERENCA DE COEFICIENTE DE MATTHEWS POR REAMOSTRAGEM PAREADA — a mesma reamostra de
  documentos alimenta os dois classificadores, e registra-se a diferenca. Responde
  qual e superior na metrica de manchete, que pondera as quatro casas da matriz de
  confusao. O pareamento importa: reamostras independentes somariam a variabilidade
  dos dois, alargando o intervalo sem razao.

Divergencia entre as duas comparacoes nao e defeito. Ela localiza a troca entre
precisao e revocacao, e informa a decisao operacional.

PERSISTENCIA DAS PREDICOES
--------------------------
As predicoes fora do ajuste sao gravadas segmento a segmento. A comparacao pareada
exige que os preditores confrontados tenham sido apurados sobre a MESMA particao e as
MESMAS unidades; reamostrar dois conjuntos obtidos em execucoes independentes somaria
variabilidade de particao a variabilidade de desempenho, e a diferenca deixaria de ser
atribuivel ao preditor. Gravar o vetor e o que permite confrontar, adiante, uma
representacao densa contra esta sem reexecutar a selecao aninhada.

A particao interna e determinista, de semente fixa, de sorte que a reexecucao reproduz
os mesmos valores.

Uso:
    python scripts/modelar_textuais.py
    python scripts/modelar_textuais.py --sensibilidade
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
from math import sqrt
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("lb", REPO / "scripts" / "linhas_base_textuais.py")
_lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lb)

VARIAVEIS = _lb.VARIAVEIS
ROTULO = _lb.ROTULO
# A grade e ESTENDIDA, e nao deslocada. A extensao decorre de diagnostico: em
# transferencia internacional a selecao saturou no extremo superior, escolhendo o
# maior valor disponivel em dez das quinze particoes, o que indica que a busca estava
# truncada. Suprimir o extremo inferior forcaria a escolha para cima nas particoes
# que legitimamente preferiam valores menores, convertendo o diagnostico em
# imposicao. A extensao pode piorar o desempenho; justifica-se pela saturacao.
GRADE_C = [0.01, 0.1, 1.0, 10.0, 80.0, 100.0, 150.0, 300.0, 1000.0]


def vetorizador():
    from sklearn.feature_extraction.text import TfidfVectorizer
    return TfidfVectorizer(lowercase=True, stop_words=None, ngram_range=(1, 3),
                           min_df=3, sublinear_tf=True, norm="l2", strip_accents=None)


def ajusta(Xtr_txt, ytr, Xte_txt, C):
    from sklearn.linear_model import LogisticRegression
    vec = vetorizador()
    Xtr = vec.fit_transform(Xtr_txt)
    Xte = vec.transform(Xte_txt)
    m = LogisticRegression(C=C, max_iter=3000, solver="liblinear")
    m.fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1], Xtr.shape[1]


def seleciona_interno(textos, y, grupos, semente=0, C_fixo=None):
    """Escolhe conjuntamente a forca da regularizacao e o limiar de decisao.

    Opera em particao interna agrupada sobre as politicas de TREINO. Ambos os
    parametros sao escolhidos pelo mesmo criterio, o coeficiente de Matthews sobre as
    predicoes internas fora do ajuste, de modo que nenhum valor do material de teste
    participe da decisao.
    """
    unicos = np.unique(grupos)
    rng = np.random.default_rng(semente)
    dobras = np.array_split(rng.permutation(unicos), min(3, len(unicos)))
    # Com C fixado, percorre-se apenas esse valor: o limiar tem de ser apurado sob a
    # mesma regularizacao que sera empregada, sob pena de combinar parametros que
    # nunca coexistiram.
    grade = GRADE_C if C_fixo is None else [C_fixo]
    melhor = (-2.0, grade[0], 0.5)
    for C in grade:
        prob = np.zeros(len(y))
        for d in dobras:
            te = np.isin(grupos, d)
            if te.all() or not te.any():
                continue
            p, _ = ajusta([textos[i] for i in np.where(~te)[0]], y[~te],
                          [textos[i] for i in np.where(te)[0]], C)
            prob[te] = p
        for c in np.quantile(prob, np.arange(0.50, 0.999, 0.02)):
            mm = _lb.metricas(y, (prob >= c).astype(int))
            if mm["mcc"] > melhor[0]:
                melhor = (mm["mcc"], C, float(c))
    return melhor[1], melhor[2]


def avalia(textos, y, grupos, C=None):
    """Avaliacao deixando um documento de fora.

    Com C igual a None, a forca da regularizacao e escolhida em particao interna,
    dentro de cada dobra. Fixa-la e reservado a analise de sensibilidade.
    """
    prob = np.zeros(len(y))
    pred = np.zeros(len(y), dtype=int)
    n_atrib, escolhidos = [], []
    for g in np.unique(grupos):
        tr, te = grupos != g, grupos == g
        txt_tr = [textos[i] for i in np.where(tr)[0]]
        Cg, lim = seleciona_interno(txt_tr, y[tr], grupos[tr], C_fixo=C)
        p, nf = ajusta(txt_tr, y[tr], [textos[i] for i in np.where(te)[0]], Cg)
        prob[te] = p
        n_atrib.append(nf)
        escolhidos.append(Cg)
        pred[te] = (p >= lim).astype(int)
    return prob, pred, int(np.median(n_atrib)), escolhidos


def mcnemar(y, a, b):
    from scipy.stats import binomtest
    n01 = int(np.sum((a == y) & (b != y)))
    n10 = int(np.sum((a != y) & (b == y)))
    if n01 + n10 == 0:
        return 1.0, n01, n10
    return binomtest(n01, n01 + n10, 0.5).pvalue, n01, n10


def reamostra_pareada(y, grupos, preditores, n, rng):
    """Reamostragem por agrupamento, com os preditores avaliados na MESMA reamostra.

    Devolve, para cada preditor, a lista de coeficientes de Matthews; e, para o par
    ordenado (primeiro menos segundo), a lista de diferencas. O pareamento elimina a
    variabilidade comum aos dois e estreita o intervalo da diferenca.
    """
    unicos = np.unique(grupos)
    indices = {g: np.where(grupos == g)[0] for g in unicos}
    vals = [[] for _ in preditores]
    dif = []
    for _ in range(n):
        sorteio = rng.integers(0, len(unicos), len(unicos))
        sel = np.concatenate([indices[unicos[k]] for k in sorteio])
        ms = [_lb.metricas(y[sel], p[sel])["mcc"] for p in preditores]
        for i, m in enumerate(ms):
            vals[i].append(m)
        if len(ms) >= 2:
            dif.append(ms[1] - ms[0])
    return vals, dif


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpo", default="outputs/segmentos_rotulados.csv")
    ap.add_argument("--reamostras", type=int, default=2000)
    ap.add_argument("--semente", type=int, default=20260811)
    ap.add_argument("--sensibilidade", action="store_true")
    ap.add_argument("--variavel", choices=VARIAVEIS, default=None,
                    help="restringe a execucao a uma variavel")
    ap.add_argument("--out", default="outputs/modelo_textuais.csv")
    ap.add_argument("--oof", default="outputs/oof_textuais.csv",
                    help="predicoes fora do ajuste, segmento a segmento")
    args = ap.parse_args()

    with (REPO / args.corpo).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    textos = [r["texto"] for r in R]
    sitios = sorted({r["site_id"] for r in R})
    idx = {s: i for i, s in enumerate(sitios)}
    grupos = np.array([idx[r["site_id"]] for r in R])
    rng = np.random.default_rng(args.semente)

    print(f"corpo: {len(R):,} segmentos, {len(sitios)} politicas")
    print(f"representacao: TF-IDF, n-gramas de 1 a 3, minusculas, sem remocao de palavras vazias")
    print(f"estimador: regressao logistica L2, C selecionado em particao interna "
          f"dentre {GRADE_C}")
    print(f"esquema: deixar um documento de fora, limiar por particao interna agrupada\n")

    linhas, fora_do_ajuste = [], []
    for v in ([args.variavel] if args.variavel else VARIAVEIS):
        y = np.array([int(r[v]) for r in R])
        regra = np.array([_lb.aplica_regra(r["texto"], v) for r in R])
        prob, pred, nf, escolhidos = avalia(textos, y, grupos)
        for i, r in enumerate(R):
            fora_do_ajuste.append({"variavel": v, "site_id": r["site_id"],
                                   "segmento_id": r["segmento_id"], "y": int(y[i]),
                                   "regra": int(regra[i]), "pred": int(pred[i]),
                                   "prob": f"{prob[i]:.6f}"})

        print("=" * 104)
        from collections import Counter as _C
        cc = _C(escolhidos)
        print(f"{ROTULO[v]}   positivos: {int(y.sum())}   proporcao 1 : "
              f"{int((1-y).sum()/max(y.sum(),1))}   atributos: {nf:,}")
        print(f"  C escolhido nas particoes internas: "
              + ", ".join(f"{c} em {n} de 15" for c, n in sorted(cc.items())))
        print("=" * 104)
        print(f"  {'':22}{'bal.acc':>10}{'macroF1':>10}{'MCC':>9}"
              f"{'prec':>9}{'rev':>8}{'F1+':>8}{'AP':>8}{'VP':>6}{'FP':>7}")
        vals, dif = reamostra_pareada(y, grupos, [regra, pred], args.reamostras, rng)
        for i, (nome, pr, esc) in enumerate((("regra do codebook", regra, None),
                                             ("TF-IDF + L2", pred, prob))):
            m = _lb.metricas(y, pr)
            a = _lb.precisao_media(y, esc) if esc is not None else float("nan")
            atxt = f"{a*100:6.1f}%" if a == a else "     —"
            print(f"  {nome:22}{m['bal']*100:9.1f}%{m['macro_f1']*100:9.1f}%{m['mcc']:9.3f}"
                  f"{m['prec']*100:8.1f}%{m['rev']*100:7.1f}%{m['f1_pos']*100:7.1f}%"
                  f"{atxt:>8}{m['vp']:6}{m['fp']:7}")
            lo, hi = np.percentile(vals[i], [2.5, 97.5])
            print(f"  {'':22}{'MCC, IC 95%:':>50} [{lo:.3f}, {hi:.3f}]")
            linhas.append({"variavel": v, "modelo": nome, **m, "ap": a,
                           "mcc_ic_inf": lo, "mcc_ic_sup": hi, "n_atributos": nf})

        dif = np.asarray(dif)
        dlo, dhi = np.percentile(dif, [2.5, 97.5])
        prop = float(np.mean(dif <= 0))
        p_mc, n01, n10 = mcnemar(y, pred, regra)
        obs = _lb.metricas(y, pred)["mcc"] - _lb.metricas(y, regra)["mcc"]
        print(f"\n  COMPARACAO CONTRA A REGRA")
        print(f"    diferenca de MCC (modelo menos regra): {obs:+.3f}"
              f"   IC 95% pareado [{dlo:+.3f}, {dhi:+.3f}]")
        veredito = ("o modelo supera a regra" if dlo > 0 else
                    "a regra supera o modelo" if dhi < 0 else
                    "os dois sao indistinguiveis")
        print(f"    reamostras em que a regra iguala ou supera: {prop*100:.1f}%"
              f"   -> {veredito}")
        print(f"    McNemar sobre a taxa de erro: p = {p_mc:.3e}   "
              f"modelo acerta onde a regra erra em {n01}; o inverso em {n10}")
        if (obs > 0) != (n01 > n10):
            print(f"    As duas comparacoes DIVERGEM: uma responde qual e superior na")
            print(f"    metrica de manchete, a outra qual erra menos no total.")
        linhas.append({"variavel": v, "modelo": "diferenca modelo-regra",
                       "mcc": obs, "mcc_ic_inf": dlo, "mcc_ic_sup": dhi,
                       "prop_regra_igual_ou_melhor": prop, "p_mcnemar": p_mc,
                       "n01": n01, "n10": n10})
        print()

    if args.sensibilidade:
        print("=" * 104)
        print("SENSIBILIDADE A FORCA DA REGULARIZACAO  (coeficiente de Matthews)")
        print("=" * 104)
        print(f"  {'variavel':22}" + "".join(f"{'C=' + str(c):>12}" for c in GRADE_C))
        for v in ([args.variavel] if args.variavel else VARIAVEIS):
            y = np.array([int(r[v]) for r in R])
            saida = []
            for C in GRADE_C:
                _, pr, _, _ = avalia(textos, y, grupos, C)
                saida.append(_lb.metricas(y, pr)["mcc"])
            print(f"  {ROTULO[v]:22}" + "".join(f"{s:>12.3f}" for s in saida))

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

    if fora_do_ajuste:
        oof = REPO / args.oof
        campos_oof = ["variavel", "site_id", "segmento_id", "y", "regra", "pred", "prob"]
        with oof.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=campos_oof, delimiter=";")
            w.writeheader(); w.writerows(fora_do_ajuste)
        faltantes = sorted(set(VARIAVEIS) - {l["variavel"] for l in fora_do_ajuste})
        print(f"predicoes fora do ajuste: {oof}  ({len(fora_do_ajuste):,} linhas)")
        if faltantes:
            print(f"  ATENCAO: execucao parcial. Ausentes: {', '.join(faltantes)}.")
            print(f"  A comparacao contra a representacao densa exige as tres.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
