"""Artefatos de modelo: gravacao, leitura e conferencia de integridade."""
from privacyscope.models.artefato import (  # noqa: F401
    ARQUIVOS_CODIFICADOR, Artefato, ArtefatoCanal, ArtefatoCorrompido, ArtefatoDenso,
    grava, grava_canal, grava_denso, le, le_canal, le_denso,
    resumo_arquivo, resumo_diretorio, resumo_texto,
)
