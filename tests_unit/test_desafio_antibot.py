# -*- coding: utf-8 -*-
"""Deteccao de desafio anti-bot e o quarto estado `nao_coletado`.

O defeito que estes testes fixam foi encontrado em 15/08/2026: paginas de desafio
guardadas como se fossem o sitio produziam `tem_politica_privacidade = false` com
rotulo de confianca ALTO. Ver scripts/verificar_desafio_antibot.py para a apuracao
retrospectiva sobre as 1.045 coletas do repositorio.
"""
from types import SimpleNamespace

import pytest

from privacyscope.core.types import NAO_COLETADO
from privacyscope.fetchers.desafio_antibot import (
    bloqueada, detecta_desafio, paginas_bloqueadas)


def ev(headers):
    return SimpleNamespace(headers=headers)


# ---------------------------------------------------------------------------
# Deteccao
# ---------------------------------------------------------------------------
def test_cf_mitigated_e_desafio():
    d = detecta_desafio(ev({"https://x.br/p": {"cf-mitigated": "challenge"}}))
    assert d and d["marcas"] == ["cloudflare_challenge"]
    assert d["paginas"] == ["https://x.br/p"]


def test_csp_do_turnstile_e_desafio():
    d = detecta_desafio(ev({"https://x.br/p": {
        "content-security-policy": "script-src https://challenges.cloudflare.com"}}))
    assert d and d["marcas"] == ["cloudflare_turnstile"]


def test_cabecalho_e_insensivel_a_caixa():
    """httpx devolve minusculas; Playwright preserva o que veio."""
    assert detecta_desafio(ev({"https://x.br/": {"CF-Mitigated": "Challenge"}}))


def test_servidor_cloudflare_sozinho_nao_e_desafio():
    """Milhoes de sitios sao servidos por Cloudflare sem qualquer mitigacao.
    Trata-lo como bloqueio invalidaria coleta boa em massa."""
    assert detecta_desafio(ev({"https://x.br/": {"server": "cloudflare",
                                                 "cf-ray": "abc-GRU"}})) is None


def test_identificador_de_sessao_datadome_nao_e_bloqueio():
    assert detecta_desafio(ev({"https://x.br/": {"x-datadome-cid": "abc"}})) is None


def test_sem_cabecalhos_nao_ha_desafio():
    assert detecta_desafio(ev({})) is None
    assert detecta_desafio(SimpleNamespace(headers=None)) is None


# ---------------------------------------------------------------------------
# Identidade de pagina
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cand", [
    "https://www.x.br/politica-privacidade",
    "https://x.br/politica-privacidade/",
    "https://x.br/POLITICA-PRIVACIDADE",
])
def test_www_e_barra_final_nao_perdem_o_par(cand):
    """A URL do cabecalho e a do fim do redirecionamento; a da candidata e a do
    link. Comparar literalmente perderia todo sitio que manda apex para www."""
    b = paginas_bloqueadas(ev({"https://x.br/politica-privacidade":
                               {"cf-mitigated": "challenge"}}))
    assert bloqueada(cand, b)


def test_caminho_diferente_nao_casa():
    b = paginas_bloqueadas(ev({"https://x.br/a": {"cf-mitigated": "challenge"}}))
    assert not bloqueada("https://x.br/b", b)


# ---------------------------------------------------------------------------
# Efeito sobre o veredito
# ---------------------------------------------------------------------------
def _evidencia(candidatas, headers, raiz=b"<html><body>portal</body></html>"):
    from privacyscope.core.types import Domain, RawEvidence
    from datetime import datetime, timezone
    return RawEvidence(
        domain=Domain(url="https://x.br", tld=".br", source_name="t"),
        html_pages={"/": raiz},
        cookies_by_phase={}, headers=headers, screenshot=None,
        phase_screenshots={}, network_log=[],
        subpage_selection={"politica_privacidade":
                           [{"url": u, "matched_pattern": "p",
                             "matched_against": "text", "snippet": ""}
                            for u in candidatas]},
        consent_actions=[], fetcher_name="http_simples",
        timestamp_utc=datetime.now(timezone.utc), errors=[])


def _avalia(evid):
    from privacyscope.tests.politica_privacidade import PoliticaPrivacidadeTest
    return PoliticaPrivacidadeTest().evaluate(
        evid, {}, protocol_version="t", run_id="r")


def test_candidata_bloqueada_nao_vira_false():
    """Nao achar politica em pagina que o servidor recusou entregar nao e
    evidencia de que nao ha politica."""
    r = _avalia(_evidencia(["https://x.br/politica-privacidade"],
                           {"https://x.br/politica-privacidade":
                            {"cf-mitigated": "challenge"}}))
    assert r.value == NAO_COLETADO
    assert r.confidence == 0.0
    assert r.audit_trail["motivo"] == "desafio_anti_bot"
    assert r.audit_trail["paginas_recusadas"] == ["https://x.br/politica-privacidade"]


def test_bloqueio_fora_das_candidatas_preserva_o_veredito():
    """Caso real de simepar.br: bloqueio em pagina de acesso a informacao, raiz
    integra, nenhuma candidata a politica. O `false` nao decorre do bloqueio."""
    r = _avalia(_evidencia([], {"https://x.br/page/18": {"cf-mitigated": "challenge"}}))
    assert r.value is False
    assert r.audit_trail["source"] == "no_match_any_source"


def test_sem_bloqueio_o_veredito_negativo_permanece():
    r = _avalia(_evidencia(["https://x.br/sobre"], {}))
    assert r.value is False


def test_candidata_legivel_que_qualifica_vence_o_bloqueio_da_outra():
    """A verificacao vem DEPOIS da busca: se alguma candidata legivel qualificou a
    politica, o bloqueio de outra e irrelevante."""
    politica = ("<html><body>" + ("politica de privacidade. dados pessoais. "
                "titular. finalidade do tratamento. lgpd. encarregado. "
                "consentimento. " * 40) + "</body></html>").encode()
    e = _evidencia(["https://x.br/priv", "https://x.br/bloqueada"],
                   {"https://x.br/bloqueada": {"cf-mitigated": "challenge"}})
    e = e.model_copy(update={"html_pages": {**e.html_pages, "/priv": politica}})
    r = _avalia(e)
    assert r.value is True
