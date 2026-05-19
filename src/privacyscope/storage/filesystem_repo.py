"""
FileSystemRepository — persistência local de RawEvidence com cadeia de custódia.

Implementa ``RawRepository`` (camada 3 — Evidência Bruta). Cada ``RawEvidence``
recebido é serializado num diretório temporário, empacotado em ``tar.gz``, e o
hash SHA-256 é registrado num manifest ``jsonl`` append-only. Um log de
auditoria paralelo registra o SHA-256 do manifest após cada escrita, fechando
a cadeia em cascata.

Padrões aderentes:
    - ABNT NBR ISO/IEC 27037:2013 — preservação de evidência digital
    - Casey (2011) — chain of custody na forense digital
    - Append-only / write-once para Raw Storage (imutabilidade do projeto)

Layout do ``base_path``::

    <base_path>/raw/
    ├── <domain_slug>__<run_id>__<ts>.tar.gz
    ├── <domain_slug>__<run_id>__<ts>.tar.gz
    ├── manifest.jsonl                  # uma linha JSON por put()
    └── audit_log.jsonl                 # hash do manifest após cada escrita

Layout interno de cada ``tar.gz``::

    <dirname>/
    ├── meta.json                       # canônico — reconstrói RawEvidence
    ├── html_root.html                  # se html_pages['/'] não-vazio
    ├── html_subpages/                  # se outras chaves de html_pages
    │   └── <path-slug>.html
    ├── headers.json                    # se headers não-vazio
    ├── network.json                    # se network_log não-vazio
    └── phases/                         # se cookies_by_phase OU phase_screenshots
        └── <phase_name>/
            ├── cookies.json
            └── screenshot.png

Arquivos só são criados se a evidência tem conteúdo correspondente.
Auditor abrindo o tar.gz vê **exatamente** o que foi capturado.

Atomicidade: o tar é escrito em ``<path>.partial``, depois renomeado
(rename é atômico em POSIX e em NTFS para arquivos no mesmo volume).
O manifest só recebe a linha **após** o rename + cálculo de hash.

Limitação consciente: não há file locking. MVP roda serial. Para
paralelização futura, adicionar ``portalocker`` ou similar.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Optional

from privacyscope.core.interfaces import RawRepository
from privacyscope.core.types import Domain, EvidenceRef, RawEvidence


# =============================================================================
# Constantes
# =============================================================================
RAW_SUBDIR = "raw"
MANIFEST_NAME = "manifest.jsonl"
AUDIT_LOG_NAME = "audit_log.jsonl"
META_FILENAME = "meta.json"
HTML_ROOT_FILENAME = "html_root.html"
HTML_SUBPAGES_DIR = "html_subpages"
HEADERS_FILENAME = "headers.json"
NETWORK_FILENAME = "network.json"
PHASES_DIR = "phases"
COOKIES_FILENAME = "cookies.json"
SCREENSHOT_FILENAME = "screenshot.png"

# Caracteres permitidos em nomes de arquivo (cross-platform: NTFS e POSIX).
# Reservados em NTFS: \ / : * ? " < > |
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


# =============================================================================
# Helpers
# =============================================================================
def _safe_slug(text: str, max_length: int = 80) -> str:
    """Slugifica string para uso seguro em path de arquivo, cross-platform."""
    s = _SAFE_NAME_RE.sub("_", text).strip("_.-")
    if not s:
        s = "_"
    return s[:max_length]


def _domain_slug(url: str) -> str:
    """Extrai host limpo da URL para usar no nome do tar."""
    host = url.replace("https://", "").replace("http://", "")
    host = host.split("/", 1)[0].rstrip("/").lower()
    return _safe_slug(host, max_length=60)


def _path_slug(path: str) -> str:
    """Slugifica path interno de subpágina (e.g. '/politica-privacidade')."""
    p = path.strip("/").replace("/", "__")
    return _safe_slug(p or "root", max_length=120)


def _ts_compact_utc() -> str:
    """Timestamp UTC em formato compacto, ordena lexicograficamente."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path: Path) -> str:
    """Calcula SHA-256 hex de arquivo. Streaming, sem carregar tudo em memória."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):  # 1 MB
            h.update(chunk)
    return h.hexdigest()


def _atomic_append_line(path: Path, line: str) -> None:
    """Append + fsync para garantir persistência da linha no manifest/log."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def _serialize_evidence_to_dir(evidence: RawEvidence, dest_dir: Path) -> None:
    """Escreve a RawEvidence no diretório ``dest_dir`` segundo o layout."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1) meta.json — TODOS os campos da RawEvidence exceto blobs (html_pages,
    #    phase_screenshots, screenshot). Esses voltam para arquivos separados.
    meta = evidence.model_dump(
        mode="json",
        exclude={"html_pages", "phase_screenshots", "screenshot"},
    )
    # screenshot principal: anotamos no meta se existe (para round-trip do get).
    meta["_has_screenshot"] = evidence.screenshot is not None
    (dest_dir / META_FILENAME).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 2) html_root.html
    root_html = evidence.html_pages.get("/")
    if root_html:
        (dest_dir / HTML_ROOT_FILENAME).write_bytes(root_html)

    # 3) html_subpages/<slug>.html
    subpages = {k: v for k, v in evidence.html_pages.items() if k != "/"}
    if subpages:
        sub_dir = dest_dir / HTML_SUBPAGES_DIR
        sub_dir.mkdir(exist_ok=True)
        index: dict[str, str] = {}
        for path_key, body in subpages.items():
            slug = _path_slug(path_key)
            # Evita colisão de slugs
            candidate = slug
            counter = 1
            while candidate in index:
                counter += 1
                candidate = f"{slug}_{counter}"
            index[candidate] = path_key
            (sub_dir / f"{candidate}.html").write_bytes(body)
        (sub_dir / "_index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 4) headers.json
    if evidence.headers:
        (dest_dir / HEADERS_FILENAME).write_text(
            json.dumps(evidence.headers, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # 5) network.json
    if evidence.network_log:
        (dest_dir / NETWORK_FILENAME).write_text(
            json.dumps(evidence.network_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # 6) phases/<name>/ — só se houver cookies OU screenshot para a fase
    all_phases = set(evidence.cookies_by_phase.keys()) | set(
        evidence.phase_screenshots.keys()
    )
    if all_phases:
        phases_dir = dest_dir / PHASES_DIR
        phases_dir.mkdir(exist_ok=True)
        for phase in sorted(all_phases):
            phase_dir = phases_dir / _safe_slug(phase, max_length=40)
            phase_dir.mkdir(exist_ok=True)
            cookies = evidence.cookies_by_phase.get(phase, [])
            if cookies:
                (phase_dir / COOKIES_FILENAME).write_text(
                    json.dumps(cookies, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            screenshot = evidence.phase_screenshots.get(phase)
            if screenshot:
                (phase_dir / SCREENSHOT_FILENAME).write_bytes(screenshot)

    # 7) screenshot "principal" (legacy field) — se presente, grava como
    #    screenshot.png na raiz do dir. Não duplica os por-fase.
    if evidence.screenshot:
        (dest_dir / SCREENSHOT_FILENAME).write_bytes(evidence.screenshot)


def _deserialize_evidence_from_dir(src_dir: Path) -> RawEvidence:
    """Reconstrói RawEvidence a partir do diretório extraído."""
    meta_path = src_dir / META_FILENAME
    if not meta_path.exists():
        raise ValueError(f"meta.json não encontrado em {src_dir}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    has_screenshot = meta.pop("_has_screenshot", False)

    # html_pages reconstrói de html_root + html_subpages
    html_pages: dict[str, bytes] = {}
    root_path = src_dir / HTML_ROOT_FILENAME
    if root_path.exists():
        html_pages["/"] = root_path.read_bytes()
    sub_dir = src_dir / HTML_SUBPAGES_DIR
    if sub_dir.exists():
        index_path = sub_dir / "_index.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for slug, original_path in index.items():
                f = sub_dir / f"{slug}.html"
                if f.exists():
                    html_pages[original_path] = f.read_bytes()
        else:
            # Fallback: usa slug como chave se _index.json não existir
            for f in sub_dir.glob("*.html"):
                html_pages[f.stem] = f.read_bytes()
    meta["html_pages"] = html_pages

    # phase_screenshots
    phase_screenshots: dict[str, bytes] = {}
    phases_dir = src_dir / PHASES_DIR
    if phases_dir.exists():
        for phase_dir in phases_dir.iterdir():
            if not phase_dir.is_dir():
                continue
            scr = phase_dir / SCREENSHOT_FILENAME
            if scr.exists():
                phase_screenshots[phase_dir.name] = scr.read_bytes()
    meta["phase_screenshots"] = phase_screenshots

    # screenshot principal (legacy)
    if has_screenshot:
        scr_main = src_dir / SCREENSHOT_FILENAME
        meta["screenshot"] = scr_main.read_bytes() if scr_main.exists() else None
    else:
        meta["screenshot"] = None

    return RawEvidence(**meta)


# =============================================================================
# FileSystemRepository
# =============================================================================
class FileSystemRepository(RawRepository):
    """Implementação de RawRepository com tar.gz + manifest.jsonl local.

    Args:
        base_path: Diretório raiz. ``data/raw/`` será criado dentro dele
            por convenção fixa (decisão de design D4).

    Métodos abstratos implementados:
        put, get, verify (conforme contrato em core/interfaces.py).
    """

    name: ClassVar[str] = "filesystem"
    version: ClassVar[str] = "0.1.0"

    def __init__(self, base_path: Path | str) -> None:
        self.base_path = Path(base_path)
        self.raw_dir = self.base_path / RAW_SUBDIR
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.raw_dir / MANIFEST_NAME
        self.audit_log_path = self.raw_dir / AUDIT_LOG_NAME

    # ------------------------------------------------------------------
    # put
    # ------------------------------------------------------------------
    def put(
        self,
        evidence: RawEvidence,
        run_id: str,
        *,
        protocol_version_hash: Optional[str] = None,
    ) -> EvidenceRef:
        """Empacota a evidência em tar.gz e registra no manifest.

        Note:
            ``protocol_version_hash`` é parâmetro adicional **opcional**,
            fora do contrato da ABC ``RawRepository.put()``. O contrato
            (evidence, run_id) -> EvidenceRef permanece honrado para qualquer
            chamada compatível. O kwarg-only protocol_version_hash existe
            para que o orquestrador (ainda a codar) possa anexar o hash do
            protocolo YAML ao manifest sem mudar a assinatura básica.
        """
        if not run_id:
            raise ValueError("run_id obrigatório")

        ts_str = _ts_compact_utc()
        domain_slug = _domain_slug(evidence.domain.url)
        run_slug = _safe_slug(run_id, max_length=40)
        tar_name = f"{ts_str}__{run_slug}__{domain_slug}.tar.gz"
        final_path = self.raw_dir / tar_name
        partial_path = final_path.with_suffix(".tar.gz.partial")

        # Diretório temporário para serialização (fora do raw_dir para não
        # poluir manifest se algo falhar).
        with tempfile.TemporaryDirectory(prefix="privacyscope_") as tmp:
            tmp_path = Path(tmp)
            content_dir_name = f"{domain_slug}__{run_slug}__{ts_str}"
            content_dir = tmp_path / content_dir_name
            _serialize_evidence_to_dir(evidence, content_dir)

            # Empacota em .partial
            with tarfile.open(partial_path, "w:gz") as tar:
                tar.add(content_dir, arcname=content_dir_name)

        # Rename atômico → arquivo final
        partial_path.replace(final_path)

        # Calcula hash do arquivo final
        sha256 = _sha256_file(final_path)
        created_at = datetime.now(timezone.utc)

        ref = EvidenceRef(
            path=str(final_path.resolve()),
            sha256=sha256,
            domain_url=evidence.domain.url,
            run_id=run_id,
            created_at=created_at,
        )

        # Manifest entry
        manifest_entry = {
            "tar_filename": tar_name,
            "sha256": sha256,
            "domain_url": evidence.domain.url,
            "run_id": run_id,
            "fetcher_name": evidence.fetcher_name,
            "created_at": created_at.isoformat(),
            "errors_count": len(evidence.errors),
            "protocol_version_hash": protocol_version_hash,
        }
        _atomic_append_line(
            self.manifest_path,
            json.dumps(manifest_entry, ensure_ascii=False),
        )

        # Audit log: recomputa hash do manifest e registra
        manifest_sha = _sha256_file(self.manifest_path)
        audit_entry = {
            "event": "manifest_updated",
            "manifest_sha256": manifest_sha,
            "tar_filename": tar_name,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_append_line(
            self.audit_log_path,
            json.dumps(audit_entry, ensure_ascii=False),
        )

        return ref

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------
    def get(self, ref: EvidenceRef) -> RawEvidence:
        """Extrai o tar.gz e reconstrói a RawEvidence (cheia, conforme D3).

        Raises:
            FileNotFoundError: se o arquivo apontado por ``ref.path`` não existir.
            ValueError: se hash divergir (chain of custody quebrada).
        """
        tar_path = Path(ref.path)
        if not tar_path.exists():
            raise FileNotFoundError(f"Evidência não encontrada: {tar_path}")

        # Verificação de integridade antes de extrair
        if not self.verify(ref):
            raise ValueError(
                f"Hash divergente para {tar_path.name}: cadeia de custódia "
                f"quebrada."
            )

        with tempfile.TemporaryDirectory(prefix="privacyscope_get_") as tmp:
            tmp_path = Path(tmp)
            with tarfile.open(tar_path, "r:gz") as tar:
                # Python 3.12+ exige filter; 3.11- não tem. Compatibilidade dupla.
                try:
                    tar.extractall(tmp_path, filter="data")
                except TypeError:
                    tar.extractall(tmp_path)
            # O tar contém um diretório único (content_dir_name)
            entries = list(tmp_path.iterdir())
            if not entries:
                raise ValueError(f"tar.gz vazio: {tar_path}")
            content_dir = entries[0]
            return _deserialize_evidence_from_dir(content_dir)

    # ------------------------------------------------------------------
    # verify
    # ------------------------------------------------------------------
    def verify(self, ref: EvidenceRef) -> bool:
        """Recomputa SHA-256 do tar.gz e compara com ``ref.sha256``."""
        tar_path = Path(ref.path)
        if not tar_path.exists():
            return False
        try:
            actual = _sha256_file(tar_path)
        except OSError:
            return False
        return actual == ref.sha256


__all__ = [
    "FileSystemRepository",
    "RAW_SUBDIR",
    "MANIFEST_NAME",
    "AUDIT_LOG_NAME",
]
