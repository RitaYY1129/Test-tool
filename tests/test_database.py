from testpilot.storage.database import Database


def test_project_lifecycle(tmp_path):
    db = Database(tmp_path / "test.db")
    project_id = db.create_project("示例项目")
    assert db.list_projects()[0]["name"] == "示例项目"
    assert db.list_environments(project_id)[0]["name"] == "测试环境"
    db.save_environment(project_id, "预发布", "https://staging.example.test", {"X-App": "test"})
    assert len(db.list_environments(project_id)) == 2
    db.delete_project(project_id)
    assert db.list_projects() == []


def test_delete_empty_sources(tmp_path):
    db = Database(tmp_path / "test.db")
    project_id = db.create_project("source cleanup")
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO api_sources(project_id,name,kind) VALUES (?,?,?)",
            (project_id, "legacy empty import", "openapi"),
        )
    assert db.delete_empty_sources(project_id) == 1
    assert db.list_sources(project_id) == []


def test_route_a_schema_and_source_analysis_are_persisted(tmp_path):
    db = Database(tmp_path / "test.db")
    project_id = db.create_project("route-a")
    analysis = {
        "root_path": str(tmp_path / "service"),
        "name": "service",
        "framework": "aspnet",
        "revision": {"revision_key": "rev-1", "content_hash": "hash-1"},
        "files": [{"path": "UserController.cs", "language": "csharp", "size_bytes": 20, "content_hash": "f1"}],
        "symbols": [{"symbol_type": "class", "qualified_name": "UserController", "file_path": "UserController.cs", "line_start": 1}],
        "edges": [{"source_symbol": "UserController", "target_symbol": "UserService", "edge_type": "dependency_reference", "file_path": "UserController.cs", "line_start": 2}],
        "evidence": [{"evidence_type": "endpoint_route", "file_path": "UserController.cs", "line_start": 3, "details": {"method": "GET", "path": "/users"}}],
        "summary": {"file_count": 1, "symbol_count": 1},
    }
    run_id = db.save_source_analysis(project_id, analysis)
    assert db.list_source_projects(project_id)[0]["framework"] == "aspnet"
    assert db.list_analysis_runs(project_id)[0]["id"] == run_id
    assert db.list_analysis_symbols(run_id)[0]["qualified_name"] == "UserController"
    assert db.list_analysis_edges(run_id)[0]["target_symbol"] == "UserService"
    assert db.list_analysis_evidence(run_id)[0]["evidence_type"] == "endpoint_route"
    with db.connect() as connection:
            assert connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 9
    # Re-opening the same legacy-compatible database must not duplicate the migration.
    Database(tmp_path / "test.db")
    with db.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 9
