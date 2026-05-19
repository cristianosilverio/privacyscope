"""
SQLiteResultStore — ResultStore concreto em SQLite long-format.

Implementa ``ResultStore`` (camada 5 — Resultados Estruturados). Cada
``VariableResult`` vira uma linha na tabela ``variables``. O formato long
(uma variável por linha) é deliberadamente escolhido em vez de wide
(uma variável por coluna):

    - Adicionar variável nova = adicionar linhas, sem ALTER TABLE.
    - Queries analíticas (frequência, kappa, F1 por variável) ficam triviais.
    - Auditoria por VariableResult preserva audit_trail individual.

Schema versionado via tabela ``schema_version``. Migrações futuras adicionam
INSERT na tabela + script de upgrade.

Aderente a:
    - Wilson et al. (2017): boas práticas de reprodutibilidade computacional
      (arquivo .sqlite versionado junto ao TCC).
    - Open/Closed: novo VariableTest produz VariableResult; este store o
      persiste sem mudança de código.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Iterable, Iterator, Optional

from privacyscope.core.interfaces import ResultStore
from privacyscope.core.types import VariableResult


# =============================================================================
# Schema
# =============================================================================
SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    protocol_version TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    sample_size INTEGER,
    errors_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS variables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    protocol_version TEXT NOT NULL,
    domain_url TEXT NOT NULL,
    variable_name TEXT NOT NULL,
    value TEXT,
    confidence REAL,
    audit_trail_json TEXT,
    plugin_version TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE(protocol_version, run_id, variable_name, domain_url)
);

CREATE INDEX IF NOT EXISTS idx_variables_run ON variables(run_id);
CREATE INDEX IF NOT EXISTS idx_variables_domain ON variables(domain_url);
CREATE INDEX IF NOT EXISTS idx_variables_name ON variables(variable_name);
"""


# =============================================================================
# SQLiteResultStore
# =============================================================================
class SQLiteResultStore(ResultStore):
    """ResultStore que persiste VariableResult em SQLite local.

    Args:
        db_path: Caminho do arquivo .sqlite. Pasta-pai criada se necessário.

    Notes:
        - Conexão pertence à instância. Não thread-safe; cada thread/asyncio
          worker deve ter sua própria instância OU usar locks externos.
        - ``upsert`` é INSERT OR REPLACE na UNIQUE (protocol_version, run_id,
          variable_name, domain_url) — re-execução sob mesma chave sobrescreve,
          conforme contrato da ABC.
        - SQLite tem WAL desabilitado por default; o framework MVP roda serial.
    """

    name: ClassVar[str] = "sqlite"
    version: ClassVar[str] = "0.1.0"

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _init_schema(self) -> None:
        """Cria tabelas e registra versão atual se ainda não houver."""
        with self._tx() as cur:
            cur.executescript(SCHEMA_SQL)
            cur.execute("SELECT MAX(version) FROM schema_version")
            row = cur.fetchone()
            if row[0] is None:
                cur.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
                )

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        """Context manager para transação. Commita ou rollback."""
        if self._conn is None:
            raise RuntimeError("ResultStore fechado")
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    # ------------------------------------------------------------------
    # Run lifecycle (não está na ABC mas é útil para metadados de execução)
    # ------------------------------------------------------------------
    def begin_run(
        self,
        run_id: str,
        *,
        protocol_version: str,
        sample_size: int,
    ) -> None:
        """Registra início de um run. Idempotente (INSERT OR REPLACE)."""
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO runs
                  (run_id, protocol_version, started_at, sample_size, errors_count)
                VALUES (?, ?, ?, ?, 0)
                """,
                (run_id, protocol_version, datetime.now(timezone.utc).isoformat(), sample_size),
            )

    def finish_run(self, run_id: str, *, errors_count: int = 0) -> None:
        """Marca fim do run e atualiza contagem de erros."""
        with self._tx() as cur:
            cur.execute(
                "UPDATE runs SET completed_at = ?, errors_count = ? WHERE run_id = ?",
                (datetime.now(timezone.utc).isoformat(), errors_count, run_id),
            )

    # ------------------------------------------------------------------
    # ABC methods
    # ------------------------------------------------------------------
    def upsert(self, result: VariableResult) -> None:
        """Insere ou substitui o VariableResult pela chave natural."""
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO variables
                  (run_id, protocol_version, domain_url, variable_name,
                   value, confidence, audit_trail_json, plugin_version, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    result.protocol_version,
                    result.domain_url,
                    result.variable_name,
                    json.dumps(result.value, ensure_ascii=False),
                    result.confidence,
                    json.dumps(result.audit_trail, ensure_ascii=False),
                    result.plugin_version,
                    result.timestamp_utc.isoformat(),
                ),
            )

    def query(self, filter: dict[str, Any]) -> Iterable[VariableResult]:
        """Retorna VariableResult que satisfazem o filtro.

        Args:
            filter: chaves aceitas — 'variable_name', 'protocol_version',
                'run_id', 'domain_url'. Filtros adicionais ignorados com
                aviso silencioso (compatibilidade futura).
        """
        if self._conn is None:
            raise RuntimeError("ResultStore fechado")

        allowed = {"variable_name", "protocol_version", "run_id", "domain_url"}
        conditions = []
        values = []
        for key, val in filter.items():
            if key not in allowed:
                continue
            conditions.append(f"{key} = ?")
            values.append(val)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = (
            "SELECT run_id, protocol_version, domain_url, variable_name, value, "
            "confidence, audit_trail_json, plugin_version, computed_at FROM variables"
            + where
            + " ORDER BY computed_at ASC"
        )

        cur = self._conn.cursor()
        try:
            for row in cur.execute(sql, values):
                yield VariableResult(
                    run_id=row[0],
                    protocol_version=row[1],
                    domain_url=row[2],
                    variable_name=row[3],
                    value=json.loads(row[4]),
                    confidence=row[5],
                    audit_trail=json.loads(row[6]) if row[6] else {},
                    plugin_version=row[7],
                    timestamp_utc=datetime.fromisoformat(row[8]),
                )
        finally:
            cur.close()

    def close(self) -> None:
        """Fecha a conexão SQLite. Idempotente."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


__all__ = ["SQLiteResultStore", "SCHEMA_VERSION", "SCHEMA_SQL"]
