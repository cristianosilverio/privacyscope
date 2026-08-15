# -*- coding: utf-8 -*-
"""Dependencia declarada entre variaveis, e o terceiro estado de saida.

Motivo, medido sobre 506 sitios: 46% nao tinham politica detectada, e neles a
variavel de finalidade ainda saia positiva em 21,8% dos casos — 16% de todos os
positivos vinham de material que nao era politica.
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from privacyscope.core.types import NAO_APLICAVEL

REPO = Path(__file__).resolve().parents[1]


def _protocolo(tmp_path, testes, base):
    d = yaml.safe_load((REPO / "protocols" / "padrao.yaml").read_text(encoding="utf-8"))
    d["tests"] = testes
    d["repository"] = {"name": "filesystem", "params": {"base_path": str(base / "repo")}}
    d["result_store"] = {"name": "sqlite", "params": {"db_path": str(base / "r.sqlite")}}
    d.pop("outputs", None)
    alvo = tmp_path / "p.yaml"
    alvo.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return alvo


def test_constante_e_distinta_dos_booleanos():
    assert NAO_APLICAVEL not in (True, False, "true", "false")


def test_protocolos_declaram_a_dependencia():
    """As tres variaveis textuais so existem enquanto propriedade da politica."""
    for nome in ("padrao.yaml", "analista.yaml", "teto.yaml"):
        d = yaml.safe_load((REPO / "protocols" / nome).read_text(encoding="utf-8"))
        textuais = [t for t in d["tests"]
                    if t["name"].startswith(("finalidade", "direitos_titular",
                                             "transf_internacional"))]
        assert textuais, nome
        for t in textuais:
            dep = (t.get("params") or {}).get("depende_de")
            assert dep == ["tem_politica_privacidade"], f"{nome}: {t['name']}"


def test_canal_nao_depende_da_politica():
    """O canal pode ser divulgado em pagina de contato: nao e propriedade do
    texto da politica, e amarra-lo a ela suprimiria deteccao legitima."""
    d = yaml.safe_load((REPO / "protocols" / "padrao.yaml").read_text(encoding="utf-8"))
    canal = [t for t in d["tests"] if t["name"].startswith("canal_titular")]
    assert canal
    for t in canal:
        assert not (t.get("params") or {}).get("depende_de")


def test_precondicao_falsa_produz_nao_aplicavel(tmp_path, monkeypatch):
    from privacyscope.core.types import Domain, RawEvidence, VariableResult
    from privacyscope.orchestrator import Orchestrator

    class Falso:
        name = "politica_privacidade"; version = "1"; variable_name = "tem_politica_privacidade"

        def evaluate(self, evidence, params, *, protocol_version, run_id):
            return VariableResult(
                domain_url=evidence.domain.url, variable_name=self.variable_name,
                value=False, confidence=1.0, audit_trail={},
                protocol_version=protocol_version, plugin_version=self.version,
                run_id=run_id, timestamp_utc=datetime.now(timezone.utc))

    class NuncaChamado:
        name = "finalidade_especificada"; version = "1"
        variable_name = "finalidade_especificada"
        chamado = False

        def evaluate(self, *a, **k):
            NuncaChamado.chamado = True
            raise AssertionError("nao deveria ser avaliado sem politica")

    proto = _protocolo(tmp_path, [{"name": "politica_privacidade", "params": {}}],
                       tmp_path)
    orq = Orchestrator(proto)
    try:
        orq.tests = [(Falso(), {}),
                     (NuncaChamado(), {"depende_de": ["tem_politica_privacidade"]})]
        ev = RawEvidence(domain=Domain(url="https://x.com.br", tld=".com.br",
                                       source_name="t"),
                         html_pages={"/": b"<p>x</p>"}, fetcher_name="t",
                         timestamp_utc=datetime.now(timezone.utc))
        orq._analyze_evidence(ev, "run-1")
        got = {r.variable_name: r for r in orq.store.query({"run_id": "run-1"})}
    finally:
        orq.close()
    assert not NuncaChamado.chamado, "o plugin dependente foi avaliado indevidamente"
    r = got["finalidade_especificada"]
    assert r.value == NAO_APLICAVEL
    assert r.value is not False, "nao pode ser confundido com ausencia de divulgacao"
    assert r.confidence == 0.0
    assert r.audit_trail["motivo"] == "precondicao_nao_satisfeita"
    assert r.audit_trail["aplicavel"] is False


def test_precondicao_satisfeita_avalia_normalmente(tmp_path):
    from privacyscope.core.types import Domain, RawEvidence, VariableResult
    from privacyscope.orchestrator import Orchestrator

    class Verdadeiro:
        name = "politica_privacidade"; version = "1"; variable_name = "tem_politica_privacidade"

        def evaluate(self, evidence, params, *, protocol_version, run_id):
            return VariableResult(
                domain_url=evidence.domain.url, variable_name=self.variable_name,
                value=True, confidence=1.0, audit_trail={},
                protocol_version=protocol_version, plugin_version=self.version,
                run_id=run_id, timestamp_utc=datetime.now(timezone.utc))

    class Dependente(Verdadeiro):
        name = "finalidade_especificada"; variable_name = "finalidade_especificada"

    proto = _protocolo(tmp_path, [{"name": "politica_privacidade", "params": {}}],
                       tmp_path)
    orq = Orchestrator(proto)
    try:
        orq.tests = [(Verdadeiro(), {}),
                     (Dependente(), {"depende_de": ["tem_politica_privacidade"]})]
        ev = RawEvidence(domain=Domain(url="https://y.com.br", tld=".com.br",
                                       source_name="t"),
                         html_pages={"/": b"<p>y</p>"}, fetcher_name="t",
                         timestamp_utc=datetime.now(timezone.utc))
        orq._analyze_evidence(ev, "run-2")
        got = {r.variable_name: r for r in orq.store.query({"run_id": "run-2"})}
    finally:
        orq.close()
    assert got["finalidade_especificada"].value is True


def test_renderizadores_distinguem_os_tres_estados():
    from privacyscope.outputs.renderizadores import _estado
    assert _estado(True) == "true"
    assert _estado(False) == "false"
    assert _estado(NAO_APLICAVEL) == NAO_APLICAVEL


def test_triagem_nao_conta_nao_aplicavel_como_ausencia(tmp_path):
    """Somar `nao_aplicavel` na contagem de sinais ausentes faria a ordenacao da
    triagem priorizar justamente os sitios em que nada foi medido."""
    from privacyscope.core.types import Domain, RawEvidence, VariableResult
    from privacyscope.outputs.renderizadores import CsvLargo
    import csv as _csv

    class Loja:
        def query(self, filtro):
            agora = datetime.now(timezone.utc)
            for nome, val in (("a", False), ("b", NAO_APLICAVEL), ("c", True)):
                yield VariableResult(
                    domain_url="https://z.com.br", variable_name=nome, value=val,
                    confidence=0.0, audit_trail={}, protocol_version="v",
                    plugin_version="1", run_id="r", timestamp_utc=agora)

    alvo = CsvLargo().render(Loja(), {"path": str(tmp_path / "l.csv")})
    linha = list(_csv.DictReader(alvo.open(encoding="utf-8"), delimiter=";"))[0]
    assert linha["n_sinais_ausentes"] == "1"
    assert linha["n_nao_aplicavel"] == "1"
    assert linha["n_variaveis_apuradas"] == "2"


# --------------------------------------------------------------------------
# Densidade de sinalizacao — indicador ordinal, sem limiar arbitrado
# --------------------------------------------------------------------------
def test_densidade_e_razao_entre_contagem_e_denominador():
    from privacyscope.outputs._comum import densidade
    assert densidade({"n_sentencas_sinalizadas": 12, "n_segmentos_avaliados": 60}) == 0.2
    assert densidade({"n_sentencas_sinalizadas": 0, "n_segmentos_avaliados": 60}) == 0.0


def test_densidade_vazia_quando_nao_ha_denominador():
    """Variavel nao aplicavel e variavel por regra nao trazem os insumos; a coluna
    fica vazia em vez de zero, que seria afirmar densidade nula."""
    from privacyscope.outputs._comum import densidade
    assert densidade({}) == ""
    assert densidade({"n_sentencas_sinalizadas": 3}) == ""
    assert densidade({"n_sentencas_sinalizadas": 0, "n_segmentos_avaliados": 0}) == ""


def test_densidade_ordena_onde_o_binario_satura(tmp_path):
    """Duas politicas ambas positivas, uma com o dobro da densidade da outra: o
    valor binario nao as distingue, a densidade sim."""
    from privacyscope.core.types import VariableResult
    from privacyscope.outputs.renderizadores import CsvLargo
    import csv as _csv
    import json as _json
    agora = datetime.now(timezone.utc)

    class Loja:
        def query(self, filtro):
            for host, n, seg in (("densa.com.br", 30, 60), ("rala.com.br", 6, 60)):
                yield VariableResult(
                    domain_url=f"https://{host}",
                    variable_name="finalidade_especificada", value=True,
                    confidence=0.9,
                    audit_trail={"n_sentencas_sinalizadas": n,
                                 "n_segmentos_avaliados": seg},
                    protocol_version="v", plugin_version="1", run_id="r",
                    timestamp_utc=agora)

    alvo = CsvLargo().render(Loja(), {"path": str(tmp_path / "l.csv")})
    L = {r["dominio"]: r for r in _csv.DictReader(alvo.open(encoding="utf-8"),
                                                  delimiter=";")}
    assert L["densa.com.br"]["finalidade_especificada"] == "true"
    assert L["rala.com.br"]["finalidade_especificada"] == "true"
    assert float(L["densa.com.br"]["finalidade_especificada__densidade"]) == 0.5
    assert float(L["rala.com.br"]["finalidade_especificada__densidade"]) == 0.1


def test_nome_da_coluna_nao_sugere_contagem_de_declaracoes():
    """A precisao do classificador em nivel de sentenca e de 31,4% em finalidade:
    a contagem sinalizada NAO e contagem de declaracoes, e o nome da coluna e a
    primeira coisa que o analista le."""
    from privacyscope.outputs._comum import DERIVADAS
    assert DERIVADAS == ("densidade_sinalizacao",)
    for proibido in ("n_finalidades", "n_declaracoes", "quantidade_finalidade"):
        assert proibido not in DERIVADAS
