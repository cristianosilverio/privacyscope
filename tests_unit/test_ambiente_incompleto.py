# -*- coding: utf-8 -*-
"""Ambiente incompleto aborta; falha de sitio escalona.

A distincao nasceu de coleta ao vivo iniciada sem o navegador do Playwright
instalado: a cadeia escalava, o lancamento falhava, e cada sitio saia sem
evidencia. Prosseguir teria produzido amostra enviesada para os sitios que
dispensam escalonamento — os mais simples, e portanto os menos informativos.
"""
import pytest

from privacyscope.fetchers._exceptions import (
    AmbienteIncompletoError, FetchError, NavigationFailedError,
)
from privacyscope.fetchers.fallback_chain import _e_ambiente_incompleto


@pytest.mark.parametrize("mensagem", [
    "BrowserType.launch: Executable doesn't exist at C:\\ms-playwright\\chromium",
    "Please run the following command to download new browsers",
    "playwright install",
])
def test_reconhece_navegador_ausente(mensagem):
    assert _e_ambiente_incompleto(Exception(mensagem))


@pytest.mark.parametrize("mensagem", [
    "timeout ao conectar",
    "403 Forbidden",
    "certificado TLS invalido",
    "DNS nao resolvido",
    "conexao recusada pelo servidor",
])
def test_nao_confunde_com_falha_de_sitio(mensagem):
    """Falha de sitio e atrito de coleta: registra-se e segue. Confundi-la com
    ambiente abortaria a execucao por um unico dominio morto."""
    assert not _e_ambiente_incompleto(NavigationFailedError(mensagem))
    assert not _e_ambiente_incompleto(Exception(mensagem))


def test_e_subclasse_de_falha_de_coleta():
    """Deriva de FetchError por conveniencia de tipagem, mas a cadeia a trata a
    parte — quem capturar FetchError generico nao deve engoli-la sem perceber."""
    assert issubclass(AmbienteIncompletoError, FetchError)


def test_mensagem_diz_como_corrigir():
    e = AmbienteIncompletoError(
        "playwright: dependencia do ambiente ausente\n"
        "Instale com:\n    playwright install chromium")
    assert "playwright install" in str(e)
