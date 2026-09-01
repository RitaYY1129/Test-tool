# Phase 1：SteelMill 框架工程化加固（2～4 周）

> 状态：进行中（已完成 Runner 协议、离线闭环、只读真实环境 Smoke 与平台受控归档；Docker 同 Manifest 证据和内部 CI 仍须在获准外部环境完成）
>
> 前置条件：Phase 0 的平台侧协议与持久化测试通过并提交；SteelMill 测试仓库可访问；具备一个可安全执行的 `api + smoke` 测试环境。
>
> 关联文档：[Phase 0：多项目接口自动化框架基线](phase0-多项目接口自动化框架基线.md)

## 当前实施进度（2026-08-31）

已完成：

- SteelMill `steelmill-runner run --manifest` 可校验项目、Runner 版本、选集、并发度与 mutation 策略；
- 每次 Runner 执行输出唯一目录的 `manifest.json`、`result.json`、`junit.xml`、`report.html`、`runner.log`；
- SteelMill `result.json` 已与 TestPilot `RunResult v1` 兼容，并带有 `schema_version: "1.0"`；
- HTTP 产物保存完整时间线，并对 Authorization、Token、Cookie、API Key 和敏感 URL query 脱敏；
- TestPilot 在入队时校验 Runner 版本、Manifest 版本、环境 mutation 能力；在归档时校验任务存在、状态和 `run_id` 一致；
- 已执行 SteelMill 离线测试（16 通过）、SteelMill Runner unit Manifest 闭环（16 通过）、TestPilot 全量测试（57 通过）；
- 已用批准的测试环境执行只读 `api + smoke`：2 通过、0 失败；只访问 GET 接口，不写入数据、不访问数据库或 Redis；
- 已验证 TestPilot 可归档 SteelMill Runner 实际生成的 `result.json`，并在桌面端提供 Runner 登记、Manifest 入队、结果归档和任务/产物查看页面；
- TestPilot 日常“一键执行”只启动已登记、已校验指纹的固定 Python + `-m runner run --manifest`；执行前要求环境授权，执行中遵循 Manifest 超时，正常归档前校验 `artifacts.root`、JUnit、HTML 与日志均在平台受控目录内；
- TestPilot CLI 已可注册 Runner、登记 Manifest、归档 `result.json` 与查询外部运行记录；整个过程不执行任意 Shell 命令。
- 平台业务流程已支持稳定 `step_id`、`depends_on`、声明式 `when`、HTTP `poll_until` 与全流程 `deadline_seconds`；数据库夹具会逆序清理并可输出 `resource_ledger.json`，记录明确创建的资源与清理结果。
- SteelMill Dockerfile 与离线 unit 镜像运行说明已加入；公司电脑不安装 Docker，须在个人电脑执行镜像构建验证。

尚未完成：

- SteelMill 侧复杂 Flow 的真实 mutation 测试接入 ResourceLedger，以及对 HTTP 创建资源的显式台账声明；平台不会猜测未知写操作是否已清理；
- 数据库/Redis/模拟器统一观察器；
- 同一 Manifest 的 Docker 构建/运行证据；
- 内部 CI 门禁落地（当前仅提供不公开代码的本地/内部工作流预案，不能在公共仓库启用）；
- 两个仓库的改动提交、版本发布和 TestPilot UI/调度接入（后者属于 Phase 2）。

## 1. 目标与边界

Phase 1 的目标不是迁移全部 SteelMill 代码，也不是在 TestPilot 中重写钢厂业务流程。目标是把 SteelMill 现有的 pytest 测试能力加固成一个可由统一协议调用的领域 Runner，并让 TestPilot 管理其任务和结果。

本阶段结束时，以下命令必须可用：

```powershell
steelmill-runner run --manifest run-manifest.json
```

对一个只读或可回收的 SteelMill API Smoke 套件，该命令应完成：

```text
读取并校验 Manifest
  → 校验环境、标签与 mutation 策略
  → 执行 pytest
  → 写入独立的 run_id 产物目录
  → 输出 result.json、junit.xml、report.html、runner.log
```

本阶段不做：

- 不把 SteelMill 领域模块、模拟器或工艺脚本复制到 TestPilot；
- 不执行生产环境、真实设备或未批准的写操作；
- 不要求 TestPilot UI 直接执行 Runner 任意命令；平台只登记 Runner、入队 Manifest、归档结果并展示产物。实际启动由受控 CLI、Docker 或未来内部 CI Worker 完成；
- 不进行一次性目录大迁移或抽取完整公共 Testkit。

