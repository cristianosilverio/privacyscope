# -*- coding: utf-8 -*-
"""Contrato de saida e comportamento dos plugins das variaveis textuais."""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from privacyscope.core.plugin_registry import resolve
from privacyscope.core.types import Domain, RawEvidence
from privacyscope.models.artefato import grava
from privacyscope.tests.ml_texto import FinalidadeEspecificadaTest

POSITIVA = ("Tratamos os seus dados pessoais para a finalidade de entrega do pedido "
            "e para a prevencao de fraudes nas transacoes realizadas.")
NEUTRA = ("Nossa empresa atua no mercado desde mil novecentos e noventa e possui "
          "unidades em diversas cidades brasileiras do territorio nacional.")


def _artefato(tmp_path, variavel="finalidade", limiar=0.5):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    textos = [POSITIVA, NEUTRA, POSITIVA.replace("entrega", "cobranca"),
              NEUTRA.replace("empresa", "companhia")]
    y = [1, 0, 1, 0]
    vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 3), min_df=1,
                          sublinear_tf=True, norm="l2")
    X = vec.fit_transform(textos)
    m = LogisticRegression(C=1.0, max_iter=3000, solver="liblinear").fit(X, y)
    caminho = tmp_path / f"{variavel}.npz"
    sha = grava(caminho, variavel=variavel,
                vocabulario={t: int(j) for t, j in vec.vocabulary_.items()},
                idf=vec.idf_, coeficientes=m.coef_[0],
                intercepto=float(m.intercept_[0]), limiar=limiar,
                regularizacao=1.0, preparo_versao="1.0.0",
                corpo_sha256="abc", cobertura_treino={"p05": 0.20, "mediana": 0.60})
    return caminho, sha


def _evidencia(paginas):
    return RawEvidence(domain=Domain(url="https://exemplo.com.br", tld=".com.br",
                                     source_name="teste"),
                       html_pages=paginas, fetcher_name="teste",
                       timestamp_utc=datetime.now(timezone.utc))


def _avalia(tmp_path, paginas, **extra):
    caminho, sha = _artefato(tmp_path, **{k: v for k, v in extra.items()
                                          if k in ("variavel", "limiar")})
    t = FinalidadeEspecificadaTest()
    return t.evaluate(_evidencia(paginas),
                      {"modelo_file": str(caminho), "modelo_sha256": sha},
                      protocol_version="v1", run_id="r1")


def test_registro_expoe_as_tres_variaveis():
    for nome, artefato in (("finalidade_especificada", "finalidade"),
                           ("direitos_titular_explicados", "direitos_titular"),
                           ("transf_internacional_divulgada", "transf_internacional")):
        c = resolve("variable_tests", nome)
        assert c.variable_name == nome and c.variavel_artefato == artefato


def test_valor_e_binario_e_contagem_vai_na_trilha(tmp_path):
    r = _avalia(tmp_path, {"/politica": f"<p>{POSITIVA}</p><p>{NEUTRA}</p>".encode()})
    assert isinstance(r.value, bool)
    assert "n_sentencas_sinalizadas" in r.audit_trail
    assert isinstance(r.audit_trail["n_sentencas_sinalizadas"], int)


def test_denominador_acompanha_a_contagem(tmp_path):
    """Contagem sem denominador nao e comparavel entre sitios."""
    r = _avalia(tmp_path, {"/politica": f"<p>{POSITIVA}</p><p>{NEUTRA}</p>".encode()})
    assert r.audit_trail["n_segmentos_avaliados"] == 2


def test_pagina_inicial_e_pre_consentimento_sao_excluidas(tmp_path):
    r = _avalia(tmp_path, {"/": f"<p>{POSITIVA}</p>".encode(),
                           "/__pre_consent": f"<p>{POSITIVA}</p>".encode(),
                           "/politica": f"<p>{NEUTRA}</p>".encode()})
    assert r.audit_trail["n_subpaginas"] == 1
    assert r.audit_trail["n_segmentos_avaliados"] == 1


def test_identidade_do_artefato_vai_na_trilha(tmp_path):
    caminho, sha = _artefato(tmp_path)
    t = FinalidadeEspecificadaTest()
    r = t.evaluate(_evidencia({"/p": f"<p>{POSITIVA}</p>".encode()}),
                   {"modelo_file": str(caminho), "modelo_sha256": sha},
                   protocol_version="v1", run_id="r1")
    assert r.audit_trail["modelo_sha256"] == sha
    assert r.audit_trail["preparo_versao"] == "1.0.0"
    assert r.audit_trail["corpo_sha256"] == "abc"


