# -*- coding: utf-8 -*-
"""Propriedades do artefato de modelo.

A verificacao decisiva e a equivalencia da vetorizacao propria com a da biblioteca
de aprendizado: e ela que autoriza a inferencia a nao depender daquela biblioteca.
Roda sobre o corpo real quando ele esta disponivel, e sobre corpo sintetico sempre.
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from privacyscope.models.artefato import (
    Artefato, ArtefatoCorrompido, grava, le, resumo_arquivo, resumo_texto,
)

REPO = Path(__file__).resolve().parents[1]
CORPO = REPO / "outputs" / "segmentos_rotulados.csv"

TEXTOS = [
    "Tratamos os seus dados pessoais para a finalidade de entrega do pedido.",
    "Voce pode solicitar a confirmacao do tratamento e o acesso aos dados.",
    "Nao compartilhamos os seus dados com terceiros sem o seu consentimento.",
    "Os dados podem ser transferidos para servidores localizados no exterior.",
    "Utilizamos cookies para melhorar a sua experiencia de navegacao.",
]


def _ajusta(textos, y):
    """Ajuste de referencia pela biblioteca, do qual se extrai o artefato."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    vec = TfidfVectorizer(lowercase=True, stop_words=None, ngram_range=(1, 3),
                          min_df=1, sublinear_tf=True, norm="l2", strip_accents=None)
    X = vec.fit_transform(textos)
    m = LogisticRegression(C=1.0, max_iter=3000, solver="liblinear").fit(X, y)
    return vec, m


@pytest.fixture
def artefato(tmp_path):
    y = [1, 0, 0, 1, 0]
    vec, m = _ajusta(TEXTOS, y)
    caminho = tmp_path / "t.npz"
    sha = grava(caminho, variavel="finalidade",
                vocabulario={t: int(j) for t, j in vec.vocabulary_.items()},
                idf=vec.idf_, coeficientes=m.coef_[0], intercepto=float(m.intercept_[0]),
                limiar=0.42, preparo_versao="1.0.0",
                preparo_parametros={"MIN_SEG": 20},
                corpo_sha256=resumo_texto(TEXTOS),
                cobertura_treino={"p05": 0.30, "mediana": 0.70},
                gerado_por="test_artefato")
    return caminho, sha, vec, m


def test_ida_e_volta_preserva_tudo(artefato):
    caminho, sha, vec, m = artefato
    a = le(caminho, sha)
    assert a.variavel == "finalidade"
    assert a.limiar == 0.42
    assert a.preparo_versao == "1.0.0"
    assert a.sha256 == sha
    assert len(a.vocabulario) == len(vec.vocabulary_)
    assert np.allclose(a.idf, vec.idf_)
    assert np.allclose(a.coeficientes, m.coef_[0])


def test_identidade_divergente_interrompe(artefato):
    caminho, sha, _, _ = artefato
    with pytest.raises(ArtefatoCorrompido) as e:
        le(caminho, "0" * 64)
    assert "nao prossegue" in str(e.value)


def test_arquivo_alterado_e_detectado(artefato):
    caminho, sha, _, _ = artefato
    dados = bytearray(caminho.read_bytes())
    dados[-1] ^= 0x01
    caminho.write_bytes(bytes(dados))
    assert resumo_arquivo(caminho) != sha


def test_vetorizacao_propria_coincide_com_a_da_biblioteca(artefato):
    """Sem esta igualdade a inferencia teria de importar a biblioteca de
    aprendizado, e o artefato voltaria a depender da versao instalada."""
    caminho, sha, vec, _ = artefato
    a = le(caminho, sha)
    novos = ["Coletamos dados pessoais para a finalidade de cobranca.",
             "Nada aqui pertence ao vocabulario conhecido zzz qqq."]
    assert np.allclose(a.vetoriza(novos), vec.transform(novos).toarray(), atol=1e-12)


def test_probabilidade_coincide_com_a_da_biblioteca(artefato):
    caminho, sha, vec, m = artefato
    a = le(caminho, sha)
    novos = ["Tratamos dados para a finalidade de entrega.", "Texto qualquer."]
    assert np.allclose(a.probabilidades(novos),
                       m.predict_proba(vec.transform(novos))[:, 1], atol=1e-10)


