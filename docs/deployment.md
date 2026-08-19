# 部署、定时任务与 CI/CD

## 运行约束

桌面端用于创建项目、环境和用例；自动化执行使用无界面命令行。桌面版请使用 Python 3.12 或 3.13，因为 PySide6 当前没有 Python 3.14 可用安装包。Python 3.14 可运行无界面 CLI、定时任务和 CI/CD；项目也已移除会崩溃的旧版 `cryptography` 运行时依赖。

安装无界面执行器：

```powershell
pip install -e ".[dev]"
```

安装桌面版：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[desktop,dev]"
testpilot-ai
```

## 命令行执行

### 从零开始的终端闭环

下面不需要桌面版。把 `openapi.json` 换成你的接口文档路径，并将 Base URL 换成测试环境地址：

```powershell
$db = ".\data\testpilot.db"
testpilot-run --db $db project-create --name "订单接口回归"
testpilot-run --db $db environment-set --project 1 --name "测试环境" --base-url "http://127.0.0.1:8080"
testpilot-run --db $db openapi-import --project 1 --input .\openapi.json
testpilot-run --db $db cases-generate --project 1
testpilot-run --db $db cases-confirm --project 1
testpilot-run --db $db run --project 1 --environment "测试环境" --retries 2
```

`cases-confirm` 默认只确认 GET/HEAD/OPTIONS 用例。要确认包含 POST、PUT、PATCH、DELETE 的用例，需显式执行 `cases-confirm --project 1 --all`；请只针对已授权的测试或预发布环境使用。

```powershell
testpilot-run --db .\data\testpilot.db run --project 1 --environment "测试环境" --retries 2
testpilot-run --db .\data\testpilot.db trend --project 1
```

失败时命令返回码为 `2`，成功为 `0`，所以 Jenkins、GitHub Actions 和 GitLab CI 可以直接调用。CLI 会保存每次执行记录、失败详情和 HTML/JSON 报告。

通知配置使用 JSON 文件。Webhook 兼容企业微信/钉钉机器人：

```json
{"kind":"webhook","url":"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."}
```

也可用 SMTP：`{"kind":"email","host":"smtp.example.com","from":"qa@example.com","to":"team@example.com","username":"...","password":"..."}`。仅在失败或执行错误时通知。

## 定时执行

通过 CLI 创建、查看和管理任务：

```powershell
testpilot-run --db .\data\testpilot.db schedule-add --project 1 --environment "测试环境" --interval-minutes 60 --retries 2 --notify-json .\notify.json
testpilot-run --db .\data\testpilot.db schedule-list --project 1
testpilot-run --db .\data\testpilot.db schedule-toggle --id 1 --enabled false
```

启动调度器：

```powershell
testpilot-run --db .\data\testpilot.db schedule
```

调度器持续扫描到期任务；`--once` 用于 Windows 任务计划程序或 CI 的单次扫描。

## 用例模板复用

```powershell
testpilot-run --db .\data\testpilot.db export-cases --project 1 --output .\smoke-cases.json
testpilot-run --db .\data\testpilot.db import-cases --project 2 --input .\smoke-cases.json
```

导入用例默认是草稿，需在桌面端确认后才会由 CLI 或定时任务执行。这避免模板意外触发写操作。通知发送失败不会覆盖已落库的执行结果，报告摘要会记录 `notification_error`。

## Docker

先用桌面端或 CLI 在 `./data/testpilot.db` 中创建项目、环境、已确认用例及定时任务，再执行：

```powershell
docker compose up --build -d
```

容器将数据库和报告保存在本机 `./data`，重启不会丢失执行历史。手动执行单次任务：

```powershell
docker compose run --rm testpilot-runner run --project 1 --environment "测试环境" --retries 2
```

## 5～10 分钟演示

1. 新建项目，导入 OpenAPI 或手动添加接口。
2. 配置“测试环境”的 Base URL、Header 和变量，生成并确认用例。
3. 在终端执行 `testpilot-run ... run`，观察结果、退出码和生成的报告路径。
4. 打开桌面端“历史测试报告”，查看逐用例失败日志和汇总。
5. 故意修改断言或目标地址，演示重试、失败报告以及机器人/邮件通知。
6. 执行 `trend`，展示历史通过率序列；最后启动 `schedule` 演示定时回归。
