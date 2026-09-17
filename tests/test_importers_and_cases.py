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
    assert evaluate({"type": "status_code", "operator": "in", "expected": [400, 422]}, 422, 10, {})["passed"]
    assert evaluate({"type": "status_code", "operator": "not_in", "expected": [500, 502]}, 200, 10, {})["passed"]
    assert evaluate({"type": "json_path", "path": "$.data.id", "operator": "not_empty"}, 200, 10, {"data": {"id": 1}})["passed"]


def test_generate_cases_from_schema_and_user_directions():
    endpoint = {
        "method": "POST", "path": "/users/{id}", "summary": "创建用户", "module": "Users",
        "source": "openapi", "security": [{"bearerAuth": []}],
        "parameters": [
            {"name": "id", "location": "path", "required": True,
             "schema": {"type": "integer", "minimum": 1, "maximum": 10}},
            {"name": "state", "location": "query", "required": True,
             "schema": {"type": "string", "enum": ["enabled", "disabled"]}},
        ],
        "request_body": {"content": {"application/json": {"schema": {
            "type": "object", "required": ["name", "email"], "properties": {
                "name": {"type": "string", "minLength": 2, "maxLength": 8},
                "email": {"type": "string", "format": "email"},
            },
        }}}},
        "responses": {"201": {"description": "created"}},
    }
    cases = generate_cases([{"id": 9, "definition_json": json.dumps(endpoint)}], "全部方向")
    names = {case["name"] for case in cases}
    tags = {tag for case in cases for tag in case.get("tags", [])}

    assert any("合法枚举组合" in name for name in names)
    assert any("缺失必填字段 name" in name for name in names)
    assert any("email 格式错误" in name for name in names)
    assert any("id 超出最大边界" in name for name in names)
    assert any("name 字符串过长" in name for name in names)
    assert {"正向", "负向", "边界值", "安全性"}.issubset(tags)
    auth_case = next(case for case in cases if "无鉴权访问" in case["name"])
    assert auth_case["request"]["disable_auth"] is True
    assert auth_case["review_status"] == "draft" and auth_case["risk"] == "high"


def test_generate_only_normal_case_when_requested():
    endpoint = {"method": "GET", "path": "/health", "parameters": [], "responses": {"200": {}}}
    cases = generate_cases([{"id": 1, "definition_json": json.dumps(endpoint)}], "检查正常响应")
    assert len(cases) == 1
    assert cases[0]["name"].endswith("正常请求")
