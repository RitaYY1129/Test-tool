# TestPilot AI

第一阶段桌面版本：双路线接口导入、资料完整度、测试计划、结构化用例、
人工确认、确定性执行、证据记录和独立报告。

## 运行

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[desktop,dev]"
testpilot-ai
```

桌面版依赖 PySide6，请使用 Python 3.12 或 3.13；当前 Python 3.14 可用于无界面 CLI、定时任务和 CI/CD，但不能安装桌面 UI 依赖。

也可以执行：

```powershell
$env:PYTHONPATH="src"
python -m testpilot.main
```

数据默认保存在 `%LOCALAPPDATA%\TestPilotAI\testpilot.db`。运行测试：

```powershell
pytest
```

## 自动化交付闭环

桌面端负责导入、环境与用例管理；新增无界面执行器用于定时回归、Docker 和 CI/CD。它支持失败重试、企业微信/钉钉 Webhook 或 SMTP 失败通知、历史通过率趋势 JSON，以及 HTML/JSON 报告。

```powershell
testpilot-run --db .\data\testpilot.db run --project 1 --environment "测试环境" --retries 2
testpilot-run --db .\data\testpilot.db schedule
```

部署、通知配置、Docker 和演示流程见 [部署说明](docs/deployment.md)。

### SteelMill 外部 Runner 归档

TestPilot 可作为 SteelMill Runner 的控制与归档端：登记项目、环境、Runner 和 Manifest，校验
版本与 mutation 策略，随后归档 Runner 输出的 `result.json`。下列 CLI **不会执行 Shell 或启动
SteelMill**；实际 Runner 仍在 SteelMill 仓库、Docker 或 CI Worker 中受控执行。

```powershell
# 先创建项目和环境；capabilities 约束该环境是否允许 mutation。
testpilot-run --db .\data\testpilot.db environment-set --project 1 --name staging `
  --base-url https://staging.example.test `
  --capabilities-json '{"allow_mutation": false}' `
  --secret-refs-json '["steelmill-staging-account"]'

# 注册固定版本的 Runner，再登记 Manifest；命令返回 runner_run_id。
testpilot-run --db .\data\testpilot.db runner-register --project 1 `
  --project-key steelmill --name steelmill-runner --version 0.1.0
testpilot-run --db .\data\testpilot.db runner-run-queue --manifest .\run-manifest.json

# Runner 完成后归档其标准结果，并查询运行记录。
testpilot-run --db .\data\testpilot.db runner-run-complete --run-id 1 --result .\result.json
testpilot-run --db .\data\testpilot.db runner-run-list --project 1
```

## 当前范围

> 说明：当前路线 A 是“源码证据 + 基础业务流程执行”原型，不等于完整的隐藏工艺覆盖；多数据库、消息/第三方副作用观测、运行时链路和 AI 受控对话按 [V4.0 落地规划](docs/project-plan-v4.0.md) 分阶段实现。

- 创建、选择和删除测试项目
- 保存多套测试环境
- 导入 OpenAPI 3.x、Swagger 2.0 JSON/YAML、Postman Collection v2.1、cURL 和 HAR
- 自动识别 ASP.NET Core 与 Spring Boot 后端源码，从 Controller 提取路由、参数、
  DTO、鉴权信息和源码位置
- 展示接口、参数、请求体、响应和来源
- 统计资料完整度并给出补充建议
- 配置 Base URL、Header，手工发送单个 HTTP 请求
- 预览测试计划，按接口约束生成结构化用例
- 人工确认高风险用例后批量执行
- 状态码、响应耗时和 JSONPath 断言
- 请求结果展示与敏感字段脱敏
- SQLite 保存用例、运行结果和报告记录
- 导出独立 HTML/JSON 测试报告
- 源码方法/事务/SQL 写入证据、运行时 Trace、A/B 差异报告和脱敏可重放测试包
- SQLite schema 观测及可选 PostgreSQL/MySQL DB-API 适配器（需项目自行安装驱动）

详细能力边界与验收状态见 [第一阶段验收清单](docs/phase1-acceptance.md)，操作流程见
[使用说明](docs/user-guide.md)，当前项目规划基线见
[V4.0 落地规划](docs/project-plan-v4.0.md)。

## Windows 构建

在安装依赖并确认桌面程序可运行后执行：

```powershell
.\scripts\build_windows.ps1
```

脚本使用 PyInstaller one-folder 模式构建不要求用户预装 Python 的目录版程序。
本次已生成并启动验证 `release/TestPilotAI/TestPilotAI.exe`。
## 三种 AI 接入方式

- **Codex · ChatGPT 登录**：在“AI 与 Codex”页面检测或安装官方 Codex CLI，
  使用 ChatGPT 完成登录，选择源码目录后生成用例。TestPilot 不读取或保存登录凭证。
- **兼容 API**：配置 OpenAI 兼容的 Base URL、模型和 API Token。Token 使用本机密钥加密。
- **本地 Ollama**：启动 Ollama，填写本地地址和模型名称，无需 API Token。

三种方式生成的内容都会经过 JSON Schema 校验，并以草稿状态进入 TestPilot，
需要人工确认后才能执行。Codex 模式使用只读沙箱，不修改导入的源码项目。
