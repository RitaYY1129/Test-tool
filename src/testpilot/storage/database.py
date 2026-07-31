from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'document',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS environments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    base_url TEXT NOT NULL DEFAULT '',
                    headers_json TEXT NOT NULL DEFAULT '{}',
                    variables_json TEXT NOT NULL DEFAULT '{}',
                    secrets_encrypted TEXT NOT NULL DEFAULT '',
                    UNIQUE(project_id, name)
                );
                CREATE TABLE IF NOT EXISTS api_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS api_endpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL REFERENCES api_sources(id) ON DELETE CASCADE,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    module TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    definition_json TEXT NOT NULL,
                    UNIQUE(source_id, method, path)
                );
                CREATE TABLE IF NOT EXISTS test_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    endpoint_id INTEGER REFERENCES api_endpoints(id) ON DELETE SET NULL,
                    name TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'P1',
                    review_status TEXT NOT NULL DEFAULT 'draft',
                    definition_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS test_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
                    case_id INTEGER REFERENCES test_cases(id) ON DELETE SET NULL,
                    status TEXT NOT NULL,
                    elapsed_ms INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
                    html_path TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                    action TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                );
                """
            )
            self._ensure_column(db, "environments", "variables_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(db, "environments", "secrets_encrypted", "TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_project(self, name: str, mode: str = "document") -> int:
        with self.connect() as db:
            cur = db.execute("INSERT INTO projects(name, mode) VALUES (?, ?)", (name.strip(), mode))
            project_id = int(cur.lastrowid)
            db.execute(
                "INSERT INTO environments(project_id, name) VALUES (?, '测试环境')",
                (project_id,),
            )
            return project_id

    def list_projects(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY updated_at DESC, id DESC")]

    def list_project_overviews(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT p.*,
                   COUNT(DISTINCT s.id) AS source_count,
                   COUNT(DISTINCT e.module) AS module_count,
                   COUNT(DISTINCT e.id) AS endpoint_count,
                   COUNT(DISTINCT c.id) AS case_count
                   FROM projects p
                   LEFT JOIN api_sources s ON s.project_id=p.id
                   LEFT JOIN api_endpoints e ON e.source_id=s.id
                   LEFT JOIN test_cases c ON c.project_id=p.id
                   GROUP BY p.id ORDER BY p.updated_at DESC,p.id DESC"""
            )]

    def project_asset_tree(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT s.id AS source_id,s.name AS source_name,s.kind,
                   e.id AS endpoint_id,e.module,e.method,e.path,e.summary
                   FROM api_sources s
                   LEFT JOIN api_endpoints e ON e.source_id=s.id
                   WHERE s.project_id=?
                   ORDER BY s.id,e.module,e.path,e.method""", (project_id,)
            )
            return [dict(row) for row in rows]

    def delete_project(self, project_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def save_document(self, project_id: int, name: str, document, report) -> int:
        metadata = {
            "title": document.title,
            "version": document.version,
            "specification": document.specification,
            "base_urls": document.base_urls,
            "completeness": report.__dict__ if hasattr(report, "__dict__") else {
                key: getattr(report, key) for key in report.__slots__
            },
        }
        with self.connect() as db:
            cur = db.execute(
                "INSERT INTO api_sources(project_id,name,kind,metadata_json) VALUES (?,?,?,?)",
                (project_id, name, document.endpoints[0].source if document.endpoints else "openapi", json.dumps(metadata, ensure_ascii=False)),
            )
            source_id = int(cur.lastrowid)
            db.executemany(
                "INSERT INTO api_endpoints(source_id,method,path,module,summary,definition_json) VALUES (?,?,?,?,?,?)",
                [
                    (source_id, e.method, e.path, e.module, e.summary, json.dumps(e.to_dict(), ensure_ascii=False))
                    for e in document.endpoints
                ],
            )
            db.execute("UPDATE projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (project_id,))
            return source_id

    def list_endpoints(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT e.id,e.method,e.path,e.module,e.summary,e.definition_json,
                          s.id AS source_id,s.name AS source_name,s.kind AS source_kind
                   FROM api_endpoints e JOIN api_sources s ON s.id=e.source_id
                   WHERE s.project_id=? ORDER BY e.module,e.path,e.method""",
                (project_id,),
            )
            return [dict(row) for row in rows]

    def list_sources(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM api_sources WHERE project_id=? ORDER BY id", (project_id,)
            )]

    def delete_empty_sources(self, project_id: int) -> int:
        """Remove legacy imports that produced a source record with no endpoints."""
        with self.connect() as db:
            rows = db.execute(
                """SELECT s.id FROM api_sources s
                   LEFT JOIN api_endpoints e ON e.source_id=s.id
                   WHERE s.project_id=? GROUP BY s.id HAVING COUNT(e.id)=0""",
                (project_id,),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                db.executemany("DELETE FROM api_sources WHERE id=?", [(item,) for item in ids])
            return len(ids)

    def list_source_endpoints(self, source_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM api_endpoints WHERE source_id=? ORDER BY method,path", (source_id,)
            )]

    def list_environments(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM environments WHERE project_id=? ORDER BY id", (project_id,))]

    def save_environment(self, project_id: int, name: str, base_url: str, headers: dict,
                         variables: dict | None = None, secrets_encrypted: str = "") -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO environments(project_id,name,base_url,headers_json,variables_json,secrets_encrypted)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(project_id,name) DO UPDATE SET base_url=excluded.base_url,
                   headers_json=excluded.headers_json,variables_json=excluded.variables_json,
                   secrets_encrypted=excluded.secrets_encrypted""",
                (project_id, name.strip(), base_url.strip(), json.dumps(headers, ensure_ascii=False),
                 json.dumps(variables or {}, ensure_ascii=False), secrets_encrypted),
            )

    def add_manual_endpoint(self, project_id: int, definition: dict) -> int:
        with self.connect() as db:
            row = db.execute(
                "SELECT id FROM api_sources WHERE project_id=? AND kind='manual' ORDER BY id LIMIT 1", (project_id,)
            ).fetchone()
            if row:
                source_id = row["id"]
            else:
                source_id = int(db.execute(
                    "INSERT INTO api_sources(project_id,name,kind) VALUES (?,'手工接口','manual')", (project_id,)
                ).lastrowid)
            cur = db.execute(
                """INSERT INTO api_endpoints(source_id,method,path,module,summary,definition_json)
                   VALUES (?,?,?,?,?,?)""",
                (source_id, definition["method"], definition["path"], definition.get("module", "手工"),
                 definition.get("summary", ""), json.dumps(definition, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def update_endpoint(self, endpoint_id: int, definition: dict) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE api_endpoints SET method=?,path=?,module=?,summary=?,definition_json=? WHERE id=?""",
                (definition["method"], definition["path"], definition.get("module", "未分组"),
                 definition.get("summary", ""), json.dumps(definition, ensure_ascii=False), endpoint_id),
            )

    def delete_endpoint(self, endpoint_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM api_endpoints WHERE id=?", (endpoint_id,))

    def update_test_case(self, case_id: int, definition: dict) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE test_cases SET name=?,priority=?,review_status=?,definition_json=? WHERE id=?""",
                (definition["name"], definition.get("priority", "P1"), definition.get("review_status", "draft"),
                 json.dumps(definition, ensure_ascii=False), case_id),
            )

    def delete_test_case(self, case_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM test_cases WHERE id=?", (case_id,))

    def list_runs(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM test_runs WHERE project_id=? ORDER BY id DESC", (project_id,)
            )]

    def audit(self, project_id: int | None, action: str, details: dict | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit_logs(project_id,action,details_json) VALUES (?,?,?)",
                (project_id, action, json.dumps(details or {}, ensure_ascii=False)),
            )

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO app_settings(key,value) VALUES (?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, value)
            )

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def save_test_cases(self, project_id: int, cases: list[dict]) -> list[int]:
        ids: list[int] = []
        with self.connect() as db:
            for case in cases:
                cur = db.execute(
                    """INSERT INTO test_cases(project_id,endpoint_id,name,priority,review_status,definition_json)
                       VALUES (?,?,?,?,?,?)""",
                    (project_id, case.get("endpoint_id"), case["name"], case.get("priority", "P1"),
                     case.get("review_status", "draft"), json.dumps(case, ensure_ascii=False)),
                )
                ids.append(int(cur.lastrowid))
        return ids

    def list_test_cases(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM test_cases WHERE project_id=? ORDER BY id", (project_id,)
            )]

    def update_case_status(self, case_id: int, status: str) -> None:
        if status not in {"draft", "confirmed", "archived"}:
            raise ValueError("无效的用例状态")
        with self.connect() as db:
            db.execute("UPDATE test_cases SET review_status=? WHERE id=?", (status, case_id))

    def create_run(self, project_id: int) -> int:
        with self.connect() as db:
            cur = db.execute("INSERT INTO test_runs(project_id,status) VALUES (?,'running')", (project_id,))
            return int(cur.lastrowid)

    def save_result(self, run_id: int, case_id: int | None, result: dict) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO test_results(run_id,case_id,status,elapsed_ms,result_json) VALUES (?,?,?,?,?)",
                (run_id, case_id, result["status"], result.get("elapsed_ms", 0), json.dumps(result, ensure_ascii=False)),
            )

    def finish_run(self, run_id: int, summary: dict) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE test_runs SET status='completed',finished_at=CURRENT_TIMESTAMP,summary_json=? WHERE id=?",
                (json.dumps(summary, ensure_ascii=False), run_id),
            )

    def get_run_results(self, run_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT r.*,c.name FROM test_results r
                   LEFT JOIN test_cases c ON c.id=r.case_id WHERE r.run_id=? ORDER BY r.id""", (run_id,)
            )]

    def save_report(self, run_id: int, html_path: str, json_path: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO reports(run_id,html_path,json_path) VALUES (?,?,?)", (run_id, html_path, json_path))

    def list_reports(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT p.*,r.status,r.started_at,r.finished_at,r.summary_json
                   FROM reports p JOIN test_runs r ON r.id=p.run_id
                   WHERE r.project_id=? ORDER BY p.id DESC""", (project_id,)
            )]
