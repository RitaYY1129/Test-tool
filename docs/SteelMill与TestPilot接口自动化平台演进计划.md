# SteelMill 与 TestPilot：从接口自动化框架到自动化测试平台的演进计划

> 文档状态：架构基线
>
> 适用范围：`D:\qinfeng\steel_mill\src\SteelMill.Test\FieldOperationsTests\python_api_tests` 与 `D:\qinfeng\Test-tool`
>
> 核心目标：TestPilot 当前第一阶段聚焦接口测试平台；将 SteelMill 已验证的工业接口、数据流和工艺测试能力强化为标准业务 Runner。平台负责管理、编排和交付，Runner 负责复杂执行与证据采集；二者通过统一协议连接，而不是重复造两套框架。

---

## 1. 先给出最终结论

当前容易混乱，是因为“测试框架”“业务用例”“平台”“CI/CD”和“Docker”都在同时发展。它们不是同一个东西，应明确分成四层。

```text
┌───────────────────────────────────────────────────────────────┐
│  TestPilot 平台层（产品、管理与编排）                            │
│  项目 / 用例资产 / 环境 / 任务 / 报告 / 趋势 / 通知 / 权限       │
├───────────────────────────────────────────────────────────────┤
│  通用接口自动化内核（可复用能力）                                │
│  HTTP / 鉴权 / 断言 / 变量 / 数据驱动 / 流程 / 数据库观察       │
│  资源生命周期 / 日志证据 / 标准结果 / 执行协议                  │
├───────────────────────────────────────────────────────────────┤
│  SteelMill 业务测试包（工业领域资产）                            │
│  现场作业 / 报警 / 追溯 / 数据采集 / 工艺模拟器 / 行业 E2E      │
├───────────────────────────────────────────────────────────────┤
│  基础设施与交付层                                                │
│  Git / CI/CD / Docker Desktop 或 Runner / 测试环境 / 密钥管理   │
└───────────────────────────────────────────────────────────────┘
```

对应关系如下：

- **SteelMill 不是平台。**它是当前最真实、最复杂的业务测试场景，也是通用执行能力的验证样板。
- **TestPilot 不是又一套业务测试脚本。**它是承载项目、环境、用例、执行、报告和调度的平台产品。
- **通用接口自动化内核是两者共享的能力边界。**HTTP、断言、变量、流程、数据驱动、报告等不应在两边长期各写一套。
- **CI/CD 和 Docker 不是功能页面。**它们是让测试在提交、部署、夜间回归中可重复执行的交付基础设施。

最终不追求“把所有 SteelMill Python 文件搬进 TestPilot”，而是追求：SteelMill 的任何一套测试，都能以统一方式由 TestPilot 或 CI 发起、执行、收集证据和展示结果。

当前的产品路线应明确为两条并行、共用标准的接口测试路线：

1. **平台原生接口测试路线**：处理 OpenAPI/Postman/cURL/HAR 导入后的单接口、契约、冒烟和标准 API 回归；重点是快、标准化、低门槛。
2. **SteelMill 复杂工艺路线**：处理接口关联、数据库/Redis/消息观察、模拟器、外部系统回调和工业 E2E；重点是真实业务链路与完整过程证据。

两条路线不是两个产品，也不是“复杂场景做不了才走脚本”。前者服务标准接口测试，后者承载必须用代码和专用适配器完成的复杂工艺；它们共享环境、用例标识、运行清单、结果模型、产物协议和 CI/CD 门禁。

---

## 2. 当前两套代码各自承担什么

### 2.1 SteelMill 当前定位：业务测试资产 + 已验证的执行实践

目录：`steel_mill/src/SteelMill.Test/FieldOperationsTests/python_api_tests`

目前已有的能力包括：

- YAML 数据驱动的单接口用例；
- HTTPX 客户端、登录鉴权、统一 API 断言；
- `${variable}` 变量替换；
- 多接口流程执行与上一步响应提取；
- `mutation` 标记保护写操作；
- PostgreSQL 只读查询和数据库断言；
- 外部工艺脚本、模拟器和现场作业 E2E；
- 失败 HTTP 产物、日志、HTML 报告、SQLite 执行记录；
- 环境配置、账号配置和外部 Runner 配置。

它的优势是有真实工业场景：现场入库、出库、炉次、质量检验、报警、追溯、数据采集和工艺状态。这些是平台不能凭空生成的领域资产。

它当前不应承担的事情：

- 多项目用户/权限管理；
- 跨项目任务调度；
- 统一的测试资产看板；
- CI 执行队列或远程 Runner 管理；
- 作为所有项目都直接依赖的复制粘贴模板。

