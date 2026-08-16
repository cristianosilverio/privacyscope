# -*- coding: utf-8 -*-
"""Todo protocolo do repositorio precisa ser executavel pelo comando que anuncia.

Os protocolos `padrao`, `analista` e `teto` declaravam `source:` no singular, com
`tld_filter` e `limit`, nomes que a fonte por ranque nao conhece — e sem `list_id`,
que ela exige. Nenhum dos tres executava, e o defeito nao aparecia porque os
protocolos do trabalho congelam a amostra em `override_domains`.
"""
from pathlib import Path

import pytest
import yaml

from privacyscope.core.plugin_registry import resolve

REPO = Path(__file__).resolve().parents[1]
PROTOCOLOS = sorted(REPO.glob("protocols/*.yaml"))


def carrega(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("p", PROTOCOLOS, ids=lambda p: p.stem)
def test_protocolo_resolve_a_origem_dos_dominios(p):
    """Ou congela a amostra, ou declara fonte resolvivel, ou e de reanalise."""
    d = carrega(p)
    if d.get("override_domains"):
        return
    fontes = d.get("sources") or ([d["source"]] if d.get("source") else [])
    if not fontes:
        # Protocolo de reanalise nao resolve ingestao: `analyze` le o manifesto.
        assert "analyze" in p.read_text(encoding="utf-8"), (
            f"{p.name} nao congela amostra, nao declara fonte e nao se anuncia "
            f"como protocolo de reanalise")
        return
    for f in fontes:
        assert resolve("sources", f["name"]) is not None


@pytest.mark.parametrize("p", PROTOCOLOS, ids=lambda p: p.stem)
def test_params_da_fonte_por_ranque_sao_os_que_ela_exige(p):
    """`_validate_params` e o contrato; params que ela recusa quebram na execucao,
    e nao na leitura do protocolo."""
    d = carrega(p)
    for f in (d.get("sources") or []):
        if f["name"] != "tranco":
            continue
        params = dict(f.get("params") or {})
        params.pop("max_n", None)          # teto de quem escreve, nao da fonte
        resolve("sources", "tranco")._validate_params(params)


@pytest.mark.parametrize("p", PROTOCOLOS, ids=lambda p: p.stem)
def test_nenhum_protocolo_declara_chave_de_fonte_vazia(p):
    """Protocolo que declara o que nao usa induz a erro quem o le."""
    d = carrega(p)
    assert not (d.get("source") and d.get("sources")), (
        f"{p.name} declara `source` e `sources`: a resolucao ficaria ambigua")


# ---------------------------------------------------------------------------
# O documento de arquitetura precisa descrever o codigo que existe
# ---------------------------------------------------------------------------
def test_arquitetura_nao_cita_classe_inexistente():
    """O documento nomeava `StructuralTest`, `LexiconTest`, `MLClassifierTest` e
    `CookieAnalyzer` como implementacoes; nenhuma das quatro existe. E o texto que
    a banca le para entender a arquitetura."""
    import re

    from privacyscope.core import plugin_registry as R

    doc = (REPO / "docs" / "arquitetura.md").read_text(encoding="utf-8")
    registradas = set()
    for camada in (R.SOURCES, R.FETCHERS, R.REPOSITORIES, R.RESULT_STORES,
                   R.VARIABLE_TESTS, R.OUTPUT_RENDERERS):
        registradas |= {c.__name__ for c in camada.values()}
    # Nomes de interface: sao contratos, e nao implementacoes registradas.
    interfaces = {"SampleSource", "PageFetcher", "RawRepository", "VariableTest",
                  "ResultStore", "OutputRenderer"}
    citadas = set(re.findall(
        r"`([A-Z][A-Za-z]*(?:Test|Source|Fetcher|Repository|Store|Chain|Renderer))`",
        doc))
    fantasmas = citadas - registradas - interfaces
    assert not fantasmas, f"o documento cita classes que nao existem: {sorted(fantasmas)}"


def test_arquitetura_descreve_os_quatro_estados():
    doc = (REPO / "docs" / "arquitetura.md").read_text(encoding="utf-8")
    for estado in ("nao_aplicavel", "nao_coletado"):
        assert estado in doc, f"o documento nao descreve o estado `{estado}`"


def test_arquitetura_lista_as_fontes_registradas():
    from privacyscope.core import plugin_registry as R

    doc = (REPO / "docs" / "arquitetura.md").read_text(encoding="utf-8")
    for nome, cls in R.SOURCES.items():
        assert cls.__name__ in doc, f"fonte `{nome}` registrada e ausente do documento"


def test_readme_descreve_os_quatro_estados():
    """O resultado de uma variavel nao e booleano, e quem chega ao repositorio
    precisa saber disso antes de ler qualquer CSV."""
    doc = (REPO / "README.md").read_text(encoding="utf-8")
    for estado in ("nao_aplicavel", "nao_coletado"):
        assert estado in doc, f"o README nao descreve o estado `{estado}`"


def test_readme_lista_as_variaveis_do_protocolo_padrao():
    """A tabela do README anunciava `cookies_set`, `categoria_cookies` e
    `menciona_lgpd`, que nao integram a bateria, e omitia as tres textuais."""
    import yaml

    from privacyscope.core.plugin_registry import resolve

    doc = (REPO / "README.md").read_text(encoding="utf-8")
    padrao = yaml.safe_load(
        (REPO / "protocols" / "padrao.yaml").read_text(encoding="utf-8"))
    for t in padrao["tests"]:
        nome = resolve("variable_tests", t["name"]).variable_name
        assert f"`{nome}`" in doc, f"variavel `{nome}` do protocolo padrao ausente do README"


def test_readme_so_anuncia_subcomandos_que_existem():
    """O README mandava rodar `privacyscope run --config ...`; a flag nao existe e
    o arquivo apontado esta marcado como esquema obsoleto. E o primeiro comando
    que alguem digita."""
    import re

    from privacyscope.cli import build_parser

    doc = (REPO / "README.md").read_text(encoding="utf-8")
    sub = [a for a in build_parser()._subparsers._group_actions[0].choices]
    citados = set(re.findall(r"privacyscope ([a-z-]+)", doc))
    assert citados, "o README deixou de mostrar qualquer comando"
    assert citados <= set(sub), f"README cita subcomando inexistente: {citados - set(sub)}"
    assert "--config" not in doc, "o caminho do protocolo e posicional"


def test_readme_nao_afirma_manifesto_assinado():
    """Assinatura implica nao repudio por chave; o que existe e encadeamento por
    hash. Num trabalho que cita a ISO/IEC 27037, a palavra e cobravel."""
    import re

    doc = (REPO / "README.md").read_text(encoding="utf-8")
    for frase in re.findall(r"[^.]*assinad[^.]*\.", doc):
        assert "não assinado" in frase or "nao assinado" in frase, (
            f"afirmacao de assinatura sem lastro no codigo: {frase.strip()!r}")
