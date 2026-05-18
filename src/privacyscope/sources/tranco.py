"""
TrancoSource — plugin de Ingestão baseado na Tranco List.

A Tranco List (Le Pochat et al., 2019) é um ranking de domínios mantido pela
KU Leuven, agregado a partir de Cisco Umbrella, Cloudflare Radar, Majestic e
Farsight, com versionamento por identificador estável. Cada `list_id` é
imutável: o mesmo `list_id` sempre devolve o mesmo conteúdo. Essa propriedade
é o que torna a Tranco adequada como fonte amostral reprodutível em pesquisa
revisada por pares.

Referência:
    LE POCHAT, V.; VAN GOETHEM, T.; TAJALIZADEHKHOOB, S.; KORCZYŃSKI, M.;
    JOOSEN, W. Tranco: A research-oriented top sites ranking hardened against
    manipulation. NDSS 2019.

Uso típico no protocol.yaml:

    sources:
      - name: tranco
        params:
          list_id: "Z2X9X"
          top_n: 100000
          tld_filters:
            - ".gov.br"
            - ".com.br"
            - ".org.br"

Política de cache:
    O CSV é baixado uma vez por (list_id, top_n) e armazenado em
    ``data/raw/tranco/{list_id}_top{top_n}.csv.gz``. Como a Tranco indexa
    listas por ID imutável, o cache nunca invalida.

Cadeia de custódia da entrada:
    Junto ao CSV, gravamos um manifest paralelo
    ``{list_id}_top{top_n}.manifest.json`` com SHA-256, byte_size, URL de
    origem e timestamp UTC do download. O orquestrador anexa este manifest
    ao audit_log da execução, dando rastreabilidade do dado de entrada.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Iterator

import httpx
import tldextract

from privacyscope.core.interfaces import SampleSource
from privacyscope.core.types import Domain, utc_now

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------
TRANCO_DOWNLOAD_URL = "https://tranco-list.eu/download/{list_id}/{top_n}"
DEFAULT_TOP_N = 1_000_000
CACHE_SUBDIR = "tranco"
HTTP_TIMEOUT_S = 60.0


# -----------------------------------------------------------------------------
# Helper privado: download + cache + manifest
# -----------------------------------------------------------------------------
def _cache_paths(cache_root: Path, list_id: str, top_n: int) -> tuple[Path, Path]:
    """Calcula os paths do arquivo cacheado e do manifest paralelo."""
    base = cache_root / CACHE_SUBDIR
    base.mkdir(parents=True, exist_ok=True)
    csv_path = base / f"{list_id}_top{top_n}.csv.gz"
    manifest_path = base / f"{list_id}_top{top_n}.manifest.json"
    return csv_path, manifest_path


#: Magic number do formato GZIP, RFC 1952 §2.3.1. Sempre os dois primeiros bytes.
GZIP_MAGIC = b"\x1f\x8b"


def _download_and_cache(list_id: str, top_n: int, cache_root: Path) -> Path:
    """Baixa a lista da Tranco e cacheia localmente; retorna o path do CSV.gz.

    Política:
        - Cache imutável: se o arquivo + manifest já existem, retorna direto.
        - Storage normalizado: o cache no disco está SEMPRE em formato gzip,
          independentemente de o servidor entregar gzip ou texto plain.
        - Detecção de formato por magic bytes (GZIP_MAGIC = ``\\x1f\\x8b``)
          após o download, antes de promover o arquivo temporário a cache
          definitivo. Não confia em Content-Encoding/Content-Type — esses
          podem ser alterados por proxies, CDN ou cabeçalhos de requisição.
        - SHA-256 é computado sobre o ARQUIVO FINAL no disco (o mesmo que
          a verificação de cache vai recomputar depois). Manifest preserva
          também ``received_as_gzip`` para rastreabilidade de proveniência.

    Args:
        list_id: identificador da lista na Tranco.
        top_n: tamanho da lista a baixar (1 a 1_000_000).
        cache_root: raiz do diretório de cache (tipicamente ``data/raw``).

    Returns:
        Path para o arquivo ``.csv.gz`` cacheado (sempre gzip).

    Raises:
        httpx.HTTPError: falha no download (4xx/5xx, timeout, conexão).
        OSError: falha de I/O ao gravar cache.
    """
    csv_path, manifest_path = _cache_paths(cache_root, list_id, top_n)

    if csv_path.exists() and manifest_path.exists():
        logger.info("Tranco cache hit: %s", csv_path)
        return csv_path

    url = TRANCO_DOWNLOAD_URL.format(list_id=list_id, top_n=top_n)
    logger.info("Baixando Tranco list_id=%s top_n=%s de %s", list_id, top_n, url)

    # Etapa 1: baixar para arquivo temporário usando iter_raw().
    # iter_raw() entrega bytes EXATAMENTE como vieram pela rede; iter_bytes()
    # faria descompactação automática ao detectar Content-Encoding: gzip.
    tmp_path = csv_path.with_suffix(csv_path.suffix + ".partial")
    received_bytes = 0
    try:
        with httpx.stream("GET", url, timeout=HTTP_TIMEOUT_S, follow_redirects=True) as resp:
            resp.raise_for_status()
            with tmp_path.open("wb") as fh:
                for chunk in resp.iter_raw(chunk_size=64 * 1024):
                    fh.write(chunk)
                    received_bytes += len(chunk)

        # Etapa 2: detectar formato real recebido por magic bytes.
        with tmp_path.open("rb") as fh:
            magic = fh.read(2)
        received_as_gzip = magic == GZIP_MAGIC

        if received_as_gzip:
            # Caminho quente: servidor entregou gzip. Rename atômico para final.
            tmp_path.replace(csv_path)
            logger.debug("Tranco entregou gzip; cache armazenado sem recompressão.")
        else:
            # Caminho frio: servidor entregou plain. Recomprime para o formato canônico.
            logger.warning(
                "Tranco entregou plain text (sem gzip); recomprimindo para o cache. "
                "Verifique configuração de CDN/proxy se isso persistir."
            )
            with tmp_path.open("rb") as src_fh, gzip.open(csv_path, "wb") as dst_fh:
                shutil.copyfileobj(src_fh, dst_fh)
    finally:
        # Garante limpeza do .partial em qualquer caso (sucesso ou exceção).
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    # Etapa 3: hash e tamanho do arquivo FINAL no disco — base da verificação.
    final_bytes = csv_path.read_bytes()
    sha256 = hashlib.sha256(final_bytes).hexdigest()
    stored_size = len(final_bytes)

    # Etapa 4: manifest completo, com proveniência da coleta.
    manifest = {
        "list_id": list_id,
        "top_n": top_n,
        "source_url": url,
        "sha256": sha256,
        "byte_size": stored_size,
        "received_bytes": received_bytes,
        "received_as_gzip": received_as_gzip,
        "stored_as_gzip": True,
        "downloaded_at_utc": utc_now().isoformat(),
        "cache_path": str(csv_path),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(
        "Tranco cacheada: received=%d bytes (gzip=%s), stored=%d bytes, sha256=%s",
        received_bytes, received_as_gzip, stored_size, sha256[:16],
    )
    return csv_path


# -----------------------------------------------------------------------------
# Plugin
# -----------------------------------------------------------------------------
class TrancoSource(SampleSource):
    """Fonte amostral baseada na Tranco List.

    Implementação concreta de SampleSource. Aceita filtros de TLD por lista
    de sufixos (ex.: ``[".gov.br", ".com.br"]``) e devolve Domains com rank
    populado a partir do ranque da Tranco.

    Atributos de classe:
        name: ``"tranco"`` — identificador no protocol.yaml.
        version: versão do plugin.

    Args do construtor:
        cache_root: raiz do diretório de cache local. Default ``Path("data/raw")``.
    """

    name: ClassVar[str] = "tranco"
    version: ClassVar[str] = "0.1.0"

    def __init__(self, cache_root: Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root is not None else Path("data/raw")

    # ------------------------------------------------------------------
    # Validação de params
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_params(params: dict[str, Any]) -> tuple[str, int, list[str]]:
        """Extrai e valida os params do protocolo. Levanta ValueError em falha."""
        list_id = params.get("list_id")
        if not isinstance(list_id, str) or not list_id.strip():
            raise ValueError(
                "TrancoSource exige params['list_id'] (string não-vazia). "
                "Gere uma lista em https://tranco-list.eu e fixe o ID no protocol.yaml."
            )
        list_id = list_id.strip()

        top_n = params.get("top_n", DEFAULT_TOP_N)
        if not isinstance(top_n, int) or not (1 <= top_n <= 1_000_000):
            raise ValueError(
                f"TrancoSource exige params['top_n'] inteiro em [1, 1_000_000]; recebido: {top_n!r}"
            )

        tld_filters = params.get("tld_filters", [])
        if not isinstance(tld_filters, list):
            raise ValueError(
                f"TrancoSource exige params['tld_filters'] como lista; recebido: {type(tld_filters).__name__}"
            )
        for f in tld_filters:
            if not isinstance(f, str) or not f.startswith("."):
                raise ValueError(
                    f"tld_filters: cada entrada deve ser string iniciando com '.' (ex.: '.gov.br'); "
                    f"recebido: {f!r}"
                )
        # normalizar para lowercase, manter ordem para audit determinístico
        tld_filters = [f.lower() for f in tld_filters]

        return list_id, top_n, tld_filters

    # ------------------------------------------------------------------
    # Match de filtro
    # ------------------------------------------------------------------
    @staticmethod
    def _matches_tld_filters(domain_str: str, tld_filters: list[str]) -> bool:
        """Verifica se o domínio termina em algum dos sufixos do filtro.

        Lista vazia = sem filtro (passa tudo).
        """
        if not tld_filters:
            return True
        d = domain_str.lower()
        return any(d.endswith(suffix) for suffix in tld_filters)

    # ------------------------------------------------------------------
    # Iteração principal
    # ------------------------------------------------------------------
    def list_domains(self, params: dict[str, Any]) -> Iterator[Domain]:
        """Itera sobre Domains produzidos pela Tranco filtrada.

        Args:
            params: dict do protocolo com chaves ``list_id`` (obrigatória),
                ``top_n`` (opcional, default 1_000_000), ``tld_filters``
                (opcional, default []).

        Yields:
            Domain: cada domínio que passa pelos filtros, na ordem do ranque.
        """
        list_id, top_n, tld_filters = self._validate_params(params)

        csv_path = _download_and_cache(list_id, top_n, self.cache_root)
        extract = tldextract.TLDExtract(cache_dir=str(self.cache_root / "tldextract_cache"))

        emitted = 0
        skipped_filter = 0
        skipped_bad = 0

        with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if len(row) < 2:
                    skipped_bad += 1
                    continue
                try:
                    rank = int(row[0])
                except ValueError:
                    skipped_bad += 1
                    continue
                domain_str = row[1].strip().lower()
                if not domain_str:
                    skipped_bad += 1
                    continue

                if not self._matches_tld_filters(domain_str, tld_filters):
                    skipped_filter += 1
                    continue

                suffix = extract(domain_str).suffix  # ex.: "gov.br"
                tld_value = "." + suffix if suffix else ".unknown"

                yield Domain(
                    url=f"https://{domain_str}",
                    tld=tld_value,
                    source_name=self.name,
                    rank=rank,
                    stratum=None,  # sampler atribui depois
                )
                emitted += 1

        logger.info(
            "TrancoSource finalizou: emitidos=%d filtrados=%d invalidos=%d filters=%s",
            emitted, skipped_filter, skipped_bad, tld_filters,
        )


__all__ = ["TrancoSource"]
