import json

from testpilot.cases.generator import generate_cases, generate_plan
from testpilot.engines.assertions import evaluate
from testpilot.parsers.curl_parser import parse_curl
from testpilot.parsers.postman_parser import PostmanParser


def test_parse_postman_collection():
    data = {
        "info": {"name": "Demo", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [{"name": "Users", "item": [{"name": "Create", "request": {
            "method": "POST", "url": {"raw": "{{baseUrl}}/users", "path": ["users"]},
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "body": {"mode": "raw", "raw": '{"name":"Ada"}'},
        }}]}],
    }
    document = PostmanParser().parse_dict(data)
    assert document.endpoints[0].path == "/users"
    assert document.endpoints[0].request_body["content"]["application/json"]["example"]["name"] == "Ada"


def test_parse_curl_and_generate_cases():
    document = parse_curl("""curl -X POST https://api.example.test/users?active=true -H "Content-Type: application/json" -d '{"name":"Ada"}'""")
    endpoint = document.endpoints[0]
    row = {"id": 7, "definition_json": json.dumps(endpoint.to_dict(), ensure_ascii=False)}
    plan = generate_plan([row], "检查鉴权和边界")
    cases = generate_cases([row])
    assert document.base_urls == ["https://api.example.test"]
    assert "鉴权" in plan["test_types"]
    assert cases[0]["endpoint_id"] == 7
    assert cases[0]["risk"] == "high"
    assert cases[0]["request"]["query"]["active"] == "true"


def test_assertions():
    assert evaluate({"type": "status_code", "expected": 200}, 200, 10, {})["passed"]
    assert evaluate({"type": "json_path", "path": "$.data.id", "operator": "not_empty"}, 200, 10, {"data": {"id": 1}})["passed"]
