from __future__ import annotations

import json
from pathlib import Path


def export_cases(rows: list[dict], output: str | Path) -> Path:
    """Export portable case definitions without database IDs or run history."""
    cases = [json.loads(row["definition_json"]) if isinstance(row.get("definition_json"), str) else row for row in rows]
    path = Path(output)
    path.write_text(json.dumps({"format": "testpilot-cases/v1", "cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def import_cases(source: str | Path) -> list[dict]:
    payload = json.loads(Path(source).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError("用例文件必须包含 cases 数组")
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict) or not case.get("name") or not isinstance(case.get("request"), dict):
            raise ValueError(f"第 {index} 条用例缺少名称或 request")
        if not case["request"].get("method") or not case["request"].get("path"):
            raise ValueError(f"第 {index} 条用例缺少请求方法或路径")
        case.setdefault("priority", "P1")
        case.setdefault("review_status", "draft")
        case.pop("id", None)
        case.pop("endpoint_id", None)
    return cases
