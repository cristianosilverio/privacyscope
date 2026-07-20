# -*- coding: utf-8 -*-
"""Regressao logistica com correcao de Firth.

MOTIVACAO
---------
Sob separacao quase completa — situacao em que um preditor nao apresenta
contraexemplo — a estimativa de maxima verossimilhanca nao existe: o otimizador
empurra o coeficiente ao infinito sem que a verossimilhanca atinja maximo finito.
Na matriz de atributos do canal do titular tres preditores estao nessa condicao.

Firth (1993) propos corrigir o vies de ordem 1/n do estimador de maxima
verossimilhanca penalizando a log-verossimilhanca pelo prior invariante de
Jeffreys:

    l*(beta) = l(beta) + (1/2) * log |I(beta)|

onde I(beta) = X' W X e a informacao de Fisher e W = diag(p_i (1 - p_i)).

Heinze e Schemper (2002) demonstraram que a estimativa resultante e sempre
finita, inclusive sob separacao completa. A propriedade decorre da correcao, nao
constitui seu objetivo original.

Duas caracteristicas motivaram a adocao neste trabalho: o metodo nao possui
hiperparametro, o que elimina decisao arbitraria e a necessidade de validacao
cruzada aninhada — ruidosa no tamanho de amostra disponivel; e enderecar
simultaneamente amostra pequena e separacao, que sao exatamente as condicoes
presentes.

ALGORITMO
---------
Minimos quadrados reponderados iterativamente sobre o escore modificado. O escore
de Firth acrescenta ao residuo comum um termo proporcional a alavancagem:

    U*(beta) = X' [ (y - p) + h * (1/2 - p) ]

com h o vetor diagonal da matriz chapeu H = W^(1/2) X (X'WX)^(-1) X' W^(1/2).
A atualizacao e beta <- beta + (X'WX)^(-1) U*(beta), com reducao pela metade do
passo sempre que a log-verossimilhanca penalizada nao aumentar.

INFERENCIA
----------
O intervalo de Wald, beta +/- 1,96 EP, pressupoe log-verossimilhanca aproximada
por parabola simetrica em torno do maximo. Sob separacao a superficie e
acentuadamente assimetrica — ingreme em direcao a zero e quase plana em direcao
ao infinito, ja que nao existe contraexemplo que penalize coeficiente grande —, e
o intervalo simetrico erra nas duas extremidades. Pelo mesmo motivo o teste de
Wald perde poder onde a evidencia e mais forte: o erro-padrao infla e a
estatistica tende a zero.

Adota-se por isso o intervalo por perfil da verossimilhanca penalizada, conforme
recomendacao de Heinze e Schemper (2002). Prende-se o coeficiente de interesse em
um valor candidato c, reotimiza-se a verossimilhanca penalizada sobre os demais
coeficientes e calcula-se

    TRV(c) = 2 [ l*(beta_chapeu) - l*(c) ]

O intervalo de nivel 1-alfa reune os valores de c com TRV(c) menor que o quantil
correspondente da distribuicao qui-quadrado com um grau de liberdade. Os extremos
sao obtidos por busca de raiz. O procedimento dispensa suposicao sobre a forma da
superficie e produz intervalos assimetricos quando a evidencia assim o determina.

Ao prender um coeficiente, o determinante de Jeffreys permanece calculado sobre a
matriz de informacao COMPLETA, e nao sobre a do submodelo: a penalizacao pertence
ao modelo integral, e substitui-la alteraria a funcao objetivo entre os pontos
comparados, invalidando a diferenca de verossimilhancas.

O mesmo mecanismo, com c fixado em zero, fornece o teste da razao de
verossimilhancas penalizada, que substitui o teste de Wald.

VALIDACAO
---------
A rotina e verificada em tests_unit/test_firth.py contra propriedades conhecidas:
equivalencia analitica ao acrescimo de 1/2 a cada celula em tabela 2x2;
convergencia ao estimador de maxima verossimilhanca a medida que n cresce na
ausencia de separacao; finitude sob separacao completa; e concordancia entre
intervalo por perfil e intervalo de Wald quando nao ha separacao, com divergencia
no sentido esperado quando ha.
"""
from __future__ import annotations

import numpy as np


