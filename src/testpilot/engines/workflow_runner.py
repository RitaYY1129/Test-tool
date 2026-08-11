from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable

from testpilot.common.security import redact
from testpilot.engines.assertions import evaluate
from testpilot.engines.http_engine import execute_request
from testpilot.engines.variables import extract_values, resolve
from testpilot.engines.runtime_trace import TraceCollector
from testpilot.engines.side_effects import FileSideEffectObserver, MessageObserver
from testpilot.domain.process_script import evaluate_process_script


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class WorkflowError(RuntimeError):
    pass


@dataclass(slots=True)
class SqliteTestDatabase:
    target_path: str
    read_only: bool = True

    def _path(self) -> Path:
        path = Path(self.target_path).expanduser().resolve()
        if not path.is_file():
            raise WorkflowError(f"SQLite 测试数据库不存在：{path}")
        return path

    def connect(self, write: bool = False) -> sqlite3.Connection:
        if write and self.read_only:
            raise WorkflowError("当前数据库连接是只读的，不能准备数据或执行补偿删除")
        path = self._path()
        if write:
            connection = sqlite3.connect(path)
        else:
            uri = f"file:{path.as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def query(self, statement: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict]:
        normalized = statement.lstrip().lower()
        if not (normalized.startswith("select") or normalized.startswith("with")):
            raise WorkflowError("数据库断言只允许 SELECT/WITH 查询")
        with self.connect(False) as connection:
            return [dict(row) for row in connection.execute(statement, params or [])]

    def snapshot(self, observations: list[dict], variables: dict | None = None) -> dict:
        """Read a named set of SELECT observations for before/after checks."""
        runtime = variables or {}
        result = {}
        for index, observation in enumerate(observations):
            name = str(observation.get("name") or f"observation_{index + 1}")
            statement = str(resolve(observation.get("query", ""), runtime))
            result[name] = self.query(statement, resolve(observation.get("params") or [], runtime))
        return result

    def insert_fixture(self, fixture: dict) -> dict:
        table = str(fixture.get("table", ""))
        rows = fixture.get("rows") or []
        _assert_identifier(table)
        if not rows or not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise WorkflowError("夹具必须包含非空 rows 对象数组")
        columns = list(rows[0])
        if not columns or not all(_IDENTIFIER.fullmatch(str(column)) for column in columns):
            raise WorkflowError("夹具字段名包含不安全字符")
        if any(set(row) != set(columns) for row in rows):
            raise WorkflowError("夹具各行必须使用相同字段")
        marks = ",".join("?" for _ in columns)
        sql = f"INSERT INTO {_quote(table)} ({','.join(_quote(x) for x in columns)}) VALUES ({marks})"
        with self.connect(True) as connection:
            ids = []
            for row in rows:
                cursor = connection.execute(sql, [row[column] for column in columns])
                ids.append(row["id"] if "id" in columns else cursor.lastrowid)
            return {"table": table, "inserted": len(rows), "ids": ids}

    def delete_rows(self, action: dict, variables: dict) -> dict:
        table = str(action.get("table", ""))
        where = resolve(action.get("where") or {}, variables)
        _assert_identifier(table)
        if not where or not isinstance(where, dict) or not all(_IDENTIFIER.fullmatch(str(key)) for key in where):
            raise WorkflowError("补偿删除必须提供安全的 where 字段")
        clauses = " AND ".join(f"{_quote(key)}=?" for key in where)
        with self.connect(True) as connection:
            cursor = connection.execute(
                f"DELETE FROM {_quote(table)} WHERE {clauses}", list(where.values())
            )
            return {"table": table, "deleted": cursor.rowcount, "where": redact(where)}


