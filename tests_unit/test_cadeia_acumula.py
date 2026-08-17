# -*- coding: utf-8 -*-
"""A cadeia acumula evidencia e nao a perde quando a camada seguinte falha.

Medido no diagnostico de 16/08/2026: cinco de vinte unidades tinham a raiz coletada
pelo `http_simples` — duas delas pela queda para `www.` — e terminaram como perda
total. A cadeia escalava por sinal, o Playwright falhava, e a evidencia ja obtida era
descartada a tres linhas de distancia da variavel que a continha.

Havia tres vias de perda: levantar por falha do coletor seguinte, zerar o acumulador
quando um coletor intermediario levantava excecao, e esgotar a cadeia com evidencia
que casara `escalate_if`.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from privacyscope.core.types import Domain, RawEvidence
from privacyscope.fetchers._exceptions import (
    FetchError, NavigationFailedError, RobotsDisallowedError)
from privacyscope.fetchers.fallback_chain import FallbackChain

DOM = Domain(url="https://x.br", tld=".br", source_name="t")


def _ev(nome: str, cookies=None) -> RawEvidence:
    return RawEvidence(
        domain=DOM, html_pages={"/": f"<html>{nome}</html>".encode()},
        cookies_by_phase={"single": cookies if cookies is not None else [{"name": "c"}]},
        headers={}, screenshot=None, phase_screenshots={}, network_log=[],
        subpage_selection={}, consent_actions=[], fetcher_name=nome,
        timestamp_utc=datetime.now(timezone.utc), errors=[])


class _Falso:
    """Coletor de teste: devolve evidencia ou levanta o que lhe mandarem."""

    def __init__(self, nome, resultado):
        self.name = nome
        self.version = "1.0.0"
        self._resultado = resultado
        self.chamadas = 0

    async def fetch(self, domain, params):
        self.chamadas += 1
        if isinstance(self._resultado, BaseException):
            raise self._resultado
        return self._resultado


def _cadeia(*coletores, escalar_do_primeiro=True):
    c = FallbackChain(list(coletores))
    entradas = []
    for i, f in enumerate(coletores):
        esc = ([{"signal": "cookies_pre_consent_zero"}, {"exception": "FetchError"}]
               if i < len(coletores) - 1 and escalar_do_primeiro else [])
        entradas.append({"name": f.name, "params": {}, "escalate_if": esc})
    return c, {"fetchers": entradas, "max_retries_per_fetcher": 0,
               "abort_on": [{"exception": "RobotsDisallowedError"}]}


def _roda(cadeia, params):
    return asyncio.run(cadeia.fetch(DOM, params))


def _marca(ev):
    return [e for e in ev.errors if e.startswith("chain.melhor_esforco")]


# ---------------------------------------------------------------------------
def test_evidencia_do_primeiro_sobrevive_a_falha_do_segundo():
    """A via de perda que custou cinco unidades: escalonamento por sinal seguido de
    excecao no coletor seguinte."""
    a = _Falso("a", _ev("a", cookies=[]))          # zero cookies -> escala
    b = _Falso("b", NavigationFailedError("timeout"))
    cadeia, params = _cadeia(a, b)
    ev = _roda(cadeia, params)
    assert ev.fetcher_name == "a"
    assert b.chamadas == 1, "o segundo coletor precisa ter sido tentado"
    assert _marca(ev), "evidencia degradada nao pode sair sem marca"


def test_marca_diz_qual_condicao_nao_foi_satisfeita():
    a = _Falso("a", _ev("a", cookies=[]))
    b = _Falso("b", NavigationFailedError("x"))
    cadeia, params = _cadeia(a, b)
    marca = _marca(_roda(cadeia, params))[0]
    assert "fetcher=a" in marca
    assert "cookies_pre_consent_zero" in marca


def test_segundo_com_evidencia_substitui_o_primeiro():
    """Substituicao por EXISTENCIA: havendo evidencia nova, ela vence."""
    a = _Falso("a", _ev("a", cookies=[]))
    b = _Falso("b", _ev("b"))
    cadeia, params = _cadeia(a, b)
    ev = _roda(cadeia, params)
    assert ev.fetcher_name == "b"
    assert not _marca(ev), "coleta satisfatoria nao e melhor esforco"


def test_coletor_intermediario_que_falha_nao_apaga_o_acumulador():
    """Terceira via de perda: `last_evidence_unsat = None` no ramo de excecao."""
    a = _Falso("a", _ev("a", cookies=[]))
    b = _Falso("b", FetchError("cai"))             # escala por excecao
    c = _Falso("c", NavigationFailedError("cai"))
    cadeia, params = _cadeia(a, b, c)
    ev = _roda(cadeia, params)
    assert ev.fetcher_name == "a"
    assert c.chamadas == 1


def test_ultimo_com_evidencia_vence_mesmo_apos_falha_intermediaria():
    a = _Falso("a", _ev("a", cookies=[]))
    b = _Falso("b", FetchError("cai"))
    c = _Falso("c", _ev("c"))
    cadeia, params = _cadeia(a, b, c)
    assert _roda(cadeia, params).fetcher_name == "c"


def test_cadeia_exaurida_com_evidencia_insatisfatoria_devolve_marcada():
    """Antes, esgotar a cadeia com evidencia que casara escalate_if levantava."""
    a = _Falso("a", _ev("a", cookies=[]))
    b = _Falso("b", _ev("b", cookies=[]))
    cadeia = FallbackChain([a, b])
    params = {"fetchers": [
        {"name": "a", "params": {}, "escalate_if": [{"signal": "cookies_pre_consent_zero"}]},
        {"name": "b", "params": {}, "escalate_if": [{"signal": "cookies_pre_consent_zero"}]},
    ], "max_retries_per_fetcher": 0, "abort_on": []}
    ev = _roda(cadeia, params)
    assert ev.fetcher_name == "b"
    assert _marca(ev)


def test_sem_evidencia_alguma_continua_levantando():
    """Melhor esforco nao pode virar sucesso onde nao houve coleta nenhuma."""
    a = _Falso("a", FetchError("cai"))
    b = _Falso("b", NavigationFailedError("cai"))
    cadeia, params = _cadeia(a, b)
    with pytest.raises(FetchError):
        _roda(cadeia, params)


def test_abort_on_continua_interrompendo():
    """Proibicao por robots.txt nao vira melhor esforco."""
    a = _Falso("a", RobotsDisallowedError("proibido"))
    b = _Falso("b", _ev("b"))
    cadeia, params = _cadeia(a, b)
    with pytest.raises(RobotsDisallowedError):
        _roda(cadeia, params)
    assert b.chamadas == 0


# ---------------------------------------------------------------------------
# A marca precisa chegar ao RESULTADO, e nao ficar so na evidencia
# ---------------------------------------------------------------------------
def test_marca_de_degradacao_chega_a_trilha_do_resultado():
    from privacyscope.orchestrator import Orchestrator

    ev = _ev("a").model_copy(update={"errors": [
        "chain.melhor_esforco fetcher=http_simples "
        "escalonamento_nao_satisfeito=signal=cookies_pre_consent_zero desfecho=x"]})
    extra = Orchestrator._marca_degradada(ev)
    assert extra["coleta_degradada"] is True
    assert extra["motivo_coleta"] == "melhor_esforco"
    assert "motivo" not in extra, (
        "a marca de coleta nao pode ocupar a chave que os testes textuais usam "
        "para `politica_outro_idioma`: sao diagnosticos de camadas diferentes")
    assert "cookies_pre_consent_zero" in extra["chain_melhor_esforco"]


def test_coleta_integra_nao_recebe_marca():
    from privacyscope.orchestrator import Orchestrator
    assert Orchestrator._marca_degradada(_ev("a")) is None