def _sigmoide(eta):
    """Funcao logistica em forma numericamente estavel.

    A expressao direta 1/(1+exp(-eta)) estoura para eta muito negativo. Avalia-se
    por isso cada ramo com o expoente de sinal favoravel, o que mantem o
    argumento de exp sempre nao positivo. A busca do perfil percorre valores
    deliberadamente extremos de coeficiente, regime em que a forma ingenua emite
    aviso de estouro a cada avaliacao.
    """
    eta = np.asarray(eta, dtype=float)
    saida = np.empty_like(eta)
    pos = eta >= 0
    saida[pos] = 1.0 / (1.0 + np.exp(-eta[pos]))
    e = np.exp(eta[~pos])
    saida[~pos] = e / (1.0 + e)
    return saida


def _log_verossimilhanca_penalizada(X, y, beta):
    """l(beta) + (1/2) log|I(beta)|. Retorna -inf em configuracao degenerada."""
    eta = X @ beta
    # forma numericamente estavel de log(1+exp(eta))
    log1pexp = np.logaddexp(0.0, eta)
    ll = float(np.sum(y * eta - log1pexp))
    p = _sigmoide(eta)
    w = p * (1.0 - p)
    info = X.T @ (X * w[:, None])
    sinal, logdet = np.linalg.slogdet(info)
    if sinal <= 0:
        return -np.inf
    return ll + 0.5 * logdet


