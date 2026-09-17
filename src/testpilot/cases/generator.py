from __future__ import annotations

import copy
import itertools
import json
import re
from typing import Any


_REJECTION_STATUSES = [400, 401, 403, 404, 405, 409, 415, 422]
_SECURITY_PAYLOADS = (
    ("SQL 注入", "' OR 1=1 --"),
    ("XSS 注入", "<script>alert(1)</script>"),
    ("命令行注入", "; whoami"),
    ("JSON 注入", '{"$ne": null}'),
    ("NoSQL 注入", "[$ne]=null"),
    ("模糊输入", "\x00\uffff%00{{7*7}}"),
)


def generate_plan(endpoints: list[dict], instruction: str = "", generated_cases: list[dict] | None = None) -> dict[str, Any]:
    definitions = [_definition(item) for item in endpoints]
    directions = _requested_directions(instruction)
    labels = {
        "positive": "正向：必要字段、语义合法、枚举组合",
        "negative": "负向：缺失必填、无效值、格式/类型/语义错误",
        "boundary": "边界值：极值、越界、Null/零值/空值、字符串长度",
        "security": "安全性：鉴权、SQL/XSS/命令/JSON/NoSQL 注入与模糊输入",
    }
    destructive = any(item.get("method", "").upper() in {"POST", "PUT", "PATCH", "DELETE"} for item in definitions)
    estimated = len(generated_cases) if generated_cases is not None else len(generate_cases(endpoints, instruction))
    test_types = [labels[key] for key in ("positive", "negative", "boundary", "security") if key in directions]
    if "security" in directions:
        test_types.extend(["鉴权", "权限"])
    return {
        "scope": [f'{item["method"]} {item["path"]}' for item in definitions],
        "test_types": test_types,
        "estimated_cases": estimated,
        "risk": "高" if destructive or "security" in directions else "低",
        "requires_confirmation": True,
        "excluded": ["压力测试", "自动执行未经确认的破坏性或安全性请求"],
        "instruction": instruction,
    }


def generate_cases(endpoints: list[dict], instruction: str = "") -> list[dict]:
    directions = _requested_directions(instruction)
    cases: list[dict] = []
    sequence = 1

    def add(base: dict, title: str, tags: list[str], *, value: tuple[dict, Any] | None = None,
            omit: dict | None = None, assertion: str = "success", security: bool = False) -> None:
        nonlocal sequence
        case = copy.deepcopy(base)
        case["id"] = f"TC-{sequence:04d}"
        case["name"] = f'{base["_endpoint_title"]} - {title}'
        case["tags"] = list(dict.fromkeys([*tags, base["source"]]))
        case.pop("_endpoint_title", None)
        if value is not None:
            _set_request_value(case["request"], value[0], value[1])
        if omit is not None:
            case["request"].setdefault("omit_parameters", []).append(omit["name"])
        if security:
            case["risk"] = "high"
        if assertion == "reject":
            case["assertions"][0] = {
                "type": "status_code", "operator": "in", "expected": _REJECTION_STATUSES,
            }
        elif assertion == "safe":
            case["assertions"][0] = {
                "type": "status_code", "operator": "not_in", "expected": list(range(500, 600)),
            }
        cases.append(case)
        sequence += 1

    for row in endpoints:
        endpoint = _definition(row)
        method = str(endpoint.get("method") or "GET").upper()
        body, content_type = _body_example(endpoint.get("request_body") or {})
        inputs = _request_inputs(endpoint)
        headers = {
            item["name"]: _parameter_example(item)
            for item in inputs if item["location"] == "header"
        }
        query = {
            item["name"]: _parameter_example(item)
            for item in inputs if item["location"] == "query"
        }
        path_values = {
            item["name"]: _parameter_example(item)
            for item in inputs if item["location"] == "path"
        }
        success_status = _success_status(endpoint.get("responses") or {})
        base = {
            "endpoint_id": row.get("id"),
            "module": endpoint.get("module", "未分组"),
            "priority": "P1",
            "tags": ["正向", endpoint.get("source", "unknown")],
            "preconditions": [],
            "request": {
                "method": method,
                "path": endpoint["path"],
                "path_parameters": path_values,
                "query": query,
                "headers": headers,
                "body": body,
                "content_type": content_type,
            },
            "assertions": [
                {"type": "status_code", "operator": "equals", "expected": success_status},
                {"type": "response_time", "operator": "less_than", "expected": 2000},
            ],
            "cleanup": [],
            "source": endpoint.get("source", "unknown"),
            "review_status": "draft",
            "risk": "high" if method in {"POST", "PUT", "PATCH", "DELETE"} else "low",
            "_endpoint_title": endpoint.get("summary") or endpoint["path"],
        }

        add(base, "正常请求", ["正向", "必要字段", "语义合法"])

        if "positive" in directions:
            enum_inputs = [item for item in inputs if item["schema"].get("enum")]
            if enum_inputs:
                enum_values = [item["schema"]["enum"] for item in enum_inputs]
                combinations = itertools.islice(itertools.product(*enum_values), 12)
                for index, values in enumerate(combinations, 1):
                    case = copy.deepcopy(base)
                    case["id"] = f"TC-{sequence:04d}"
                    case["name"] = f'{base["_endpoint_title"]} - 合法枚举组合 {index}'
                    case["tags"] = ["正向", "枚举组合", base["source"]]
                    case.pop("_endpoint_title", None)
                    for item, value in zip(enum_inputs, values):
                        _set_request_value(case["request"], item, value)
                    cases.append(case)
                    sequence += 1

        if "negative" in directions:
            for item in inputs:
                schema = item["schema"]
                if item["required"]:
                    add(base, f'缺失必填字段 {item["name"]}', ["负向", "缺失必填字段"],
                        omit=item, assertion="reject")
                invalid = _wrong_type_value(schema)
                if invalid is not None:
                    add(base, f'{item["name"]} 类型错误', ["负向", "类型错误"],
                        value=(item, invalid), assertion="reject")
                if schema.get("enum"):
                    add(base, f'{item["name"]} 无效枚举值', ["负向", "无效值", "语义非法"],
                        value=(item, "__INVALID_ENUM__"), assertion="reject")
                if schema.get("format"):
                    add(base, f'{item["name"]} 格式错误', ["负向", "格式错误"],
                        value=(item, _invalid_format(str(schema["format"]))), assertion="reject")
                semantic = _semantic_invalid_value(schema)
                if semantic is not None:
                    add(base, f'{item["name"]} 语义非法', ["负向", "语义非法"],
                        value=(item, semantic), assertion="reject")

        if "boundary" in directions:
            for item in inputs:
                for label, value, should_reject in _boundary_values(item["schema"]):
                    add(base, f'{item["name"]} {label}', ["边界值", label],
                        value=(item, value), assertion="reject" if should_reject else "success")

        if "security" in directions:
            auth_case = copy.deepcopy(base)
            auth_case["id"] = f"TC-{sequence:04d}"
            auth_case["name"] = f'{base["_endpoint_title"]} - 无鉴权访问'
            auth_case["tags"] = ["安全性", "鉴权控制", base["source"]]
            auth_case["risk"] = "high"
            auth_case["request"]["disable_auth"] = True
            auth_case["assertions"][0] = {
                "type": "status_code",
                "operator": "in",
                "expected": [401, 403] if endpoint.get("security") else [success_status, 401, 403],
            }
            auth_case.pop("_endpoint_title", None)
            cases.append(auth_case)
            sequence += 1

            target = next((item for item in inputs if _schema_type(item["schema"]) == "string"), None)
            if target is None and inputs:
                target = inputs[0]
            if target is not None:
                for label, payload in _SECURITY_PAYLOADS:
                    add(base, f'{target["name"]} {label}', ["安全性", label],
                        value=(target, payload), assertion="safe", security=True)

    return cases