### 2.2 TestPilot 当前定位：接口自动化平台（当前第一阶段）

目录：`Test-tool`

当前已具备或已开始建设：

- 项目、环境、接口来源、接口定义和测试用例存储；
- OpenAPI、Postman、cURL、HAR、源码等导入；
- HTTP 执行、断言、批量运行和工作流；
- SQLite 历史记录、HTML/JSON 报告、趋势数据；
- 无界面 CLI、定时任务、失败重试和通知；
- Docker Compose 和 GitHub Actions 基础；
- 数据库观察、流程证据、测试夹具、审计与可重放包；
- 面向人工确认的 AI 生成用例/流程草稿能力。

它的优势是有平台外壳和统一管理能力。当前最优先完善的是接口测试闭环：接口资产、环境、执行、结果、报告、定时任务、Git/CI/CD 和 Docker Runner；AI、更多测试类型和复杂看板属于后续扩展，不能抢占接口自动化主线。

它当前不应直接承担的事情：

- 在 UI 里硬编码 SteelMill 的入库、装炉、出库工艺；
- 再实现一遍 SteelMill 已验证的流程逻辑；
- 把“能发 HTTP 请求”误当作“已支持工业 E2E”；
- 让桌面 UI 成为 CI/CD 的唯一入口。

### 2.3 当前真正的风险：两套执行能力漂移

目前 TestPilot 有自己的 HTTP/工作流执行逻辑，SteelMill 也有 `ApiClient`、`case_runner`、`flow_runner`、pytest hook 和数据库断言。

如果继续各自独立演进，会出现：

- 同一种断言，两边语法和结果不同；
- 变量表达式、认证、重试、脱敏规则不同；
- 平台报告显示通过，但 SteelMill pytest 实际失败；
- 新功能要分别开发、修复、测试；
- 业务人员不知道该在 YAML、Python 还是 UI 中维护用例。

因此第一原则是：**先统一执行契约和能力边界，再逐步抽取公共实现；不要急于大搬家。**

---

## 3. 目标架构：控制面与执行面分离

这是向大厂方向演进最重要的结构。

```text
                         控制面（Control Plane）
┌────────────────────────────────────────────────────────────────┐
│ TestPilot                                                        │
│ - 项目、仓库、接口资产、用例资产                                │
│ - 环境、凭据引用、数据源、执行策略                              │
│ - 任务创建、审批、定时调度、通知                                │
│ - 报告归档、趋势、质量门禁、审计                                │
└───────────────────────────────┬────────────────────────────────┘
                                │ Run Manifest（统一执行契约）
                                ▼
                         执行面（Data Plane）
┌────────────────────────────────────────────────────────────────┐
│ Runner                                                           │
│ - TestPilot 内置通用 HTTP Runner                                 │
│ - SteelMill Pytest Runner（当前工业业务执行器）                  │
│ - 后续：UI、性能、消息队列、移动端等专用 Runner                  │
└───────────────────────────────┬────────────────────────────────┘
                                │ 标准结果、产物、日志、JUnit
                                ▼
┌────────────────────────────────────────────────────────────────┐
│ 产物与证据层                                                     │
│ - case / step 结果                                               │
│ - HTTP 请求响应（脱敏）                                          │
│ - 数据库断言结果                                                 │
│ - 进程日志、截图、文件、Trace                                   │
│ - HTML/JSON/JUnit 报告                                           │
└────────────────────────────────────────────────────────────────┘
```

### 3.1 TestPilot 是控制面

平台负责“决定什么时间、在哪个环境、以什么策略运行什么测试”，但不需要知道每一步工艺的具体业务含义。

平台的责任：

1. 管理项目与关联仓库。
2. 管理环境、环境变量、凭据引用和风险等级。
3. 管理接口文档、用例、工作流、测试数据模板。
4. 选择 Runner，生成一次不可变的执行清单。
5. 提交/调度任务，显示执行状态，保存报告和产物索引。
6. 把质量结果反馈给 Git/CI/CD 或通知渠道。
7. 提供权限、审批、审计和趋势指标。

### 3.2 SteelMill 是执行面中的领域 Runner

SteelMill 负责“如何在钢厂测试环境中验证现场作业业务”。

它的责任：

1. 维护领域模块、业务测试数据、YAML 用例和复杂 Python 场景。
2. 执行 HTTP、流程、数据库、模拟器、Redis/外部进程校验。
3. 管理测试数据的创建、标识、清理和补偿。
4. 输出统一的结果与证据，不关心平台页面如何展示。

### 3.3 通用内核的责任

