from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from testpilot.common.security import SecretStore
from testpilot.engines.database_adapters import create_database_adapter
from testpilot.engines.runtime_trace import TraceCollector
from testpilot.engines.workflow_report import generate_workflow_report
from testpilot.engines.workflow_runner import run_workflow
from testpilot.storage.database import Database


SOURCE_ROOT = Path(r"D:\qingfeng\ZIYAN\Love\love-diary-backend")
BASE_URL = "http://127.0.0.1:3000"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def main() -> None:
    data_dir = Path(os.environ["LOCALAPPDATA"]) / "TestPilotAI"
    db = Database(data_dir / "testpilot.db")
    secret_store = SecretStore(data_dir / "config" / "master.key")
    env = read_env(SOURCE_ROOT / ".env")

    with db.connect() as connection:
        project = connection.execute(
            """SELECT p.id,p.name FROM projects p JOIN source_projects s ON s.project_id=p.id
               WHERE s.root_path=? ORDER BY p.id DESC LIMIT 1""",
            (str(SOURCE_ROOT),),
        ).fetchone()
        analysis = connection.execute(
            """SELECT a.id FROM analysis_runs a JOIN source_projects s ON s.id=a.source_project_id
               WHERE s.root_path=? ORDER BY a.id DESC LIMIT 1""",
            (str(SOURCE_ROOT),),
        ).fetchone()
    if not project:
        raise RuntimeError("TestPilot 中尚未导入 love-diary-backend 项目。")
    project_id, project_name = int(project["id"]), str(project["name"])

    public_db_config = {
        "host": env.get("DB_HOST", "localhost"),
        "port": int(env.get("DB_PORT", "3306")),
        "user": env.get("DB_USER", "root"),
        "database": env.get("DB_NAME", "love_diary"),
    }
    password = env.get("DB_PASSWORD", "")
    encrypted = secret_store.encrypt_dict({"password": password}) if password else ""
    db.save_environment(project_id, "本地联合测试环境", BASE_URL, {}, {})
    connection_id = db.save_db_connection(
        project_id, "love_diary MySQL（只读观测）", "", read_only=True,
        config=public_db_config, secrets_encrypted=encrypted, backend="mysql",
    )

    adapter = create_database_adapter("mysql", "", True, {**public_db_config, "password": password})
    ping = adapter.query("SELECT 1 AS connected")
    table_rows = adapter.query("SHOW TABLES")
    table_names = [str(next(iter(row.values()))) for row in table_rows]
    snapshot_id = db.save_db_schema_snapshot(project_id, connection_id, {
        "backend": "mysql", "target": f"{public_db_config['host']}:{public_db_config['port']}/{public_db_config['database']}",
        "status": "healthy", "connected": ping, "table_count": len(table_names), "tables": table_names,
    })

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    workflow = {
        "name": f"love-diary 后端只读联合验证 {stamp}",
        "review_status": "confirmed",
        "scope_confirmed": True,
        "requires_confirmation": False,
        "test_focus": ["服务健康", "登录参数校验", "未授权访问拦截", "MySQL 连接与数据不变性"],
        "state_observations": [{"name": "users_count", "query": "SELECT COUNT(*) AS count FROM users"}],
        "state_expectations": {"users_count": {"change": "unchanged"}},
        "steps": [
            {
                "name": "后端健康检查", "kind": "http", "review_status": "confirmed",
                "request": {"method": "GET", "path": "/api/health", "headers": {}, "query": {}, "body": None},
                "assertions": [
                    {"type": "status_code", "expected": 200},
                    {"type": "json_path", "path": "$.status", "operator": "equals", "expected": "ok"},
                ],
            },
            {
                "name": "登录接口空参数校验", "kind": "http", "review_status": "confirmed",
                "request": {"method": "POST", "path": "/api/auth/login", "headers": {}, "query": {}, "body": {}},
                "assertions": [{"type": "status_code", "expected": 400}],
            },
            {
                "name": "个人资料接口未授权拦截", "kind": "http", "review_status": "confirmed",
                "request": {"method": "GET", "path": "/api/auth/profile", "headers": {}, "query": {}, "body": None},
                "assertions": [{"type": "status_code", "expected": 401}],
            },
            {
                "name": "MySQL 用户表只读检查", "kind": "db_assertion", "review_status": "confirmed",
                "assertion": {"query": "SELECT COUNT(*) AS count FROM users", "row_count": 1},
            },
        ],
    }
    workflow_id = db.save_workflow(
        project_id, workflow["name"], workflow,
        source_analysis_run_id=int(analysis["id"]) if analysis else None,
    )
    run_id = db.create_workflow_run(project_id, workflow_id, connection_id)
    trace = TraceCollector()
    results, summary = run_workflow(workflow, BASE_URL, database=adapter, trace=trace)
    for index, result in enumerate(results, 1):
        db.save_workflow_step_result(
            run_id, None, int(result.get("step_order", index)), result.get("status", "error"), result,
        )
    db.finish_workflow_run(run_id, summary["status"], summary)
    trace_row_id = db.save_workflow_trace(run_id, trace.to_dict(), summary["status"])
    db.audit_workflow(run_id, "workflow_completed", summary)
    html_path, json_path = generate_workflow_report(
        data_dir / "reports", project_name, workflow["name"], results, summary,
        report_type="API + MySQL 只读联合测试", route="route_a", environment="本地联合测试环境",
    )
    db.save_workflow_report(
        run_id, str(html_path), str(json_path), "API + MySQL 只读联合测试", "route_a", "本地联合测试环境",
    )
    db.audit(project_id, "real_backend_validation", {
        "workflow_id": workflow_id, "run_id": run_id, "snapshot_id": snapshot_id,
        "trace_row_id": trace_row_id, "status": summary["status"], "table_count": len(table_names),
    })
    print(json.dumps({
        "project_id": project_id, "workflow_id": workflow_id, "run_id": run_id,
        "snapshot_id": snapshot_id, "trace_row_id": trace_row_id,
        "status": summary["status"], "completed_steps": summary["completed_steps"],
        "total_steps": summary["total_steps"], "table_count": len(table_names),
        "html_report": str(html_path), "json_report": str(json_path), "results": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
