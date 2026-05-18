"""Plugins de Ingestão (SampleSource).

Reexporta as implementações concretas para que o orquestrador possa
descobri-las por nome a partir do protocol.yaml.
"""

from privacyscope.sources.tranco import TrancoSource

__all__ = ["TrancoSource"]
