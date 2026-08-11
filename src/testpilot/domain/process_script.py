from __future__ import annotations

"""Route A process-script construction and evidence completeness checks."""

from typing import Any
import json
import re


CRITICAL_INTERNAL_KINDS = {"transaction", "database_write", "message_publish", "external_call"}


def build_process_script(workflow: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """Enrich endpoint steps with internal candidates; static evidence is not runtime proof."""
    candidates = []
    for item in analysis.get("evidence") or []:
        details = item.get("details") or item.get("details_json") or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except (TypeError, ValueError):
                details = {}
        kind = _checkpoint_kind(str(item.get("evidence_type") or "source"), details)
        if kind:
            candidates.append({
                "id": f"internal-{len(candidates) + 1}",
                "name": details.get("symbol") or details.get("method") or item.get("evidence_type"),
                "kind": kind,
                "expectation": _expectation(kind, details),
                "evidence": [{"type": "static_source", "locator": _locator(item), "confidence": "static"}],
                "observation": {"status": "unobserved", "adapter": ""},
                "critical": kind in CRITICAL_INTERNAL_KINDS,
                "table": details.get("table", ""),
            })
    for edge in analysis.get("edges") or []:
        metadata = edge.get("metadata") or edge.get("metadata_json") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (TypeError, ValueError):
                metadata = {}
        table = str(metadata.get("table") or "")
        if edge.get("edge_type") == "writes" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            candidates.append({
                "id": f"internal-{len(candidates) + 1}", "name": f"写入表 {table}",
                "kind": "database_write", "table": table,
                "expectation": f"表 {table} 的数据变化与接口业务结果一致",
                "evidence": [{"type": "static_source", "locator": _locator(edge), "confidence": "static"}],
                "observation": {"status": "configured", "adapter": "database_snapshot", "name": table},
                "critical": True,
            })
    for step in workflow.get("steps") or []:
        if step.get("kind", "http") == "http":
            step.setdefault("phase", "external")
            step.setdefault("preconditions", [])
            step.setdefault("internal_checkpoints", [dict(item) for item in candidates])
            step.setdefault("failure_branches", [])
            step.setdefault("invariants", [])
    workflow["process_script_version"] = "2.0"
    workflow.setdefault("launch_profile", {"mode": "external", "working_directory": analysis.get("root_path", ""), "healthcheck_url": "", "note": "默认连接用户已启动的测试后端；受控启动配置需人工确认。"})
    workflow["call_chain"] = [{"from": edge.get("source_symbol", ""), "to": edge.get("target_symbol", ""), "kind": edge.get("edge_type", "calls"), "evidence": {"locator": _locator(edge), "confidence": "inferred"}} for edge in analysis.get("edges") or []]
    workflow.setdefault("state_observations", [])
    workflow.setdefault("state_expectations", {})
    known_observations = {item.get("name") for item in workflow["state_observations"]}
    for table in sorted({item.get("table") for item in candidates if item.get("table")}):
        if table not in known_observations:
            workflow["state_observations"].append({"name": table, "query": f"SELECT * FROM {table} LIMIT 200", "params": [], "source": "static_write_evidence"})
        workflow["state_expectations"].setdefault(table, {"change": "changed"})
    workflow.setdefault("invariants", [])
    workflow.setdefault("failure_scenarios", [])
    workflow.setdefault("cleanup", [])
    workflow["coverage"] = evaluate_process_script(workflow)
    return workflow


def evaluate_process_script(workflow: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    total = observed = critical_total = critical_observed = 0
    for step_index, step in enumerate(workflow.get("steps") or [], 1):
        if step.get("kind", "http") != "http":
            continue
        checkpoints = step.get("internal_checkpoints") or []
        if not checkpoints:
            issues.append(_issue("missing_internal_process", step_index, "接口动作没有内部工艺检查点", False))
        for checkpoint in checkpoints:
            total += 1
            critical = bool(checkpoint.get("critical") or checkpoint.get("kind") in CRITICAL_INTERNAL_KINDS)
            is_observed = checkpoint.get("observation", {}).get("status") in {"observed", "passed", "failed"}
            critical_total += int(critical)
            observed += int(is_observed)
            critical_observed += int(critical and is_observed)
            if not is_observed:
                issues.append(_issue("critical_internal_unobserved" if critical else "internal_unobserved", step_index, f"内部节点“{checkpoint.get('name', checkpoint.get('kind', 'unknown'))}”尚无运行证据", critical, checkpoint.get("id", "")))
        if not step.get("failure_branches"):
            issues.append(_issue("missing_failure_branch", step_index, "尚未描述异常/回滚分支", False))
        if not step.get("invariants") and not workflow.get("invariants"):
            issues.append(_issue("missing_invariant", step_index, "尚未定义跨层数据一致性约束", False))
    score = 100 if not total else round(observed * 100 / total)
    return {"status": "complete" if not issues else "incomplete", "score": score, "internal_total": total, "internal_observed": observed, "critical_total": critical_total, "critical_observed": critical_observed, "issues": issues}


def validate_process_script(workflow: dict[str, Any], require_observed: bool = False) -> list[str]:
    if not str(workflow.get("process_script_version", "")).startswith("2"):
        return []
    coverage = evaluate_process_script(workflow)
    workflow["coverage"] = coverage
    return [item["message"] for item in coverage["issues"] if item["critical"]] if require_observed else []


def _issue(kind: str, step: int, message: str, critical: bool, checkpoint_id: str = "") -> dict:
    return {"kind": kind, "step": step, "checkpoint_id": checkpoint_id, "message": message, "critical": critical}


def _locator(item: dict) -> str:
    path, line = item.get("file_path") or item.get("source") or "", item.get("line_start") or item.get("line")
    return f"{path}:{line}" if path and line else str(path)


def _checkpoint_kind(evidence_type: str, details: dict) -> str:
    text = f"{evidence_type} {details}".lower()
    if "transaction" in text: return "transaction"
    if any(x in text for x in ("sql_write", "insert", "update", "delete", "savechanges")): return "database_write"
    if any(x in text for x in ("publish", "message", "event")): return "message_publish"
    if any(x in text for x in ("httpclient", "external", "remote")): return "external_call"
    return ""


def _expectation(kind: str, details: dict) -> str:
    defaults = {"transaction": "事务提交与异常回滚符合预期", "database_write": "写入数据与外部响应保持一致", "message_publish": "消息主题、载荷和次数符合预期", "external_call": "外部请求及失败处理符合预期"}
    return details.get("statement") or details.get("operation") or defaults[kind]
