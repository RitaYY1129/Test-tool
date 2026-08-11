from __future__ import annotations

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from testpilot.cases.generator import generate_cases
from testpilot.engines.batch_runner import run_cases
from testpilot.engines.workflow_report import generate_workflow_report
from testpilot.engines.workflow_runner import SqliteTestDatabase, run_workflow
from testpilot.parsers.backend_source_parser import BackendSourceParser
from testpilot.parsers.completeness_checker import check_completeness
from testpilot.parsers.openapi_parser import OpenApiParser
from testpilot.reports.generator import generate_report
from testpilot.storage.database import Database


class RouteHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": {"id": 1}, "route": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def _server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), RouteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_route_b_full_import_execute_and_report(tmp_path):
    server = _server()
    try:
        document = OpenApiParser().parse_dict({
            "openapi": "3.0.0", "info": {"title": "Demo", "version": "1"},
            "paths": {"/users": {"get": {"responses": {"200": {"description": "ok"}}}}},
        })
        db = Database(tmp_path / "route-b.db")
        project_id = db.create_project("route-b")
        source_id = db.save_document(project_id, "openapi.json", document, check_completeness(document))
        endpoints = db.list_endpoints(project_id)
        cases = generate_cases(endpoints, "检查正常响应")
        case_ids = db.save_test_cases(project_id, cases)
        stored = db.list_test_cases(project_id)
        for row in stored:
            db.update_case_status(row["id"], "confirmed")
        confirmed = db.list_test_cases(project_id)
        results, summary = run_cases(confirmed, f"http://127.0.0.1:{server.server_port}")
        run_id = db.create_run(project_id)
        for result in results:
            db.save_result(run_id, result.get("case_id"), result)
        db.finish_run(run_id, summary)
        html_path, json_path = generate_report(tmp_path / "reports", "route-b", results, summary)
        db.save_report(run_id, str(html_path), str(json_path))
        assert source_id > 0 and case_ids
        assert summary["passed"] == summary["total"] == len(results)
        assert db.list_reports(project_id)[0]["run_id"] == run_id
        assert html_path.exists() and json_path.exists()
    finally:
        server.shutdown()


def test_route_a_full_source_workflow_database_and_report(tmp_path):
    source = tmp_path / "service"
    source.mkdir()
    (source / "Demo.csproj").write_text("<Project Sdk='Microsoft.NET.Sdk.Web' />", encoding="utf-8")
    (source / "CreateUserRequest.cs").write_text(
        "public class CreateUserRequest { public string Name { get; set; } }", encoding="utf-8"
    )
    (source / "UserController.cs").write_text(
        """[ApiController]\n[Route("api/users")]\npublic class UserController : ControllerBase {
        [HttpGet]\n        public IActionResult Get() { return Ok(); }\n}
        """, encoding="utf-8"
    )
    parser = BackendSourceParser()
    analysis = parser.analyze_directory(source)
    candidate = parser.suggest_workflow(source)[1]
    assert candidate["steps"] and candidate["requires_confirmation"]

    db_path = tmp_path / "route-a.db"
    business_db = tmp_path / "business.sqlite"
    with sqlite3.connect(business_db) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
    db = Database(db_path)
    project_id = db.create_project("route-a")
    document = analysis["document"]
    source_id = db.save_document(project_id, "service", document, check_completeness(document))
    analysis_run_id = db.save_source_analysis(project_id, analysis, source_id)
    candidate["review_status"] = "confirmed"
    candidate["steps"] = [
        {"name": "检查用户数据", "kind": "db_assertion",
         "assertion": {"query": "SELECT name FROM users WHERE name = ?", "params": ["Ada"], "row_count": 1}},
        {"name": "查询接口", "kind": "http", "request": {"method": "GET", "path": "/users"},
         "assertions": [{"type": "status_code", "expected": 200}]},
        {"name": "检查外部副作用", "kind": "side_effect_check",
         "request": {"method": "GET", "path": "/side-effect"},
         "assertions": [{"type": "status_code", "expected": 200}]},
    ]
    workflow_id = db.save_workflow(project_id, candidate["name"], candidate, analysis_run_id)
    db.update_workflow_status(workflow_id, "confirmed")
    connection_id = db.save_db_connection(project_id, "业务流程测试库", str(business_db), read_only=False)
    database = SqliteTestDatabase(str(business_db), read_only=False)
    server = _server()
    try:
        results, summary = run_workflow(
            candidate, f"http://127.0.0.1:{server.server_port}", database=database,
            fixtures=[{"name": "Ada夹具", "table": "users", "rows": [{"name": "Ada"}]}],
        )
        run_id = db.create_workflow_run(project_id, workflow_id, connection_id)
        for index, result in enumerate(results, 1):
            db.save_workflow_step_result(run_id, None, int(result.get("step_order", index)), result["status"], result)
        db.finish_workflow_run(run_id, summary["status"], summary)
        report_html, report_json = generate_workflow_report(tmp_path / "reports", "route-a", candidate["name"], results, summary)
        db.save_workflow_report(run_id, str(report_html), str(report_json))
    finally:
        server.shutdown()
    with sqlite3.connect(business_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert source_id > 0 and analysis_run_id > 0 and workflow_id > 0
    assert summary["status"] == "passed"
    assert len(results) == 4  # fixture preparation + three confirmed workflow steps
    assert db.list_workflow_reports(project_id)[0]["workflow_run_id"] == run_id
    assert report_html.exists() and report_json.exists()
