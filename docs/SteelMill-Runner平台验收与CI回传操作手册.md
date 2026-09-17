# SteelMill Runner 平台验收与 CI 回传操作手册

> 适用版本：TestPilot 当前工作区、steelmill-runner 0.1.0、RunManifest/RunResult 1.0。

## 1. 安全边界

- 只读任务默认执行，写入型任务必须同时满足 Manifest `allow_mutation=true`、环境能力 `allow_mutation=true` 和 Base URL 为 `localhost` 或环回 IP。
- Runner 命令来自平台登记项，页面不能拼接任意 Shell。
- 账号、密码、Token 只从本机加密配置或 Gitea Secret 注入，不写入 Manifest、Result、报告或日志。
- mutation Flow 必须串行执行，结束时无论成功失败都运行 ResourceLedger 补偿。

## 2. 平台端到端验收

1. 在“外部 Runner”高级设置中确认 `steelmill-runner 0.1.0`、Python、工作目录和启用状态。
2. 创建或确认测试环境。只读环境可关闭 mutation；写入环境的 Base URL 必须为环回地址。
3. 在“测试套件目录”刷新目录，选择只读 Smoke、离线 Unit 或完整现场作业 Flow。
4. 从套件卡片创建任务，填写任务名称和可选工单，核对右侧执行确认后创建。
5. 在“任务与结果”中点击任意单元格查看详情，核对状态、真实开始/完成时间、耗时、测试内容、流转数据、原始 Manifest 和原始结果。
6. 点击“打开产物目录”，确认同一 `run_id` 下至少有 `manifest.json`、`result.json`、`junit.xml`、`report.html`、`runner.log`。
7. 重复执行必须生成新的 `run_id`，不得覆盖历史证据。

## 3. 三类结果验收

| 场景 | 预期状态 | 必查证据 |
|---|---|---|
| 正常通过 | `passed` | Result 汇总与用例数一致，JUnit/HTML/日志可打开 |
| 业务断言失败 | `failed` | 用例分类为 `test_failure`，保留失败详情与请求时间线 |
| 初始化/环境失败 | `error` | 即使 pytest 未启动也生成四件套，Result 包含 `error` 和 `failure_phase=initialization` |

受控失败样例为 `tests/test_acceptance_failure_probe.py`。它先执行现有只读 GET，再故意断言失败；默认跳过，只有设置 `STEELMILL_ACCEPTANCE_FORCE_FAILURE=1` 并使用 `examples/run-manifest.controlled-failure.example.json` 时才运行。

## 4. Gitea 审批任务

- L2：手工触发 `Approved Read-only Smoke`，输入 `RUN_READONLY_SMOKE`。
- L3：在受保护环境批准后触发 `Approved Mutation Flow`，输入 `RUN_MUTATION_FLOW`。
- 两条任务均走 `runner.cli run --manifest`，上传 `reports/ci/<run_id>`。
- Result 元数据保存 `git_sha`、`ci_job_id`、`ci_job_url` 和 `runner_host`；TestPilot 详情页会展示这些执行来源。

## 5. 验收记录模板

每次正式验收记录：日期、审批人、环境、被测服务 SHA、测试资产 SHA、Runner 版本、平台任务号、run_id、CI Job URL、套件、结果、耗时、产物目录、清理结论和遗留问题。

## 6. 尚需外部环境完成

代码就绪不等于正式验收完成。以下项目必须在真实 Gitea/本机服务环境执行并留存制品：L2 首次通过、受控失败回传、L3 Flow 通过及清理确认、CI 通过 TestPilot CLI/API 自动归档。HTTPS、令牌轮换、受保护 Tag 和 Release 按发布维护窗口实施。
