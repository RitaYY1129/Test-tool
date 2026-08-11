from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DatabaseObservationError(RuntimeError):
    pass


def inspect_sqlite_database(target_path: str | Path, read_only: bool = True) -> dict[str, Any]:
    """Return a safe schema snapshot and health status for a SQLite test DB."""
    path = Path(target_path).expanduser().resolve()
    if not path.is_file():
        raise DatabaseObservationError(f"SQLite 测试库不存在：{path}")
    uri = f"file:{path.as_posix()}?mode=ro" if read_only else str(path)
    connection = sqlite3.connect(uri, uri=read_only)
    try:
        connection.row_factory = sqlite3.Row
        tables = []
        for row in connection.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            name = str(row["name"])
            columns = [dict(item) for item in connection.execute(f'PRAGMA table_info("{name.replace(chr(34), chr(34) * 2)}")')]
            tables.append({"name": name, "type": row["type"], "columns": columns})
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return {"backend": "sqlite", "target": str(path), "read_only": read_only, "status": "healthy" if integrity == "ok" else "warning", "integrity": integrity, "tables": tables}
    finally:
        connection.close()


def execute_read_only_query(target_path: str | Path, statement: str, params: list[Any] | None = None) -> list[dict]:
    normalized = statement.lstrip().lower()
    if not (normalized.startswith("select") or normalized.startswith("with") or normalized.startswith("pragma")):
        raise DatabaseObservationError("只读观测只允许 SELECT/WITH/PRAGMA")
    snapshot = inspect_sqlite_database(target_path, read_only=True)
    connection = sqlite3.connect(f"file:{Path(target_path).expanduser().resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(statement, params or [])]
    finally:
        connection.close()
