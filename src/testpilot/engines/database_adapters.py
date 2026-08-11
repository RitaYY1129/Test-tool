from __future__ import annotations

import importlib
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pymysql

from testpilot.engines.workflow_runner import WorkflowError, SqliteTestDatabase


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatabaseAdapter(ABC):
    backend = "unknown"

    @abstractmethod
    def query(self, statement: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict]: ...

    @abstractmethod
    def snapshot(self, observations: list[dict], variables: dict | None = None) -> dict: ...

    @abstractmethod
    def insert_fixture(self, fixture: dict) -> dict: ...

    @abstractmethod
    def delete_rows(self, action: dict, variables: dict) -> dict: ...


class DbApiAdapter(DatabaseAdapter):
    """Small DB-API adapter for PostgreSQL/MySQL without bundling drivers."""

    def __init__(self, backend: str, config: dict, read_only: bool = True):
        self.backend = backend.lower()
        self.config = dict(config)
        self.read_only = read_only
        self._driver = self._load_driver()

    def _load_driver(self):
        if self.backend == "mysql":
            return pymysql
        names = {"postgresql": ("psycopg", "psycopg2"), "postgres": ("psycopg", "psycopg2"), "mysql": ("mysql.connector", "pymysql")}.get(self.backend, ())
        for name in names:
            try:
                return importlib.import_module(name)
            except ImportError:
                continue
        raise WorkflowError(f"{self.backend} 适配器需要安装 DB-API 驱动：{', '.join(names)}")

    def _connect(self):
        if "dsn" in self.config:
            return self._driver.connect(self.config["dsn"])
        kwargs = {key: value for key, value in self.config.items() if key in {"host", "port", "user", "password", "database", "dbname"}}
        if self.backend == "mysql" and "dbname" in kwargs:
            kwargs["database"] = kwargs.pop("dbname")
        return self._driver.connect(**kwargs)

    def _validate_read(self, statement: str):
        if not statement.lstrip().lower().startswith(("select", "with", "show", "pragma")):
            raise WorkflowError("数据库观测只允许 SELECT/WITH/SHOW/PRAGMA")

    def query(self, statement: str, params=None) -> list[dict]:
        self._validate_read(statement)
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(statement, params or [])
            names = [item[0] for item in cursor.description or []]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def snapshot(self, observations: list[dict], variables: dict | None = None) -> dict:
        from testpilot.engines.variables import resolve
        return {str(item.get("name") or f"observation_{index + 1}"): self.query(str(resolve(item.get("query", ""), variables or {})), resolve(item.get("params") or [], variables or {})) for index, item in enumerate(observations)}

    def insert_fixture(self, fixture: dict) -> dict:
        if self.read_only:
            raise WorkflowError("当前数据库连接是只读的，不能准备夹具")
        table = str(fixture.get("table", "")); rows = fixture.get("rows") or []
        _safe_identifier(table)
        if not rows or not all(isinstance(row, dict) for row in rows):
            raise WorkflowError("夹具必须包含非空 rows 对象数组")
        columns = list(rows[0]); [ _safe_identifier(column) for column in columns ]
        marks = ",".join("%s" for _ in columns)
        sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({marks})"
        connection = self._connect(); ids = []
        try:
            cursor = connection.cursor()
            for row in rows:
                cursor.execute(sql, [row[column] for column in columns]); ids.append(getattr(cursor, "lastrowid", None))
            connection.commit()
            return {"table": table, "inserted": len(rows), "ids": ids}
        finally:
            connection.close()

    def delete_rows(self, action: dict, variables: dict) -> dict:
        if self.read_only:
            raise WorkflowError("当前数据库连接是只读的，不能执行补偿删除")
        from testpilot.engines.variables import resolve
        table = str(action.get("table", "")); where = resolve(action.get("where") or {}, variables)
        _safe_identifier(table)
        if not where or not all(_IDENTIFIER.fullmatch(str(key)) for key in where):
            raise WorkflowError("补偿删除必须提供安全的 where 字段")
        clauses = " AND ".join(f"{key}=%s" for key in where)
        connection = self._connect()
        try:
            cursor = connection.cursor(); cursor.execute(f"DELETE FROM {table} WHERE {clauses}", list(where.values())); connection.commit()
            return {"table": table, "deleted": cursor.rowcount, "where": where}
        finally:
            connection.close()


def create_database_adapter(backend: str, target_path: str, read_only: bool = True, config: dict | None = None) -> DatabaseAdapter:
    backend = backend.lower()
    if backend == "sqlite":
        return SqliteTestDatabase(target_path, read_only)
    return DbApiAdapter(backend, {**(config or {}), "dsn": target_path} if target_path and not config else (config or {}), read_only)


def _safe_identifier(value: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise WorkflowError(f"不安全的数据库标识符：{value}")
