from __future__ import annotations

import copy
import re
from typing import Any


def generate_plan(endpoints: list[dict], instruction: str = "") -> dict[str, Any]:
    definitions = [_definition(e) for e in endpoints]
    destructive = sum(e["method"].upper() in {"POST", "PUT", "PATCH", "DELETE"} for e in definitions)
    types = ["正常功能", "必填参数", "参数类型", "边界值", "响应结构", "响应时间"]
    lowered = instruction.lower()
    if any(x in lowered for x in ("鉴权", "token", "权限", "登录")):
        types.extend(["鉴权", "权限"])
    return {
        "scope": [f'{e["method"]} {e["path"]}' for e in definitions],
        "test_types": list(dict.fromkeys(types)),
        "estimated_cases": sum(1 + len([p for p in _definition(e).get("parameters", []) if p.get("required")]) for e in endpoints),
        "risk": "高" if destructive else "低",
        "requires_confirmation": True,
        "excluded": ["压力测试", "入侵式安全测试", "自动执行破坏性操作"],
        "instruction": instruction,
    }


def generate_cases(endpoints: list[dict], instruction: str = "") -> list[dict]:
    cases: list[dict] = []
    sequence = 1
    for row in endpoints:
        endpoint = _definition(row)
        body, content_type = _body_example(endpoint.get("request_body") or {})
        headers = {
            p["name"]: p.get("example", "")
            for p in endpoint.get("parameters", []) if p.get("location") == "header" and p.get("example") is not None
        }
        query = {
            p["name"]: _parameter_example(p)
            for p in endpoint.get("parameters", []) if p.get("location") == "query"
        }
        path_values = {
            p["name"]: _parameter_example(p)
            for p in endpoint.get("parameters", []) if p.get("location") == "path"
        }
        success_status = _success_status(endpoint.get("responses") or {})
        base = {
            "endpoint_id": row.get("id"),
            "module": endpoint.get("module", "未分组"),
            "priority": "P1",
            "tags": ["功能", endpoint.get("source", "unknown")],
            "preconditions": [],
            "request": {
                "method": endpoint["method"], "path": endpoint["path"], "path_parameters": path_values,
                "query": query, "headers": headers, "body": body, "content_type": content_type,
            },
            "assertions": [
                {"type": "status_code", "operator": "equals", "expected": success_status},
                {"type": "response_time", "operator": "less_than", "expected": 2000},
            ],
            "cleanup": [],
            "source": endpoint.get("source", "unknown"),
            "review_status": "draft",
            "risk": "high" if endpoint["method"] in {"POST", "PUT", "PATCH", "DELETE"} else "low",
        }
        normal = copy.deepcopy(base)
        normal.update({"id": f"TC-{sequence:04d}", "name": f'{endpoint.get("summary") or endpoint["path"]} - 正常请求'})
        cases.append(normal); sequence += 1
        for param in endpoint.get("parameters", []):
            if not param.get("required"):
                continue
            negative = copy.deepcopy(base)
            negative["id"] = f"TC-{sequence:04d}"
            negative["name"] = f'{endpoint.get("summary") or endpoint["path"]} - 缺少必填参数 {param["name"]}'
            negative["tags"] = ["参数校验", "必填"]
            negative["request"].setdefault("omit_parameters", []).append(param["name"])
            negative["assertions"][0]["expected"] = 400
            cases.append(negative); sequence += 1
    return cases


def _definition(row: dict) -> dict:
    value = row.get("definition_json")
    if isinstance(value, str):
        import json
        return json.loads(value)
    return value if isinstance(value, dict) else row


def _body_example(body: dict) -> tuple[Any, str]:
    for content_type, media in body.get("content", {}).items():
        if not isinstance(media, dict):
            continue
        if "example" in media:
            return media["example"], content_type
        schema = media.get("schema") or {}
        return _example_from_schema(schema), content_type
    return None, "application/json"


def _example_from_schema(schema: dict) -> Any:
    if "example" in schema:
        return schema["example"]
    if "$ref" in schema:
        return {}
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {key: _example_from_schema(value) for key, value in schema.get("properties", {}).items()}
    if kind == "array":
        return [_example_from_schema(schema.get("items", {}))]
    if schema.get("enum"):
        return schema["enum"][0]
    return {"integer": 1, "number": 1.0, "boolean": True, "string": "test"}.get(kind)


def _success_status(responses: dict) -> int:
    statuses = [int(x) for x in responses if re.fullmatch(r"2\d\d", str(x))]
    return min(statuses) if statuses else 200


def _parameter_example(parameter: dict) -> Any:
    if parameter.get("example") is not None:
        return parameter["example"]
    schema = parameter.get("schema") or {}
    return _example_from_schema(schema)
