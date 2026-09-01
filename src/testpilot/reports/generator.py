from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def generate_report(
    output_dir: str | Path,
    project_name: str,
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    report_type: str = "接口契约报告",
    route: str = "route_b",
    environment: str = "",
) -> tuple[Path, Path]:
    """Write one immutable HTML/JSON report pair for an API test run."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    json_path = directory / f"api-{stamp}.json"
    html_path = directory / f"api-{stamp}.html"
    payload = {
        "project": project_name, "report_type": report_type, "route": route,
        "environment": environment, "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary, "results": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    rows = "".join(_row(result) for result in results)
    summary_json = html.escape(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    document = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>{html.escape(report_type)}</title><style>
body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:32px;color:#1f2937}}
table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{padding:10px;border:1px solid #ddd;text-align:left;vertical-align:top}}
.passed{{color:#15803d;font-weight:600}}.failed,.error{{color:#b91c1c;font-weight:600}}.skipped{{color:#a16207;font-weight:600}}
pre{{white-space:pre-wrap;word-break:break-word;margin:0}}details{{min-width:320px}}
</style></head><body><h1>{html.escape(report_type)}</h1>
<p>项目：{html.escape(project_name)}　环境：{html.escape(environment or '未命名环境')}　路线：{html.escape(route)}</p>
<h2>执行摘要</h2><pre>{summary_json}</pre><p>通过率：{html.escape(str(summary.get('pass_rate', 0)))}%</p>
<table><thead><tr><th>用例</th><th>模块</th><th>结果</th><th>耗时</th><th>状态码</th><th>证据</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    html_path.write_text(document, encoding="utf-8")
    return html_path, json_path


def _row(result: dict[str, Any]) -> str:
    status = str(result.get("status", "error"))
    evidence = {key: result[key] for key in (
        "error", "assertions", "request", "response_headers", "response_body", "cleanup_results"
    ) if key in result}
    detail = html.escape(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
    return (
        "<tr>"
        f"<td>{html.escape(str(result.get('name', '')))}</td>"
        f"<td>{html.escape(str(result.get('module', '')))}</td>"
        f"<td class='{html.escape(status)}'>{html.escape(status)}</td>"
        f"<td>{html.escape(str(result.get('elapsed_ms', 0)))} ms</td>"
        f"<td>{html.escape(str(result.get('status_code', '')))}</td>"
        f"<td><details><summary>查看</summary><pre>{detail}</pre></details></td>"
        "</tr>"
    )
