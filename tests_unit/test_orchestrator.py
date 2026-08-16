

# ---------------------------------------------------------------------------
# Resolucao de dominios pela camada de ingestao
# ---------------------------------------------------------------------------
def _orq_com_fontes(tmp_path, fontes):
    """Instancia so o suficiente para exercitar `_iter_domains`."""
    from privacyscope.orchestrator import Orchestrator
    orq = Orchestrator.__new__(Orchestrator)
    orq.protocol = {"sources": fontes}
    return orq


def _lista(tmp_path, hosts):
    p = tmp_path / "lista.csv"
    p.write_text("dominio\n" + "\n".join(hosts) + "\n", encoding="utf-8")
    return p


def test_fonte_declarada_e_consumida(tmp_path):
    """O caminho `sources` precisa funcionar: ate aqui todo protocolo do
    repositorio usava `override_domains`, e o defeito nao aparecia."""
    p = _lista(tmp_path, ["a.com.br", "b.com.br", "c.com.br"])
    orq = _orq_com_fontes(tmp_path, [{"name": "csv", "params": {"path": str(p)}}])
    assert [d.url for d in orq._iter_domains()] == [
        "https://a.com.br", "https://b.com.br", "https://c.com.br"]


def test_sem_max_n_nao_ha_corte(tmp_path):
    """Truncar por padrao produziria conjunto menor que o declarado sem que nada
    no registro dissesse isso."""
    p = _lista(tmp_path, [f"s{i}.com.br" for i in range(80)])
    orq = _orq_com_fontes(tmp_path, [{"name": "csv", "params": {"path": str(p)}}])
    assert len(list(orq._iter_domains())) == 80


def test_max_n_corta_e_nao_vaza_para_a_fonte(tmp_path):
    p = _lista(tmp_path, [f"s{i}.com.br" for i in range(10)])
    orq = _orq_com_fontes(
        tmp_path, [{"name": "csv", "params": {"path": str(p), "max_n": 3}}])
    assert len(list(orq._iter_domains())) == 3


def test_source_no_singular_e_lido(tmp_path):
    """Forma usada pelos protocolos anteriores a existencia de mais de uma fonte."""
    p = _lista(tmp_path, ["a.com.br"])
    from privacyscope.orchestrator import Orchestrator
    orq = Orchestrator.__new__(Orchestrator)
    orq.protocol = {"source": {"name": "csv", "params": {"path": str(p)}}}
    assert [d.url for d in orq._iter_domains()] == ["https://a.com.br"]


# ---------------------------------------------------------------------------
# Unidades sem coleta aparecem no resultado
# ---------------------------------------------------------------------------
class _LojaFalsa:
    def __init__(self):
        self.gravados = []

    def upsert(self, r):
        self.gravados.append(r)


class _TesteFalso:
    version = "1.0.0"

    def __init__(self, nome):
        self.variable_name = nome


def _orq_para_falha():
    from privacyscope.orchestrator import Orchestrator
    o = Orchestrator.__new__(Orchestrator)
    o.protocol = {"metadata": {"protocol_version": "t"}}
    o.tests = [(_TesteFalso("tem_politica_privacidade"), {}),
               (_TesteFalso("tem_banner_cookies"), {})]
    o.store = _LojaFalsa()
    return o


def test_dominio_sem_coleta_vira_linha_e_nao_desaparece():
    """Sumir da saida tira a unidade do numerador e do denominador ao mesmo tempo,
    e a proporcao resultante mede prevalencia entre os alcancados."""
    from privacyscope.core.types import NAO_COLETADO
    o = _orq_para_falha()
    o._registra_nao_coletado("https://x.br", "r", motivo="coleta_expirou",
                             detalhe={"excecao": "NavigationFailedError"})
    assert len(o.store.gravados) == 2
    assert {g.variable_name for g in o.store.gravados} == {
        "tem_politica_privacidade", "tem_banner_cookies"}
    for g in o.store.gravados:
        assert g.value == NAO_COLETADO
        assert g.confidence == 0.0
        assert g.audit_trail["coletado"] is False
        assert g.audit_trail["motivo"] == "coleta_expirou"


