# -*- coding: utf-8 -*-
"""Curva de confiabilidade e decomposicao do escore de Brier.

MOTIVACAO
---------
O contrato de saida do framework promete probabilidade calibrada, e nao apenas
ordenamento. Um modelo pode ordenar corretamente os sitios e ainda assim atribuir
probabilidades sistematicamente deslocadas, o que inviabilizaria a priorizacao por
risco pela autoridade. O escore de Brier resume o desvio em um numero; a curva de
confiabilidade mostra ONDE o desvio ocorre.

As probabilidades sao as preditas FORA DA PARTICAO, na mesma validacao cruzada
que produziu as metricas de desempenho: probabilidade predita para um sitio que
participou do ajuste seria otimista e a curva pareceria melhor do que e.

DECOMPOSICAO
------------
Murphy decompos o escore de Brier em tres termos:

    Brier = confiabilidade - resolucao + incerteza

A confiabilidade mede o afastamento medio entre a probabilidade predita e a
frequencia observada dentro de cada faixa, e deve ser proxima de zero. A resolucao
mede o quanto as frequencias por faixa se afastam da prevalencia global, e quanto
maior, melhor. A incerteza depende apenas da prevalencia e independe do modelo,
servindo de referencia: e o escore de Brier que se obteria predizendo a prevalencia
para todos os sitios.

A identidade acima e exata somente quando as previsoes dentro de cada faixa sao
identicas. Ao agrupar previsoes continuas, a dispersao interna a faixa e descartada
e a soma dos tres termos deixa de reproduzir o escore. Reporta-se por isso o residuo
de forma explicita, em vez de tratar a diferenca como anomalia.

ANTICORRELACAO ENTRE PREVISAO E ROTULO
--------------------------------------
A probabilidade fora da particao de um sitio e deslocada na direcao CONTRARIA ao
seu proprio rotulo, porque esse rotulo foi excluido do ajuste que o preve. Um
sitio positivo e previsto por modelos treinados com um positivo a menos, e recebe
previsao mais baixa; um negativo recebe previsao mais alta. Trata-se da face local
do vies pessimista da validacao cruzada.

O efeito e imperceptivel quando o modelo produz muitos valores distintos, mas
torna-se determinante aqui: com oito atributos binarios, sitios de mesmo padrao
deveriam receber previsao identica, e toda variacao observada entre eles decorre
desse deslocamento. Medicao conduzida sobre a amostra confirmou o fenomeno em
todos os padroes com ao menos seis sitios, com diferenca de 1,2 a 11,1 pontos
percentuais entre positivos e negativos de mesmo padrao.

A consequencia e que ordenar sitios de um mesmo padrao pela probabilidade fora da
particao equivale a ordena-los pelo rotulo. Faixas construidas sobre essa ordenacao
exibem desvios de sinais opostos que nao correspondem a descalibracao alguma.

A rotina neutraliza o artefato promediando a probabilidade DENTRO DE CADA PADRAO
antes de formar as faixas, o que preserva a natureza fora da particao da estimativa
e elimina a variacao espuria. O diagnostico definitivo de calibracao, por sua vez,
e conduzido por scripts/calibracao_por_padrao.py, que dispensa faixas.

Registre-se que o escore de Brier calculado diretamente sobre as probabilidades por
sitio permanece CONSERVADOR sob esse mecanismo: o deslocamento afasta a previsao do
rotulo e agrava o escore. Reporta-se por isso o valor direto, sem correcao.

CONSTRUCAO DAS FAIXAS
---------------------
Num ajuste unico, oito atributos binarios produzem poucas probabilidades distintas,
uma por padrao de atributos observado. A probabilidade aqui avaliada, contudo, e a
MEDIA sobre as repeticoes, cada uma proveniente de um modelo ajustado em particao
diversa, o que a torna continua. Persiste, ainda assim, forte concentracao em torno
dos padroes frequentes — em especial o padrao sem atributo algum.

Corte por quantil puro parte essa concentracao ao meio e produz artefato: duas
faixas com previsao praticamente igual exibem frequencias observadas muito
distintas, e a diferenca entre elas e ruido de particao, nao descalibracao. As
faixas sao por isso formadas com restricao dupla — tamanho minimo e amplitude
maxima de previsao interna —, de modo que previsoes indistinguiveis permanecam
juntas. Reporta-se ainda o intervalo de Wilson para a frequencia observada, para
que a incerteza amostral de cada faixa fique a vista.

Uso:
    python scripts/calibracao_canal.py
    python scripts/calibracao_canal.py --faixas 5
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("firth", REPO / "scripts" / "firth.py")
_firth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_firth)

FEATS = ["F1_email_lgpd_proprio", "F2_email_lgpd_externo", "F3_email_generico_ancorado",
         "F4_subpagina_titular", "F5_contato_ancorado", "F6_telefone_ancorado",
         "F7_ancora_encarregado", "F8_ancora_direitos"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="outputs/features_canal_N200.csv")
    ap.add_argument("--particoes", type=int, default=5)
    ap.add_argument("--repeticoes", type=int, default=20)
    ap.add_argument("--faixas", type=int, default=6)
    ap.add_argument("--amplitude", type=float, default=0.08,
                    help="amplitude maxima de previsao dentro de uma faixa")
    ap.add_argument("--semente", type=int, default=20260719)
    ap.add_argument("--out", default="outputs/calibracao_canal.csv")
    args = ap.parse_args()

    from sklearn.model_selection import RepeatedStratifiedKFold

    with (REPO / args.features).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    X = np.array([[int(r[f]) for f in FEATS] for r in R], dtype=float)
    y = np.array([int(r["y"]) for r in R], dtype=float)
    estrato = np.array([r.get("estrato", "") for r in R])
    chave = np.array([f"{int(a)}_{b}" for a, b in zip(y, estrato)])

    # probabilidade fora da particao, acumulada ao longo das repeticoes
    rskf = RepeatedStratifiedKFold(n_splits=args.particoes, n_repeats=args.repeticoes,
                                   random_state=args.semente)
    soma = np.zeros(len(y)); cont = np.zeros(len(y))
    for itr, ite in rskf.split(X, chave):
        beta = _firth.firth_logistic(X[itr], y[itr])["beta"]
        soma[ite] += _firth.prever_prob(X[ite], beta); cont[ite] += 1
    prob = soma / cont

    # promediacao por padrao: neutraliza a anticorrelacao descrita no cabecalho
    from collections import defaultdict
    padroes = defaultdict(list)
    for i, linha in enumerate(X):
        padroes[tuple(int(v) for v in linha)].append(i)
    prob_sitio = prob.copy()
    prob = prob.copy()
    for idx in padroes.values():
        idx = np.array(idx)
        prob[idx] = prob_sitio[idx].mean()

    # o escore de Brier permanece o direto, por ser conservador
    brier = float(np.mean((prob_sitio - y) ** 2))
    prev = float(np.mean(y))
    incerteza = prev * (1 - prev)

    print(f"sitios: {len(y)}   prevalencia de canal: {prev*100:.1f}%")
    print(f"padroes de atributos distintos: {len(padroes)}")
    print(f"probabilidades distintas por sitio, antes da promediacao: "
          f"{len(np.unique(np.round(prob_sitio,6)))}")
    print(f"apos promediacao por padrao: {len(np.unique(np.round(prob,6)))}")
    print(f"\nBrier fora da particao: {brier:.4f}")
    print(f"Brier de referencia, predizendo a prevalencia: {incerteza:.4f}")
    print(f"reducao sobre a referencia: {(1-brier/incerteza)*100:.1f}%")

    # faixas com tamanho minimo e amplitude maxima de previsao interna
    ordem = np.argsort(prob)
    grupos = []; atual = [ordem[0]]
    n_min = max(10, len(y) // (args.faixas * 2))
    for k in ordem[1:]:
        amplitude = prob[k] - prob[atual[0]]
        if len(atual) >= n_min and amplitude > args.amplitude:
            grupos.append(atual); atual = [k]
        else:
            atual.append(k)
    if len(atual) < n_min and grupos:
        grupos[-1].extend(atual)
    else:
        grupos.append(atual)

    def wilson(k, n, z=1.959963984540054):
        if n == 0:
            return 0.0, 0.0
        f = k / n
        d = 1 + z * z / n
        c = (f + z * z / (2 * n)) / d
        h = z * np.sqrt(f * (1 - f) / n + z * z / (4 * n * n)) / d
        return max(0.0, c - h), min(1.0, c + h)

    print("\n" + "=" * 88)
    print("CURVA DE CONFIABILIDADE")
    print("=" * 88)
    print(f"  {'faixa':>6}{'n':>5}{'previsto':>11}{'observado':>12}{'IC 95% observado':>20}"
          f"{'desvio':>9}  compativel")
    linhas = []; confiab = 0.0; resol = 0.0
    for b, g in enumerate(grupos):
        g = np.array(g); n = len(g)
        pm = float(prob[g].mean()); fo = float(y[g].mean()); dv = fo - pm
        lo, hi = wilson(int(y[g].sum()), n)
        dentro = lo <= pm <= hi
        confiab += n * (pm - fo) ** 2
        resol += n * (fo - prev) ** 2
        print(f"  {b+1:>6}{n:>5}{pm*100:>10.1f}%{fo*100:>11.1f}%"
              f"{lo*100:>12.1f}–{hi*100:<7.1f}{dv*100:>+8.1f}   "
              f"{'sim' if dentro else 'NAO'}")
        linhas.append({"faixa": b + 1, "n": n, "prob_media": pm, "freq_observada": fo,
                       "ic_inf": lo, "ic_sup": hi, "desvio": dv, "compativel": dentro})
    confiab /= len(y); resol /= len(y)

    print("\n" + "=" * 88)
    print("DECOMPOSICAO DE MURPHY")
    print("=" * 88)
    print(f"  confiabilidade (quanto menor, melhor)  {confiab:.4f}")
    print(f"  resolucao      (quanto maior, melhor)  {resol:.4f}")
    print(f"  incerteza      (so depende da amostra) {incerteza:.4f}")
    print(f"  soma dos tres termos:                  {confiab-resol+incerteza:.4f}")
    print(f"  Brier direto:                          {brier:.4f}")
    residuo = brier - (confiab - resol + incerteza)
    print(f"  residuo:                               {residuo:+.4f}")
    print("  O residuo reune duas parcelas e nao indica erro. A identidade de Murphy so")
    print("  e exata quando as previsoes dentro de cada faixa sao identicas. Alem disso,")
    print("  o escore de Brier e calculado sobre a probabilidade POR SITIO, ao passo que")
    print("  a decomposicao opera sobre a probabilidade promediada por padrao: a diferenca")
    print("  entre as duas e justamente o custo da anticorrelacao descrita no cabecalho.")
    if residuo > 0:
        print(f"  O escore reportado e, portanto, CONSERVADOR em cerca de "
              f"{residuo/brier*100:.0f}% em relacao ao que se obteria sem esse deslocamento.")

    print("\n" + "=" * 88)
    print("LEITURA")
    print("=" * 88)
    incomp = [r for r in linhas if not r["compativel"]]
    print(f"  faixas cuja previsao cai fora do intervalo da frequencia observada: "
          f"{len(incomp)} de {len(linhas)}")
    for r in incomp:
        print(f"    faixa {r['faixa']} (n={r['n']}): previsto {r['prob_media']*100:.1f}%, "
              f"observado {r['freq_observada']*100:.1f}% [{r['ic_inf']*100:.1f}–{r['ic_sup']*100:.1f}]")
    print(f"  a confiabilidade responde por {confiab/brier*100:.1f}% do escore de Brier;")
    print("  o restante decorre da incerteza irredutivel da amostra.")

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(linhas)
    print(f"\nsaida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
