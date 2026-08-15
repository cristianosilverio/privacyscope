"""
Plugin Registry — mapping nome → classe para resolução declarativa de plugins.

Centraliza o conhecimento sobre "qual plugin atende qual nome no protocol.yaml"
num único arquivo auditável. Camadas vizinhas (orchestrator, CLI, futuros
inspetores) consultam este registry — nenhuma delas precisa importar plugins
diretamente. Isso reforça o Open/Closed Principle: adicionar um plugin novo
é (1) criar o arquivo do plugin, (2) adicionar uma linha aqui.

A separação por dicionário (``SOURCES``, ``FETCHERS``, ...) reflete as camadas
da arquitetura e impede que um plugin de uma camada seja inadvertidamente
resolvido como plugin de outra (e.g., um Fetcher sendo invocado como Test).

Adicionar um plugin novo:

    # Em algum arquivo da sua camada (ex.: src/privacyscope/tests/foo.py):
    class FooTest(VariableTest):
        name = "foo"
        version = "0.1.0"
        variable_name = "foo"
        def evaluate(self, evidence, params): ...

    # Aqui:
    from privacyscope.tests.foo import FooTest
    VARIABLE_TESTS["foo"] = FooTest

    # No protocol.yaml:
    tests:
      - name: foo
        params: {}
"""

from __future__ import annotations

from typing import Type

from privacyscope.core.interfaces import (
    OutputRenderer,
    PageFetcher,
    RawRepository,
    ResultStore,
    SampleSource,
    VariableTest,
)

# --- Plugins concretos já existentes ------------------------------------
from privacyscope.sources.tranco import TrancoSource
from privacyscope.fetchers.http_fetcher import HttpFetcher
from privacyscope.fetchers.playwright_fetcher import PlaywrightFetcher
from privacyscope.fetchers.fallback_chain import FallbackChain
from privacyscope.storage.filesystem_repo import FileSystemRepository
from privacyscope.storage.sqlite_store import SQLiteResultStore
from privacyscope.tests.banner_cookies import BannerCookiesTest
from privacyscope.tests.canal_titular import CanalTitularTest
from privacyscope.tests.canal_titular_ml import CanalTitularMLTest
from privacyscope.tests.politica_privacidade import PoliticaPrivacidadeTest
from privacyscope.tests.bertimbau import (
    DireitosDensaTest, FinalidadeDensaTest, TransfDensaTest,
)
from privacyscope.tests.ml_texto import (
    DireitosTitularExplicadosTest, FinalidadeEspecificadaTest,
    TransfInternacionalDivulgadaTest,
)


# =============================================================================
# Registries por camada
# =============================================================================
SOURCES: dict[str, Type[SampleSource]] = {
    "tranco": TrancoSource,
}

FETCHERS: dict[str, Type[PageFetcher]] = {
    "http_simples": HttpFetcher,
    "playwright": PlaywrightFetcher,
    "fallback_chain": FallbackChain,
}

REPOSITORIES: dict[str, Type[RawRepository]] = {
    "filesystem": FileSystemRepository,
}

RESULT_STORES: dict[str, Type[ResultStore]] = {
    "sqlite": SQLiteResultStore,
}

VARIABLE_TESTS: dict[str, Type[VariableTest]] = {
    "banner_cookies": BannerCookiesTest,
    "politica_privacidade": PoliticaPrivacidadeTest,
    "canal_titular": CanalTitularTest,
    # ACRESCENTA o regime supervisionado sem retirar o determinístico: os
    # resultados reportam os dois para esta variavel, e o arcabouco precisa
    # poder produzir ambos sob declaracao no protocolo.
    "canal_titular_ml": CanalTitularMLTest,
    # Variaveis textuais por classificacao supervisionada. Uma implementacao,
    # tres entradas: o orquestrador resolve nome -> classe e instancia sem
    # argumentos, de sorte que a identidade da variavel vive na classe.
    "finalidade_especificada": FinalidadeEspecificadaTest,
    "direitos_titular_explicados": DireitosTitularExplicadosTest,
    "transf_internacional_divulgada": TransfInternacionalDivulgadaTest,
    # Teto comparativo por representacao densa. Registrado e NAO habilitado na
    # configuracao padrao: custa horas por execucao, exige pesos que nao
    # acompanham o repositorio, e produz as mesmas variaveis — declarar os dois
    # no mesmo run exige `variavel_sufixo`, sob pena de um sobrescrever o outro.
    "finalidade_especificada_densa": FinalidadeDensaTest,
    "direitos_titular_explicados_densa": DireitosDensaTest,
    "transf_internacional_divulgada_densa": TransfDensaTest,
}

from privacyscope.outputs.renderizadores import (      # noqa: E402
    CsvEvidencias, CsvLargo, CsvLongo, JsonEvidencia, ParquetLongo,
)

OUTPUT_RENDERERS: dict[str, Type[OutputRenderer]] = {
    # A sexta camada. Cinco artefatos porque quem tabula, quem prioriza, quem
    # verifica e quem reprocessa querem recortes distintos do mesmo conjunto.
    "csv": CsvLongo,
    "csv_largo": CsvLargo,
    "csv_evidencias": CsvEvidencias,
    "parquet": ParquetLongo,
    "json": JsonEvidencia,
}


# =============================================================================
# API pública: resolução por (camada, nome)
# =============================================================================
def resolve(layer: str, name: str):
    """Resolve nome de plugin para a classe correspondente.

    Args:
        layer: nome da camada ('sources', 'fetchers', 'repositories',
            'result_stores', 'variable_tests', 'output_renderers').
        name: nome do plugin conforme declarado no protocol.yaml.

    Returns:
        A classe do plugin (não instância — caller chama o __init__).

    Raises:
        KeyError: se a camada não existir ou o nome não estiver registrado
            naquela camada. A mensagem lista nomes disponíveis para ajudar
            diagnose precoce (falha-cedo do orchestrator).
    """
    registry_map = {
        "sources": SOURCES,
        "fetchers": FETCHERS,
        "repositories": REPOSITORIES,
        "result_stores": RESULT_STORES,
        "variable_tests": VARIABLE_TESTS,
        "output_renderers": OUTPUT_RENDERERS,
    }
    if layer not in registry_map:
        raise KeyError(
            f"camada desconhecida: {layer!r}. Disponíveis: {sorted(registry_map.keys())}"
        )
    registry = registry_map[layer]
    if name not in registry:
        raise KeyError(
            f"plugin {name!r} não registrado em {layer}. "
            f"Disponíveis: {sorted(registry.keys())}"
        )
    return registry[name]


def list_plugins() -> dict[str, list[str]]:
    """Snapshot de todos os plugins registrados, agrupados por camada.

    Usado por ``privacyscope list-plugins`` (CLI) e por testes que verificam
    que um plugin foi devidamente registrado.
    """
    return {
        "sources": sorted(SOURCES.keys()),
        "fetchers": sorted(FETCHERS.keys()),
        "repositories": sorted(REPOSITORIES.keys()),
        "result_stores": sorted(RESULT_STORES.keys()),
        "variable_tests": sorted(VARIABLE_TESTS.keys()),
        "output_renderers": sorted(OUTPUT_RENDERERS.keys()),
    }


__all__ = [
    "SOURCES",
    "FETCHERS",
    "REPOSITORIES",
    "RESULT_STORES",
    "VARIABLE_TESTS",
    "OUTPUT_RENDERERS",
    "resolve",
    "list_plugins",
]
