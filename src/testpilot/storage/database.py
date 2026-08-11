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
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
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
            self._apply_migrations(db)

    @staticmethod
    def _apply_migrations(db: sqlite3.Connection) -> None:
        """Apply additive database migrations in order.

        The original application used CREATE TABLE IF NOT EXISTS plus a couple
        of ad-hoc columns.  Keeping a numbered migration ledger makes future
        route-A additions safe for existing desktop installations.
        """
        current = db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]
        migrations = {
            1: """
                CREATE TABLE IF NOT EXISTS source_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    root_path TEXT NOT NULL,
                    framework TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_id, root_path)
                );
                CREATE TABLE IF NOT EXISTS source_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_project_id INTEGER NOT NULL REFERENCES source_projects(id) ON DELETE CASCADE,
                    revision_key TEXT NOT NULL,
                    file_count INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_project_id, revision_key)
                );
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_project_id INTEGER NOT NULL REFERENCES source_projects(id) ON DELETE CASCADE,
                    revision_id INTEGER REFERENCES source_revisions(id) ON DELETE SET NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    analyzer TEXT NOT NULL DEFAULT 'builtin',
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS source_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision_id INTEGER NOT NULL REFERENCES source_revisions(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(revision_id, path)
                );
                CREATE TABLE IF NOT EXISTS code_symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
                    symbol_type TEXT NOT NULL,
                    qualified_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER NOT NULL DEFAULT 0,
                    line_end INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS code_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
                    source_symbol TEXT NOT NULL,
                    target_symbol TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    file_path TEXT NOT NULL DEFAULT '',
                    line_start INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS analysis_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
                    evidence_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER NOT NULL DEFAULT 0,
                    line_end INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
            """,
            2: """
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    source_analysis_run_id INTEGER REFERENCES analysis_runs(id) ON DELETE SET NULL,
                    name TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'draft',
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    step_order INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(workflow_id, step_order)
                );
                CREATE TABLE IF NOT EXISTS db_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    backend TEXT NOT NULL DEFAULT 'sqlite',
                    target_path TEXT NOT NULL,
                    read_only INTEGER NOT NULL DEFAULT 1,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    secrets_encrypted TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_id, name)
                );
                CREATE TABLE IF NOT EXISTS test_fixtures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    workflow_id INTEGER REFERENCES workflows(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    review_status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    db_connection_id INTEGER REFERENCES db_connections(id) ON DELETE SET NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS workflow_step_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
                    step_id INTEGER REFERENCES workflow_steps(id) ON DELETE SET NULL,
                    step_order INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    elapsed_ms INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS workflow_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER REFERENCES workflow_runs(id) ON DELETE CASCADE,
                    action TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """,
            3: """
                CREATE TABLE IF NOT EXISTS workflow_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_run_id INTEGER NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
                    html_path TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """,
            4: """
                CREATE TABLE IF NOT EXISTS data_flow_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    source_analysis_run_id INTEGER REFERENCES analysis_runs(id) ON DELETE SET NULL,
                    workflow_id INTEGER REFERENCES workflows(id) ON DELETE SET NULL,
                    name TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'draft',
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS data_flow_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL REFERENCES data_flow_models(id) ON DELETE CASCADE,
                    node_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'unknown',
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(model_id, node_key)
                );
                CREATE TABLE IF NOT EXISTS data_flow_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL REFERENCES data_flow_models(id) ON DELETE CASCADE,
                    source_key TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    definition_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS state_invariants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    workflow_id INTEGER REFERENCES workflows(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    review_status TEXT NOT NULL DEFAULT 'draft'
                );
            """,
            5: """
                CREATE TABLE IF NOT EXISTS ai_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    route TEXT NOT NULL DEFAULT 'route_a',
                    environment_id INTEGER REFERENCES environments(id) ON DELETE SET NULL,
                    model_provider TEXT NOT NULL DEFAULT 'rule_based',
                    permission_policy_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS ai_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    redacted_content TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS ai_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    schema_version TEXT NOT NULL DEFAULT '1.0',
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    review_status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS ai_evidence_refs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id INTEGER NOT NULL REFERENCES ai_artifacts(id) ON DELETE CASCADE,
                    evidence_kind TEXT NOT NULL,
                    locator TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    confidence TEXT NOT NULL DEFAULT 'inferred'
                );
                CREATE TABLE IF NOT EXISTS ai_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
                    artifact_id INTEGER REFERENCES ai_artifacts(id) ON DELETE SET NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewer TEXT NOT NULL DEFAULT 'human',
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    decided_at TEXT
                );
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
                    approval_id INTEGER REFERENCES ai_approvals(id) ON DELETE SET NULL,
                    tool_name TEXT NOT NULL,
                    risk_level TEXT NOT NULL DEFAULT 'low',
                    arguments_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'blocked',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """,
            6: """
                CREATE TABLE IF NOT EXISTS db_schema_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    db_connection_id INTEGER REFERENCES db_connections(id) ON DELETE SET NULL,
                    backend TEXT NOT NULL DEFAULT 'sqlite',
                    target_fingerprint TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'healthy',
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """,
            7: """
                ALTER TABLE reports ADD COLUMN report_type TEXT NOT NULL DEFAULT '接口契约报告';
                ALTER TABLE reports ADD COLUMN route TEXT NOT NULL DEFAULT 'route_b';
                ALTER TABLE reports ADD COLUMN environment TEXT NOT NULL DEFAULT '';
                ALTER TABLE workflow_reports ADD COLUMN report_type TEXT NOT NULL DEFAULT '业务流程报告';
                ALTER TABLE workflow_reports ADD COLUMN route TEXT NOT NULL DEFAULT 'route_a';
                ALTER TABLE workflow_reports ADD COLUMN environment TEXT NOT NULL DEFAULT '';
            """,
            8: """
                CREATE TABLE IF NOT EXISTS workflow_traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
                    trace_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    definition_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS workflow_trace_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id INTEGER NOT NULL REFERENCES workflow_traces(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'observed',
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    data_json TEXT NOT NULL DEFAULT '{}'
                );
            """,
            9: """
                CREATE TABLE IF NOT EXISTS evidence_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    report_type TEXT NOT NULL,
                    route TEXT NOT NULL DEFAULT 'combined',
                    environment TEXT NOT NULL DEFAULT '',
                    html_path TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """,
        }
        for version in sorted(migrations):
            if version <= current:
                continue
            db.executescript(migrations[version])
            db.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))

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

    def save_source_analysis(self, project_id: int, analysis: dict, source_id: int | None = None) -> int:
        """Persist a route-A source snapshot and conservative analysis evidence.

        Source contents are never copied into SQLite.  Only hashes, relative
        paths, symbols, edges and line-based evidence are stored so projects
        containing proprietary code remain local and auditable.
        """
        root_path = str(analysis["root_path"])
        files = analysis.get("files") or []
        revision = analysis.get("revision") or {}
        framework = str(analysis.get("framework") or "unknown")
        with self.connect() as db:
            db.execute(
                """INSERT INTO source_projects(project_id,root_path,framework,name,metadata_json)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(project_id,root_path) DO UPDATE SET framework=excluded.framework,
                   name=excluded.name,metadata_json=excluded.metadata_json,updated_at=CURRENT_TIMESTAMP""",
                (project_id, root_path, framework, str(analysis.get("name") or Path(root_path).name),
                 json.dumps(analysis.get("metadata") or {}, ensure_ascii=False)),
            )
            source_project_id = int(db.execute(
                "SELECT id FROM source_projects WHERE project_id=? AND root_path=?", (project_id, root_path)
            ).fetchone()[0])
            db.execute(
                """INSERT INTO source_revisions(source_project_id,revision_key,file_count,content_hash,metadata_json)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(source_project_id,revision_key) DO UPDATE SET file_count=excluded.file_count,
                   content_hash=excluded.content_hash,metadata_json=excluded.metadata_json""",
                (source_project_id, str(revision.get("revision_key") or revision.get("content_hash") or "unknown"),
                 len(files), str(revision.get("content_hash") or ""),
                 json.dumps(revision.get("metadata") or {}, ensure_ascii=False)),
            )
            revision_id = int(db.execute(
                "SELECT id FROM source_revisions WHERE source_project_id=? AND revision_key=?",
                (source_project_id, str(revision.get("revision_key") or revision.get("content_hash") or "unknown")),
            ).fetchone()[0])
            db.execute("DELETE FROM source_files WHERE revision_id=?", (revision_id,))
            db.executemany(
                """INSERT INTO source_files(revision_id,path,language,size_bytes,content_hash,metadata_json)
                   VALUES (?,?,?,?,?,?)""",
                [(revision_id, str(item.get("path", "")), str(item.get("language", "")),
                  int(item.get("size_bytes", 0)), str(item.get("content_hash", "")),
                  json.dumps(item.get("metadata") or {}, ensure_ascii=False)) for item in files],
            )
            cur = db.execute(
                """INSERT INTO analysis_runs(source_project_id,revision_id,status,analyzer,finished_at,summary_json)
                   VALUES (?,?,?,?,CURRENT_TIMESTAMP,?)""",
                (source_project_id, revision_id, "completed", str(analysis.get("analyzer") or "builtin"),
                 json.dumps(analysis.get("summary") or {}, ensure_ascii=False)),
            )
            analysis_run_id = int(cur.lastrowid)
            db.executemany(
                """INSERT INTO code_symbols(analysis_run_id,symbol_type,qualified_name,file_path,line_start,line_end,metadata_json)
                   VALUES (?,?,?,?,?,?,?)""",
                [(analysis_run_id, str(item.get("symbol_type", "unknown")), str(item.get("qualified_name", "")),
                  str(item.get("file_path", "")), int(item.get("line_start", 0)), int(item.get("line_end", 0)),
                  json.dumps(item.get("metadata") or {}, ensure_ascii=False)) for item in analysis.get("symbols", [])],
            )
            db.executemany(
                """INSERT INTO code_edges(analysis_run_id,source_symbol,target_symbol,edge_type,file_path,line_start,metadata_json)
                   VALUES (?,?,?,?,?,?,?)""",
                [(analysis_run_id, str(item.get("source_symbol", "")), str(item.get("target_symbol", "")),
                  str(item.get("edge_type", "unknown")), str(item.get("file_path", "")), int(item.get("line_start", 0)),
                  json.dumps(item.get("metadata") or {}, ensure_ascii=False)) for item in analysis.get("edges", [])],
            )
            db.executemany(
                """INSERT INTO analysis_evidence(analysis_run_id,evidence_type,file_path,line_start,line_end,content_hash,details_json)
                   VALUES (?,?,?,?,?,?,?)""",
                [(analysis_run_id, str(item.get("evidence_type", "unknown")), str(item.get("file_path", "")),
                  int(item.get("line_start", 0)), int(item.get("line_end", item.get("line_start", 0))),
                  str(item.get("content_hash", "")), json.dumps(item.get("details") or {}, ensure_ascii=False))
                 for item in analysis.get("evidence", [])],
            )
            if source_id is not None:
                source_row = db.execute(
                    "SELECT metadata_json FROM api_sources WHERE id=?", (source_id,)
                ).fetchone()
                source_metadata = {}
                if source_row:
                    try:
                        source_metadata = json.loads(source_row[0] or "{}")
                    except (TypeError, ValueError):
                        source_metadata = {}
                source_metadata["analysis_run_id"] = analysis_run_id
                db.execute(
                    "UPDATE api_sources SET metadata_json=? WHERE id=?",
                    (json.dumps(source_metadata, ensure_ascii=False), source_id),
                )
            return analysis_run_id

    def list_source_projects(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM source_projects WHERE project_id=? ORDER BY id", (project_id,)
            )]

    def list_analysis_runs(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT a.*,s.root_path,s.framework FROM analysis_runs a
                   JOIN source_projects s ON s.id=a.source_project_id
                   WHERE s.project_id=? ORDER BY a.id DESC""", (project_id,)
            )]

    def list_analysis_symbols(self, analysis_run_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM code_symbols WHERE analysis_run_id=? ORDER BY id", (analysis_run_id,)
            )]

    def list_analysis_edges(self, analysis_run_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM code_edges WHERE analysis_run_id=? ORDER BY id", (analysis_run_id,)
            )]

    def list_analysis_evidence(self, analysis_run_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM analysis_evidence WHERE analysis_run_id=? ORDER BY id", (analysis_run_id,)
            )]

    def save_data_flow_model(self, project_id: int, name: str, definition: dict,
                             source_analysis_run_id: int | None = None,
                             workflow_id: int | None = None) -> int:
        """Persist a versioned visible/hidden data-flow graph."""
        nodes = definition.get("nodes") or []
        edges = definition.get("edges") or []
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO data_flow_models(project_id,source_analysis_run_id,workflow_id,name,review_status,definition_json)
                   VALUES (?,?,?,?,?,?)""",
                (project_id, source_analysis_run_id, workflow_id, name.strip(),
                 definition.get("review_status", "draft"), json.dumps(definition, ensure_ascii=False)),
            )
            model_id = int(cur.lastrowid)
            db.executemany(
                """INSERT INTO data_flow_nodes(model_id,node_key,kind,name,visibility,definition_json)
                   VALUES (?,?,?,?,?,?)""",
                [(model_id, str(node.get("key", "")), str(node.get("kind", "unknown")),
                  str(node.get("name", "")), str(node.get("visibility", "unknown")),
                  json.dumps(node, ensure_ascii=False)) for node in nodes],
            )
            db.executemany(
                """INSERT INTO data_flow_edges(model_id,source_key,target_key,kind,definition_json)
                   VALUES (?,?,?,?,?)""",
                [(model_id, str(edge.get("source", "")), str(edge.get("target", "")),
                  str(edge.get("kind", "calls")), json.dumps(edge, ensure_ascii=False)) for edge in edges],
            )
            return model_id

    def list_data_flow_models(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM data_flow_models WHERE project_id=? ORDER BY id DESC", (project_id,)
            )]

    def get_data_flow_model(self, model_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM data_flow_models WHERE id=?", (model_id,)).fetchone()
            if not row:
                return None
            value = dict(row)
            value["nodes"] = [json.loads(item["definition_json"] or "{}") for item in db.execute(
                "SELECT definition_json FROM data_flow_nodes WHERE model_id=? ORDER BY id", (model_id,)
            )]
            value["edges"] = [json.loads(item["definition_json"] or "{}") for item in db.execute(
                "SELECT definition_json FROM data_flow_edges WHERE model_id=? ORDER BY id", (model_id,)
            )]
            try:
                value["definition"] = json.loads(value.pop("definition_json") or "{}")
            except (TypeError, ValueError):
                value["definition"] = {}
            return value

    def confirm_data_flow_model(self, model_id: int, reviewer: str = "human") -> None:
        with self.connect() as db:
            row = db.execute("SELECT definition_json FROM data_flow_models WHERE id=?", (model_id,)).fetchone()
            if not row:
                raise ValueError("数据流模型不存在")
            definition = json.loads(row[0] or "{}")
            definition["review_status"] = "confirmed"
            definition["confirmed_by"] = reviewer
            db.execute(
                "UPDATE data_flow_models SET review_status='confirmed',definition_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(definition, ensure_ascii=False), model_id),
            )

    def create_ai_session(self, project_id: int, route: str = "route_a",
                          model_provider: str = "rule_based", environment_id: int | None = None,
                          permission_policy: dict | None = None) -> int:
        if route not in {"chat", "route_a", "route_b", "combined"}:
            raise ValueError("无效的 AI 路线")
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO ai_sessions(project_id,route,environment_id,model_provider,permission_policy_json)
                   VALUES (?,?,?,?,?)""",
                (project_id, route, environment_id, model_provider, json.dumps(permission_policy or {
                    "allow_source_read": True, "allow_db_read": False, "allow_network": False,
                    "allow_write": False, "require_human_approval": True,
                }, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def add_ai_message(self, session_id: int, role: str, content: str,
                       redacted_content: str = "", metadata: dict | None = None) -> int:
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("无效的消息角色")
        with self.connect() as db:
            cur = db.execute(
                "INSERT INTO ai_messages(session_id,role,content,redacted_content,metadata_json) VALUES (?,?,?,?,?)",
                (session_id, role, content, redacted_content or content, json.dumps(metadata or {}, ensure_ascii=False)),
            )
            db.execute("UPDATE ai_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))
            return int(cur.lastrowid)

    def list_ai_messages(self, session_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM ai_messages WHERE session_id=? ORDER BY id", (session_id,)
            )]

    def save_ai_artifact(self, session_id: int, kind: str, title: str, definition: dict,
                         evidence_refs: list[dict] | None = None, review_status: str = "draft") -> int:
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO ai_artifacts(session_id,kind,title,schema_version,definition_json,review_status)
                   VALUES (?,?,?,?,?,?)""",
                (session_id, kind, title, str(definition.get("version", "1.0")),
                 json.dumps(definition, ensure_ascii=False), review_status),
            )
            artifact_id = int(cur.lastrowid)
            db.executemany(
                "INSERT INTO ai_evidence_refs(artifact_id,evidence_kind,locator,detail,confidence) VALUES (?,?,?,?,?)",
                [(artifact_id, str(item.get("evidence_kind", "unknown")), str(item.get("locator", "")),
                  str(item.get("detail", "")), str(item.get("confidence", "inferred"))) for item in (evidence_refs or [])],
            )
            return artifact_id

    def list_ai_artifacts(self, session_id: int) -> list[dict]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM ai_artifacts WHERE session_id=? ORDER BY id DESC", (session_id,)
            )]
            for row in rows:
                row["definition"] = json.loads(row.pop("definition_json") or "{}")
                row["evidence_refs"] = [dict(ref) for ref in db.execute(
                    "SELECT * FROM ai_evidence_refs WHERE artifact_id=? ORDER BY id", (row["id"],)
                )]
            return rows

    def create_ai_approval(self, session_id: int, action: str, artifact_id: int | None = None) -> int:
        with self.connect() as db:
            cur = db.execute(
                "INSERT INTO ai_approvals(session_id,artifact_id,action) VALUES (?,?,?)",
                (session_id, artifact_id, action),
            )
            return int(cur.lastrowid)

    def decide_ai_approval(self, approval_id: int, status: str, comment: str = "", reviewer: str = "human") -> None:
        if status not in {"approved", "rejected"}:
            raise ValueError("审批状态必须是 approved 或 rejected")
        with self.connect() as db:
            db.execute(
                "UPDATE ai_approvals SET status=?,comment=?,reviewer=?,decided_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, comment, reviewer, approval_id),
            )

    def list_ai_approvals(self, session_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM ai_approvals WHERE session_id=? ORDER BY id DESC", (session_id,)
            )]

    def save_tool_call(self, session_id: int, tool_name: str, arguments: dict,
                       result: dict | None = None, status: str = "blocked",
                       risk_level: str = "low", approval_id: int | None = None) -> int:
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO tool_calls(session_id,approval_id,tool_name,risk_level,arguments_json,result_json,status)
                   VALUES (?,?,?,?,?,?,?)""",
                (session_id, approval_id, tool_name, risk_level, json.dumps(arguments, ensure_ascii=False),
                 json.dumps(result or {}, ensure_ascii=False), status),
            )
            return int(cur.lastrowid)

    def save_workflow(self, project_id: int, name: str, definition: dict,
                      source_analysis_run_id: int | None = None) -> int:
        steps = definition.get("steps") or []
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO workflows(project_id,source_analysis_run_id,name,review_status,definition_json)
                   VALUES (?,?,?,?,?)""",
                (project_id, source_analysis_run_id, name.strip(), definition.get("review_status", "draft"),
                 json.dumps(definition, ensure_ascii=False)),
            )
            workflow_id = int(cur.lastrowid)
            db.executemany(
                """INSERT INTO workflow_steps(workflow_id,step_order,name,kind,definition_json)
                   VALUES (?,?,?,?,?)""",
                [(workflow_id, index, str(step.get("name") or f"步骤 {index}"), str(step.get("kind", "http")),
                  json.dumps(step, ensure_ascii=False)) for index, step in enumerate(steps, 1)],
            )
            return workflow_id

    def list_workflows(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM workflows WHERE project_id=? ORDER BY updated_at DESC,id DESC", (project_id,)
            )]

    def get_workflow(self, workflow_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row:
                return None
            value = dict(row)
            value["steps"] = [dict(item) for item in db.execute(
                "SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY step_order", (workflow_id,)
            )]
            return value

    def update_workflow(self, workflow_id: int, definition: dict) -> None:
        steps = definition.get("steps") or []
        with self.connect() as db:
            db.execute(
                "UPDATE workflows SET name=?,review_status=?,definition_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (definition.get("name", "未命名流程"), definition.get("review_status", "draft"),
                 json.dumps(definition, ensure_ascii=False), workflow_id),
            )
            db.execute("DELETE FROM workflow_steps WHERE workflow_id=?", (workflow_id,))
            db.executemany(
                "INSERT INTO workflow_steps(workflow_id,step_order,name,kind,definition_json) VALUES (?,?,?,?,?)",
                [(workflow_id, index, str(step.get("name") or f"步骤 {index}"), str(step.get("kind", "http")),
                  json.dumps(step, ensure_ascii=False)) for index, step in enumerate(steps, 1)],
            )

    def update_workflow_status(self, workflow_id: int, status: str) -> None:
        if status not in {"draft", "confirmed", "archived"}:
            raise ValueError("无效的流程状态")
        with self.connect() as db:
            db.execute("UPDATE workflows SET review_status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, workflow_id))

    def save_db_connection(self, project_id: int, name: str, target_path: str,
                           read_only: bool = True, config: dict | None = None,
                           secrets_encrypted: str = "", backend: str = "sqlite") -> int:
        with self.connect() as db:
            db.execute(
                """INSERT INTO db_connections(project_id,name,backend,target_path,read_only,config_json,secrets_encrypted)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(project_id,name) DO UPDATE SET backend=excluded.backend,target_path=excluded.target_path,
                   read_only=excluded.read_only,config_json=excluded.config_json,secrets_encrypted=excluded.secrets_encrypted""",
                (project_id, name.strip(), backend.strip().lower() or "sqlite", target_path, 1 if read_only else 0,
                 json.dumps(config or {}, ensure_ascii=False), secrets_encrypted),
            )
            return int(db.execute(
                "SELECT id FROM db_connections WHERE project_id=? AND name=?", (project_id, name.strip())
            ).fetchone()[0])

    def list_db_connections(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM db_connections WHERE project_id=? ORDER BY id", (project_id,)
            )]

    def save_db_schema_snapshot(self, project_id: int, db_connection_id: int | None,
                                snapshot: dict) -> int:
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO db_schema_snapshots(project_id,db_connection_id,backend,target_fingerprint,status,definition_json)
                   VALUES (?,?,?,?,?,?)""",
                (project_id, db_connection_id, snapshot.get("backend", "sqlite"),
                 snapshot.get("target", ""), snapshot.get("status", "unknown"),
                 json.dumps(snapshot, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def list_db_schema_snapshots(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM db_schema_snapshots WHERE project_id=? ORDER BY id DESC", (project_id,)
            )]
            for row in rows:
                row["definition"] = json.loads(row.pop("definition_json") or "{}")
            return rows

    def save_fixture(self, project_id: int, name: str, definition: dict,
                     workflow_id: int | None = None) -> int:
        with self.connect() as db:
            cur = db.execute(
                "INSERT INTO test_fixtures(project_id,workflow_id,name,definition_json) VALUES (?,?,?,?)",
                (project_id, workflow_id, name.strip(), json.dumps(definition, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def list_fixtures(self, project_id: int, workflow_id: int | None = None) -> list[dict]:
        with self.connect() as db:
            if workflow_id is None:
                rows = db.execute("SELECT * FROM test_fixtures WHERE project_id=? ORDER BY id", (project_id,))
            else:
                rows = db.execute(
                    "SELECT * FROM test_fixtures WHERE project_id=? AND workflow_id=? ORDER BY id",
                    (project_id, workflow_id),
                )
            return [dict(row) for row in rows]

    def create_workflow_run(self, project_id: int, workflow_id: int,
                            db_connection_id: int | None = None) -> int:
        with self.connect() as db:
            cur = db.execute(
                "INSERT INTO workflow_runs(project_id,workflow_id,db_connection_id) VALUES (?,?,?)",
                (project_id, workflow_id, db_connection_id),
            )
            return int(cur.lastrowid)

    def save_workflow_step_result(self, run_id: int, step_id: int | None, step_order: int,
                                  status: str, result: dict) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO workflow_step_runs(run_id,step_id,step_order,status,elapsed_ms,result_json) VALUES (?,?,?,?,?,?)",
                (run_id, step_id, step_order, status, int(result.get("elapsed_ms", 0)),
                 json.dumps(result, ensure_ascii=False)),
            )

    def finish_workflow_run(self, run_id: int, status: str, summary: dict) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE workflow_runs SET status=?,finished_at=CURRENT_TIMESTAMP,summary_json=? WHERE id=?",
                (status, json.dumps(summary, ensure_ascii=False), run_id),
            )

    def save_workflow_trace(self, run_id: int, trace: dict, status: str = "completed") -> int:
        with self.connect() as db:
            cur = db.execute(
                "INSERT INTO workflow_traces(run_id,trace_id,status,definition_json) VALUES (?,?,?,?)",
                (run_id, trace.get("trace_id", ""), status, json.dumps(trace, ensure_ascii=False)),
            )
            trace_row_id = int(cur.lastrowid)
            db.executemany(
                """INSERT INTO workflow_trace_events(trace_id,kind,name,status,timestamp,source,data_json)
                   VALUES (?,?,?,?,?,?,?)""",
                [(trace_row_id, item.get("kind", ""), item.get("name", ""), item.get("status", "observed"),
                  item.get("timestamp", ""), item.get("source", ""), json.dumps(item.get("data") or {}, ensure_ascii=False))
                 for item in trace.get("events", [])],
            )
            return trace_row_id

    def get_workflow_trace(self, trace_row_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM workflow_traces WHERE id=?", (trace_row_id,)).fetchone()
            if not row:
                return None
            value = dict(row)
            value["events"] = []
            for event in db.execute("SELECT * FROM workflow_trace_events WHERE trace_id=? ORDER BY id", (trace_row_id,)):
                item = dict(event)
                item["data"] = json.loads(item.pop("data_json") or "{}")
                value["events"].append(item)
            return value

    def audit_workflow(self, run_id: int | None, action: str, details: dict | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO workflow_audits(run_id,action,details_json) VALUES (?,?,?)",
                (run_id, action, json.dumps(details or {}, ensure_ascii=False)),
            )

    def list_workflow_runs(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM workflow_runs WHERE project_id=? ORDER BY id DESC", (project_id,)
            )]

    def save_workflow_report(self, run_id: int, html_path: str, json_path: str,
                             report_type: str = "业务流程报告", route: str = "route_a",
                             environment: str = "") -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO workflow_reports(workflow_run_id,html_path,json_path,report_type,route,environment) VALUES (?,?,?,?,?,?)",
                (run_id, html_path, json_path, report_type, route, environment),
            )

    def list_workflow_reports(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT r.*,w.name AS workflow_name,wr.status,wr.started_at,wr.finished_at,wr.summary_json
                   FROM workflow_reports r JOIN workflow_runs wr ON wr.id=r.workflow_run_id
                   JOIN workflows w ON w.id=wr.workflow_id
                   WHERE wr.project_id=? ORDER BY r.id DESC""", (project_id,)
            )]

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

    def save_report(self, run_id: int, html_path: str, json_path: str,
                    report_type: str = "接口契约报告", route: str = "route_b",
                    environment: str = "") -> None:
        with self.connect() as db:
            db.execute("INSERT INTO reports(run_id,html_path,json_path,report_type,route,environment) VALUES (?,?,?,?,?,?)",
                       (run_id, html_path, json_path, report_type, route, environment))

    def list_reports(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT p.*,r.status,r.started_at,r.finished_at,r.summary_json
                   FROM reports p JOIN test_runs r ON r.id=p.run_id
                   WHERE r.project_id=? ORDER BY p.id DESC""", (project_id,)
            )]

    def save_evidence_report(self, project_id: int, report_type: str, html_path: str,
                             json_path: str, summary: dict, route: str = "combined",
                             environment: str = "") -> int:
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO evidence_reports(project_id,report_type,route,environment,html_path,json_path,summary_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (project_id, report_type, route, environment, html_path, json_path, json.dumps(summary, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def list_evidence_reports(self, project_id: int) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM evidence_reports WHERE project_id=? ORDER BY id DESC", (project_id,)
            )]
