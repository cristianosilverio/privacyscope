# -*- coding: utf-8 -*-
"""Fontes amostrais: lista fornecida e coorte de reexame."""
from datetime import datetime, timezone

import pytest

from privacyscope.core.plugin_registry import resolve
from privacyscope.core.types import NAO_APLICAVEL, VariableResult
from privacyscope.sources.coorte_reexame import CoorteInvalidaError, CoorteReexameSource
from privacyscope.sources.csv_lista import (
    CsvSource, ListaInvalidaError, normaliza_host, resumo_arquivo, sufixo,
)


def _lista(tmp_path, texto, nome="l.csv"):
    p = tmp_path / nome
    p.write_text(texto, encoding="utf-8")
    return p


# --------------------------------------------------------------- CsvSource
def test_registro_expoe_as_tres_fontes():
    for n in ("tranco", "csv", "coorte_reexame"):
        assert resolve("sources", n)


def test_aceita_dominio_nu_e_endereco_completo(tmp_path):
    p = _lista(tmp_path, "dominio\nexemplo.com.br\nhttps://outro.gov.br/politica\n")
    d = list(CsvSource().list_domains({"path": str(p)}))
    assert [x.url for x in d] == ["https://exemplo.com.br", "https://outro.gov.br"]
    assert [x.tld for x in d] == [".com.br", ".gov.br"]


def test_detecta_o_delimitador(tmp_path):
    """Virgula e ponto e virgula convivem em planilhas brasileiras."""
    for texto in ("dominio;estrato\na.com.br;corp\n", "dominio,estrato\na.com.br,corp\n"):
        p = _lista(tmp_path, texto, nome=f"{abs(hash(texto))}.csv")
        d = list(CsvSource().list_domains({"path": str(p)}))
        assert len(d) == 1 and d[0].stratum == "corp"


def test_identifica_a_coluna_por_nome_alternativo(tmp_path):
    p = _lista(tmp_path, "url;setor\nhttps://x.com.br;saude\n")
    d = list(CsvSource().list_domains({"path": str(p)}))
    assert d[0].url == "https://x.com.br" and d[0].stratum == "saude"


def test_sem_coluna_de_dominio_a_mensagem_orienta(tmp_path):
    p = _lista(tmp_path, "nome;cnpj\nAlfa;123\n")
    with pytest.raises(ListaInvalidaError, match="coluna_dominio"):
        list(CsvSource().list_domains({"path": str(p)}))


def test_repetidos_e_invalidos_sao_descartados(tmp_path):
    p = _lista(tmp_path, "dominio\na.com.br\nA.COM.BR\n\nsemponto\nb.com.br\n")
    d = list(CsvSource().list_domains({"path": str(p)}))
    assert [x.url for x in d] == ["https://a.com.br", "https://b.com.br"]


def test_identidade_da_lista_e_conferida(tmp_path):
    """O quadro amostral integra a cadeia de custodia como qualquer outro insumo."""
    p = _lista(tmp_path, "dominio\na.com.br\n")
    sha = resumo_arquivo(p)
    assert len(list(CsvSource().list_domains({"path": str(p), "sha256": sha}))) == 1
    with pytest.raises(ListaInvalidaError, match="nao corresponde"):
        list(CsvSource().list_domains({"path": str(p), "sha256": "0" * 64}))


def test_lista_ausente_interrompe(tmp_path):
    with pytest.raises(ListaInvalidaError, match="nao encontrada"):
        list(CsvSource().list_domains({"path": str(tmp_path / "nao_existe.csv")}))


def test_sufixo_composto_brasileiro():
    assert sufixo("prefeitura.sp.gov.br") == ".sp.gov.br" or \
           sufixo("prefeitura.sp.gov.br").endswith("gov.br")
    assert normaliza_host("HTTPS://Www.X.com.br/a/b") == "www.x.com.br"


# ------------------------------------------------------- CoorteReexameSource
def _banco(tmp_path, linhas, run_id="r1"):
    loja = resolve("result_stores", "sqlite")(db_path=str(tmp_path / "r.sqlite"))
    try:
        loja.begin_run(run_id, protocol_version="v", sample_size=len(linhas))
        for host, var, val, at in linhas:
            loja.upsert(VariableResult(
                domain_url=f"https://{host}", variable_name=var, value=val,
                confidence=0.0, audit_trail=at or {}, protocol_version="v",
                plugin_version="1", run_id=run_id,
                timestamp_utc=datetime.now(timezone.utc)))
        loja.finish_run(run_id, errors_count=0)
    finally:
        loja.close()
    return tmp_path / "r.sqlite"


def test_coorte_por_valor_falso(tmp_path):
    b = _banco(tmp_path, [("a.com.br", "tem_politica_privacidade", False, None),
                          ("b.com.br", "tem_politica_privacidade", True, None)])
    d = list(CoorteReexameSource().list_domains(
        {"db_path": str(b), "variavel": "tem_politica_privacidade", "valor": False}))
    assert [x.url for x in d] == ["https://a.com.br"]


def test_coorte_por_nao_aplicavel(tmp_path):
    b = _banco(tmp_path, [("a.com.br", "finalidade_especificada", NAO_APLICAVEL, None),
                          ("b.com.br", "finalidade_especificada", True, None)])
    d = list(CoorteReexameSource().list_domains(
        {"db_path": str(b), "variavel": "finalidade_especificada",
         "valor": NAO_APLICAVEL}))
    assert [x.url for x in d] == ["https://a.com.br"]


