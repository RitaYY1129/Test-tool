from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from testpilot.common.security import SecretStore
from testpilot.cases.exchange import export_cases, import_cases
from testpilot.cases.generator import generate_cases
from testpilot.engines.batch_runner import run_cases
from testpilot.engines.external_runner import complete_external_run, queue_external_run
from testpilot.notifications import notify
from testpilot.parsers.completeness_checker import check_completeness
from testpilot.parsers.openapi_parser import OpenApiParser
from testpilot.reports.generator import generate_report
from testpilot.storage.database import Database


def _environment(db: Database, project_id: int, name: str) -> dict:
    row = next((item for item in db.list_environments(project_id) if item["name"] == name), None)
    if not row:
        raise ValueError(f"未找到环境：{name}")
    variables = json.loads(row["variables_json"] or "{}")
    if row.get("secrets_encrypted"):
        # Keep the CLI interoperable with environments saved by the desktop app.
        variables.update(SecretStore(db.path.parent / "config" / "master.key").decrypt_dict(row["secrets_encrypted"]))
    return {"base_url": row["base_url"], "headers": json.loads(row["headers_json"] or "{}"), "variables": variables}


def execute(db: Database, project_id: int, environment_name: str, retries: int = 0,
            notification: dict | None = None) -> tuple[dict, Path]:
    project = next((item for item in db.list_projects() if item["id"] == project_id), None)
    if not project:
        raise ValueError(f"未找到项目：{project_id}")
    environment = _environment(db, project_id, environment_name)
    cases = [case for case in db.list_test_cases(project_id) if case["review_status"] == "confirmed"]
    if not cases:
        raise ValueError("项目没有可执行用例")
    attempts = 0
    while True:
        results, summary = run_cases(cases, environment["base_url"], environment["headers"], variables=environment["variables"])
        attempts += 1
        if not (summary["failed"] or summary["error"]) or attempts > retries:
            break
    summary.update(attempts=attempts)
    run_id = db.create_run(project_id)
    for result in results:
        db.save_result(run_id, result.get("case_id"), result)
    db.finish_run(run_id, summary)
    html_path, json_path = generate_report(db.path.parent / "reports", project["name"], results, summary, environment=environment_name)
    db.save_report(run_id, str(html_path), str(json_path), environment=environment_name)
    if notification:
        try:
            notify(notification, project["name"], summary, str(html_path))
        except Exception as error:
            summary["notification_error"] = str(error)
            db.finish_run(run_id, summary)
    return summary, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TestPilot AI 无界面执行器")
    parser.add_argument("--db", default="testpilot.db", help="SQLite 数据库路径")
    sub = parser.add_subparsers(dest="command", required=True)
    project_create = sub.add_parser("project-create", help="创建测试项目")
    project_create.add_argument("--name", required=True)
    project_list = sub.add_parser("project-list", help="列出测试项目")
    environment_set = sub.add_parser("environment-set", help="创建或更新测试环境")
    environment_set.add_argument("--project", type=int, required=True)
    environment_set.add_argument("--name", required=True)
    environment_set.add_argument("--base-url", required=True)
    environment_set.add_argument("--headers-json", default="{}")
    environment_set.add_argument("--variables-json", default="{}")
    environment_set.add_argument("--capabilities-json", default="{}")
    environment_set.add_argument("--secret-refs-json", default="[]")
    environment_list = sub.add_parser("environment-list", help="列出项目环境")
    environment_list.add_argument("--project", type=int, required=True)
    openapi = sub.add_parser("openapi-import", help="导入 OpenAPI 或 Swagger 文件")
    openapi.add_argument("--project", type=int, required=True)
    openapi.add_argument("--input", required=True)
    generated = sub.add_parser("cases-generate", help="从已导入接口生成草稿用例")
    generated.add_argument("--project", type=int, required=True)
    generated.add_argument("--instruction", default="")
    confirmed = sub.add_parser("cases-confirm", help="确认项目内的草稿用例")
    confirmed.add_argument("--project", type=int, required=True)
    confirmed.add_argument("--all", action="store_true", help="确认全部草稿；包含写操作用例")
    case_list = sub.add_parser("cases-list", help="列出项目用例")
    case_list.add_argument("--project", type=int, required=True)
    run = sub.add_parser("run", help="执行一个项目")
    run.add_argument("--project", type=int, required=True)
    run.add_argument("--environment", required=True)
    run.add_argument("--retries", type=int, default=0)
    run.add_argument("--notify-json", default="", help="通知配置 JSON 文件")
    runner_register = sub.add_parser("runner-register", help="注册不执行 Shell 的外部 Runner")
    runner_register.add_argument("--project", type=int, required=True)
    runner_register.add_argument("--project-key", required=True, help="例如 steelmill")
    runner_register.add_argument("--name", required=True, help="例如 steelmill-runner")
    runner_register.add_argument("--version", required=True)
    runner_register.add_argument("--manifest-schema-version", default="1.0")
    runner_register.add_argument("--command", dest="runner_command", default="", help="仅保存供受控 Worker 使用，CLI 不会执行")
    runner_queue = sub.add_parser("runner-run-queue", help="校验并登记外部 Runner Manifest")
    runner_queue.add_argument("--manifest", required=True)
    runner_complete = sub.add_parser("runner-run-complete", help="归档外部 Runner result.json")
    runner_complete.add_argument("--run-id", type=int, required=True, help="平台运行记录 ID")
    runner_complete.add_argument("--result", required=True)
    runner_list = sub.add_parser("runner-run-list", help="列出外部 Runner 运行记录")
    runner_list.add_argument("--project", type=int, required=True)
    trend = sub.add_parser("trend", help="输出最近执行趋势 JSON")
    trend.add_argument("--project", type=int, required=True)
    export = sub.add_parser("export-cases", help="导出项目用例模板")
    export.add_argument("--project", type=int, required=True)
    export.add_argument("--output", required=True)
    imported = sub.add_parser("import-cases", help="导入用例模板，默认保存为草稿")
    imported.add_argument("--project", type=int, required=True)
    imported.add_argument("--input", required=True)
    add_schedule = sub.add_parser("schedule-add", help="创建定时回归任务")
    add_schedule.add_argument("--project", type=int, required=True)
    add_schedule.add_argument("--environment", required=True)
    add_schedule.add_argument("--interval-minutes", type=int, required=True)
    add_schedule.add_argument("--retries", type=int, default=0)
    add_schedule.add_argument("--notify-json", default="")
    schedules = sub.add_parser("schedule-list", help="列出定时任务")
    schedules.add_argument("--project", type=int)
    schedule_toggle = sub.add_parser("schedule-toggle", help="启用或停用定时任务")
    schedule_toggle.add_argument("--id", type=int, required=True)
    schedule_toggle.add_argument("--enabled", choices=("true", "false"), required=True)
    schedule_delete = sub.add_parser("schedule-delete", help="删除定时任务")
    schedule_delete.add_argument("--id", type=int, required=True)
    daemon = sub.add_parser("schedule", help="执行数据库中到期的定时任务")
    daemon.add_argument("--once", action="store_true", help="仅扫描并执行一次")
    daemon.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    db = Database(args.db)
    if args.command == "project-create":
        project_id = db.create_project(args.name)
        print(json.dumps({"project_id": project_id, "name": args.name}, ensure_ascii=False))
        return 0
    if args.command == "project-list":
        print(json.dumps(db.list_projects(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "environment-set":
        db.save_environment(
            args.project, args.name, args.base_url, json.loads(args.headers_json), json.loads(args.variables_json),
            capabilities=json.loads(args.capabilities_json), secret_refs=json.loads(args.secret_refs_json),
        )
        print(json.dumps({"project": args.project, "environment": args.name}, ensure_ascii=False))
        return 0
    if args.command == "environment-list":
        print(json.dumps(db.list_environments(args.project), ensure_ascii=False, indent=2))
        return 0
    if args.command == "openapi-import":
        document = OpenApiParser().parse_file(args.input)
        source_id = db.save_document(args.project, Path(args.input).name, document, check_completeness(document))
        print(json.dumps({"source_id": source_id, "endpoints": len(document.endpoints), "title": document.title}, ensure_ascii=False))
        return 0
    if args.command == "cases-generate":
        ids = db.save_test_cases(args.project, generate_cases(db.list_endpoints(args.project), args.instruction))
        print(json.dumps({"generated": len(ids), "case_ids": ids}, ensure_ascii=False))
        return 0
    if args.command == "cases-list":
        rows = db.list_test_cases(args.project)
        print(json.dumps([{"id": row["id"], "name": row["name"], "review_status": row["review_status"], "priority": row["priority"]} for row in rows], ensure_ascii=False, indent=2))
        return 0
    if args.command == "cases-confirm":
        rows = db.list_test_cases(args.project)
        if not args.all:
            rows = [row for row in rows if json.loads(row["definition_json"])["request"]["method"] in {"GET", "HEAD", "OPTIONS"}]
        for row in rows:
            db.update_case_status(row["id"], "confirmed")
        print(json.dumps({"confirmed": len(rows)}, ensure_ascii=False))
        return 0
    if args.command == "trend":
        print(json.dumps(db.trend_summary(args.project), ensure_ascii=False, indent=2))
        return 0
    if args.command == "export-cases":
        path = export_cases(db.list_test_cases(args.project), args.output)
        print(json.dumps({"exported": str(path)}, ensure_ascii=False))
        return 0
    if args.command == "import-cases":
        ids = db.save_test_cases(args.project, import_cases(args.input))
        print(json.dumps({"imported": len(ids), "case_ids": ids}, ensure_ascii=False))
        return 0
    if args.command == "schedule-add":
        _environment(db, args.project, args.environment)
        notification = json.loads(Path(args.notify_json).read_text(encoding="utf-8")) if args.notify_json else None
        schedule_id = db.save_schedule(args.project, args.environment, args.interval_minutes, args.retries, notification)
        print(json.dumps({"schedule_id": schedule_id}, ensure_ascii=False))
        return 0
    if args.command == "schedule-list":
        print(json.dumps(db.list_schedules(args.project), ensure_ascii=False, indent=2))
        return 0
    if args.command == "schedule-toggle":
        db.set_schedule_enabled(args.id, args.enabled == "true")
        return 0
    if args.command == "schedule-delete":
        db.delete_schedule(args.id)
        return 0
    if args.command == "run":
        notification = json.loads(Path(args.notify_json).read_text(encoding="utf-8")) if args.notify_json else None
        summary, report = execute(db, args.project, args.environment, args.retries, notification)
        print(json.dumps({"summary": summary, "report": str(report)}, ensure_ascii=False))
        return 0 if not (summary["failed"] or summary["error"]) else 2
    if args.command == "runner-register":
        db.save_project_adapter(args.project, args.project_key, {})
        runner_id = db.save_runner(
            args.project, args.name, version=args.version, command=args.runner_command,
            manifest_schema_version=args.manifest_schema_version,
        )
        print(json.dumps({"runner_id": runner_id, "project_key": args.project_key, "name": args.name}, ensure_ascii=False))
        return 0
    if args.command == "runner-run-queue":
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        run_id = queue_external_run(db, manifest)
        print(json.dumps({"runner_run_id": run_id, "run_id": manifest["run_id"], "status": "queued"}, ensure_ascii=False))
        return 0
    if args.command == "runner-run-complete":
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
        complete_external_run(db, args.run_id, result)
        print(json.dumps({"runner_run_id": args.run_id, "status": result["status"]}, ensure_ascii=False))
        return 0
    if args.command == "runner-run-list":
        print(json.dumps(db.list_runner_runs(args.project), ensure_ascii=False, indent=2))
        return 0
    while True:
        for task in db.list_due_schedules():
            try:
                execute(db, task["project_id"], task["environment_name"], task["retry_count"], json.loads(task["notification_json"]))
            except Exception as error:
                print(f"schedule {task['id']} failed: {error}", file=sys.stderr)
            finally:
                db.complete_schedule(task["id"])
        if args.once:
            return 0
        time.sleep(max(1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