def test_robots_proibe_e_motivo_proprio():
    """Proibicao por robots nao e indisponibilidade: e estado legitimo e
    permanente, e a distincao muda o que se faz no ciclo seguinte."""
    from privacyscope.orchestrator import Orchestrator
    from privacyscope.fetchers._exceptions import RobotsDisallowedError
    assert Orchestrator._motivo_da_falha(RobotsDisallowedError("x")) == "robots_proibe"
    assert Orchestrator._motivo_da_falha(RuntimeError("x")) == "coleta_falhou"


# ---------------------------------------------------------------------------
# Destino da reanalise
# ---------------------------------------------------------------------------
def _repo_com_uma_evidencia(tmp_path, run_id="antiga"):
    """Monta repositorio e armazenamento minimos com uma evidencia coletada."""
    import asyncio
    from datetime import datetime, timezone
    from privacyscope.core.plugin_registry import resolve
    from privacyscope.core.types import Domain, RawEvidence
    from privacyscope.orchestrator import Orchestrator

    repo = resolve("repositories", "filesystem")(base_path=str(tmp_path))
    ev = RawEvidence(
        domain=Domain(url="https://x.br", tld=".br", source_name="t"),
        html_pages={"/": b"<html><body>portal</body></html>"},
        cookies_by_phase={}, headers={}, screenshot=None, phase_screenshots={},
        network_log=[], subpage_selection={}, consent_actions=[],
        fetcher_name="http_simples", timestamp_utc=datetime.now(timezone.utc),
        errors=[])
    repo.put(ev, run_id, protocol_version_hash="h")

    loja = resolve("result_stores", "sqlite")(db_path=str(tmp_path / "r.sqlite"))
    loja.begin_run(run_id, protocol_version="t", sample_size=1)
    loja.finish_run(run_id, errors_count=0)

    o = Orchestrator.__new__(Orchestrator)
    o.protocol = {"metadata": {"protocol_version": "t"}}
    o.protocol_version_hash = "h"
    o.repo, o.store = repo, loja
    o.tests = [(resolve("variable_tests", "politica_privacidade")(), {})]
    o.renderers = []
    return o, loja


def test_reanalise_sob_novo_identificador_preserva_o_registro(tmp_path):
    """Resultado que se altera no lugar nao deixa rastro de que foi alterado, e a
    diferenca entre o antes e o depois e o que precisa ser mostrado."""
    from datetime import datetime, timezone
    from privacyscope.core.types import VariableResult

    o, loja = _repo_com_uma_evidencia(tmp_path)
    try:
        # Veredito antigo, que a correcao mudaria: precisa sobreviver intacto.
        loja.upsert(VariableResult(
            domain_url="https://x.br", variable_name="tem_politica_privacidade",
            value=True, confidence=0.9, audit_trail={"source": "regra_anterior"},
            protocol_version="t", plugin_version="0", run_id="antiga",
            timestamp_utc=datetime.now(timezone.utc)))

        assert o.analyze_only("antiga", destino_run_id="nova") == "nova"

        antigos = list(loja.query({"run_id": "antiga"}))
        assert len(antigos) == 1
        assert antigos[0].value is True
        assert antigos[0].audit_trail["source"] == "regra_anterior"

        novos = list(loja.query({"run_id": "nova"}))
        assert novos and all(r.audit_trail.get("reanalise_de") == "antiga"
                             for r in novos)
        assert novos[0].value is False          # a evidencia minima nao tem politica
    finally:
        loja.close()


def test_reanalise_sem_destino_substitui(tmp_path):
    o, loja = _repo_com_uma_evidencia(tmp_path)
    try:
        assert o.analyze_only("antiga") == "antiga"
        assert all("reanalise_de" not in r.audit_trail
                   for r in loja.query({"run_id": "antiga"}))
    finally:
        loja.close()


def test_destino_ja_usado_interrompe(tmp_path):
    """O motivo de existir a opcao e nao apagar registro."""
    import pytest
    o, loja = _repo_com_uma_evidencia(tmp_path)
    try:
        o.analyze_only("antiga", destino_run_id="nova")
        with pytest.raises(ValueError, match="ja consta"):
            o.analyze_only("antiga", destino_run_id="nova")
    finally:
        loja.close()
