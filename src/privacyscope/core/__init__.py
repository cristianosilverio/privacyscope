"""Interfaces e tipos centrais do PrivacyScope.

Este módulo expõe o contrato de dados e os contratos comportamentais (ABCs)
que circulam entre as seis camadas da arquitetura. Toda camada deve importar
daqui — nenhuma deve definir tipos próprios para tráfego inter-camadas, e
nenhum plugin deve duplicar interfaces.
"""

from privacyscope.core.interfaces import (
    OutputRenderer,
    PageFetcher,
    RawRepository,
    ResultStore,
    SampleSource,
    VariableTest,
)
from privacyscope.core.types import (
    Domain,
    EvidenceRef,
    RawEvidence,
    VariableResult,
    utc_now,
)

__all__ = [
    # Tipos de dados
    "Domain",
    "RawEvidence",
    "EvidenceRef",
    "VariableResult",
    "utc_now",
    # Interfaces (ABCs)
    "SampleSource",
    "PageFetcher",
    "RawRepository",
    "VariableTest",
    "ResultStore",
    "OutputRenderer",
]