通用内核是未来最值得沉淀和复用的部分。它只能放“与钢厂业务无关”的能力：

```text
testpilot-core 或 testpilot-testkit
├─ contracts/       用例、流程、环境、结果、产物的 Schema
├─ http/            客户端、认证策略、超时、重试、Correlation ID
├─ assertions/      HTTP、JSONPath、JSON Schema、耗时、业务 Envelope
├─ variables/       变量替换、提取、作用域、敏感值标记
├─ data/            CSV/YAML/JSON 数据驱动、数据工厂、资源台账
├─ workflow/        步骤编排、依赖、条件、轮询、补偿
├─ observers/       数据库、消息、文件、缓存等只读观察适配器
├─ artifacts/       脱敏、日志、请求响应、附件、结果清单
└─ pytest_plugin/   marker、fixture、JUnit/产物 Hook
```

SteelMill 中 `common/` 里真正通用的部分，未来可渐进移动或被 TestPilot Core 替代；但不在第一阶段做目录大迁移。

---

## 4. 必须先统一的执行契约

先定义 JSON Schema / Pydantic 模型，之后平台和 Runner 才能解耦。以下不是 UI 数据结构，而是一条实际任务的“执行清单（Run Manifest）”。

```json
{
  "schema_version": "1.0",
  "run_id": "tp_20260825_001",
  "project": {"id": "steel-mill", "repository": "steel_mill", "revision": "git-sha"},
  "runner": {"kind": "pytest", "name": "steelmill-api", "version": "0.1.0"},
  "environment": {
    "name": "staging",
    "base_url": "https://staging.example",
    "secret_refs": ["steelmill-staging-account"],
    "risk_level": "test-only"
  },
  "selection": {
    "paths": ["modules/现场作业"],
    "include_markers": ["api", "smoke"],
    "exclude_markers": ["mutation", "e2e"]
  },
  "execution_policy": {
    "timeout_seconds": 1800,
    "parallel_workers": 1,
    "allow_mutation": false,
    "retry_policy": "read_only_only"
  },
  "artifacts": {
    "directory": "/artifacts/tp_20260825_001",
    "formats": ["json", "html", "junit"],
    "redaction_policy": "default-v1"
  }
}
```

### 4.1 输入必须标准化

平台向 Runner 传递的不是随意拼接的命令行，而是 Manifest。Runner 可把它映射为 pytest 参数、环境变量和配置文件。

至少包括：

- 项目 ID、Git revision、Runner 版本；
- 环境名、Base URL、凭据引用；
- 要执行的目录、套件、标签、用例 ID；
- 是否允许写操作；
- 并行度、超时、重试策略；
- 产物目录和脱敏策略；
- 任务来源：本地、平台手工、定时、PR、部署后、发布门禁。

### 4.2 输出必须标准化

所有 Runner 都要输出 `result.json`，并同时尽量生成 JUnit XML。

```json
{
  "run_id": "tp_20260825_001",
  "status": "failed",
  "started_at": "2026-08-25T10:00:00Z",
  "finished_at": "2026-08-25T10:08:12Z",
  "summary": {"total": 40, "passed": 35, "failed": 2, "skipped": 3, "error": 0},
  "cases": [
    {
      "id": "field.material_inbound.invalid_supplier",
      "status": "failed",
      "duration_ms": 512,
      "category": "product_defect",
      "artifacts": ["artifacts/case-1/http.json", "artifacts/case-1/log.txt"]
    }
  ],
  "artifacts": {"html": "report.html", "junit": "junit.xml", "log": "runner.log"}
}
```

测试平台只依赖这一标准输出；它不应通过解析中文 pytest 控制台文本来判断结果。

---

## 5. SteelMill 接口自动化框架的目标形态

SteelMill 不是只要“能调接口”，而要成为可迁移到其他业务项目的工程化接口自动化框架。

### 5.1 建议的模块职责

```text
python_api_tests/
├─ framework/                     # 通用框架能力，未来可抽取到 TestPilot Core
│  ├─ contracts/                  # Pydantic/JSON Schema
│  ├─ http/                       # HTTP、认证、重试、超时、Trace ID
│  ├─ assertions/                 # HTTP/JSON/Schema/性能/业务断言
│  ├─ data/                       # 数据加载、变量、工厂、资源台账
│  ├─ workflow/                   # 流程、轮询、补偿、步骤生命周期
│  ├─ observers/                  # PostgreSQL、Redis、文件、消息观察
│  ├─ reporting/                  # 结构化结果、日志、产物、JUnit/HTML
│  └─ pytest_plugin/              # fixture、marker、Hook、CLI 参数
├─ domains/                       # SteelMill 领域用例，不可通用化
│  ├─ field_operations/
│  ├─ alarm_management/
│  ├─ traceability/
│  └─ data_collection/
├─ config/
│  ├─ environments/               # 非敏感环境模板
│  └─ schemas/                    # 用例与数据 Schema
├─ tests/                         # framework 的离线单元测试
├─ runner/                        # 接收 TestPilot Manifest 的入口
└─ reports/                       # 运行产物，不提交 Git
```

