"""
Auditoria do manifest do FileSystemRepository — utilitário separado.

Fora do contrato ``RawRepository`` (que define apenas put/get/verify por
ref individual). Esta função opera sobre o manifest inteiro do diretório
raw e produz um relatório de integridade — útil para defesa em banca:
"rodei verify_manifest() e os N tar.gz conferem".

Modo de uso típico (CLI futura):

    from privacyscope.storage.manifest_audit import verify_manifest
    report = verify_manifest(Path("data/"))
    if not report.all_valid:
        for tar_name, problem in report.problems:
            print(f"  {tar_name}: {problem}")
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from privacyscope.storage.filesystem_repo import (
    RAW_SUBDIR,
    MANIFEST_NAME,
    AUDIT_LOG_NAME,
)


@dataclass
class ManifestAuditReport:
    """Resultado da auditoria do manifest.

    Attributes:
        manifest_path: Caminho absoluto do manifest auditado.
        total_entries: Linhas do manifest.
        verified: Entradas onde sha256 do arquivo confere com o registrado.
        missing: Entradas cujo arquivo não existe mais no disco.
        corrupted: Entradas onde sha256 diverge — adulteração detectada.
        manifest_sha256: Hash atual do manifest.
        audit_log_consistent: Se o último audit_log registra o hash atual do manifest.
        problems: Lista de (tar_filename, descrição) para inspeção manual.
    """

    manifest_path: Path
    total_entries: int = 0
    verified: int = 0
    missing: int = 0
    corrupted: int = 0
    manifest_sha256: Optional[str] = None
    audit_log_consistent: bool = False
    problems: list[tuple[str, str]] = field(default_factory=list)

    @property
    def all_valid(self) -> bool:
        return (
            self.missing == 0
            and self.corrupted == 0
            and self.audit_log_consistent
            and self.total_entries == self.verified
        )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(base_path: Path | str) -> ManifestAuditReport:
    """Audita o manifest de um diretório base de evidências.

    Para cada entrada do ``manifest.jsonl``:
        1. Verifica se o arquivo tar.gz existe.
        2. Recomputa SHA-256 e compara com o registrado.

    Adicionalmente verifica se o último evento do ``audit_log.jsonl``
    contém o hash atual do manifest — confirma que a cadeia em cascata
    está fechada.

    Args:
        base_path: diretório raiz do repositório (contém ``raw/``).

    Returns:
        ManifestAuditReport com contagens e lista de problemas.
    """
    base = Path(base_path)
    raw_dir = base / RAW_SUBDIR
    manifest_path = raw_dir / MANIFEST_NAME
    audit_log_path = raw_dir / AUDIT_LOG_NAME

    report = ManifestAuditReport(manifest_path=manifest_path)

    if not manifest_path.exists():
        report.problems.append(("", f"manifest não encontrado em {manifest_path}"))
        return report

    # 1) Verifica cada entrada do manifest
    for line_no, line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            report.problems.append(("", f"linha {line_no} ilegível: {e}"))
            continue

        report.total_entries += 1
        tar_name = entry.get("tar_filename")
        expected = entry.get("sha256")
        if not tar_name or not expected:
            report.problems.append((tar_name or "", f"linha {line_no}: campos ausentes"))
            continue

        tar_path = raw_dir / tar_name
        if not tar_path.exists():
            report.missing += 1
            report.problems.append((tar_name, "arquivo não encontrado"))
            continue

        actual = _sha256_file(tar_path)
        if actual != expected:
            report.corrupted += 1
            report.problems.append(
                (tar_name, f"hash divergente: esperado {expected[:16]}..., atual {actual[:16]}...")
            )
        else:
            report.verified += 1

    # 2) Hash atual do manifest + consistência do audit log
    report.manifest_sha256 = _sha256_file(manifest_path)
    if audit_log_path.exists():
        audit_lines = [
            l for l in audit_log_path.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
        if audit_lines:
            try:
                last = json.loads(audit_lines[-1])
                report.audit_log_consistent = (
                    last.get("manifest_sha256") == report.manifest_sha256
                )
                if not report.audit_log_consistent:
                    report.problems.append(
                        (
                            "",
                            f"audit_log[-1].manifest_sha256 = {last.get('manifest_sha256','?')[:16]}..., "
                            f"manifest atual = {report.manifest_sha256[:16]}...",
                        )
                    )
            except json.JSONDecodeError as e:
                report.problems.append(("", f"audit_log última linha ilegível: {e}"))

    return report


__all__ = ["ManifestAuditReport", "verify_manifest"]
