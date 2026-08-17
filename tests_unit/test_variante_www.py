# -*- coding: utf-8 -*-
"""Queda para a variante `www.` e o estado de unidade inexistente.

O PlaywrightFetcher ja tentava `www.` em qualquer falha de navegacao; o coletor por
requisicao simples nao tentava. A inconsistencia custou 9 unidades em 100 na coleta
ao vivo de 15/08/2026 — nomes cujo apex nao resolve ou nao aceita conexao e cujo
`www.` responde.

Outras 10 daquelas 20 nao tinham remedio de coletor: `portaldeservicos.pdpj.jus.br`,
`fulltrack-tools.ftdata.com.br`, `policiacivil` sem hifen. Sao defeito do quadro
amostral, e ganham estado proprio.
"""
import pytest

from privacyscope.core.types import NAO_COLETADO, UNIDADE_INEXISTENTE
from privacyscope.fetchers._exceptions import (
    FetchError, NomeNaoResolveError, RobotsDisallowedError)
from privacyscope.fetchers.http_fetcher import _com_www, _e_falha_de_nome
from privacyscope.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# A transformacao
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("origem,esperado", [
    ("https://uems.br", "https://www.uems.br/"),
    ("https://tjap.jus.br", "https://www.tjap.jus.br/"),
    ("http://exemplo.com.br/caminho", "http://www.exemplo.com.br/caminho"),
])
def test_prefixa_www(origem, esperado):
    assert _com_www(origem) == esperado


@pytest.mark.parametrize("origem", ["https://www.uems.br", "https://1.2.3.4"])
def test_nao_prefixa_o_que_nao_cabe(origem):
    """Hospedeiro que ja e `www.` e endereco numerico nao tem variante."""
    assert _com_www(origem) is None


def test_subdominio_recebe_prefixo_assim_mesmo():
    """Distinguir dominio registravel de subdominio exigiria lista de sufixos
    publicos no caminho quente; o custo de errar e uma consulta que nao resolve."""
    assert _com_www("https://smart.exemplo.com.br") == "https://www.smart.exemplo.com.br/"


# ---------------------------------------------------------------------------
# Falha de nome x falha de alcance
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "[Errno 11001] getaddrinfo failed",
    "Name or service not known",
    "Temporary failure in name resolution",
])
def test_reconhece_falha_de_resolucao(msg):
    assert _e_falha_de_nome(Exception(msg))


@pytest.mark.parametrize("msg", ["ConnectTimeout", "ReadTimeout", "SSLError: bad cert"])
def test_hospedeiro_que_nao_responde_nao_e_falha_de_nome(msg):
    """Hospedeiro que resolve e nao responde EXISTE; nome que nao resolve, nao."""
    assert not _e_falha_de_nome(Exception(msg))


# ---------------------------------------------------------------------------
# O estado proprio
# ---------------------------------------------------------------------------
def test_nome_que_nao_resolve_tem_motivo_proprio():
    assert Orchestrator._motivo_da_falha(NomeNaoResolveError("x")) == "nome_nao_resolve"
    assert Orchestrator._motivo_da_falha(RobotsDisallowedError("x")) == "robots_proibe"
    assert Orchestrator._motivo_da_falha(FetchError("x")) == "coleta_falhou"


class _Loja:
    def __init__(self): self.gravados = []
    def upsert(self, r): self.gravados.append(r)


class _Teste:
    version = "1.0.0"
    def __init__(self, nome): self.variable_name = nome


def _orq():
    o = Orchestrator.__new__(Orchestrator)
    o.protocol = {"metadata": {"protocol_version": "t"}}
    o.tests = [(_Teste("tem_politica_privacidade"), {})]
    o.store = _Loja()
    return o


def test_nome_que_nao_resolve_grava_unidade_inexistente():
    """Defeito do QUADRO amostral, e nao do instrumento: nenhum coletor o corrige,
    e soma-lo a taxa de alcance esconderia qual dos dois se esta medindo."""
    o = _orq()
    o._registra_nao_coletado("https://ia.br", "r", motivo="nome_nao_resolve",
                             detalhe={"excecao": "NomeNaoResolveError"})
    assert o.store.gravados[0].value == UNIDADE_INEXISTENTE


def test_demais_falhas_seguem_nao_coletado():
    o = _orq()
    o._registra_nao_coletado("https://x.br", "r", motivo="coleta_expirou", detalhe={})
    assert o.store.gravados[0].value == NAO_COLETADO


def test_estado_novo_entra_no_conjunto_dos_indeterminados():
    from privacyscope.core.types import ESTADOS_INDETERMINADOS
    assert UNIDADE_INEXISTENTE in ESTADOS_INDETERMINADOS


# ---------------------------------------------------------------------------
# Certificado invalido tem motivo proprio
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
    "Hostname mismatch, certificate is not valid for 'acessorh.com.br'",
    "SSLCertVerificationError: unable to get local issuer certificate",
])
def test_certificado_invalido_nao_se_confunde_com_tempo_esgotado(msg):
    """Transporte sem protecao adequada e materia do art. 46 da Lei 13.709/2018;
    registrar so `coleta_falhou` descartaria observacao sobre o controlador."""
    assert Orchestrator._motivo_da_falha(FetchError(msg)) == "tls_invalido"


def test_tempo_esgotado_continua_sendo_tempo_esgotado():
    """Tempo esgotado na conexao e na renderizacao caem no mesmo motivo: em ambos o
    hospedeiro existe e nao respondeu no orcamento."""
    for msg in ("ConnectTimeout: ", "Page.goto: Timeout 15000ms exceeded",
                "ReadTimeout: "):
        assert Orchestrator._motivo_da_falha(FetchError(msg)) == "coleta_expirou"


def test_falha_sem_marca_reconhecivel_cai_no_balde_residual():
    assert Orchestrator._motivo_da_falha(
        FetchError("getaddrinfo failed; variante https://www.uems.br/: Co")
    ) == "coleta_falhou"


def test_robots_tem_precedencia_sobre_a_leitura_da_mensagem():
    """A classificacao por tipo vem antes da classificacao por texto."""
    assert Orchestrator._motivo_da_falha(
        RobotsDisallowedError("certificate verify failed")) == "robots_proibe"
