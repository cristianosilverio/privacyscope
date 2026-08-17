"""Base comum dos renderizadores de saida.

TRES DECISOES QUE VALEM PARA TODOS
----------------------------------
PROCEDENCIA VIAJA JUNTO. Todo artefato de saida carrega o identificador da
execucao, a versao do protocolo e, quando o resultado provem de classificacao, o
resumo criptografico do artefato de modelo que o produziu. Planilha que sai do
arcabouco sem esses campos perde o vinculo com a evidencia e com o modelo, e deixa
de ser conferivel — que e precisamente o que o desenho promete.

O REGISTRO DE AUDITORIA NAO CABE EM CELULA. Ele e estrutura aninhada, com as
sentencas que fundamentam cada sinalizacao. Nos formatos tabulares extraem-se dele
apenas os campos escalares; a estrutura integra vai para a saida em notacao de
objetos, e as sentencas ganham arquivo proprio, em formato de lista de trabalho.

SEPARAR TABULACAO DE VERIFICACAO. Quem tabula quer uma linha por sitio; quem
verifica quer uma linha por sentenca a conferir. Sao usos distintos, e forcar os
dois no mesmo arquivo atende mal a ambos.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from privacyscope.core.interfaces import ResultStore
from privacyscope.core.types import VariableResult

# Campos escalares do registro de auditoria que se promovem a coluna. A escolha
# recai sobre os que sustentam leitura e conferencia: quanto se sinalizou, sobre
# quantos segmentos, sob que limiar, com que cobertura, e qual modelo decidiu.
ESCALARES = (
    "n_sentencas_sinalizadas", "n_segmentos_avaliados", "limiar",
    "cobertura_vocabulario", "extrapolacao", "motivo",
    "modelo_sha256", "preparo_versao", "extrator_versao", "corpo_sha256",
    # Coleta que a cadeia declarou insuficiente e devolveu assim mesmo, por ser
    # melhor que perder a unidade. Sem coluna, a distincao ficaria so no tar.gz.
    "coleta_degradada", "motivo_coleta",
    # Condicao do transporte. O arcabouco registra o que foi apresentado;
    # a valoracao da evidencia e de quem a examina.
    "tls_estado", "tls_certificado_de", "tls_emissor",
)

COLUNAS_BASE = ("domain_url", "variable_name", "value", "confidence",
                "run_id", "protocol_version", "plugin_version", "computed_at")

# Derivada, e nao lida do registro: a razao entre contagem e denominador nao e
# gravada pelo plugin, e calcula-la aqui evita que cada consumidor a refaca.
DERIVADAS = ("densidade_sinalizacao",)


def coleta(store: ResultStore, params: dict[str, Any]) -> list[VariableResult]:
    """Resultados a renderizar, na ordem em que o armazenamento os devolve."""
    filtro = {k: v for k, v in (params.get("filtro") or {}).items() if v}
    return list(store.query(filtro))


def destino(params: dict[str, Any], padrao: str) -> Path:
    p = Path(params.get("path") or padrao)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def trilha(r: VariableResult) -> dict:
    at = r.audit_trail
    if isinstance(at, str):
        try:
            at = json.loads(at)
        except Exception:                                     # noqa: BLE001
            at = {}
    return at if isinstance(at, dict) else {}


def linha_plana(r: VariableResult) -> dict[str, Any]:
    """Uma linha tabular por resultado, com os escalares do registro promovidos."""
    at = trilha(r)
    linha: dict[str, Any] = {
        "domain_url": r.domain_url,
        "variable_name": r.variable_name,
        "value": _texto(r.value),
        "confidence": round(float(r.confidence), 6),
        "run_id": r.run_id,
        "protocol_version": r.protocol_version,
        "plugin_version": r.plugin_version,
        "computed_at": r.timestamp_utc.isoformat() if hasattr(r.timestamp_utc, "isoformat")
        else str(r.timestamp_utc),
    }
    for campo in ESCALARES:
        v = at.get(campo)
        linha[campo] = _texto(v) if v is not None else ""
    linha["densidade_sinalizacao"] = densidade(at)
    return linha


def densidade(at: dict) -> Any:
    """Sentencas sinalizadas sobre segmentos submetidos.

    A contagem bruta e confundida pelo comprimento do documento: politica extensa
    acumula sinalizacoes por ser extensa. Normalizar pelo denominador recupera parte
    do poder de ordenacao — em finalidade, de 62,9% para 75,3% de separacao entre
    documentos que a rotulagem manual distingue.

    O valor e ORDINAL. Serve para ordenar sitios entre si, e nao para afirmar quantas
    declaracoes o documento contem: a precisao do classificador em nivel de sentenca
    e de 31,4% em finalidade, de sorte que a contagem sinalizada nao e contagem de
    declaracoes. Dai o nome — densidade de SINALIZACAO, e nao de finalidades.
    """
    n, d = at.get("n_sentencas_sinalizadas"), at.get("n_segmentos_avaliados")
    try:
        n, d = int(n), int(d)
    except (TypeError, ValueError):
        return ""
    return round(n / d, 6) if d > 0 else ""


def _texto(v: Any) -> Any:
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


def dominio(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").split("/")[0]


def sentencas(r: VariableResult) -> Iterable[dict[str, Any]]:
    """Sentencas sinalizadas, com escore e posicao, para a lista de trabalho."""
    at = trilha(r)
    for s in (at.get("sentencas") or []):
        if isinstance(s, dict):
            yield s
