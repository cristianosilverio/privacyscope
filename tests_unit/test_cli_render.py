# -*- coding: utf-8 -*-
"""Subcomando `render`: regera saidas sem reanalisar."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]


def _protocolo(tmp_path, com_saidas=True):
    d = yaml.safe_load((REPO / "protocols" / "padrao.yaml").read_text(encoding="utf-8"))
    d["repository"] = {"name": "filesystem", "params": {"base_path": str(tmp_path / "repo")}}
    d["result_store"] = {"name": "sqlite", "params": {"db_path": str(tmp_path / "r.sqlite")}}
    if com_saidas:
        d["outputs"] = [
            {"name": "csv", "params": {"path": str(tmp_path / "saida.csv")}},
            {"name": "csv_triagem", "params": {"path": str(tmp_path / "largo.csv")}},
        ]
    else:
        d.pop("outputs", None)
    alvo = tmp_path / "p.yaml"
    alvo.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return alvo


def _semeia(caminho, run_id="r1"):
    from privacyscope.core.plugin_registry import resolve
    from privacyscope.core.types import VariableResult
    loja = resolve("result_stores", "sqlite")(db_path=str(caminho))
    try:
        for h in ("a.com.br", "b.com.br"):
            loja.upsert(VariableResult(
                domain_url=f"https://{h}", variable_name="finalidade_especificada",
                value=True, confidence=0.7,
                audit_trail={"n_sentencas_sinalizadas": 5, "n_segmentos_avaliados": 50},
                protocol_version="padrao-v1.0.0", plugin_version="1.0.0",
                run_id=run_id, timestamp_utc=datetime.now(timezone.utc)))
    finally:
        loja.close()


def test_render_gera_sem_reanalisar(tmp_path):
    from privacyscope.cli import main
    proto = _protocolo(tmp_path)
    _semeia(tmp_path / "r.sqlite")
    assert main(["render", str(proto)]) == 0
    assert (tmp_path / "saida.csv").exists()
    assert (tmp_path / "largo.csv").exists()


def test_render_traz_a_densidade(tmp_path):
    import csv
    from privacyscope.cli import main
    proto = _protocolo(tmp_path)
    _semeia(tmp_path / "r.sqlite")
    main(["render", str(proto)])
    linhas = list(csv.DictReader((tmp_path / "saida.csv").open(encoding="utf-8"),
                                 delimiter=";"))
    assert float(linhas[0]["densidade_sinalizacao"]) == 0.1


def test_render_filtra_por_execucao(tmp_path):
    import csv
    from privacyscope.cli import main
    proto = _protocolo(tmp_path)
    _semeia(tmp_path / "r.sqlite", run_id="r1")
    _semeia(tmp_path / "r.sqlite", run_id="r2")
    main(["render", str(proto), "--run-id", "r2"])
    linhas = list(csv.DictReader((tmp_path / "saida.csv").open(encoding="utf-8"),
                                 delimiter=";"))
    assert linhas and {l["run_id"] for l in linhas} == {"r2"}


def test_protocolo_sem_saidas_avisa_e_falha(tmp_path, capsys):
    from privacyscope.cli import main
    proto = _protocolo(tmp_path, com_saidas=False)
    _semeia(tmp_path / "r.sqlite")
    assert main(["render", str(proto)]) == 1
    assert "não declara" in capsys.readouterr().out


def test_render_nao_toca_a_camada_de_evidencia(tmp_path, monkeypatch):
    """`render` le apenas resultados; recoletar ou reanalisar seria outro comando."""
    from privacyscope.cli import main
    import privacyscope.orchestrator as mod
    proto = _protocolo(tmp_path)
    _semeia(tmp_path / "r.sqlite")
    chamou = {"analyze": False}

    def nao(*a, **k):
        chamou["analyze"] = True
        raise AssertionError("render nao pode reanalisar")

    monkeypatch.setattr(mod.Orchestrator, "analyze_only", nao)
    monkeypatch.setattr(mod.Orchestrator, "_analyze_evidence", nao)
    assert main(["render", str(proto)]) == 0
    assert not chamou["analyze"]


def test_todos_os_caminhos_que_encerram_analise_rendem(tmp_path):
    """`run` e `analyze` produzem resultados e devem fechar o ciclo do mesmo modo.

    O defeito que motivou este teste: a chamada dos renderizadores foi acrescentada
    ao fim de `analyze_only` e esquecida em `run`, de sorte que a coleta ao vivo
    concluiu sem gerar artefato de saida algum — sem erro, sem aviso.
    """
    import inspect
    from privacyscope.orchestrator import Orchestrator
    for metodo in ("run", "analyze_only"):
        fonte = inspect.getsource(getattr(Orchestrator, metodo))
        assert "render_outputs" in fonte, (
            f"Orchestrator.{metodo} nao chama render_outputs; a execucao encerraria "
            f"sem artefato de saida")


def test_coleta_isolada_nao_rende():
    """`collect_only` para na terceira camada e nao produz resultado: render ali
    geraria arquivo vazio e daria impressao de saida legitima."""
    import inspect
    from privacyscope.orchestrator import Orchestrator
    assert "render_outputs" not in inspect.getsource(Orchestrator.collect_only)
