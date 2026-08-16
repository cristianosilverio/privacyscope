

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


# ---------------------------------------------------------------------------
# Ordenacao da triagem por nao conformidade
# ---------------------------------------------------------------------------
def _triagem(tmp_path, sitios):
    """sitios = {dominio: {variavel: valor}} -> linhas do csv_largo, na ordem."""
    import csv
    from datetime import datetime, timezone
    from privacyscope.core.plugin_registry import resolve
    from privacyscope.core.types import VariableResult

    loja = resolve("result_stores", "sqlite")(db_path=str(tmp_path / "t.sqlite"))
    loja.begin_run("R", protocol_version="t", sample_size=len(sitios))
    for host, vars_ in sitios.items():
        for v, val in vars_.items():
            at = {"coletado": False, "motivo": "desafio_anti_bot"} \
                if val == "nao_coletado" else {}
            loja.upsert(VariableResult(
                domain_url=f"https://{host}", variable_name=v, value=val,
                confidence=0.0, audit_trail=at, protocol_version="t",
                plugin_version="1", run_id="R",
                timestamp_utc=datetime.now(timezone.utc)))
    loja.finish_run("R", errors_count=0)
    alvo = resolve("output_renderers", "csv_largo")().render(
        loja, {"path": str(tmp_path / "largo.csv"), "run_id": "R"})
    loja.close()
    return list(csv.DictReader(alvo.open(encoding="utf-8"), delimiter=";"))


def test_sem_politica_vem_antes_de_com_politica_que_falha_tudo(tmp_path):
    """O caso que a soma bruta invertia: na coleta ao vivo, seis sitios COM
    politica ficaram acima dos trinta e um SEM politica, porque `nao_aplicavel`
    tira tres variaveis da contagem e rebaixa o teto do pior caso."""
    linhas = _triagem(tmp_path, {
        # 3 medidas ausentes, 3 sem medicao por precondicao: o pior caso real
        "sem_nada.br": {"tem_banner_cookies": False,
                        "tem_politica_privacidade": False,
                        "tem_canal_titular": False,
                        "finalidade_especificada": "nao_aplicavel",
                        "direitos_titular_explicados": "nao_aplicavel",
                        "transf_internacional_divulgada": "nao_aplicavel"},
        # 4 medidas ausentes, nenhuma impedida: soma bruta o poria em primeiro
        "com_politica.br": {"tem_banner_cookies": False,
                            "tem_politica_privacidade": True,
                            "tem_canal_titular": False,
                            "finalidade_especificada": True,
                            "direitos_titular_explicados": False,
                            "transf_internacional_divulgada": False},
    })
    assert [l["dominio"] for l in linhas] == ["sem_nada.br", "com_politica.br"]
    assert linhas[0]["ordem_triagem"] == "1"
    # a soma bruta continua visivel, e continua dizendo o contrario da ordem
    assert int(linhas[0]["n_sinais_ausentes"]) < int(linhas[1]["n_sinais_ausentes"])


def test_nao_coletado_vai_para_o_fim(tmp_path):
    """Perfil incompleto nao se compara com perfil completo, e recoleta e outra
    fila que nao a de fiscalizacao."""
    linhas = _triagem(tmp_path, {
        "bloqueado.br": {"tem_politica_privacidade": "nao_coletado",
                         "tem_banner_cookies": "nao_coletado"},
        "conforme.br": {"tem_politica_privacidade": True,
                        "tem_banner_cookies": True},
    })
    assert [l["dominio"] for l in linhas] == ["conforme.br", "bloqueado.br"]
    assert linhas[-1]["motivo_nao_coleta"] == "desafio_anti_bot"


def test_ordem_e_estavel_em_empate(tmp_path):
    linhas = _triagem(tmp_path, {
        "zulu.br": {"tem_politica_privacidade": False},
        "alfa.br": {"tem_politica_privacidade": False},
    })
    assert [l["dominio"] for l in linhas] == ["alfa.br", "zulu.br"]