## 2. 完成定义（Definition of Done）

Phase 1 完成必须同时满足：

- 同一份 Manifest 可从 IDE、本机无界面 CLI 和 Docker 运行；
- `api`、`smoke` 与非 mutation Flow 可选择、可执行、可追溯；
- 任何结束路径（通过、断言失败、初始化失败、超时、Runner 异常）都有合法 `result.json`；
- 每次运行使用唯一 `run_id`，历史产物不得覆盖；
- HTML、JUnit、JSON、日志和用例/步骤产物可相互索引；
- 密码、Token、Cookie、API Key 和数据库连接串不进入 Git、日志、HTML 或 JSON 产物；
- mutation 默认拒绝；批准后使用资源台账、逆序清理、补偿与脏数据清单；
- 核心框架单元测试、YAML Schema 校验与静态检查进入本地和 CI 门禁；
- TestPilot 可以按项目登记 SteelMill Runner、保存 Manifest 任务、校验并归档对应 `result.json`、查看状态与产物目录；
- 一个真实 SteelMill API Smoke 端到端样例在本机和 Docker 均可重复通过；Docker 在个人电脑或获准的内部构建机执行；
- CI 配置不得把公司代码、测试地址或 Secret 推送至公共托管平台；未具备内部 CI 时，先执行等价本地门禁并保存证据。

## 3. 工作分解与排期

### 第 0 天：启动与基线确认

| 工作项 | 产出 | 验收方式 |
|---|---|---|
| 固化 Phase 0 | 已提交的协议、Migration 11、测试结果 | 执行 TestPilot 定向测试与全量测试 |
| 选定首个样例 | 1 个安全的 SteelMill API Smoke 用例/套件 | 明确接口、环境、期望断言、是否只读、所需 Secret |
| 冻结输入 | `run-manifest.example.json` | 可通过 Phase 0 `RunManifest v1` 校验 |
| 明确安全边界 | 环境白名单、测试账号、secret_ref、mutation 审批人 | 书面确认生产地址、真实设备和未授权写入默认拒绝 |

### 第 1 周：Runner CLI、环境治理与工程质量

**工作内容**

1. 建立 SteelMill Runner 的稳定入口与模块边界：`runner/`、`framework/`、`domains/`、`config/`、`tests/`。
2. 引入依赖锁定、Ruff、mypy、pytest-cov、pre-commit；固定 Python 版本并提供本地安装说明。
3. 实现 `steelmill-runner run --manifest`：加载 JSON、调用 `RunManifest v1` 校验、输出清晰错误码。
4. 将 `selection.paths`、markers、case IDs、timeout、parallel workers 映射为受控 pytest 参数，禁止拼接任意 Shell 命令。
5. 实现环境解析：只读取非敏感环境模板和运行时 Secret；禁止生产 URL；校验 `capabilities` 与 `allow_mutation`。
6. 注册并校验统一 marker：`unit/api/smoke/flow/e2e/mutation/nightly/p0/p1/p2`。

**本周验收**

- 错误 Schema、空选集、未知 marker、未配置环境在发送 HTTP 前失败；
- `allow_mutation=false` 时，包含 `mutation` 的选集被拒绝；
- CLI 的退出码、错误信息和日志可区分配置错误、策略拒绝和 Runner 初始化错误；
- 框架 lint、类型检查和离线单测可在无 TestPilot UI 环境运行。

### 第 2 周：标准结果、报告与第一个 API Smoke 闭环

**工作内容**

1. 以 `artifacts/<run_id>/` 创建独立目录，保存输入 Manifest 副本。
2. 在 pytest Hook 中收集 session、case 与步骤事件；标准化状态、耗时、失败分类和相对产物路径。
3. 输出 `result.json`、`junit.xml`、`report.html`、`runner.log`；即使 collection、setup 或超时失败也必须输出结果文件。
4. 记录每个 HTTP exchange timeline：脱敏请求、响应摘要、Trace ID、耗时、断言和失败栈。
5. 建立统一脱敏器，至少覆盖 Authorization、Token、Cookie、API Key、敏感 Header、URL query 和异常文本。
6. 为第一个 SteelMill `api + smoke` 套件接入 Manifest 执行路径。

**本周验收**