def _requested_directions(instruction: str) -> set[str]:
    text = (instruction or "").strip().lower()
    if not text:
        return {"positive", "negative"}
    if any(word in text for word in ("所有", "全部", "全选", "全面", "综合")):
        return {"positive", "negative", "boundary", "security"}
    directions: set[str] = set()
    if any(word in text for word in ("正向", "正常", "必要字段", "语义合法", "枚举", "成功")):
        directions.add("positive")
    if any(word in text for word in (
        "负向", "无效", "缺失", "必填", "格式错误", "类型错误", "语义非法", "异常", "错误值",
    )):
        directions.add("negative")
    if any(word in text for word in (
        "边界", "极大", "极小", "最大", "最小", "null", "零值", "空值", "过长", "过短",
    )):
        directions.add("boundary")
    if any(word in text for word in (
        "安全", "鉴权", "权限", "token", "登录", "sql", "xss", "注入", "模糊",
    )):
        directions.add("security")
    directions.add("positive")
    return directions


def _definition(row: dict) -> dict:
    value = row.get("definition_json")
    if isinstance(value, str):
        return json.loads(value)
    return value if isinstance(value, dict) else row


def _request_inputs(endpoint: dict) -> list[dict]:
    result = []
    for parameter in endpoint.get("parameters") or []:
        if not isinstance(parameter, dict) or not parameter.get("name"):
            continue
        result.append({
            "name": str(parameter["name"]),
            "location": str(parameter.get("location") or parameter.get("in") or "query"),
            "required": bool(parameter.get("required")),
            "schema": parameter.get("schema") or {},
            "example": parameter.get("example"),
        })
    request_body = endpoint.get("request_body") or {}
    for _content_type, media in (request_body.get("content") or {}).items():
        if not isinstance(media, dict):
            continue
        schema = media.get("schema") or {}
        required = set(schema.get("required") or [])
        for name, property_schema in (schema.get("properties") or {}).items():
            result.append({
                "name": str(name), "location": "body", "required": name in required,
                "schema": property_schema or {}, "example": (property_schema or {}).get("example"),
            })
        break
    return result