@pytest.mark.skipif(not CORPO.exists(), reason="corpo rotulado indisponivel")
def test_equivalencia_sobre_o_corpo_real(tmp_path):
    """A igualdade tem de valer no material do trabalho, e nao so em exemplo."""
    import csv
    csv.field_size_limit(10 ** 7)
    with CORPO.open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    textos = [r["texto"] for r in R]
    y = [int(r["finalidade"]) for r in R]
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    vec = TfidfVectorizer(lowercase=True, stop_words=None, ngram_range=(1, 3),
                          min_df=3, sublinear_tf=True, norm="l2", strip_accents=None)
    X = vec.fit_transform(textos)
    m = LogisticRegression(C=10.0, max_iter=3000, solver="liblinear").fit(X, y)
    caminho = tmp_path / "real.npz"
    sha = grava(caminho, variavel="finalidade",
                vocabulario={t: int(j) for t, j in vec.vocabulary_.items()},
                idf=vec.idf_, coeficientes=m.coef_[0],
                intercepto=float(m.intercept_[0]), limiar=0.5)
    a = le(caminho, sha)
    amostra = textos[:400]
    assert np.allclose(a.vetoriza(amostra), vec.transform(amostra).toarray(), atol=1e-12)
    assert np.allclose(a.probabilidades(amostra),
                       m.predict_proba(vec.transform(amostra))[:, 1], atol=1e-10)


def test_cobertura_e_extrapolacao(artefato):
    caminho, sha, _, _ = artefato
    a = le(caminho, sha)
    conhecido = a.cobertura(TEXTOS[0])
    estranho = a.cobertura("zzz qqq www vvv uuu ttt sss rrr")
    assert conhecido > estranho
    assert a.em_extrapolacao(estranho)
    assert not a.em_extrapolacao(conhecido)


def test_dimensoes_incompativeis_sao_recusadas(tmp_path):
    with pytest.raises(ValueError, match="dimensoes incompativeis"):
        grava(tmp_path / "x.npz", variavel="v", vocabulario={"a": 0, "b": 1},
              idf=[1.0], coeficientes=[1.0, 2.0], intercepto=0.0, limiar=0.5)


def test_vocabulario_com_lacuna_e_recusado(tmp_path):
    with pytest.raises(ValueError, match="intervalo contiguo"):
        grava(tmp_path / "x.npz", variavel="v", vocabulario={"a": 0, "b": 2},
              idf=[1.0, 1.0], coeficientes=[1.0, 2.0], intercepto=0.0, limiar=0.5)


def test_nao_ha_pickle_no_arquivo(artefato):
    """O artefato e recipiente de dados; se contivesse codigo serializado, le-lo
    seria executa-lo."""
    caminho, _, _, _ = artefato
    bruto = caminho.read_bytes()
    assert b"sklearn" not in bruto and b"__reduce__" not in bruto


def test_resumo_de_texto_distingue_sequencias(tmp_path):
    assert resumo_texto(["ab", "c"]) != resumo_texto(["a", "bc"])


def test_sigmoide_estavel_em_argumento_extremo(artefato):
    caminho, sha, _, _ = artefato
    a = le(caminho, sha)
    from privacyscope.models.artefato import _sigmoide
    p = _sigmoide(np.array([-2000.0, 0.0, 2000.0]))
    assert p[0] == pytest.approx(0.0) and p[2] == pytest.approx(1.0)
    assert p[1] == pytest.approx(0.5)


def test_regularizacao_e_proveniencia_e_nao_afeta_a_inferencia(tmp_path):
    """O valor viaja no artefato para que o ajuste de origem seja reproduzivel,
    mas nao entra em conta alguma na predicao."""
    vec, m = _ajusta(TEXTOS, [1, 0, 0, 1, 0])
    comum = dict(variavel="v", vocabulario={t: int(j) for t, j in vec.vocabulary_.items()},
                 idf=vec.idf_, coeficientes=m.coef_[0],
                 intercepto=float(m.intercept_[0]), limiar=0.5)
    s1 = grava(tmp_path / "a.npz", regularizacao=1.0, **comum)
    s2 = grava(tmp_path / "b.npz", regularizacao=80.0, **comum)
    a, b = le(tmp_path / "a.npz", s1), le(tmp_path / "b.npz", s2)
    assert a.regularizacao == 1.0 and b.regularizacao == 80.0
    assert np.allclose(a.probabilidades(TEXTOS), b.probabilidades(TEXTOS))
    assert s1 != s2, "artefatos com proveniencia distinta tem identidades distintas"
