

def test_triagem_mostra_causa_raiz_e_nao_a_consequencia(tmp_path):
    """`dependencia_nao_coletada` e consequencia; deixa-la sobrescrever o motivo
    original esconderia por que a coluna ficou vazia."""
    import csv
    from datetime import datetime, timezone
    from privacyscope.core.plugin_registry import resolve
    from privacyscope.core.types import NAO_COLETADO, VariableResult

    loja = resolve("result_stores", "sqlite")(db_path=str(tmp_path / "r.sqlite"))
    loja.begin_run("R", protocol_version="t", sample_size=1)
    for v, motivo in (("tem_politica_privacidade", "desafio_anti_bot"),
                      ("finalidade_especificada", "dependencia_nao_coletada")):
        loja.upsert(VariableResult(
            domain_url="https://x.br", variable_name=v, value=NAO_COLETADO,
            confidence=0.0, audit_trail={"motivo": motivo, "coletado": False},
            protocol_version="t", plugin_version="1", run_id="R",
            timestamp_utc=datetime.now(timezone.utc)))
    loja.finish_run("R", errors_count=0)
    alvo = resolve("output_renderers", "csv_largo")().render(
        loja, {"path": str(tmp_path / "largo.csv"), "run_id": "R"})
    loja.close()
    linhas = list(csv.DictReader(alvo.open(encoding="utf-8"), delimiter=";"))
    assert linhas[0]["motivo_nao_coleta"] == "desafio_anti_bot"
    assert linhas[0]["n_nao_coletado"] == "2"
    assert linhas[0]["n_variaveis_apuradas"] == "0"
