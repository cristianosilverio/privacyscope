# -*- coding: utf-8 -*-
"""Validacao da regressao logistica com correcao de Firth.

Rotinas estatisticas falham em silencio: produzem numeros plausiveis e errados.
A implementacao e portanto confrontada com propriedades conhecidas do estimador
de Firth, cada uma verificavel de forma independente.

  1. Equivalencia analitica em tabela 2x2. Para um unico preditor binario, a
     estimativa de Firth coincide com a razao de chances calculada apos somar
     1/2 a cada celula. A propriedade decorre de o prior de Jeffreys para a
     binomial ser Beta(1/2, 1/2).

  2. Convergencia ao estimador de maxima verossimilhanca. A correcao remove um
     vies de ordem 1/n; na ausencia de separacao, a diferenca entre Firth e
     maxima verossimilhanca deve diminuir a medida que n cresce.

  3. Finitude sob separacao completa. Onde a maxima verossimilhanca diverge, a
     estimativa de Firth permanece finita — propriedade demonstrada por Heinze e
     Schemper (2002) e razao pela qual o metodo foi adotado.

  4. Coerencia da inferencia por perfil. Na ausencia de separacao a
     verossimilhanca e aproximadamente quadratica e o intervalo por perfil deve
     reproduzir o de Wald; sob separacao a superficie e assimetrica e os dois
     devem divergir, com o perfil deslocando o limite superior para cima.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_spec = importlib.util.spec_from_file_location(
    "firth", Path(__file__).resolve().parents[1] / "scripts" / "firth.py")
_firth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_firth)
firth_logistic = _firth.firth_logistic
prever_prob = _firth.prever_prob
erro_padrao_wald = _firth.erro_padrao_wald
ic_perfil = _firth.ic_perfil
razao_verossimilhanca_penalizada = _firth.razao_verossimilhanca_penalizada


def _tabela_2x2(a, b, c, d):
    """Constroi (X, y) a partir das contagens de uma tabela 2x2.

    a: x=1,y=1   b: x=1,y=0   c: x=0,y=1   d: x=0,y=0
    """
    X = np.concatenate([np.ones(a + b), np.zeros(c + d)]).reshape(-1, 1)
    y = np.concatenate([np.ones(a), np.zeros(b), np.ones(c), np.zeros(d)])
    return X, y


# ---------------------------------------------------------------- propriedade 1
@pytest.mark.parametrize("a,b,c,d", [
    (20, 10, 15, 25),
    (12, 8, 30, 40),
    (7, 3, 5, 9),
])
def test_equivalencia_tabela_2x2(a, b, c, d):
    """Firth equivale ao acrescimo de 1/2 por celula em tabela 2x2."""
    X, y = _tabela_2x2(a, b, c, d)
    beta = firth_logistic(X, y)["beta"]
    esperado = np.log(((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5)))
    assert beta[1] == pytest.approx(esperado, abs=1e-6)


def test_equivalencia_2x2_com_celula_zerada():
    """A equivalencia vale tambem sob separacao, onde a razao de chances bruta
    seria infinita: nenhum caso com x=1 e y=0."""
    a, b, c, d = 15, 0, 10, 20
    X, y = _tabela_2x2(a, b, c, d)
    beta = firth_logistic(X, y)["beta"]
    esperado = np.log(((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5)))
    assert np.isfinite(beta[1])
    assert beta[1] == pytest.approx(esperado, abs=1e-6)


# ---------------------------------------------------------------- propriedade 2
def test_converge_para_maxima_verossimilhanca_com_n_grande():
    """Sem separacao, a diferenca para a maxima verossimilhanca decresce com n."""
    from sklearn.linear_model import LogisticRegression

    def distancia(n):
        rng = np.random.default_rng(20260719)
        X = rng.normal(size=(n, 2))
        eta = 0.4 + 0.8 * X[:, 0] - 0.5 * X[:, 1]
        y = (rng.uniform(size=n) < 1 / (1 + np.exp(-eta))).astype(float)
        b_firth = firth_logistic(X, y)["beta"]
        # C=np.inf equivale a ausencia de regularizacao e independe da forma
        # como a versao do scikit-learn expoe o argumento de penalizacao
        mle = LogisticRegression(C=np.inf, max_iter=2000).fit(X, y)
        b_mle = np.concatenate([mle.intercept_, mle.coef_.ravel()])
        return float(np.max(np.abs(b_firth - b_mle)))

    d_pequeno, d_grande = distancia(200), distancia(4000)
    assert d_grande < d_pequeno
    assert d_grande < 0.06


# ---------------------------------------------------------------- propriedade 3
def test_finitude_sob_separacao_completa():
    """Onde a maxima verossimilhanca diverge, Firth permanece finito."""
    from sklearn.linear_model import LogisticRegression

    X = np.arange(40, dtype=float).reshape(-1, 1)
    y = (X.ravel() >= 20).astype(float)          # separacao perfeita

    mle = LogisticRegression(C=np.inf, max_iter=5000).fit(X, y)
    b_mle = abs(float(mle.coef_.ravel()[0]))

    r = firth_logistic(X, y)
    b_firth = abs(float(r["beta"][1]))

    assert np.all(np.isfinite(r["beta"]))
    assert b_firth < b_mle                        # nao diverge como o MLE
    assert b_firth > 0                            # e preserva o sinal detectado


def test_probabilidades_no_intervalo_unitario():
    """As probabilidades preditas permanecem estritamente em (0, 1)."""
    X, y = _tabela_2x2(15, 0, 10, 20)
    beta = firth_logistic(X, y)["beta"]
    p = prever_prob(X, beta)
    assert np.all((p > 0) & (p < 1))


def test_convergencia_declarada():
    """O ajuste sinaliza convergencia em configuracao regular."""
    X, y = _tabela_2x2(20, 10, 15, 25)
    r = firth_logistic(X, y)
    assert r["convergiu"] is True
    assert r["iteracoes"] < 50


# ---------------------------------------------------------------------------
# 4. Inferencia por perfil da verossimilhanca penalizada
# ---------------------------------------------------------------------------
def _amostra(n, semente, separado=False, n_sep=18):
    """Gera amostra com um preditor continuo e um binario.

    Com ``separado``, o preditor binario ocorre exclusivamente na classe
    positiva, reproduzindo a condicao de separacao quase completa observada em
    F1 e F2 na matriz de atributos do canal.
    """
    rng = np.random.default_rng(semente)
    x1 = rng.normal(size=n)
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-(0.2 + 0.9 * x1)))).astype(float)
    x2 = np.zeros(n)
    if separado:
        x2[np.where(y == 1)[0][:n_sep]] = 1.0
    else:
        x2[rng.permutation(n)[: n // 4]] = 1.0
    return np.column_stack([x1, x2]), y


def test_fixar_mantem_o_coeficiente_no_valor_pedido():
    """O coeficiente preso nao se move; os demais se reacomodam."""
    X, y = _amostra(200, 11)
    livre = firth_logistic(X, y)["beta"]
    preso = firth_logistic(X, y, fixar=(1, 0.0))["beta"]
    assert preso[1] == pytest.approx(0.0, abs=1e-12)
    # a reotimizacao dos demais e o que caracteriza o perfil
    assert not np.allclose(preso[0], livre[0])


def test_verossimilhanca_do_perfil_nunca_supera_a_do_maximo():
    """Restringir o espaco de busca nao pode elevar o maximo atingido."""
    X, y = _amostra(200, 12)
    ll_max = firth_logistic(X, y)["loglik_penalizada"]
    for c in (-2.0, -0.5, 0.0, 0.5, 2.0):
        ll_c = firth_logistic(X, y, fixar=(1, c))["loglik_penalizada"]
        assert ll_c <= ll_max + 1e-8


def test_intervalo_por_perfil_contem_a_estimativa_pontual():
    X, y = _amostra(200, 13)
    r = ic_perfil(X, y, 1)
    assert r["identificado"]
    assert r["inferior"] < r["beta"] < r["superior"]


def test_perfil_reproduz_wald_na_ausencia_de_separacao():
    """Verossimilhanca quase quadratica: os dois intervalos devem coincidir."""
    X, y = _amostra(600, 14)
    beta = firth_logistic(X, y)["beta"]
    ep = erro_padrao_wald(X, y, beta)
    perfil = ic_perfil(X, y, 1)
    assert perfil["inferior"] == pytest.approx(beta[1] - 1.96 * ep[1], abs=0.12)
    assert perfil["superior"] == pytest.approx(beta[1] + 1.96 * ep[1], abs=0.12)


def test_perfil_e_assimetrico_sob_separacao():
    """Sem contraexemplo, a superficie e plana para cima e ingreme para baixo."""
    X, y = _amostra(200, 7, separado=True)
    beta = firth_logistic(X, y)["beta"]
    r = ic_perfil(X, y, 2)
    assert r["identificado"]
    abaixo = r["beta"] - r["inferior"]
    acima = r["superior"] - r["beta"]
    assert acima > 1.5 * abaixo         # cauda superior sensivelmente mais longa

    # o intervalo de Wald, simetrico por construcao, erra nas duas extremidades
    ep = erro_padrao_wald(X, y, beta)
    assert r["inferior"] > beta[2] - 1.96 * ep[2]
    assert r["superior"] > beta[2] + 1.96 * ep[2]


def test_razao_de_verossimilhancas_separa_preditor_util_de_ruido():
    X, y = _amostra(300, 15)
    forte = razao_verossimilhanca_penalizada(X, y, 1)      # preditor com efeito real
    assert forte["p"] < 1e-4
    assert forte["gl"] == 1

    rng = np.random.default_rng(16)
    Xr = np.column_stack([X[:, 0], rng.normal(size=len(y))])
    ruido = razao_verossimilhanca_penalizada(Xr, y, 2)     # preditor sem relacao
    assert ruido["p"] > 0.05
    assert ruido["p"] > forte["p"]


def test_razao_de_verossimilhancas_rejeita_sob_separacao():
    """Onde o teste de Wald perderia poder, a razao de verossimilhancas rejeita."""
    X, y = _amostra(200, 7, separado=True)
    assert razao_verossimilhanca_penalizada(X, y, 2)["p"] < 0.001