现有目录可以渐进迁移；短期不必改动所有中文模块目录。重点先分清：`common/` 中哪些是通用能力，`modules/` 中哪些是 SteelMill 领域资产。

### 5.2 要补齐的八项框架能力

#### A. 用例 Schema 与静态校验

问题：当前 YAML 灵活，但字段拼错、变量不存在、断言不合法可能在执行中才报错。

行动：

- 定义 `ApiCase`、`FlowCase`、`DatabaseAssertion`、`DataSource` 的 Pydantic 模型；
- 在 `pytest --collect-only` 前校验 YAML；
- 检查重复 case ID、未定义变量、未知 marker、没有断言的成功用例；
- 为平台导入和 SteelMill 本地执行共用同一份 Schema。

验收：错误 YAML 不发 HTTP 请求即可给出“文件、行、字段、原因”。

#### B. 环境与凭据治理

问题：环境、账号、数据库和外部脚本配置分散，平台与 CI 不容易安全复用。

行动：

- 环境使用明确的 `environment_id`，如 `local/staging/preprod`；
- 非敏感配置可提交 Git；密码、Token、数据库口令只传 `secret_ref`；
- 本地通过 `.env`/系统凭据，CI 通过 Secret，Docker 通过 Secret/环境变量注入；
- 测试环境默认白名单，生产 Base URL 强制阻断；
- 配置增加 `capabilities`：是否允许 mutation、数据库观察、Redis、模拟器。

验收：同一套用例不改代码，只切换 `environment_id` 即可运行；任何生产环境或缺失审批的写操作都被拒绝。

#### C. 接口关联与流程编排

问题：当前已有 `extract` 和变量替换，但需要可诊断、可扩展的流程模型。

行动：

- 每一步具有稳定 `step_id`；
- 显式表示 `depends_on`、`extract`、`when`、`poll_until`、`compensation`；
- 每个步骤保存请求、响应、耗时、提取变量的脱敏快照；
- 失败时报告流程图、最后上下文与已创建资源；
- 只在安全/幂等的查询步骤启用自动重试；写操作不能无条件重试。

验收：任何一步失败，能定位“第几步、什么输入、什么输出、上下文是什么、是否需要清理”。

#### D. 数据驱动与测试数据生命周期

问题：固定环境基线数据容易冲突，多个执行器并行时最容易产生脏数据和偶发失败。

行动：

- 使用 YAML/JSON/CSV 管理边界与参数化数据；
- 引入 `run_id`，新建数据统一带唯一标识；
- 引入 `ResourceLedger`：记录创建资源、删除策略、补偿策略、清理状态；
- `yield` fixture 逆序清理，失败时保留脏数据清单；
- 为不同测试账号/工位/设备建立资源池，杜绝共享同一固定业务记录。

验收：同一套 mutation 测试可连续运行；可说明每个资源由哪次运行创建和是否清理。

#### E. 数据库与外部状态观察

问题：仅断言 HTTP 200 容易产生“接口返回成功、内部业务状态错误”的假通过。

行动：

- 保留并强化 PostgreSQL 只读事务，不在测试框架中开放任意写 SQL；
- 抽象 `Observer`：PostgreSQL、Redis、文件、消息队列、第三方回调；
- 支持前后快照、最终状态、不变量、异步轮询；
- 查询必须参数化、白名单化、可审计；
- 将“已观测”和“仅推断”在报告中明确区分。

验收：一个核心现场作业链路能输出 HTTP、数据库、Redis/模拟器状态的关联证据。

#### F. 日志、证据和报告

问题：当前报告和失败产物已有基础，但流程中间交互、运行唯一标识、CI 标准格式仍需统一。

行动：

- 一个执行对应唯一 `run_id` 和独立产物目录，不能重复覆盖 `report.html`；
- 每个用例保存完整 request/response timeline，不只保存最后一次交换；
- 统一脱敏器，覆盖 `accessToken`、`refreshToken`、Cookie、API Key、URL query 和异常文本；
- 输出 HTML（人工阅读）、JSON（平台导入）、JUnit XML（CI 识别）；
- 记录 Git SHA、Runner 镜像版本、环境、执行参数、服务版本和 Trace ID；
- 失败分类：产品缺陷、环境故障、测试数据、脚本缺陷、超时、依赖不可用。

