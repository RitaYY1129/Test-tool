from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def build_combined_difference(document: Any, analysis: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
    """Compare API evidence with workflow/internal-state evidence conservatively."""
    endpoints = [
        f"{getattr(item, 'method', 'GET')} {getattr(item, 'path', '')}"
        for item in getattr(document, "endpoints", [])
    ]
    flow_model = workflow.get("flow_model") if isinstance(workflow, dict) else {}
    flow_model = flow_model if isinstance(flow_model, dict) else {}
    nodes = flow_model.get("nodes") or []
    hidden_nodes = [item for item in nodes if isinstance(item, dict) and item.get("visibility") == "hidden"]
    issues: list[dict[str, Any]] = []
    if hidden_nodes:
        issues.append({
            "kind": "hidden_state_unobserved", "severity": "warning",
            "message": "流程包含未被运行时观察验证的内部状态。",
            "nodes": [item.get("name") or item.get("key") for item in hidden_nodes],
        })
    if workflow.get("review_status") != "confirmed":
        issues.append({
            "kind": "workflow_not_confirmed", "severity": "error",
            "message": "工作流尚未经过人工确认，不能作为已验证流程。",
        })
    if not endpoints:
        issues.append({"kind": "endpoint_missing", "severity": "error", "message": "当前项目没有可比较的接口。"})
    evidence = analysis.get("evidence") if isinstance(analysis, dict) else []
    if not evidence:
        issues.append({"kind": "source_evidence_missing", "severity": "warning", "message": "没有导入可追溯的源码或文档证据。"})
    status = "passed" if not issues else "failed" if any(item["severity"] == "error" for item in issues) else "partial"
    return {
        "report_type": "A/B 差异报告", "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status, "endpoints": endpoints, "evidence_count": len(evidence),
        "workflow_review_status": workflow.get("review_status", "draft"),
        "hidden_node_count": len(hidden_nodes), "issues": issues,
    }


def generate_difference_report(output_dir: str | Path, project_name: str, difference: dict[str, Any]) -> tuple[Path, Path]:
    """Persist human-readable and machine-readable A/B difference reports."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    json_path = directory / f"difference-{stamp}.json"
    html_path = directory / f"difference-{stamp}.html"
    payload = {"project": project_name, **difference}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    issues = "".join(
        f"<li class='{html.escape(str(item.get('severity', 'warning')))}'><b>{html.escape(str(item.get('kind', '')))}</b>：{html.escape(str(item.get('message', '')))}</li>"
        for item in difference.get("issues", [])
    ) or "<li class='passed'>未发现差异</li>"
    document = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>A/B 差异报告</title><style>
body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:32px;color:#1f2937}}.error{{color:#b91c1c}}.warning{{color:#a16207}}.passed{{color:#15803d}}pre{{white-space:pre-wrap}}</style></head>
<body><h1>A/B 差异报告</h1><p>项目：{html.escape(project_name)}　状态：<b>{html.escape(str(difference.get('status', 'unknown')))}</b></p>
<h2>发现的问题</h2><ul>{issues}</ul><h2>完整数据</h2><pre>{html.escape(json.dumps(payload, ensure_ascii=False, indent=2, default=str))}</pre></body></html>"""
    html_path.write_text(document, encoding="utf-8")
    return html_path, json_path