def test_coorte_por_extrapolacao(tmp_path):
    b = _banco(tmp_path, [
        ("a.com.br", "finalidade_especificada", True, {"extrapolacao": True}),
        ("b.com.br", "finalidade_especificada", True, {"extrapolacao": False})])
    d = list(CoorteReexameSource().list_domains(
        {"db_path": str(b), "variavel": "finalidade_especificada",
         "extrapolacao": True}))
    assert [x.url for x in d] == ["https://a.com.br"]


def test_coorte_por_ausencia_de_resultado(tmp_path):
    """Dominio que entrou na execucao e nao produziu a variavel: falha de coleta."""
    b = _banco(tmp_path, [("a.com.br", "tem_banner_cookies", True, None),
                          ("b.com.br", "tem_banner_cookies", True, None),
                          ("b.com.br", "tem_politica_privacidade", True, None)])
    d = list(CoorteReexameSource().list_domains(
        {"db_path": str(b), "variavel": "tem_politica_privacidade",
         "sem_resultado": True}))
    assert [x.url for x in d] == ["https://a.com.br"]


def test_dois_criterios_sao_recusados(tmp_path):
    b = _banco(tmp_path, [("a.com.br", "v", False, None)])
    with pytest.raises(CoorteInvalidaError, match="UM criterio"):
        list(CoorteReexameSource().list_domains(
            {"db_path": str(b), "variavel": "v", "valor": False,
             "extrapolacao": True}))


def test_limite_recorta(tmp_path):
    b = _banco(tmp_path, [(f"s{i}.com.br", "v", False, None) for i in range(10)])
    d = list(CoorteReexameSource().list_domains(
        {"db_path": str(b), "variavel": "v", "valor": False, "limite": 3}))
    assert len(d) == 3


def test_banco_ausente_interrompe(tmp_path):
    with pytest.raises(CoorteInvalidaError, match="nao encontrado"):
        list(CoorteReexameSource().list_domains(
            {"db_path": str(tmp_path / "x.sqlite"), "variavel": "v", "valor": False}))


def _banco_dois(tmp_path, r1, r2):
    loja = resolve("result_stores", "sqlite")(db_path=str(tmp_path / "d.sqlite"))
    try:
        import time
        for rid, linhas in (("antiga", r1), ("nova", r2)):
            loja.begin_run(rid, protocol_version="v", sample_size=len(linhas))
            for host, var, val in linhas:
                loja.upsert(VariableResult(
                    domain_url=f"https://{host}", variable_name=var, value=val,
                    confidence=0.0, audit_trail={}, protocol_version="v",
                    plugin_version="1", run_id=rid,
                    timestamp_utc=datetime.now(timezone.utc)))
            loja.finish_run(rid, errors_count=0)
            time.sleep(0.01)
    finally:
        loja.close()
    return tmp_path / "d.sqlite"


def test_mudanca_entre_execucoes(tmp_path):
    """Quem regularizou e quem regrediu: as duas listas do ciclo do art. 20."""
    b = _banco_dois(tmp_path,
                    [("regularizou.br", "v", False), ("regrediu.br", "v", True),
                     ("estavel.br", "v", True)],
                    [("regularizou.br", "v", True), ("regrediu.br", "v", False),
                     ("estavel.br", "v", True)])
    d = list(CoorteReexameSource().list_domains(
        {"db_path": str(b), "mudanca": True, "variavel": "v"}))
    assert sorted(x.url for x in d) == ["https://regrediu.br",
                                        "https://regularizou.br"]


def test_mudanca_sem_variavel_considera_qualquer_uma(tmp_path):
    b = _banco_dois(tmp_path,
                    [("a.br", "x", True), ("a.br", "y", True), ("b.br", "x", True)],
                    [("a.br", "x", True), ("a.br", "y", False), ("b.br", "x", True)])
    d = list(CoorteReexameSource().list_domains({"db_path": str(b), "mudanca": True}))
    assert [x.url for x in d] == ["https://a.br"]


def test_mudanca_ignora_dominio_ausente_de_uma_execucao(tmp_path):
    """Variavel ausente de um lado e falha de coleta; trata-la como mudanca
    confundiria instabilidade do detector com instabilidade da coleta."""
    b = _banco_dois(tmp_path, [("so_na_antiga.br", "v", True), ("comum.br", "v", True)],
                    [("comum.br", "v", True)])
    d = list(CoorteReexameSource().list_domains(
        {"db_path": str(b), "mudanca": True, "variavel": "v"}))
    assert d == []


def test_mudanca_com_uma_so_execucao_interrompe(tmp_path):
    b = _banco(tmp_path, [("a.br", "v", True, None)])
    with pytest.raises(CoorteInvalidaError, match="apenas uma"):
        list(CoorteReexameSource().list_domains(
            {"db_path": str(b), "mudanca": True, "variavel": "v"}))


def test_execucao_em_curso_nao_define_coorte(tmp_path):
    """Sem `finish_run`, a execucao nao entra: o que ela ainda nao alcancou seria
    lido como ausencia de sinal."""
    loja = resolve("result_stores", "sqlite")(db_path=str(tmp_path / "e.sqlite"))
    try:
        loja.begin_run("parcial", protocol_version="v", sample_size=1)
        loja.upsert(VariableResult(
            domain_url="https://a.br", variable_name="v", value=True,
            confidence=0.0, audit_trail={}, protocol_version="v", plugin_version="1",
            run_id="parcial", timestamp_utc=datetime.now(timezone.utc)))
    finally:
        loja.close()
    with pytest.raises(CoorteInvalidaError, match="CONCLUIDA"):
        list(CoorteReexameSource().list_domains(
            {"db_path": str(tmp_path / "e.sqlite"), "variavel": "v", "valor": True}))
