"""Artefatos de modelo: gravacao, leitura e conferencia de integridade."""
from privacyscope.models.artefato import (  # noqa: F401
    Artefato, ArtefatoCanal, ArtefatoCorrompido, grava, grava_canal, le, le_canal,
    resumo_arquivo, resumo_texto,
)