- 用同一 Manifest 连续运行两次，产生两个不互相覆盖的 `run_id` 目录；
- 人工打开 HTML 可定位失败用例；CI 可读取 JUnit；TestPilot 可读取 `result.json`；
- 人工构造一个失败断言后，`result.json` 状态为 `failed`，并带有可定位的证据路径；
- 产物全文搜索不到测试凭据明文。

### 第 3 周：Schema、Flow 可靠性与数据生命周期（4 周方案）

**工作内容**

1. 为 API Case、Flow Case、Data Source、数据库断言定义版本化 Schema。
2. 在 pytest collection 前校验 YAML：文件位置、字段、重复 case ID、未定义变量、未知 marker、空断言均需清晰报错。
3. 强化 Flow：稳定 `step_id`、`depends_on`、`when`、`extract`、`poll_until`、步骤超时与全流程 deadline。
4. 仅为幂等读操作启用有限退避重试；写操作不得自动重试。
5. 引入 `ResourceLedger`：记录 `run_id`、创建资源、清理策略、补偿结果与未清理资源。
6. mutation 使用 `yield` fixture 逆序清理；失败后保留脏数据清单而不是静默忽略。

**本周验收**

- 错误 YAML 在 collect 阶段失败，不发生 HTTP 调用；
- Flow 任一步失败时，报告能显示失败步骤、脱敏上下文、已提取变量与补偿执行情况；
- 一条受控 mutation 用例可连续执行，且资源台账显示创建、清理或明确的残留原因。

### 第 4 周：观察器、Docker 一致性与交付收口（4 周方案）

**工作内容**

1. 统一 PostgreSQL 只读观察器与可选 Redis/模拟器观察器的步骤结果；所有查询参数化、白名单化、可审计。
2. 输出 HTTP、数据库/外部状态、模拟器证据和清理结果的关联时间线。
3. 制作 `steelmill-runner` Dockerfile，固定 Python、依赖与启动命令；不将 Secret 写入镜像。
4. 通过 volume 输出 `artifacts/<run_id>/`；Manifest 和 Secret 只在运行时挂载或注入。
5. 在 IDE、本机 CLI、Docker 中执行同一 API Smoke，并比较核心 `result.json` 字段。
6. 建立最小**内部** CI Job 或等价本地门禁：静态检查、离线单测、YAML collect-only、Docker Smoke、上传 JUnit 与 artifacts；不得使用公开仓库或公开 CI。

**本周验收**

- 三种运行方式的状态、用例数和产物结构一致；
- Docker 退出码和 `result.json.status` 一致；
- 数据库使用只读凭据，生产地址、真实设备和未批准外部系统仍被阻断；
- CI 失败可直接定位 JUnit、HTML 和 `result.json`。

## 4. 两周压缩版本

若只能投入两周，只交付可用的最小闭环：

1. 第 1 周完成 Runner CLI、Manifest/环境/mutation 校验、静态检查与离线单测。
2. 第 2 周完成唯一产物目录、JSON/JUnit/HTML/日志、脱敏与一个真实 API Smoke。

Flow 强化、ResourceLedger、观察器统一和 Docker 可进入紧随其后的迭代，但不得宣称已支持高风险 mutation 或复杂工业 E2E。

## 5. 剩余工作与执行顺序（当前环境）

### 第一步：平台 Runner 管理与结果展示（公司电脑执行）

**目标**：TestPilot 作为项目管理和审计平台。日常操作不手写 Manifest、不手动导入结果；平台只会启动首次登记过的固定 Python + `python -m runner` 组合，绝不从 Manifest 接受任意 Shell。

1. 在“项目中心”创建并选择项目，例如 `SteelMill`；在“环境校验”保存测试环境名称、非敏感地址、能力和 Secret 引用。密码只由本机环境变量或受控密钥库提供。
2. 进入“接口测试 → 外部 Runner”的“高级设置”，登记一次 `project_key=steelmill`、`runner_name=steelmill-runner`、版本 `0.1.0`、SteelMill `python_api_tests` 工作目录以及运行 SteelMill 的 `python.exe` 完整路径。
3. 日常只在上方“一键执行 SteelMill”选择环境与套件（只读 Smoke 或离线 Unit），点击“一键执行”。
4. 平台自动生成唯一 `run_id`、受控 Manifest 和产物目录，执行固定 `python -m runner run --manifest <自动生成文件>`，并将 TestPilot 中加密保存的测试账号/密码仅注入子进程环境变量。
5. 进程结束后平台自动读取同一 `run_id` 的 `result.json`，更新 queued/running/passed/failed 状态，展示 HTML/JUnit/日志等产物目录。
6. “导入 Manifest 并入队”“导入 result.json 并归档”仅保留给 Docker、内部 CI 和故障排查，不是日常步骤。