def test_artefato_divergente_interrompe(tmp_path):
    from privacyscope.models.artefato import ArtefatoCorrompido
    caminho, _ = _artefato(tmp_path)
    t = FinalidadeEspecificadaTest()
    with pytest.raises(ArtefatoCorrompido):
        t.evaluate(_evidencia({"/p": b"<p>x</p>"}),
                   {"modelo_file": str(caminho), "modelo_sha256": "0" * 64},
                   protocol_version="v1", run_id="r1")


def test_artefato_de_outra_variavel_e_recusado(tmp_path):
    caminho, sha = _artefato(tmp_path, variavel="transf_internacional")
    t = FinalidadeEspecificadaTest()
    with pytest.raises(ValueError, match="Artefato trocado"):
        t.evaluate(_evidencia({"/p": b"<p>x</p>"}),
                   {"modelo_file": str(caminho), "modelo_sha256": sha},
                   protocol_version="v1", run_id="r1")


def test_protocolo_sem_modelo_declarado_interrompe(tmp_path):
    t = FinalidadeEspecificadaTest()
    with pytest.raises(ValueError, match="modelo_file"):
        t.evaluate(_evidencia({"/p": b"<p>x</p>"}), {},
                   protocol_version="v1", run_id="r1")


def test_documento_sem_texto_nao_e_ausencia_de_divulgacao(tmp_path):
    r = _avalia(tmp_path, {})
    assert r.value is False
    assert r.audit_trail["motivo"] == "sem_texto_avaliavel"
    assert r.audit_trail["n_segmentos_avaliados"] == 0


def test_politica_so_em_outro_idioma_recebe_motivo_proprio(tmp_path):
    en = ("<p>We use your personal data and information for the purposes of this "
          "privacy policy and we may share it with third parties as needed.</p>") * 6
    r = _avalia(tmp_path, {"/policy": en.encode()})
    assert r.value is False
    assert r.audit_trail["motivo"] == "politica_outro_idioma"
    assert r.audit_trail["subpaginas_outro_idioma"] == ["/policy"]


def test_extrapolacao_e_marcada(tmp_path):
    r = _avalia(tmp_path, {"/p": b"<p>zzz qqq www vvv uuu ttt sss rrr ppp nnn mmm</p>"})
    assert r.audit_trail["extrapolacao"] is True
    assert r.audit_trail["cobertura_vocabulario"] < 0.20


def test_sentencas_sao_limitadas_e_o_excedente_e_contado(tmp_path):
    caminho, sha = _artefato(tmp_path, limiar=0.0)   # sinaliza tudo
    paginas = {"/p": "".join(f"<p>{POSITIVA} {i}</p>" for i in range(14)).encode()}
    t = FinalidadeEspecificadaTest()
    r = t.evaluate(_evidencia(paginas),
                   {"modelo_file": str(caminho), "modelo_sha256": sha,
                    "n_sentencas_auditoria": 3},
                   protocol_version="v1", run_id="r1")
    assert len(r.audit_trail["sentencas"]) == 3
    assert r.audit_trail["sentencas_omitidas"] == r.audit_trail["n_sentencas_sinalizadas"] - 3
    escores = [s["escore"] for s in r.audit_trail["sentencas"]]
    assert escores == sorted(escores, reverse=True), "as de maior escore vem primeiro"


def test_confianca_e_a_maior_probabilidade_entre_as_sinalizadas(tmp_path):
    caminho, sha = _artefato(tmp_path, limiar=0.0)
    t = FinalidadeEspecificadaTest()
    r = t.evaluate(_evidencia({"/p": f"<p>{POSITIVA}</p><p>{NEUTRA}</p>".encode()}),
                   {"modelo_file": str(caminho), "modelo_sha256": sha},
                   protocol_version="v1", run_id="r1")
    assert r.confidence == pytest.approx(max(s["escore"] for s in r.audit_trail["sentencas"]),
                                         abs=1e-4)


def test_artefato_lido_uma_unica_vez(tmp_path, monkeypatch):
    """Reler por sitio multiplicaria a leitura de disco por toda a amostra."""
    import privacyscope.tests.ml_texto as mod
    caminho, sha = _artefato(tmp_path)
    n = {"leituras": 0}
    original = mod.le

    def conta(*a, **k):
        n["leituras"] += 1
        return original(*a, **k)

    monkeypatch.setattr(mod, "le", conta)
    t = FinalidadeEspecificadaTest()
    for _ in range(4):
        t.evaluate(_evidencia({"/p": f"<p>{POSITIVA}</p>".encode()}),
                   {"modelo_file": str(caminho), "modelo_sha256": sha},
                   protocol_version="v1", run_id="r1")
    assert n["leituras"] == 1
