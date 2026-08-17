# -*- coding: utf-8 -*-
"""Certificado defeituoso e registrado, e nao motivo para desistir da coleta.

O arcabouco tratava TLS invalido de duas maneiras contraditorias: o coletor por
requisicao simples validava e desistia; o PlaywrightFetcher ignorava erros por padrao
e coletava sem registrar nada. Coletar ou nao dependia de qual coletor vencia.

Recusar a coleta nao protege atribuicao alguma — apaga o achado. Medido em
17/08/2026 sobre b7, b9 e a coleta ao vivo: 21 unidades perdidas seriam alcancaveis,
e entre elas orgaos estaduais compartilhando certificado entre secretarias, autarquia
federal com curinga que nao cobre o proprio apex, e instituicao servindo com o
certificado padrao da nuvem. Nada disso apareceria.
"""
import pytest

from privacyscope.fetchers._tls import _casa, _mesmo_registravel, inspeciona, marca
from privacyscope.fetchers.http_fetcher import _e_certificado
from privacyscope.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Casamento de nome — RFC 6125
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nome,host,esperado", [
    ("uems.br", "uems.br", True),
    ("*.uems.br", "www.uems.br", True),
    # O caso de cbtu.gov.br e incra.gov.br: curinga cobre UM rotulo, nao o apex.
    ("*.cbtu.gov.br", "cbtu.gov.br", False),
    ("*.exemplo.com.br", "a.b.exemplo.com.br", False),
    ("www.trilhasdefuturo.mg.gov.br", "trilhasdefuturo.mg.gov.br", False),
])
def test_casamento_de_nome(nome, host, esperado):
    assert _casa(nome, host) is esperado


def test_mesmo_registravel_separa_escopo_de_terceiro():
    assert _mesmo_registravel("cbtu.gov.br", "*.cbtu.gov.br")
    assert not _mesmo_registravel("pge.rn.gov.br", "arsep.rn.gov.br")
    assert not _mesmo_registravel("jbcred.com.br", "*.azurewebsites.net")


# ---------------------------------------------------------------------------
# Deteccao da falha de validacao
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
    "SSLCertVerificationError: unable to get local issuer certificate",
])
def test_reconhece_falha_de_certificado(msg):
    assert _e_certificado(Exception(msg))


@pytest.mark.parametrize("msg", ["ConnectTimeout", "getaddrinfo failed",
                                 "UNEXPECTED_EOF_WHILE_READING"])
def test_nao_confunde_com_outras_falhas(msg):
    """Handshake que morre nao entrega certificado a inspecionar; nao e o mesmo caso."""
    assert not _e_certificado(Exception(msg))


# ---------------------------------------------------------------------------
# A marca e o que chega ao resultado
# ---------------------------------------------------------------------------
def test_marca_carrega_o_que_foi_apresentado():
    linha = marca({"estado": "certificado_de_terceiro", "host": "acessorh.com.br",
                   "cn": "api.people.unico.app", "sans": ["api.people.unico.app"],
                   "emissor": "Google Trust Services", "valido_ate": "2026-11-02",
                   "detalhe": "Hostname mismatch"})
    assert "estado=certificado_de_terceiro" in linha
    assert "api.people.unico.app" in linha


def test_estado_do_certificado_chega_a_trilha_do_resultado():
    from datetime import datetime, timezone
    from privacyscope.core.types import Domain, RawEvidence

    ev = RawEvidence(
        domain=Domain(url="https://x.br", tld=".br", source_name="t"),
        html_pages={"/": b"<html></html>"}, cookies_by_phase={}, headers={},
        screenshot=None, phase_screenshots={}, network_log=[], subpage_selection={},
        consent_actions=[], fetcher_name="http_simples",
        timestamp_utc=datetime.now(timezone.utc),
        errors=[marca({"estado": "escopo_do_certificado", "host": "x.br",
                       "cn": "*.x.br", "sans": [], "emissor": "Lets Encrypt",
                       "valido_ate": "2027-01-01", "detalhe": ""})])
    extra = Orchestrator._marca_tls(ev)
    assert extra["tls_estado"] == "escopo_do_certificado"
    assert extra["tls_certificado_de"] == "*.x.br"


def test_coleta_com_certificado_valido_nao_recebe_marca():
    from datetime import datetime, timezone
    from privacyscope.core.types import Domain, RawEvidence

    ev = RawEvidence(
        domain=Domain(url="https://x.br", tld=".br", source_name="t"),
        html_pages={"/": b"<html></html>"}, cookies_by_phase={}, headers={},
        screenshot=None, phase_screenshots={}, network_log=[], subpage_selection={},
        consent_actions=[], fetcher_name="http_simples",
        timestamp_utc=datetime.now(timezone.utc), errors=[])
    assert Orchestrator._marca_tls(ev) == {}


def test_inspecao_nunca_levanta():
    """Roda no caminho de coleta: falhar aqui derrubaria a unidade inteira."""
    r = inspeciona("nome-que-nao-existe-jamais.invalid", timeout=2.0)
    assert r["estado"] == "indeterminado"