验收：CI 中点击失败用例即可定位证据；历史运行的报告不被新报告覆盖。

#### G. 稳定性、并发与性能

行动：

- HTTP、外部进程、轮询都必须有超时；
- 为幂等读取增加有限退避重试；
- 用 marker 区分 `unit/api/smoke/flow/e2e/mutation/nightly`；
- 在测试数据隔离完成前，mutation 测试串行执行；
- 完成隔离后引入 `pytest-xdist`；SQLite 报告存储需迁移为单写入器、WAL 或平台服务端存储；
- 指标：耗时、通过率、失败分类、重跑通过率（flaky）、最长用例。

#### H. 可交付的 Runner CLI

行动：

- 提供稳定入口，例如 `steelmill-runner run --manifest manifest.json`；
- CLI 验证 Manifest、生成临时环境配置、调用 pytest、收集产物；
- 无论 pytest 成功、失败、初始化失败或超时，都写出 `result.json`；
- Runner 不直接依赖 TestPilot 数据库，也不需要桌面 UI。

验收：在开发机、CI 和 Docker 中以同一个 Manifest 获得相同格式的结果。

---

### 5.3 内部工艺与外部工艺联合测试模型

复杂工业测试不能只把接口串起来，也不能把所有内部实现写进平台页面。应把一次工艺测试定义为“外部动作 + 内部状态 + 外部副作用 + 补偿”的受控流程。

```text
测试数据 / 外部设备或模拟器输入
        ↓
HTTP API 接收或下达作业指令                 ← 外部可见工艺
        ↓
Service / 状态机 / 事务 / 工艺计算          ← 内部工艺
        ↓
数据库 / Redis / 消息队列 / 文件发生变化     ← 内部可观测状态
        ↓
设备、工位、第三方系统回调或输出             ← 外部副作用
        ↓
查询最终状态、不变量和清理/补偿结果
```

每个步骤都要记录以下内容：

| 维度 | 必填内容 |
|---|---|
| 步骤类型 | `http`、`simulator`、`database_observe`、`redis_observe`、`message_observe`、`external_callback`、`cleanup` |
| 工艺边界 | 外部可见、内部可观测、仅静态推断或人工确认 |
| 输入与输出 | 脱敏后的请求、响应、变量提取、外部输出 |
| 状态断言 | 最终状态、状态迁移顺序、数量、幂等性、不变量 |
| 风险 | 是否写数据、是否调用真实设备、是否需要审批 |
| 时间 | 单步超时、轮询间隔、全流程 deadline |
| 清理 | 资源标识、补偿动作、清理结果和脏数据清单 |

平台展示这个流程和结果，但复杂执行仍留在 SteelMill Runner 的 Python 代码、pytest 用例和专用观察器中。这样既能在 IDE 中断点调试复杂工艺，也能在平台中看到完整的测试过程、测试用例和报告。

内部工艺没有可观测证据时，报告只能显示“未观测”或“静态推断”，不能把 HTTP 成功当作内部工艺正确。生产数据库、真实设备和未授权第三方系统默认禁止自动执行；优先使用测试副本、模拟器、只读观察器和明确审批。

---

## 6. TestPilot 平台需要如何承接接口测试

平台不应强迫所有场景转换成可视化拖拽流程；代码和 YAML 仍然是复杂业务测试的事实来源。平台应提供两种运行模式。

### 6.1 模式一：平台原生接口用例

适用：简单单接口、文档导入、冒烟、契约回归。

```text
OpenAPI / Postman / cURL / HAR
       ↓
TestPilot 导入、生成、人工确认用例
       ↓
TestPilot 通用 HTTP Runner
       ↓
结果、报告、通知、趋势
```

优势：新项目接入快，适合接口文档驱动。

### 6.2 模式二：外部业务 Runner（SteelMill 首先接入）

适用：复杂流程、数据库校验、模拟器、行业 E2E、已有 pytest 测试资产。

```text
TestPilot 选择项目 / 环境 / 套件 / 风险策略
       ↓
生成 Run Manifest
       ↓
SteelMill Runner（Docker 中 pytest）
       ↓
result.json + JUnit + HTML/JSON + artifacts
       ↓
TestPilot 归档、展示、告警、回写 CI 状态
```

优势：复用 SteelMill 已有资产，不在平台内复制复杂工艺脚本。

### 6.3 双路线的统一边界

