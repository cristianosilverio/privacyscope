

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