def firth_logistic(X, y, *, max_iter=200, tol=1e-8, com_intercepto=True,
                   max_halving=25, fixar=None):
    """Ajusta regressao logistica com correcao de Firth.

    Args:
        X: matriz (n, p) de preditores.
        y: vetor (n,) com valores em {0, 1}.
        max_iter: teto de iteracoes do IRLS.
        tol: criterio de parada sobre a norma maxima do passo.
        com_intercepto: acrescenta coluna de uns como primeira coluna.
        max_halving: reducoes sucessivas do passo por iteracao.
        fixar: par ``(j, c)`` que prende o coeficiente de indice ``j`` no valor
            ``c``, maximizando sobre os demais. O indice segue a numeracao de
            ``beta``, na qual a posicao 0 corresponde ao intercepto quando este e
            solicitado. Sustenta o perfil da verossimilhanca; em uso comum
            permanece ``None``.

    Returns:
        dict com ``beta`` (coeficientes; o intercepto ocupa a posicao 0 quando
        solicitado), ``iteracoes``, ``convergiu`` e ``loglik_penalizada``.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float).ravel()
    if com_intercepto:
        X = np.column_stack([np.ones(len(X)), X])
    n, p = X.shape
    beta = np.zeros(p)
    if fixar is None:
        livres = np.arange(p)
    else:
        j_fixo, valor_fixo = int(fixar[0]), float(fixar[1])
        if not 0 <= j_fixo < p:
            raise ValueError(f"indice {j_fixo} fora da faixa de coeficientes")
        beta[j_fixo] = valor_fixo
        livres = np.array([k for k in range(p) if k != j_fixo])
    ll_atual = _log_verossimilhanca_penalizada(X, y, beta)
    convergiu = False
    it = 0

    for it in range(1, max_iter + 1):
        eta = X @ beta
        pr = _sigmoide(eta)
        w = pr * (1.0 - pr)
        w = np.clip(w, 1e-12, None)          # evita informacao singular
        info = X.T @ (X * w[:, None])
        info_inv = np.linalg.pinv(info)

        # diagonal da matriz chapeu, sem materializar H inteira
        Xw = X * np.sqrt(w)[:, None]
        h = np.einsum("ij,jk,ik->i", Xw, info_inv, Xw)

        escore = X.T @ ((y - pr) + h * (0.5 - pr))
        if fixar is None:
            passo = info_inv @ escore
        else:
            # passo de Newton restrito as coordenadas livres: resolve-se o
            # subsistema correspondente, mantendo o coeficiente preso intacto
            passo = np.zeros(p)
            sub = np.linalg.pinv(info[np.ix_(livres, livres)]) @ escore[livres]
            passo[livres] = sub

        # reducao do passo pela metade ate que a log-verossimilhanca aumente
        fator = 1.0
        for _ in range(max_halving):
            cand = beta + fator * passo
            ll_cand = _log_verossimilhanca_penalizada(X, y, cand)
            if ll_cand > ll_atual or not np.isfinite(ll_atual):
                beta, ll_atual = cand, ll_cand
                break
            fator /= 2.0
        else:
            break                             # nenhum passo melhora: encerra

        if np.max(np.abs(fator * passo)) < tol:
            convergiu = True
            break

    return {"beta": beta, "iteracoes": it, "convergiu": convergiu,
            "loglik_penalizada": ll_atual}


def prever_prob(X, beta, *, com_intercepto=True):
    """Probabilidades preditas para a matriz X sob os coeficientes beta."""
    X = np.asarray(X, dtype=float)
    if com_intercepto:
        X = np.column_stack([np.ones(len(X)), X])
    return _sigmoide(X @ beta)


def _quantil_qui2(nivel):
    """Quantil da qui-quadrado com um grau de liberdade."""
    from scipy.stats import chi2
    return float(chi2.ppf(nivel, 1))


def erro_padrao_wald(X, y, beta, *, com_intercepto=True):
    """Erro-padrao pela raiz da diagonal da inversa da informacao de Fisher.

    Reportado apenas como referencia de comparacao. Sob separacao o valor infla e
    nao sustenta intervalo confiavel; o intervalo valido e o do perfil.
    """
    X = np.asarray(X, dtype=float)
    if com_intercepto:
        X = np.column_stack([np.ones(len(X)), X])
    pr = _sigmoide(X @ beta)
    w = np.clip(pr * (1.0 - pr), 1e-12, None)
    return np.sqrt(np.diag(np.linalg.pinv(X.T @ (X * w[:, None]))))


def ic_perfil(X, y, j, *, nivel=0.95, com_intercepto=True, passo_busca=0.5,
              limite=80.0, tol=1e-4):
    """Intervalo de confianca por perfil da verossimilhanca penalizada.

    Args:
        X, y: dados, na mesma convencao de ``firth_logistic``.
        j: indice do coeficiente na numeracao de ``beta``.
        nivel: nivel de confianca.
        passo_busca: incremento na expansao do intervalo de busca.
        limite: afastamento maximo da estimativa pontual antes de declarar o
            extremo nao identificado.
        tol: tolerancia da busca de raiz.

    Returns:
        dict com ``inferior``, ``superior``, ``beta`` e ``identificado``. Um
        extremo nao identificado retorna infinito com o sinal correspondente.
    """
    from scipy.optimize import brentq

    ajuste = firth_logistic(X, y, com_intercepto=com_intercepto)
    beta = ajuste["beta"]
    ll_max = ajuste["loglik_penalizada"]
    critico = _quantil_qui2(nivel)

    def excesso(c):
        """TRV(c) menos o valor critico. Negativo dentro do intervalo."""
        ll_c = firth_logistic(X, y, com_intercepto=com_intercepto,
                              fixar=(j, c))["loglik_penalizada"]
        if not np.isfinite(ll_c):
            return np.inf
        return 2.0 * (ll_max - ll_c) - critico

    def extremo(sentido):
        """Percorre em um sentido ate cruzar o valor critico e refina a raiz."""
        borda = beta[j]
        for _ in range(int(limite / passo_busca)):
            proximo = borda + sentido * passo_busca
            if excesso(proximo) > 0:
                a, b = (proximo, borda) if sentido < 0 else (borda, proximo)
                return float(brentq(excesso, a, b, xtol=tol))
            borda = proximo
        return sentido * np.inf

    inf, sup = extremo(-1.0), extremo(+1.0)
    return {"inferior": inf, "superior": sup, "beta": float(beta[j]),
            "identificado": bool(np.isfinite(inf) and np.isfinite(sup))}


def razao_verossimilhanca_penalizada(X, y, j, *, com_intercepto=True):
    """Teste da razao de verossimilhancas penalizada contra beta_j igual a zero.

    O nome evita o prefixo ``teste`` porque coletores de teste automatizados
    recolhem funcoes assim nomeadas ao importa-las, tratando-as como casos de
    teste.

    Substitui o teste de Wald, cuja estatistica se degrada sob separacao porque o
    erro-padrao infla e conduz a nao rejeicao justamente onde a associacao e mais
    intensa.
    """
    from scipy.stats import chi2

    completo = firth_logistic(X, y, com_intercepto=com_intercepto)
    restrito = firth_logistic(X, y, com_intercepto=com_intercepto, fixar=(j, 0.0))
    est = 2.0 * (completo["loglik_penalizada"] - restrito["loglik_penalizada"])
    est = max(est, 0.0)                       # protege contra ruido numerico
    return {"qui2": float(est), "gl": 1, "p": float(chi2.sf(est, 1))}


__all__ = ["firth_logistic", "prever_prob", "erro_padrao_wald", "ic_perfil",
           "razao_verossimilhanca_penalizada"]