def run_workflow(workflow: dict, base_url: str, common_headers: dict | None = None,
                 variables: dict | None = None, database: SqliteTestDatabase | None = None,
                 fixtures: list[dict] | None = None, on_step: Callable[[dict], None] | None = None,
                 stop_event: Event | None = None, trace: TraceCollector | None = None,
                 file_observer: FileSideEffectObserver | None = None,
                 message_observer: MessageObserver | None = None) -> tuple[list[dict], dict]:
    """Run a confirmed workflow sequentially with assertions and compensation."""
    if workflow.get("review_status") != "confirmed":
        raise WorkflowError("业务流程必须先人工确认")
    steps = workflow.get("steps") or []
    runtime = dict(variables or {})
    results: list[dict] = []
    compensations: list[dict] = []
    failed = False
    started = time.perf_counter()
    started_at = datetime.now().isoformat(timespec="seconds")
    observations = workflow.get("state_observations") or []
    state_before = database.snapshot(observations, runtime) if observations and database else {}
    files_before = file_observer.snapshot() if file_observer else {}
    messages_before = message_observer.snapshot() if message_observer else []
    if trace:
        trace.start_span(workflow.get("name", "workflow"), route="route_a")
        if state_before:
            trace.record("database.snapshot", "before", data=state_before)

    for fixture in fixtures or []:
        if not database:
            raise WorkflowError("准备数据库夹具需要配置测试数据库")
        result = database.insert_fixture(fixture)
        results.append({"name": fixture.get("name", "fixture"), "kind": "fixture", "status": "passed", **result})
        for row_id in result.get("ids") or []:
            if row_id is not None:
                compensations.append({"kind": "db_delete", "table": result["table"], "where": {"id": row_id}})
        compensation = fixture.get("compensation")
        if compensation:
            compensations.append(compensation)

    for index, step in enumerate(steps, 1):
        if stop_event and stop_event.is_set():
            result = {"step_order": index, "name": step.get("name", f"步骤 {index}"), "status": "skipped", "error": "任务已停止"}
            results.append(result)
            if on_step:
                on_step(result)
            failed = True
            break
        step_started = time.perf_counter()
        result = {"step_order": index, "name": step.get("name", f"步骤 {index}"), "kind": step.get("kind", "http")}
        if trace:
            trace.start_span(result["name"], step_order=index, kind=result["kind"])
        try:
            kind = step.get("kind", "http")
            if kind == "http":
                result.update(_run_http_step(step, base_url, common_headers or {}, runtime))
            elif kind == "db_assertion":
                if not database:
                    raise WorkflowError("数据库断言需要配置测试数据库")
                result.update(_run_db_assertion(step, database, runtime))
            elif kind == "state_assertion":
                if not database:
                    raise WorkflowError("状态断言需要配置测试数据库")
                result.update(_run_db_assertion(step, database, runtime))
            elif kind == "fixture":
                if not database:
                    raise WorkflowError("夹具步骤需要配置测试数据库")
                inserted = database.insert_fixture(resolve(step.get("fixture") or {}, runtime))
                result.update(status="passed", **inserted)
                for row_id in inserted.get("ids") or []:
                    if row_id is not None:
                        compensations.append({"kind": "db_delete", "table": inserted["table"], "where": {"id": row_id}})
                if step.get("compensation"):
                    compensations.append(step["compensation"])
            elif kind == "side_effect_check":
                result.update(_run_http_step(step, base_url, common_headers or {}, runtime, side_effect=True))
            elif kind == "file_assertion":
                if not file_observer:
                    raise WorkflowError("文件副作用断言需要配置测试目录观测器")
                changes = file_observer.diff(files_before, file_observer.snapshot())
                expected = step.get("expected_change")
                passed = expected is None or any(item.get("path") == expected.get("path") and item.get("change") == expected.get("change") for item in changes)
                result.update(status="passed" if passed else "failed", changes=changes)
            elif kind == "message_assertion":
                if not message_observer:
                    raise WorkflowError("消息副作用断言需要配置消息观测器")
                expected = step.get("expected") or {}
                events = message_observer.find(expected.get("topic"), expected.get("field"), expected.get("value"))
                result.update(status="passed" if events else "failed", events=events, before_count=len(messages_before))
            else:
                raise WorkflowError(f"不支持的流程步骤类型：{kind}")
            if step.get("compensation") and kind not in {"fixture"}:
                compensations.append(step["compensation"])
        except Exception as exc:
            result.update(status="error", error=str(exc))
            failed = True
        if result.get("status") in {"failed", "error"}:
            failed = True
        result["elapsed_ms"] = round((time.perf_counter() - step_started) * 1000)
        results.append(result)
        if trace:
            trace.finish_span(result["name"], result.get("status", "error"), step_order=index, result=redact(result))
        if on_step:
            on_step(result)
        if failed:
            break

    compensation_results = _run_compensations(compensations, database, base_url, common_headers or {}, runtime)
    state_after = database.snapshot(observations, runtime) if observations and database else {}
    files_after = file_observer.snapshot() if file_observer else {}
    messages_after = message_observer.snapshot() if message_observer else []
    if trace and state_after:
        trace.record("database.snapshot", "after", data=state_after)
    state_check = _compare_state_observations(state_before, state_after, workflow.get("state_expectations") or {}) if observations and database else {"status": "not_configured"}
    if state_check.get("status") == "failed":
        failed = True
    if str(workflow.get("process_script_version", "")).startswith("2"):
        _attach_database_runtime_evidence(workflow, state_before, state_after, state_check)
        process_coverage = evaluate_process_script(workflow)
    else:
        process_coverage = {"status": "not_configured", "issues": []}
    evidence_gap = any(item.get("critical") for item in process_coverage.get("issues", []))
    status = "failed" if failed or any(item.get("status") == "error" for item in compensation_results) else ("inconclusive" if evidence_gap else "passed")
    if trace:
        trace.finish_span(workflow.get("name", "workflow"), status, summary_preview={"status": status, "compensations": len(compensation_results)})
    summary = {
        "status": status,
        "total_steps": len(steps),
        "completed_steps": sum(item.get("status") == "passed" for item in results if item.get("kind") != "fixture"),
        "failed_steps": sum(item.get("status") in {"failed", "error"} for item in results),
        "compensations": compensation_results,
        "state_observations": {"before": redact(state_before), "after": redact(state_after), "check": state_check},
        "side_effects": {"files": FileSideEffectObserver.diff(files_before, files_after) if file_observer else [], "messages_before": len(messages_before), "messages_after": len(messages_after)},
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "trace_id": trace.trace_id if trace else "",
        "process_coverage": process_coverage,
    }
    return results, summary


