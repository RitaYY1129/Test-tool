from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from testpilot.cli import execute, main
from testpilot.cases.exchange import export_cases, import_cases
from testpilot.storage.database import Database


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *_):
        pass


def test_cli_execute_persists_report_and_trend(tmp_path, capsys):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        db = Database(tmp_path / "testpilot.db")
        project_id = db.create_project("CLI demo")
        db.save_environment(project_id, "staging", f"http://127.0.0.1:{server.server_port}", {})
        definition = {"name": "health", "review_status": "confirmed", "risk": "low",
                      "request": {"method": "GET", "path": "/health"},
                      "assertions": [{"type": "status_code", "expected": 200}]}
        db.save_test_cases(project_id, [definition])
        row = db.list_test_cases(project_id)[0]
        db.update_case_status(row["id"], "confirmed")
        summary, report = execute(db, project_id, "staging")
        assert summary["passed"] == 1 and report.exists()
        assert db.trend_summary(project_id)[0]["pass_rate"] == 100.0
        assert main(["--db", str(db.path), "trend", "--project", str(project_id)]) == 0
        assert '"pass_rate": 100.0' in capsys.readouterr().out
    finally:
        server.shutdown()


def test_schedule_due_task_is_executed_once(tmp_path):
    db = Database(tmp_path / "testpilot.db")
    project_id = db.create_project("schedule demo")
    schedule_id = db.save_schedule(project_id, "测试环境", 5, retry_count=1)
    assert db.list_due_schedules()[0]["id"] == schedule_id
    db.complete_schedule(schedule_id)
    assert db.list_due_schedules() == []


def test_case_exchange_and_schedule_cli_management(tmp_path, capsys):
    db = Database(tmp_path / "testpilot.db")
    project_id = db.create_project("automation management")
    db.save_environment(project_id, "staging", "http://example.test", {})
    definition = {"name": "template", "request": {"method": "GET", "path": "/health"}, "assertions": []}
    db.save_test_cases(project_id, [definition])
    path = export_cases(db.list_test_cases(project_id), tmp_path / "cases.json")
    loaded = import_cases(path)
    assert loaded[0]["review_status"] == "draft"
    assert main(["--db", str(db.path), "import-cases", "--project", str(project_id), "--input", str(path)]) == 0
    assert len(db.list_test_cases(project_id)) == 2
    assert main(["--db", str(db.path), "schedule-add", "--project", str(project_id), "--environment", "staging", "--interval-minutes", "10"]) == 0
    schedule_id = db.list_schedules(project_id)[0]["id"]
    assert main(["--db", str(db.path), "schedule-toggle", "--id", str(schedule_id), "--enabled", "false"]) == 0
    assert not db.list_schedules(project_id)[0]["enabled"]
    assert main(["--db", str(db.path), "schedule-delete", "--id", str(schedule_id)]) == 0
    assert db.list_schedules(project_id) == []
    assert "schedule_id" in capsys.readouterr().out


def test_terminal_only_openapi_to_report_flow(tmp_path, capsys):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        db_path = tmp_path / "terminal.db"
        spec = tmp_path / "openapi.json"
        spec.write_text(json.dumps({"openapi": "3.0.0", "info": {"title": "terminal", "version": "1"}, "paths": {"/health": {"get": {"responses": {"200": {"description": "ok"}}}}}}), encoding="utf-8")
        assert main(["--db", str(db_path), "project-create", "--name", "terminal demo"]) == 0
        project_id = Database(db_path).list_projects()[0]["id"]
        assert main(["--db", str(db_path), "environment-set", "--project", str(project_id), "--name", "staging", "--base-url", f"http://127.0.0.1:{server.server_port}"]) == 0
        assert main(["--db", str(db_path), "openapi-import", "--project", str(project_id), "--input", str(spec)]) == 0
        assert main(["--db", str(db_path), "cases-generate", "--project", str(project_id)]) == 0
        assert main(["--db", str(db_path), "cases-confirm", "--project", str(project_id)]) == 0
        assert main(["--db", str(db_path), "run", "--project", str(project_id), "--environment", "staging"]) == 0
        assert '"passed": 1' in capsys.readouterr().out
    finally:
        server.shutdown()


def test_cli_registers_queues_and_archives_external_runner(tmp_path, capsys):
    db_path = tmp_path / "runner.db"
    assert main(["--db", str(db_path), "project-create", "--name", "SteelMill"]) == 0
    project_id = Database(db_path).list_projects()[0]["id"]
    assert main([
        "--db", str(db_path), "environment-set", "--project", str(project_id), "--name", "staging",
        "--base-url", "https://staging.example.test", "--capabilities-json", '{"allow_mutation": false}',
        "--secret-refs-json", '["steelmill-staging-account"]',
    ]) == 0
    assert main([
        "--db", str(db_path), "runner-register", "--project", str(project_id), "--project-key", "steelmill",
        "--name", "steelmill-runner", "--version", "0.1.0",
    ]) == 0
    manifest = {
        "schema_version": "1.0", "run_id": "steelmill_unit_001", "project_id": "steelmill",
        "runner": {"name": "steelmill-runner", "version": "0.1.0"}, "environment_id": "staging",
        "selection": {"paths": ["tests"], "markers": ["unit"], "case_ids": []},
        "policy": {"allow_mutation": False, "timeout_seconds": 60, "parallel_workers": 1, "retry_policy": "none"},
        "artifacts_dir": "artifacts/steelmill_unit_001",
    }
    result = {
        "schema_version": "1.0", "run_id": "steelmill_unit_001", "status": "passed",
        "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0},
        "cases": [{"id": "unit.contract", "status": "passed"}], "artifacts": {"html": "report.html"},
    }
    manifest_path = tmp_path / "manifest.json"
    result_path = tmp_path / "result.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result_path.write_text(json.dumps(result), encoding="utf-8")
    assert main(["--db", str(db_path), "runner-run-queue", "--manifest", str(manifest_path)]) == 0
    runner_run_id = Database(db_path).list_runner_runs(project_id)[0]["id"]
    assert main(["--db", str(db_path), "runner-run-complete", "--run-id", str(runner_run_id), "--result", str(result_path)]) == 0
    assert main(["--db", str(db_path), "runner-run-list", "--project", str(project_id)]) == 0
    assert '"status": "passed"' in capsys.readouterr().out
