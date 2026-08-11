from testpilot.domain.process_script import build_process_script, evaluate_process_script, validate_process_script
from testpilot.engines.workflow_runner import run_workflow
from testpilot.engines.workflow_runner import SqliteTestDatabase
import sqlite3


def _analysis():
    return {"root_path": "/sample", "edges": [{"source_symbol": "OrderService", "target_symbol": "OrderRepository", "edge_type": "calls", "file_path": "Order.cs", "line_start": 8}], "evidence": [{"evidence_type": "sql_write", "file_path": "OrderRepository.cs", "line_start": 20, "details": {"operation": "INSERT orders"}}]}


def test_process_script_exposes_unobserved_internal_work_as_blocking():
    script = build_process_script({"name": "order", "steps": [{"name": "create", "kind": "http", "request": {"method": "POST", "path": "/orders"}}]}, _analysis())
    coverage = evaluate_process_script(script)
    assert script["process_script_version"] == "2.0"
    assert coverage["critical_total"] == 1 and coverage["critical_observed"] == 0
    assert validate_process_script(script, require_observed=True)


def test_observed_internal_checkpoint_allows_complete_execution(monkeypatch):
    workflow = build_process_script({"name": "order", "steps": [{"name": "get", "kind": "http", "request": {"method": "GET", "path": "/orders"}}]}, _analysis())
    checkpoint = workflow["steps"][0]["internal_checkpoints"][0]
    checkpoint["observation"] = {"status": "observed", "adapter": "database_snapshot", "evidence_id": "db-1"}
    workflow["steps"][0]["failure_branches"] = [{"name": "db failure", "expected": "rollback"}]
    workflow["steps"][0]["invariants"] = [{"name": "one order only"}]
    workflow["review_status"] = "confirmed"
    class Response:
        status_code, elapsed_ms, body, headers = 200, 1, [], {}
    monkeypatch.setattr("testpilot.engines.workflow_runner.execute_request", lambda *args, **kwargs: Response())
    _, summary = run_workflow(workflow, "http://test")
    assert summary["status"] == "passed"
    assert summary["process_coverage"]["status"] == "complete"


def test_api_execution_observes_related_database_change(monkeypatch, tmp_path):
    database_path = tmp_path / "business.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY, state TEXT)")
    analysis = {"root_path": "/sample", "evidence": [], "edges": [{
        "source_symbol": "OrderService.Create", "target_symbol": "db:orders", "edge_type": "writes",
        "file_path": "OrderService.cs", "line_start": 20,
        "metadata": {"table": "orders", "operation": "INSERT", "confidence": "static"},
    }]}
    workflow = build_process_script({"name": "create order", "steps": [{"name": "POST /orders", "kind": "http", "request": {"method": "POST", "path": "/orders"}}]}, analysis)
    workflow["review_status"] = "confirmed"

    class Response:
        status_code, elapsed_ms, body, headers = 201, 1, {"id": 1}, {}

    def send_request(*args, **kwargs):
        with sqlite3.connect(database_path) as connection:
            connection.execute("INSERT INTO orders(id,state) VALUES (1,'created')")
        return Response()

    monkeypatch.setattr("testpilot.engines.workflow_runner.execute_request", send_request)
    _, summary = run_workflow(workflow, "http://test", database=SqliteTestDatabase(str(database_path)))
    assert summary["status"] == "passed"
    assert summary["state_observations"]["check"]["status"] == "passed"
    assert summary["process_coverage"]["critical_observed"] == 1