def _set_request_value(request: dict, item: dict, value: Any) -> None:
    location = item["location"]
    name = item["name"]
    target_key = {"path": "path_parameters", "query": "query", "header": "headers"}.get(location)
    if target_key:
        if location == "header" and not isinstance(value, (str, bytes)):
            value = json.dumps(value, ensure_ascii=False)
        request.setdefault(target_key, {})[name] = value
        return
    if location == "body":
        if not isinstance(request.get("body"), dict):
            request["body"] = {}
        request["body"][name] = value


def _body_example(body: dict) -> tuple[Any, str]:
    for content_type, media in body.get("content", {}).items():
        if not isinstance(media, dict):
            continue
        if "example" in media:
            return media["example"], content_type
        return _example_from_schema(media.get("schema") or {}), content_type
    return None, "application/json"


def _example_from_schema(schema: dict) -> Any:
    if schema.get("example") is not None:
        return schema["example"]
    if schema.get("default") is not None:
        return schema["default"]
    if "$ref" in schema:
        return {}
    kind = _schema_type(schema)
    if kind == "object" or "properties" in schema:
        return {key: _example_from_schema(value) for key, value in schema.get("properties", {}).items()}
    if kind == "array":
        return [_example_from_schema(schema.get("items", {}))]
    if schema.get("enum"):
        return schema["enum"][0]
    if kind in {"integer", "number"}:
        return schema.get("minimum", 1 if kind == "integer" else 1.0)
    if kind == "string":
        minimum = max(1, int(schema.get("minLength", 1)))
        return "test" if minimum <= 4 else "t" * minimum
    return {"boolean": True}.get(kind)


def _success_status(responses: dict) -> int:
    statuses = [int(item) for item in responses if re.fullmatch(r"2\d\d", str(item))]
    return min(statuses) if statuses else 200


def _parameter_example(parameter: dict) -> Any:
    if parameter.get("example") is not None:
        return parameter["example"]
    return _example_from_schema(parameter.get("schema") or {})


def _schema_type(schema: dict) -> str:
    kind = str(schema.get("type") or "")
    if kind:
        return kind
    if "properties" in schema:
        return "object"
    if "enum" in schema and schema["enum"]:
        value = schema["enum"][0]
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
    return "string"


def _wrong_type_value(schema: dict) -> Any:
    return {
        "string": 12345,
        "integer": "not-an-integer",
        "number": "not-a-number",
        "boolean": "not-a-boolean",
        "array": {"unexpected": "object"},
        "object": "unexpected-string",
    }.get(_schema_type(schema))


def _invalid_format(format_name: str) -> str:
    return {
        "email": "not-an-email",
        "uuid": "not-a-uuid",
        "date": "31-31-2026",
        "date-time": "not-a-date-time",
        "uri": "not a uri",
        "ipv4": "999.999.999.999",
        "ipv6": "not-an-ipv6",
    }.get(format_name.lower(), "__INVALID_FORMAT__")


def _semantic_invalid_value(schema: dict) -> Any:
    if schema.get("minimum") is not None:
        return schema["minimum"] - 1
    if schema.get("maximum") is not None:
        return schema["maximum"] + 1
    if schema.get("minLength") is not None:
        return "x" * max(0, int(schema["minLength"]) - 1)
    if schema.get("maxLength") is not None:
        return "x" * (int(schema["maxLength"]) + 1)
    return None


def _boundary_values(schema: dict) -> list[tuple[str, Any, bool]]:
    kind = _schema_type(schema)
    values: list[tuple[str, Any, bool]] = []
    if kind in {"integer", "number"}:
        if schema.get("minimum") is not None:
            minimum = schema["minimum"]
            values.extend([("最小边界值", minimum, False), ("小于最小边界", minimum - 1, True)])
        if schema.get("maximum") is not None:
            maximum = schema["maximum"]
            values.extend([("最大边界值", maximum, False), ("超出最大边界", maximum + 1, True)])
        values.append(("零值", 0, bool(schema.get("minimum", 0) > 0)))
    elif kind == "string":
        minimum = int(schema.get("minLength", 0))
        maximum = schema.get("maxLength")
        values.extend([("Null 值", None, True), ("空值", "", minimum > 0)])
        if minimum:
            values.extend([("最短合法字符串", "x" * minimum, False), ("字符串过短", "x" * max(0, minimum - 1), True)])
        if maximum is not None:
            maximum = int(maximum)
            values.extend([("最长合法字符串", "x" * maximum, False), ("字符串过长", "x" * (maximum + 1), True)])
    elif kind == "array":
        minimum = int(schema.get("minItems", 0))
        maximum = schema.get("maxItems")
        values.append(("空值", [], minimum > 0))
        if maximum is not None:
            values.append(("超出最大边界", [_example_from_schema(schema.get("items") or {})] * (int(maximum) + 1), True))
    else:
        values.append(("Null 值", None, True))
    deduplicated: list[tuple[str, Any, bool]] = []
    for item in values:
        if item not in deduplicated:
            deduplicated.append(item)
    return deduplicated
