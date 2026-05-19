"""Persistência: Raw Repository (evidência bruta) e Result Store (resultados)."""

from privacyscope.storage.filesystem_repo import FileSystemRepository
from privacyscope.storage.sqlite_store import SQLiteResultStore

__all__ = ["FileSystemRepository", "SQLiteResultStore"]