平台原生接口测试和 SteelMill Runner 必须共用以下边界，才能在同一个项目、报告和 CI/CD 中管理：

- **统一环境**：环境 ID、Base URL、密钥引用、能力开关和风险等级一致；
- **统一选择条件**：模块、套件、用例 ID、优先级、`api/smoke/flow/e2e/mutation` 标签一致；
- **统一执行协议**：都接收 `Run Manifest`，都输出 `Run Result`；
- **统一产物索引**：平台均可链接 HTML、JSON、JUnit、HTTP 证据、数据库断言和外部日志；
- **统一质量语义**：通过、失败、跳过、环境错误、超时、数据问题和脚本问题不能混为一谈。

平台原生路线不应试图替代复杂工艺 Runner；SteelMill Runner 也不应自行维护项目管理、定时调度和质量看板。

### 6.4 平台要新增/强化的接口

| 能力 | 平台职责 | SteelMill Runner 职责 |
|---|---|---|
| Runner 注册 | 保存名称、版本、镜像、支持能力 | 声明支持 marker、观察器与 Manifest 版本 |
| 执行任务 | 创建任务、审批、下发 Manifest | 校验 Manifest 并执行 |
| 环境 | 保存 Base URL、Secret 引用、风险策略 | 只接收已注入的参数 |
| 用例选择 | UI/API 选择 suite、标签、case ID | 映射为 pytest 选择参数 |
| 报告 | 保存索引、历史、趋势、链接 | 生成原始结果与产物 |
| 通知 | Webhook/邮件/CI 状态 | 提供失败分类与产物路径 |
| 权限 | 控制谁能运行 mutation/E2E | 二次校验环境与 allow_mutation |

### 6.5 TestPilot 不要做的错误设计

- 不从 UI 拼接任意 Shell 命令；只能提交已注册 Runner 的参数化 Manifest。
- 不把账号密码写入 SQLite 明文或报告。
- 不让 AI 直接执行 mutation、SQL 写入或第三方调用。
- 不依赖桌面 GUI 才能执行任务；CI/Docker 使用 CLI 或 API。
- 不把 SteelMill 的领域 Python 逻辑复制到 `TestPilot/src`。

---

## 7. Git、CI/CD 与质量门禁设计

### 7.1 Git 仓库职责

建议保持两个仓库清晰：

```text
steel_mill
  - SteelMill 业务用例、领域脚本、执行器实现
  - 测试数据模板、用例 YAML、容器定义

Test-tool
  - TestPilot 平台产品、通用 Core、Runner 协议、管理 UI/CLI
  - 不保存 SteelMill 的账号、运行产物或环境私密值
```

用例和框架代码应与被测服务版本存在关联。每次运行报告至少记录：测试仓库 SHA、被测服务 SHA/镜像 Tag、TestPilot 版本、Runner 镜像 Tag。

### 7.2 四级流水线

```text
L0：本地提交前
    Ruff / 格式化 / YAML Schema / framework 单测

L1：Pull Request
    依赖锁定安装、静态检查、离线单测、契约解析、用例收集
    不访问真实接口、不写数据

L2：测试环境部署后
    Smoke API（只读或极小范围可回收数据）
    失败则部署标记失败，不进入下一环境

L3：夜间或发布候选
    API 回归、Flow、数据库断言、模拟器、E2E、Mutation
    高风险步骤需环境白名单和审批
```

### 7.3 CI 的标准步骤

以 SteelMill Runner 为例：

```text
检出 steel_mill 指定 SHA
  ↓
构建/拉取 steelmill-runner 镜像
  ↓
注入测试环境 Secret 与 Run Manifest
  ↓
执行 pytest / steelmill-runner
  ↓
上传 artifacts、JUnit、result.json
  ↓
TestPilot 导入结果并生成平台报告
  ↓
CI 根据质量策略设置成功、失败或人工审批等待
```

### 7.4 质量门禁不能只看通过率

发布门禁建议同时判断：

- P0/P1 冒烟用例是否全部通过；
- 是否存在 `environment_error`、`runner_error`、`timeout`；
- 是否存在未清理的 mutation 资源；
- 与上一个基线相比是否出现接口契约破坏；
- 是否出现关键数据库不变量失败；
- Flaky 用例不能被简单重试后掩盖，必须单独统计。

---

## 8. Docker Desktop 的正确落地方式

Docker 的目的不是把项目“放进容器”就结束，而是保证执行器在任何电脑和 CI 上使用一致的 Python、依赖、命令和产物协议。

### 8.1 建议的 Compose 结构