def test_sem_a_biblioteca_o_estado_diz_que_nao_inspecionou(monkeypatch):
    """`indeterminado` mudo se confunde com hospedeiro inalcancavel. A execucao
    798449dd saiu com `tls_estado=indeterminado` em toda coleta porque a biblioteca
    de leitura de certificado nao estava declarada nas dependencias."""
    import builtins
    real = builtins.__import__

    def sem_cryptography(nome, *a, **k):
        if nome.startswith("cryptography"):
            raise ImportError("ausente")
        return real(nome, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sem_cryptography)
    r = inspeciona("acessorh.com.br", timeout=8.0)
    assert r["estado"] in ("nao_inspecionado", "indeterminado", "valido")
    if r["estado"] == "nao_inspecionado":
        assert "cryptography" in r["detalhe"]


def test_cadeia_inspeciona_o_host_efetivo_e_nao_o_declarado():
    """Coleta recuperada pela variante `www.` tem nome declarado que nao resolve;
    inspecionar o declarado devolveria indeterminado para todas elas."""
    from datetime import datetime, timezone
    from privacyscope.core.types import Domain, RawEvidence
    from privacyscope.fetchers.fallback_chain import FallbackChain

    ev = RawEvidence(
        domain=Domain(url="https://wurthdobrasil.com.br", tld=".br", source_name="t"),
        html_pages={"/": b"<html></html>"},
        cookies_by_phase={},
        headers={"https://www.wurthdobrasil.com.br/": {"server": "x"}},
        screenshot=None, phase_screenshots={}, network_log=[], subpage_selection={},
        consent_actions=[], fetcher_name="http_simples",
        timestamp_utc=datetime.now(timezone.utc), errors=[])
    saida = FallbackChain._enrich_with_tls(ev)
    # Certificado valido no host efetivo: nenhuma marca deve ser acrescentada.
    assert not [e for e in saida.errors if str(e).startswith("tls.")]


def test_achado_de_tls_sobrevive_a_perda_da_unidade():
    """acessorh.com.br: certificado de api.people.unico.app, coleta perdida depois no
    destino do redirecionamento. Sem isto, o achado existiria so no log."""
    msg = ("FallbackChain falhou em playwright: timeout | "
           + marca({"estado": "certificado_de_terceiro", "host": "acessorh.com.br",
                    "cn": "api.people.unico.app", "sans": [],
                    "emissor": "Google Trust Services", "valido_ate": "2026-11-02",
                    "detalhe": ""}))
    extra = Orchestrator._le_marca_tls(msg)
    assert extra["tls_estado"] == "certificado_de_terceiro"
    assert extra["tls_certificado_de"] == "api.people.unico.app"


def test_marca_de_tls_nao_altera_o_motivo_da_perda():
    """O que perdeu a unidade foi tempo esgotado; o certificado e achado paralelo."""
    from privacyscope.fetchers._exceptions import FetchError
    msg = ("timeout em goto: Page.goto: Timeout 15000ms exceeded | "
           + marca({"estado": "certificado_de_terceiro", "host": "x.br",
                    "cn": "outro.app", "sans": [], "emissor": "CA",
                    "valido_ate": "", "detalhe": ""}))
    assert Orchestrator._motivo_da_falha(FetchError(msg)) == "coleta_expirou"


def test_marca_vira_linha_propria_de_auditoria_e_nao_e_truncada():
    """`message` da tentativa e truncada em 120 caracteres. Anexar a marca ao fim da
    mensagem a fazia desaparecer exatamente nas unidades perdidas por outro motivo —
    que sao as que mais precisam do achado."""
    import asyncio
    from datetime import datetime, timezone

    from privacyscope.core.types import Domain
    from privacyscope.fetchers._exceptions import FetchError
    from privacyscope.fetchers.fallback_chain import FallbackChain

    marca_tls = marca({"estado": "certificado_de_terceiro", "host": "acessorh.com.br",
                       "cn": "api.people.unico.app", "sans": [],
                       "emissor": "Google Trust Services", "valido_ate": "2026-11-02",
                       "detalhe": ""})
    longa = "x" * 300  # empurra a marca para alem do corte de 120

    class F:
        def __init__(self, n): self.name, self.version = n, "1"
        async def fetch(self, d, p):
            raise FetchError(f"{longa} | {marca_tls}")

    c = FallbackChain([F("http_simples"), F("playwright")])
    params = {"fetchers": [
        {"name": "http_simples", "params": {}, "escalate_if": [{"exception": "FetchError"}]},
        {"name": "playwright", "params": {}, "escalate_if": []}],
        "max_retries_per_fetcher": 0, "abort_on": []}
    try:
        asyncio.run(c.fetch(Domain(url="https://acessorh.com.br", tld=".br",
                                   source_name="t"), params))
        raise AssertionError("deveria ter levantado")
    except Exception as e:
        extra = Orchestrator._le_marca_tls(str(e))
    assert extra.get("tls_estado") == "certificado_de_terceiro"
    assert extra.get("tls_certificado_de") == "api.people.unico.app"
