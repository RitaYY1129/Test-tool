import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from testpilot.engines.batch_runner import run_cases
from testpilot.reports.generator import generate_report


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = json.dumps({"data": {"id": 1}, "token": "must-be-redacted"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_DELETE(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_):
        pass


def test_execute_and_report(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    case = {
        "id": 1, "name": "查询", "review_status": "confirmed",
        "definition_json": json.dumps({
            "name": "查询", "review_status": "confirmed", "risk": "low",
            "request": {"method": "GET", "path": "/users", "headers": {}, "body": None},
            "assertions": [{"type": "status_code", "expected": 200},
                           {"type": "json_path", "path": "$.data.id", "operator": "not_empty"}],
        }),
    }
    try:
        results, summary = run_cases([case], f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
    assert summary["passed"] == 1
    assert results[0]["response_body"]["token"] == "***"
    html_path, json_path = generate_report(tmp_path, "Demo", results, summary)
    assert html_path.exists() and json_path.exists()
    assert "通过率" in html_path.read_text(encoding="utf-8")


def test_data_driven_parallel_and_cleanup():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    definition = {
        "name": "数据驱动查询", "review_status": "confirmed", "risk": "low",
        "request": {"method": "GET", "path": "/users", "query": {"id": "${id}"}},
        "assertions": [{"type": "status_code", "expected": 200}],
        "data_sets": [{"id": 1}, {"id": 2}],
    }
    cases = [{"id": 1, "name": definition["name"], "review_status": "confirmed",
              "definition_json": json.dumps(definition)}]
    try:
        results, summary = run_cases(cases, f"http://127.0.0.1:{server.server_port}", max_workers=2)
    finally:
        server.shutdown()
    assert summary["total"] == 2
    assert summary["passed"] == 2