```text
compose.yaml
├─ testpilot-scheduler       平台 CLI/调度服务（可选）
├─ steelmill-runner          执行一次任务后退出的 Job 容器
├─ postgres-test             可选：本地测试库/副本
├─ redis-test                可选：现场作业模拟所需 Redis
├─ field-simulator           可选：数据采集模拟器
└─ artifact-volume           报告、JUnit、日志、失败产物
```

### 8.2 Runner 镜像原则

- 使用固定 Python 版本，例如 Python 3.13；
- 使用 lock 文件安装精确依赖；
- 镜像内不保存 `config.yaml`、账号、Token、生产连接串；
- Manifest、Secret 和环境配置在运行时挂载或注入；
- `reports/` 通过 Volume 输出；
- 每次任务使用独立 `run_id` 目录；
- 容器退出码和 `result.json.status` 都要表达最终状态。

### 8.3 容器网络注意事项

- 容器中的 `127.0.0.1` 指向容器自己，不是宿主机。
- 测试本机服务时，Docker Desktop 使用 `host.docker.internal`；Compose 服务互相访问使用服务名，例如 `postgres-test:5432`。
- 数据库必须优先使用只读账号；本地测试副本和生产库必须完全隔离。

---

## 9. 分阶段实施计划

不建议一次性重构。每阶段应能独立验收、独立发布。

### Phase 0：多项目复用边界与协议冻结（已完成）

目标：把“SteelMill 专用自动化代码”调整为“SteelMill 作为首个参考项目的通用框架基线”。新项目只新增 Adapter、测试资产和环境配置，不能复制或修改通用内核。TestPilot 已落地平台侧的 Adapter/Runner/运行记录基础，SteelMill Runner 执行实现进入下一阶段。

行动：

1. 定义“通用内核 + 项目适配层 + 测试资产层”的复用结构。
2. 盘点 SteelMill 与 TestPilot 的现有能力，并确定通用、领域和平台归属。
3. 冻结新项目的最小接入配置：项目、环境、认证、数据库、风险能力和 Secret 引用。
4. 定义 `RunManifest v1`、`RunResult v1` 和 Artifact 目录约定。
5. 定义统一 marker/标签字典：`unit/api/smoke/flow/e2e/mutation/nightly/p0/p1/p2`。

交付物：[Phase 0 多项目接口自动化框架基线](phase0-多项目接口自动化框架基线.md)。

### Phase 1：SteelMill 框架工程化加固（2～4 周）

目标：使 SteelMill 能作为可靠 Runner 被调用。

行动：

1. 补充 `pyproject.toml` 的依赖锁定、Ruff、mypy、pytest-cov、pre-commit。
2. 为 API/Flow/数据库断言 YAML 定义 Schema，并在 collection 阶段校验。
3. 改造报告为按 `run_id` 唯一目录，输出 JSON/JUnit/HTML。
4. 将完整 HTTP exchange timeline、步骤上下文和资源台账写入产物。
5. 完善脱敏、超时、失败分类和 setup 阶段失败记录。
6. 实现 `steelmill-runner run --manifest`，先支持 `api`、`smoke` 和非 mutation 流程。
7. 为 mutation 测试增加 `run_id`、ResourceLedger、逆序清理、补偿与脏数据清单；未完成隔离前保持串行执行。
8. 强化 Flow：步骤依赖、轮询、全流程 deadline、安全重试和内部/外部观察器的统一步骤结果。
9. 为 `common/` 增加离线单测和基础覆盖率门槛。

验收：一份 Manifest 可在 IDE、本机无 UI 和 Docker 中运行，得到稳定的 `result.json`、JUnit、HTML 与完整过程产物；复杂工艺失败时可定位到 HTTP、内部状态、外部模拟器或清理阶段。

### Phase 2：TestPilot Runner 接入（2～3 周）

目标：平台可以调度并展示 SteelMill 测试，但不迁移业务代码。

行动：

1. 在 TestPilot 增加 Runner 注册模型：名称、镜像、版本、Schema、能力声明。
2. 增加 SteelMill Runner Adapter：生成 Manifest、启动进程/容器、收集结果。
3. 增加外部 Runner Run 表、case/step 结果、产物索引和失败分类。
4. 平台环境模型增加 Secret reference、环境能力和 mutation 策略。
5. 平台界面先只提供：选择环境、选择标签、是否允许 mutation、发起任务、查看结果。
6. TestPilot 原生 API Runner 保持用于简单契约和冒烟；SteelMill 复杂流程走外部 Runner。
7. 平台为外部 Runner 保存关联仓库、Git revision、工作目录和 Manifest 下载入口；开发者可在已配置的 IDE 中打开对应仓库调试，但平台不执行任意 IDE/Shell 指令。

