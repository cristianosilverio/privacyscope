# -*- coding: utf-8 -*-
"""Teto comparativo: identidade do codificador e contrato de saida.

Os testes que exigiriam os pesos do codificador sao dispensados quando as
dependencias opcionais nao estao instaladas — o que e, ele proprio, o ponto: o
artefato do teto NAO e autocontido, ao contrario dos outros quatro.
"""
from pathlib import Path

import numpy as np
import pytest

from privacyscope.core.plugin_registry import resolve
from privacyscope.models.artefato import (
    ARQUIVOS_CODIFICADOR, ArtefatoCorrompido, grava_denso, le_denso,
    resumo_diretorio,
)
from privacyscope.tests.bertimbau import FinalidadeDensaTest


def _codificador(tmp_path, vocab=b"[PAD]\n[UNK]\ndados\n"):
    d = tmp_path / "codificador"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_bytes(b'{"model_type": "bert"}')
    (d / "vocab.txt").write_bytes(vocab)
    (d / "model.safetensors").write_bytes(b"pesos-simulados")
    return d


def _artefato(tmp_path, cod_sha, variavel="finalidade", dim=8):
    caminho = tmp_path / "denso.npz"
    sha = grava_denso(caminho, variavel=variavel,
                      codificador="neuralmind/bert-base-portuguese-cased",
                      codificador_sha256=cod_sha, agregacao="media", max_len=256,
                      coeficientes=np.arange(dim, dtype=float) - dim / 2,
                      intercepto=-0.5, limiar=0.5, regularizacao=10.0,
                      preparo_versao="1.0.0", corpo_sha256="abc")
    return caminho, sha


def test_registro_expoe_os_tres_tetos():
    for nome, artefato in (("finalidade_especificada_densa", "finalidade"),
                           ("direitos_titular_explicados_densa", "direitos_titular"),
                           ("transf_internacional_divulgada_densa", "transf_internacional")):
        c = resolve("variable_tests", nome)
        assert c.variavel_artefato == artefato


def test_resumo_cobre_pesos_e_tokenizador(tmp_path):
    """Vocabulario distinto produz entrada distinta para os mesmos pesos."""
    a = _codificador(tmp_path / "a")
    b = _codificador(tmp_path / "b", vocab=b"[PAD]\n[UNK]\noutro\n")
    assert resumo_diretorio(a) != resumo_diretorio(b)


def test_resumo_muda_com_os_pesos(tmp_path):
    d = _codificador(tmp_path)
    antes = resumo_diretorio(d)
    (d / "model.safetensors").write_bytes(b"pesos-outros")
    assert resumo_diretorio(d) != antes


def test_diretorio_sem_modelo_e_recusado(tmp_path):
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    with pytest.raises(FileNotFoundError, match="nenhum arquivo de modelo"):
        resumo_diretorio(vazio)


def test_resumo_do_codificador_e_obrigatorio(tmp_path):
    with pytest.raises(ValueError, match="rotulo nao detecta"):
        grava_denso(tmp_path / "x.npz", variavel="v", codificador="m",
                    codificador_sha256="", agregacao="media", max_len=256,
                    coeficientes=[1.0], intercepto=0.0, limiar=0.5)


def test_codificador_trocado_interrompe(tmp_path):
    d = _codificador(tmp_path)
    caminho, sha = _artefato(tmp_path, resumo_diretorio(d))
    a = le_denso(caminho, sha)
    a.confere_codificador(d)                       # confere
    (d / "model.safetensors").write_bytes(b"outros-pesos")
    with pytest.raises(ArtefatoCorrompido, match="nao corresponde ao do ajuste"):
        a.confere_codificador(d)


def test_dimensao_incompativel_e_recusada(tmp_path):
    d = _codificador(tmp_path)
    caminho, sha = _artefato(tmp_path, resumo_diretorio(d), dim=8)
    a = le_denso(caminho, sha)
    with pytest.raises(ValueError, match="codificador ou agregacao trocados"):
        a.probabilidades(np.ones((3, 5)))


def test_probabilidade_normaliza_a_linha(tmp_path):
    """A cabeca foi ajustada sobre vetores normalizados; escala do vetor de
    entrada nao pode alterar a decisao."""
    d = _codificador(tmp_path)
    caminho, sha = _artefato(tmp_path, resumo_diretorio(d))
    a = le_denso(caminho, sha)
    v = np.arange(8, dtype=float) + 1
    assert a.probabilidades(v)[0] == pytest.approx(a.probabilidades(v * 7.3)[0])


def test_artefato_de_outro_tipo_e_recusado(tmp_path):
    from privacyscope.models.artefato import grava_canal
    caminho = tmp_path / "canal.npz"
    sha = grava_canal(caminho, variavel="v", atributos=("A",), coeficientes=[1.0],
                      intercepto=0.0)
    with pytest.raises(ArtefatoCorrompido, match="tipo"):
        le_denso(caminho, sha)


def test_sem_dependencias_a_mensagem_orienta(tmp_path, monkeypatch):
    """O artefato do teto nao e autocontido, e a falta tem de ser dita."""
    import builtins
    d = _codificador(tmp_path)
    caminho, sha = _artefato(tmp_path, resumo_diretorio(d))
    real = builtins.__import__

    def bloqueia(nome, *a, **k):
        if nome.split(".")[0] in ("torch", "transformers"):
            raise ImportError(nome)
        return real(nome, *a, **k)

    monkeypatch.setattr(builtins, "__import__", bloqueia)
    t = FinalidadeDensaTest()
    a = le_denso(caminho, sha)
    with pytest.raises(RuntimeError, match="ml-advanced"):
        t._carrega_codificador(a, {"codificador_dir": str(d)})
