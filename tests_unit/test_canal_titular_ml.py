# -*- coding: utf-8 -*-
"""Contrato e recusas do plugin do canal do titular por classificacao."""
from datetime import datetime, timezone

import pytest

from privacyscope.core.plugin_registry import resolve
from privacyscope.core.types import Domain, RawEvidence
from privacyscope.features.canal_titular import ATRIBUTOS, VERSAO_EXTRATOR
from privacyscope.models.artefato import ArtefatoCorrompido, grava, grava_canal
from privacyscope.tests.canal_titular_ml import CanalTitularMLTest

COEF = [4.5, 3.6, 2.5, 0.6, -0.4, -1.2, 1.2, 1.8]


def _artefato(tmp_path, variavel="tem_canal_titular", extrator=VERSAO_EXTRATOR):
    caminho = tmp_path / "canal.npz"
    sha = grava_canal(caminho, variavel=variavel, atributos=ATRIBUTOS,
                      coeficientes=COEF, intercepto=-2.41, limiar=0.5,
                      extrator_versao=extrator, extrator_parametros={"janela": 200},
                      corpo_sha256="abc", n_observacoes=207)
    return caminho, sha


def _evidencia(paginas, subsel=None):
    return RawEvidence(domain=Domain(url="https://exemplo.com.br", tld=".com.br",
                                     source_name="teste"),
                       html_pages=paginas, subpage_selection=subsel or {},
                       fetcher_name="teste", timestamp_utc=datetime.now(timezone.utc))


COM_CANAL = (b"<html><body><p>Para exercer seus direitos, escreva para "
             b"dpo@exemplo.com.br.</p></body></html>")
SEM_CANAL = b"<html><body><p>Nossa empresa atua desde 1990 no mercado.</p></body></html>"


def test_registro_mantem_os_dois_regimes():
    """O determinístico permanece: os resultados reportam ambos."""
    regra = resolve("variable_tests", "canal_titular")
    ml = resolve("variable_tests", "canal_titular_ml")
    assert regra is not ml
    assert regra.variable_name == ml.variable_name == "tem_canal_titular"


def test_contrato_de_saida(tmp_path):
    caminho, sha = _artefato(tmp_path)
    r = CanalTitularMLTest().evaluate(
        _evidencia({"/": COM_CANAL}),
        {"modelo_file": str(caminho), "modelo_sha256": sha},
        protocol_version="v1", run_id="r1")
    assert isinstance(r.value, bool)
    assert 0.0 <= r.confidence <= 1.0
    assert set(r.audit_trail["atributos"]) == set(ATRIBUTOS)
    assert r.audit_trail["modelo_sha256"] == sha
    assert r.audit_trail["janela"] == 200
    assert r.variable_name == "tem_canal_titular"


def test_atributos_refletem_o_material(tmp_path):
    caminho, sha = _artefato(tmp_path)
    t = CanalTitularMLTest()
    params = {"modelo_file": str(caminho), "modelo_sha256": sha}
    com = t.evaluate(_evidencia({"/": COM_CANAL}), params,
                     protocol_version="v", run_id="r")
    sem = t.evaluate(_evidencia({"/": SEM_CANAL}), params,
                     protocol_version="v", run_id="r")
    assert com.audit_trail["atributos"]["F1_email_lgpd_proprio"] == 1
    assert sem.audit_trail["atributos"]["F1_email_lgpd_proprio"] == 0
    assert com.confidence > sem.confidence


def test_ordem_de_concatenacao_e_declarada(tmp_path):
    """Pagina inicial primeiro, subpaginas ordenadas pela chave."""
    ev = _evidencia({"/z": b"<p>zzz</p>", "/": b"<p>raiz</p>", "/a": b"<p>aaa</p>"})
    html = CanalTitularMLTest.html_concatenado(ev)
    assert html.index("raiz") < html.index("aaa") < html.index("zzz")


def test_artefato_divergente_interrompe(tmp_path):
    caminho, _ = _artefato(tmp_path)
    with pytest.raises(ArtefatoCorrompido):
        CanalTitularMLTest().evaluate(
            _evidencia({"/": COM_CANAL}),
            {"modelo_file": str(caminho), "modelo_sha256": "0" * 64},
            protocol_version="v", run_id="r")


def test_artefato_de_outra_variavel_e_recusado(tmp_path):
    caminho, sha = _artefato(tmp_path, variavel="outra_coisa")
    with pytest.raises(ValueError, match="Artefato trocado"):
        CanalTitularMLTest().evaluate(
            _evidencia({"/": COM_CANAL}),
            {"modelo_file": str(caminho), "modelo_sha256": sha},
            protocol_version="v", run_id="r")


def test_extrator_de_outra_versao_e_recusado(tmp_path):
    """Extrator e coeficientes formam par; aplicar um sobre o outro produz
    predicao plausivel e errada."""
    caminho, sha = _artefato(tmp_path, extrator="0.9.0")
    with pytest.raises(ValueError, match="formam par"):
        CanalTitularMLTest().evaluate(
            _evidencia({"/": COM_CANAL}),
            {"modelo_file": str(caminho), "modelo_sha256": sha},
            protocol_version="v", run_id="r")


def test_artefato_de_texto_e_recusado(tmp_path):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    vec = TfidfVectorizer(min_df=1)
    X = vec.fit_transform(["um texto qualquer", "outro texto diferente"])
    m = LogisticRegression().fit(X, [0, 1])
    caminho = tmp_path / "texto.npz"
    sha = grava(caminho, variavel="finalidade",
                vocabulario={t: int(j) for t, j in vec.vocabulary_.items()},
                idf=vec.idf_, coeficientes=m.coef_[0],
                intercepto=float(m.intercept_[0]), limiar=0.5)
    with pytest.raises(ArtefatoCorrompido, match="tipo"):
        CanalTitularMLTest().evaluate(
            _evidencia({"/": COM_CANAL}),
            {"modelo_file": str(caminho), "modelo_sha256": sha},
            protocol_version="v", run_id="r")


def test_protocolo_sem_modelo_interrompe():
    with pytest.raises(ValueError, match="modelo_file"):
        CanalTitularMLTest().evaluate(_evidencia({"/": COM_CANAL}), {},
                                      protocol_version="v", run_id="r")


def test_artefato_lido_uma_unica_vez(tmp_path, monkeypatch):
    import privacyscope.tests.canal_titular_ml as mod
    caminho, sha = _artefato(tmp_path)
    n = {"leituras": 0}
    original = mod.le_canal

    def conta(*a, **k):
        n["leituras"] += 1
        return original(*a, **k)

    monkeypatch.setattr(mod, "le_canal", conta)
    t = CanalTitularMLTest()
    for _ in range(4):
        t.evaluate(_evidencia({"/": COM_CANAL}),
                   {"modelo_file": str(caminho), "modelo_sha256": sha},
                   protocol_version="v", run_id="r")
    assert n["leituras"] == 1


def test_sitio_sem_paginas_nao_levanta(tmp_path):
    caminho, sha = _artefato(tmp_path)
    r = CanalTitularMLTest().evaluate(
        _evidencia({}), {"modelo_file": str(caminho), "modelo_sha256": sha},
        protocol_version="v", run_id="r")
    assert r.value is False
    assert all(v == 0 for v in r.audit_trail["atributos"].values())