验收：在 TestPilot 中选择 SteelMill 项目和 staging 环境，可发起 API Smoke；完成后平台能查看每个用例、HTML、JUnit 和失败产物。

### Phase 3：Docker Desktop 本地一致执行（1～2 周）

目标：开发机和 CI 不再依赖个人 Python 环境。

行动：

1. 创建 `steelmill-runner` Dockerfile 和 Compose profile。
2. 使用 lock 文件固定依赖；制作最小镜像。
3. 配置 artifacts Volume 和按 `run_id` 的目录结构。
4. 为本地测试环境增加 Redis/模拟器 profile；不默认启动高风险 E2E。
5. 验证容器网络、数据库只读凭据、超时退出和日志采集。

验收：Docker Desktop 一条命令执行 Smoke，平台和本地都可读取相同结果格式。

### Phase 4：Git 与 CI/CD 质量门禁（2 周）

目标：让接口测试影响发布，而非只是手工工具。

行动：

1. SteelMill PR Pipeline：格式、类型、框架单测、YAML Schema、collect-only。
2. 部署后 Pipeline：以 Docker Runner 跑 Smoke，上传 JUnit/产物。
3. 夜间 Pipeline：API/Flow/E2E/模拟器，mutation 需要专门测试环境。
4. 建立 TestPilot 导入接口或 CLI 回传；CI Job URL 与 Git SHA 写入结果。
5. 按 P0/P1、失败分类、未清理资源和质量阈值实现门禁。

验收：PR、测试环境部署、夜间回归三类流程可区分运行、报告可回溯、失败可阻断。

### Phase 5：公共内核提取与多项目复用（持续）

前提：SteelMill 和平台已通过 Manifest 集成稳定运行至少一个迭代周期。

行动：

1. 从 SteelMill `common/` 中抽取已稳定的无领域依赖代码。
2. 与 TestPilot 对应实现做“保留/替换/适配”决策，禁止双向复制。
3. 发布内部 `testpilot-testkit` 包，采用语义化版本。
4. 新项目优先使用 TestPilot Core/Testkit；SteelMill 只保留领域扩展。
5. 增加第二个非 SteelMill 项目验证复用性。

验收：新项目不需要复制 SteelMill 整个目录，只需引用 Testkit、声明环境和编写领域用例。

---

## 10. 近期优先级清单

### 必须先做

1. 冻结 TestPilot 平台原生接口路线与 SteelMill 复杂工艺路线的职责边界。
2. 定义 Manifest、Result、Artifact 三个标准模型。
3. 将 SteelMill 报告改成唯一 `run_id` 的 JSON/JUnit/HTML 产物，并保存完整步骤证据。
4. 为 SteelMill 写一个无界面 Runner CLI，同时保留 IDE 调试入口。
5. 优先补齐环境能力、测试数据台账、清理补偿、内部/外部观察器和 Flow 超时。
6. 将 TestPilot 接入该 CLI/容器，而不是复制其业务逻辑。

### 之后做

1. YAML Schema、资源台账、环境能力模型、数据观察器。
2. Docker 化 Runner。
3. CI/CD 分层执行与质量门禁。
4. 平台 UI 扩展、趋势看板、审批与通知。

### 暂时不要做

1. 把全部 SteelMill 用例强行迁移为平台拖拽流程。
2. 再写第三套 HTTP 客户端或第三套报告格式。
3. 一开始就做微服务、Kubernetes、复杂多租户权限。
4. 让 AI 自动写库、自动修复环境或绕过 mutation 审批。
5. 把生产账号、真实连接串或请求产物提交到 Git/镜像。

---

## 11. 大厂方向的衡量标准

真正的工程化，不是目录多、页面多，而是具备以下能力：

- **可复现**：相同 Git SHA、Runner 版本、Manifest 和环境，结果可重复。
- **可追溯**：每个结果可追到代码版本、用例版本、环境、数据、日志和证据。
- **可隔离**：测试数据、账号、环境、权限和生产边界清晰。
- **可扩展**：新项目只需接入通用契约和 Runner，不复制粘贴框架。
- **可交付**：测试能在 Git、CI/CD 和容器中稳定运行并影响发布决策。
- **可治理**：高风险写操作可审批、可审计、可清理，失败不掩盖。
- **有价值**：不只断言 HTTP 200；核心流程同时验证接口、状态、不变量和必要副作用。

SteelMill 是证明这些能力的第一个工业级样板；TestPilot 是把这些能力沉淀成可被更多项目使用的产品。二者分工明确、通过标准执行契约连接，整体路线才不会乱。
