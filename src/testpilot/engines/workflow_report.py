from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path


def generate_workflow_report(output_dir: str | Path, project_name: str, workflow_name: str,
                             results: list[dict], summary: dict, report_type: str = "业务流程报告",
                             route: str = "route_a", environment: str = "") -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = directory / f"workflow-{stamp}.json"
    html_path = directory / f"workflow-{stamp}.html"
    payload = {
        "project": project_name, "workflow": workflow_name,
        "report_type": report_type, "route": route, "environment": environment,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary, "results": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "".join(
        f"<tr><td>{html.escape(str(item.get('step_order', '')))}</td>"
        f"<td>{html.escape(str(item.get('name', '')))}</td>"
        f"<td class='{html.escape(str(item.get('status', 'error')))}'>{html.escape(str(item.get('status', 'error')))}</td>"
        f"<td>{html.escape(str(item.get('elapsed_ms', 0)))} ms</td>"
        f"<td><pre>{html.escape(json.dumps({k: item.get(k) for k in ('error','assertions','rows','compensations') if k in item}, ensure_ascii=False, indent=2))}</pre></td></tr>"
        for item in results
    )
    document = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>TestPilot AI 业务流程审计报告</title><style>
body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:32px;color:#1f2937}}
table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{padding:10px;border:1px solid #ddd;text-align:left;vertical-align:top}}
.passed{{color:#15803d}}.failed,.error{{color:#b91c1c}}.skipped{{color:#a16207}}pre{{white-space:pre-wrap}}
</style></head><body><h1>业务流程审计报告</h1>
<p>项目：{html.escape(project_name)}　流程：{html.escape(workflow_name)}</p>
<p>类型：{html.escape(report_type)}　路线：{html.escape(route)}　环境：{html.escape(environment or '未命名环境')}</p>
<pre>{html.escape(json.dumps(summary, ensure_ascii=False, indent=2))}</pre>
<table><thead><tr><th>步骤</th><th>名称</th><th>结果</th><th>耗时</th><th>证据</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    html_path.write_text(document, encoding="utf-8")
    return html_path, json_path