**验收证据**：平台任务列表有对应记录；详情中的 Manifest 与 Result 的 `run_id` 相同；结果目录包含 `result.json`、`junit.xml`、`report.html`、`runner.log`。日常本地执行还会校验解释器指纹、环境授权、Manifest deadline 与受控产物目录；任一校验不通过会以错误任务收口。这一步已在本次实现。

### 第二步：个人电脑 Docker 一致性验证（不在公司电脑执行）

公司电脑未安装 Docker，不能把“未执行 Docker”误判为代码缺陷。请只在个人电脑的**获准副本**上执行；若公司策略不允许复制公司仓库、测试环境地址或测试数据到个人电脑，则只运行脱敏的离线 unit 示例，真实环境验证改在内部构建机。

```powershell
cd <获准的 SteelMill python_api_tests 目录>
docker build -t steelmill-runner:0.1.0 .
docker run --rm --network none `
  -v "${PWD}/examples:/input:ro" `
  -v "${PWD}/reports:/reports" `
  steelmill-runner:0.1.0 run --manifest /input/run-manifest.unit.example.json
```

离线命令通过后，检查 `reports/<run_id>/result.json`。若个人电脑可以在授权网络中访问测试环境，再使用同一份只读 Smoke Manifest 运行容器；Base URL、账号密码只以运行时环境变量或受控 Secret 注入，绝不写进 Manifest、镜像层、日志或 Git。随后将生成的**脱敏产物**复制回公司电脑，在 TestPilot 的“外部 Runner”页面归档；不要复制密钥文件。

### 第三步：内部门禁预案（有内部 CI 后启用）

当前不在公共 GitHub/GitLab 开启 CI。先在本地或内部构建机按下面顺序运行并留存 JUnit/HTML/result 作为证据：

```powershell
uv sync --all-groups
uv run ruff check .
uv run mypy common runner
uv run pytest tests -q --cov=common --cov=runner
uv run pytest --collect-only
```

| 门禁 | 触发时机 | 允许访问 | 通过条件 |
|---|---|---|---|
| PR/代码门禁 | 每次提交、合并请求 | 不访问真实 Tansu | Ruff、mypy、框架单测、YAML collect、Manifest/Result 协议、Secret 扫描通过 |
| Smoke 门禁 | 测试环境部署后或人工批准 | 只读测试环境 | P0 核心接口通过、无超时、无环境错误、产物完整 |
| Mutation/E2E | 夜间或发布候选，需审批 | 获批测试环境 | 资源台账清理成功或遗留项明确；不得作为每次提交默认门禁 |
| 发布门禁 | 发布候选 | 按批准范围 | P0 全通过、无环境错误/超时、无未解释脏数据、报告可追溯 |

内部 CI 到位时，只需把这四类命令放进公司内部 Git、Jenkins、GitLab CI、Azure DevOps 或构建机；将 Secret 存在内部凭据库，Smoke/Mutation 使用审批变量，上传产物到内部存储。代码不需要公开。

## 6. 风险与控制点

| 风险 | 控制措施 |
|---|---|
| 误连生产或真实设备 | URL/环境白名单；Runner 与平台双重校验；默认拒绝 |
| 测试数据污染 | `run_id` 前缀、资源台账、逆序清理、补偿、脏数据报告 |
| 密钥泄漏 | 仅 secret_ref/环境变量注入；统一脱敏；产物扫描 |
| 偶发失败被重试掩盖 | 仅幂等读取重试；记录每次尝试；单独统计 flaky |
| 报告无法定位 | case/step 稳定 ID、时间线、相对证据路径、失败分类 |
| Docker 与本机行为漂移 | 固定 Python/依赖；同一 Manifest 对比测试 |

## 7. Phase 1 与后续阶段的交接

Phase 1 完成后，SteelMill Runner 只需要从文件或标准输入接收 Manifest，并写出标准产物；它不依赖 TestPilot 数据库或桌面 UI。TestPilot 已在本阶段承担 Runner 注册、Manifest 任务、结果归档和展示；下一阶段才增加受控的内部 Worker 调度、任务重试、Web 平台和跨 Runner 队列。这样不会将 SteelMill 领域逻辑复制到平台中。