def _compare_state_observations(before: dict, after: dict, expectations: dict) -> dict:
    differences = {}
    for name in sorted(set(before) | set(after)):
        if name not in expectations:
            continue
        expected = expectations[name]
        actual = after.get(name)
        if isinstance(expected, dict) and expected.get("change") in {"changed", "unchanged"}:
            changed = before.get(name) != actual
            if changed != (expected["change"] == "changed"):
                differences[name] = {"expected": expected, "before": before.get(name), "after": actual}
        elif expected != actual:
            differences[name] = {"expected": expected, "actual": actual}
    return {"status": "not_configured" if not expectations else ("failed" if differences else "passed"), "differences": differences}


def _attach_database_runtime_evidence(workflow: dict, before: dict, after: dict, state_check: dict) -> None:
    failed_names = set((state_check.get("differences") or {}).keys())
    for step in workflow.get("steps") or []:
        for checkpoint in step.get("internal_checkpoints") or []:
            table = checkpoint.get("table")
            if table and table in before and table in after:
                checkpoint["observation"] = {
                    "status": "failed" if table in failed_names else "observed",
                    "adapter": "database_snapshot", "name": table,
                    "before": redact(before[table]), "after": redact(after[table]),
                }


def _run_http_step(step: dict, base_url: str, common_headers: dict, variables: dict, side_effect: bool = False) -> dict:
    request = resolve(step.get("request") or {}, variables)
    headers = {**common_headers, **(request.get("headers") or {})}
    response = execute_request(
        request["method"], base_url, request["path"], headers,
        request.get("body"), request.get("query"), request.get("content_type", "application/json"),
    )
    assertions = [evaluate(item, response.status_code, response.elapsed_ms, response.body) for item in step.get("assertions", [])]
    passed = all(item["passed"] for item in assertions) if assertions else 200 <= response.status_code < 400
    variables.update(extract_values(response.body, response.headers, step.get("extract") or []))
    return {
        "status": "passed" if passed else "failed",
        "side_effect": side_effect,
        "status_code": response.status_code,
        "elapsed_ms": response.elapsed_ms,
        "assertions": assertions,
        "request": redact(request),
        "response_headers": redact(response.headers),
        "response_body": response.body,
    }


def _run_db_assertion(step: dict, database: SqliteTestDatabase, variables: dict) -> dict:
    assertion = resolve(step.get("assertion") or step, variables)
    rows = database.query(str(assertion.get("query", "")), assertion.get("params") or [])
    passed = True
    actual: Any = rows
    if "row_count" in assertion:
        actual = len(rows)
        passed = actual == assertion["row_count"]
    elif "value" in assertion:
        value = assertion["value"]
        if not rows or value.get("column") not in rows[0]:
            passed = False
            actual = None
        else:
            actual = rows[0][value["column"]]
            passed = actual == value.get("equals")
    elif "equals" in assertion:
        actual = next(iter(rows[0].values())) if rows and rows[0] else None
        passed = actual == assertion["equals"]
    return {"status": "passed" if passed else "failed", "rows": redact(rows), "assertion": redact(assertion), "actual": redact(actual)}


def _run_compensations(actions: list[dict], database: SqliteTestDatabase | None, base_url: str,
                       headers: dict, variables: dict) -> list[dict]:
    results = []
    for action in reversed(actions):
        try:
            kind = action.get("kind", "http")
            if kind == "db_delete":
                if not database:
                    raise WorkflowError("数据库补偿需要配置测试数据库")
                value = database.delete_rows(action, variables)
            elif kind == "http":
                value = _run_http_step({"request": action.get("request"), "assertions": action.get("assertions", [])}, base_url, headers, variables)
            else:
                raise WorkflowError(f"不支持的补偿类型：{kind}")
            results.append({"status": "passed", "kind": kind, **value})
        except Exception as exc:
            results.append({"status": "error", "kind": action.get("kind", "unknown"), "error": str(exc)})
    return results


def _assert_identifier(value: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise WorkflowError(f"不安全的数据库标识符：{value}")


def _quote(value: str) -> str:
    _assert_identifier(value)
    return f'"{value}"'
