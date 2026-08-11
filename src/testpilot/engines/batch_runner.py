from __future__ import annotations

import json
import copy
import base64
from datetime import datetime
from collections import Counter
from typing import Callable
from threading import Event
from concurrent.futures import ThreadPoolExecutor, as_completed

from testpilot.common.security import redact
from testpilot.engines.assertions import evaluate
from testpilot.engines.http_engine import execute_request
from testpilot.engines.variables import extract_values, resolve


def run_cases(cases: list[dict], base_url: str, common_headers: dict | None = None,
              on_result: Callable[[dict], None] | None = None, variables: dict | None = None,
              stop_event: Event | None = None, max_workers: int = 1) -> tuple[list[dict], dict]:
    started_at = datetime.now().isoformat(timespec="seconds")
    cases = _expand_data_sets(cases)
    if max_workers > 1 and all(_parallel_safe(case) for case in cases):
        results = []
        with ThreadPoolExecutor(max_workers=min(max_workers, 8)) as pool:
            futures = [
                pool.submit(run_cases, [case], base_url, common_headers, None, variables, stop_event, 1)
                for case in cases
            ]
            for future in as_completed(futures):
                item_results, _ = future.result()
                results.extend(item_results)
                if on_result:
                    on_result(item_results[0])
        summary = _summary(results); summary.update(started_at=started_at, finished_at=datetime.now().isoformat(timespec="seconds")); return results, summary
    results = []
    runtime_variables = dict(variables or {})
    statuses: dict[str, str] = {}
    for stored in cases:
        case = json.loads(stored["definition_json"]) if isinstance(stored.get("definition_json"), str) else stored
        case_id = stored.get("id")
        request = case["request"]
        if stop_event and stop_event.is_set():
            result = {"case_id": case_id, "name": case["name"], "status": "skipped", "elapsed_ms": 0,
                      "error": "任务已停止"}
            results.append(result)
            if on_result:
                on_result(result)
            continue
        dependencies = case.get("depends_on") or []
        if any(statuses.get(str(item)) != "passed" for item in dependencies):
            result = {"case_id": case_id, "name": case["name"], "status": "skipped", "elapsed_ms": 0,
                      "error": "依赖用例未通过"}
            results.append(result); statuses[str(case.get("id", case_id))] = "skipped"
            if on_result:
                on_result(result)
            continue
        headers = resolve({**(common_headers or {}), **(request.get("headers") or {})}, runtime_variables)
        auth_type = str(runtime_variables.get("AUTH_TYPE", "")).lower()
        if auth_type in {"bearer", "jwt"} and runtime_variables.get("TOKEN"):
            headers.setdefault("Authorization", f"Bearer {runtime_variables['TOKEN']}")
        elif auth_type == "basic":
            raw = f"{runtime_variables.get('USERNAME','')}:{runtime_variables.get('PASSWORD','')}".encode()
            headers.setdefault("Authorization", "Basic " + base64.b64encode(raw).decode())
        elif auth_type == "api_key" and runtime_variables.get("API_KEY"):
            headers.setdefault(str(runtime_variables.get("API_KEY_HEADER", "X-API-Key")), runtime_variables["API_KEY"])
        query = resolve(copy.deepcopy(request.get("query") or {}), runtime_variables)
        path_values = resolve(copy.deepcopy(request.get("path_parameters") or {}), runtime_variables)
        body = resolve(copy.deepcopy(request.get("body")), runtime_variables)
        for name in request.get("omit_parameters") or []:
            headers.pop(name, None); query.pop(name, None); path_values.pop(name, None)
            if isinstance(body, dict):
                body.pop(name, None)
        path = request["path"]
        for name, value in path_values.items():
            path = path.replace("{" + name + "}", str(value))
        if case.get("risk") == "high" and case.get("review_status") != "confirmed" and stored.get("review_status") != "confirmed":
            result = {"case_id": case_id, "name": case["name"], "status": "skipped", "elapsed_ms": 0,
                      "error": "高风险用例未经人工确认"}
        else:
            try:
                response = execute_request(
                    request["method"], base_url, path, headers, body, query,
                    request.get("content_type", "application/json"),
                )
                assertion_results = [
                    evaluate(a, response.status_code, response.elapsed_ms, response.body) for a in case.get("assertions", [])
                ]
                result = {
                    "case_id": case_id, "name": case["name"],
                    "module": case.get("module", "未分组"), "risk": case.get("risk", "low"),
                    "source": case.get("source", "unknown"),
                    "status": "passed" if all(x["passed"] for x in assertion_results) else "failed",
                    "elapsed_ms": response.elapsed_ms, "status_code": response.status_code,
                    "assertions": assertion_results,
                    "request": redact({"method": request["method"], "path": path, "query": query, "headers": headers, "body": body}),
                    "response_headers": redact(response.headers), "response_body": response.body,
                }
                runtime_variables.update(extract_values(response.body, response.headers, case.get("extract") or []))
                cleanup_results = []
                for cleanup in case.get("cleanup") or []:
                    try:
                        cleanup_request = resolve(cleanup, runtime_variables)
                        cleaned = execute_request(
                            cleanup_request["method"], base_url, cleanup_request["path"],
                            {**headers, **(cleanup_request.get("headers") or {})},
                            cleanup_request.get("body"), cleanup_request.get("query"),
                            cleanup_request.get("content_type", "application/json"),
                        )
                        cleanup_results.append({"status": "passed", "status_code": cleaned.status_code})
                    except Exception as cleanup_error:
                        cleanup_results.append({"status": "error", "error": str(cleanup_error)})
                result["cleanup_results"] = cleanup_results
            except Exception as exc:
                result = {"case_id": case_id, "name": case["name"], "status": "error", "elapsed_ms": 0, "error": str(exc)}
        results.append(result)
        statuses[str(case.get("id", case_id))] = result["status"]
        if on_result:
            on_result(result)
    summary = _summary(results); summary.update(started_at=started_at, finished_at=datetime.now().isoformat(timespec="seconds")); return results, summary


def _summary(results: list[dict]) -> dict:
    counts = Counter(x["status"] for x in results)
    total = len(results)
    return {"total": total, "passed": counts["passed"], "failed": counts["failed"], "error": counts["error"],
            "skipped": counts["skipped"], "pass_rate": round(counts["passed"] * 100 / total, 2) if total else 0}


def _expand_data_sets(cases: list[dict]) -> list[dict]:
    expanded = []
    for stored in cases:
        definition = json.loads(stored["definition_json"]) if isinstance(stored.get("definition_json"), str) else stored
        data_sets = definition.get("data_sets") or []
        if not data_sets:
            expanded.append(stored)
            continue
        for index, values in enumerate(data_sets, 1):
            variant = copy.deepcopy(definition)
            variant["name"] = f'{definition["name"]} [数据集 {index}]'
            variant["request"] = resolve(variant["request"], values)
            variant.pop("data_sets", None)
            wrapped = {**stored, "definition_json": json.dumps(variant, ensure_ascii=False)}
            expanded.append(wrapped)
    return expanded


def _parallel_safe(stored: dict) -> bool:
    definition = json.loads(stored["definition_json"]) if isinstance(stored.get("definition_json"), str) else stored
    return not definition.get("depends_on") and not definition.get("extract") and not definition.get("cleanup")
