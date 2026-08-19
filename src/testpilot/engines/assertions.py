from __future__ import annotations

from typing import Any


def evaluate(assertion: dict, status_code: int, elapsed_ms: int, body: Any) -> dict:
    kind = assertion.get("type")
    expected = assertion.get("expected")
    actual: Any
    passed = False
    if kind == "status_code":
        actual = status_code
        passed = actual == expected
    elif kind == "response_time":
        actual = elapsed_ms
        passed = actual < expected
    elif kind == "json_path":
        actual = json_path(body, assertion.get("path", ""))
        operator = assertion.get("operator", "equals")
        passed = actual == expected if operator == "equals" else actual not in (None, "", [], {}) if operator == "not_empty" else False
    elif kind == "response_schema":
        from testpilot.common.schema_validation import validate
        actual = body
        try:
            validate(body, expected)
            passed = True
        except Exception:
            passed = False
    else:
        actual = None
    return {"type": kind, "passed": passed, "expected": expected, "actual": actual}


def json_path(body: Any, path: str) -> Any:
    current = body
    for part in path.removeprefix("$.").split("."):
        if not part:
            continue
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
