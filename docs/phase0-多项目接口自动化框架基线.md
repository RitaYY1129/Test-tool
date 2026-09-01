# Phase 0：多项目接口自动化框架基线

> 状态：已完成（架构、协议与 TestPilot 平台侧基础实现；不包含 SteelMill 业务代码迁移）
>
> 关联主计划：[SteelMill 与 TestPilot 接口自动化平台演进计划](SteelMill与TestPilot接口自动化平台演进计划.md)

## 1. Phase 0 的决定

目标框架不是只服务 SteelMill。SteelMill 是第一个复杂工业项目和参考实现；以后接入相似项目时，开发者只应维护项目配置、测试用例、测试数据和必要的领域脚本，不能复制或修改通用执行内核。

```text
新项目接入 = 项目适配配置 + 测试资产 + 可选领域扩展

不需要修改 = HTTP 执行、认证策略、变量、断言、流程、数据库观察、
             数据生命周期、日志、报告、Runner 协议、Docker/CI 交付
```

框架应采用“通用内核 + 项目适配层 + 测试资产层”的结构。

```text
testpilot-testkit（通用内核）
    ├─ HTTP / 认证 / 超时 / 重试
    ├─ 断言 / 变量 / 数据驱动 / 流程编排
    ├─ 数据库和外部状态观察器
    ├─ 测试数据台账、清理与补偿
    ├─ 脱敏、日志、产物、结果协议
    └─ pytest 插件和 Runner CLI

project-adapter（项目适配层）
    ├─ 项目环境定义、凭据引用、数据库 Profile
    ├─ 成功 Envelope、登录策略、业务状态字典
    ├─ 可选外部系统、模拟器和领域观察器
    └─ 项目风险策略与资源池

test-assets（测试资产层）
    ├─ API / Flow / E2E 用例
    ├─ YAML / JSON / CSV 数据集
    ├─ 领域数据工厂和复杂 Python 脚本
    └─ 业务不变量、数据库断言和补偿定义
```

## 2. 三层边界

### 2.1 通用内核：任何项目都不能修改业务含义

通用内核只解决“如何测试”，不解决“钢厂业务是什么”。

| 能力 | 通用内核负责 | 禁止硬编码 |
|---|---|---|
| HTTP | 请求、超时、重试、Trace ID、认证策略接口 | SteelMill 路径、字段、工艺状态 |
| 断言 | HTTP、JSONPath、Schema、耗时、集合、不变量语法 | 某项目的 `code=200` 含义 |
| 变量 | `${name}`、提取、作用域、敏感标记 | `batchNo`、`furnaceId` 等业务变量 |
| 流程 | 步骤、依赖、轮询、条件、补偿 | 入库、装炉、出库顺序 |
| 数据 | YAML/JSON/CSV、数据工厂接口、资源台账 | 某项目固定账号/设备/物料 |
| 观察器 | Database/Redis/File/Message 接口和只读安全规则 | 表名、SQL、消息主题 |
| 报告 | Run/Case/Step/Artifact 标准结果、脱敏、JUnit/HTML/JSON | 业务页面文案和字段映射 |

### 2.2 项目适配层：每个项目只提供差异

项目适配层是“换项目时应该改的地方”。它必须是声明式配置优先，只有无法声明的差异才允许写 Python Adapter。

```text
projects/
  steelmill/
    project.yaml              项目元数据、默认策略
    environments/*.yaml       非敏感环境模板
    adapters/
      auth.py                 可选：特殊登录/刷新 Token
      observers.py            可选：Redis、模拟器、第三方观察器
      factories.py            可选：领域测试数据创建与清理
  another-project/
    project.yaml
    environments/*.yaml
    adapters/...
```

项目适配层允许定义：

- API Base URL、超时、TLS、代理等环境差异；
- 凭据名称和 Secret 引用，不允许保存真实密码；
- 登录接口、Token 提取路径、业务成功/失败 Envelope；
- 数据库连接引用、只读账号、允许的查询模板；
- 资源池：测试账号、设备、工位、唯一数据前缀；
- 外部系统/模拟器的启动、健康检查和观察方式；
- 项目级的 marker、风险策略和默认选集。

### 2.3 测试资产层：业务团队长期维护的内容

测试资产是项目特有的“测什么”。它应与应用代码一起进入 Git，并随着业务版本演进。

```text
tests/
  api/                        单接口和数据驱动用例
  flows/                      多接口流程
  e2e/                        复杂工艺和跨系统场景
  data/                       YAML/JSON/CSV 数据集
  sql/                        经审核的只读 SQL 模板
  scripts/                    仅在 YAML 无法表达时使用的领域脚本
```

任何新项目的接入原则是：优先新增这两层，禁止通过复制 `common/` 或修改全局 HTTP 客户端来实现业务需求。

## 3. 当前代码的能力归类

以下是当前 SteelMill 与 TestPilot 代码的初步分类。这个分类指导后续 Phase 1 的渐进抽取，不要求 Phase 0 立刻移动文件。

| 当前位置 | 当前能力 | 目标归属 | 处理策略 |
|---|---|---|---|
| SteelMill `common/client.py`、`auth.py` | HTTP、登录、Token | 通用内核 + 项目适配 | 抽象认证策略；SteelMill 登录细节保留在 Adapter |
| SteelMill `common/assertions.py` | HTTP/JSON/业务 Envelope 断言 | 通用内核 + 项目适配 | 基础断言通用化；成功码范围移入项目配置 |
| SteelMill `common/data_loader.py` | YAML/JSON/CSV、变量替换 | 通用内核 | 优先抽取，补 Schema 校验 |
| SteelMill `common/flow.py`、`flow_runner.py` | 流程与上下文 | 通用内核 | 扩展为依赖、轮询、补偿、步骤产物 |
| SteelMill `common/database_assertions.py` | PostgreSQL 只读断言 | 通用观察器 | 保留只读限制；表和 SQL 归测试资产 |
| SteelMill `common/logger.py`、`report.py`、`hooks.py` | 日志、产物、报告 | 通用内核 | 统一 Run ID、JSON/JUnit/HTML 协议 |
| SteelMill `modules/`、Simulator、工艺 E2E | 钢厂领域测试 | SteelMill 测试资产/扩展 | 保留在 SteelMill，不迁移进平台 UI |
| TestPilot `engines/http_engine.py`、`assertions.py`、`variables.py` | 平台原生 API 执行 | 通用内核候选 | 与 SteelMill 对齐后只保留一个标准实现 |
| TestPilot `storage/`、`ui/`、`cli.py`、`notifications.py` | 平台控制面 | TestPilot 平台 | 不进入测试框架包 |
| TestPilot `parsers/`、`model_providers/` | 导入、分析、AI 草稿 | TestPilot 平台 | 不依赖 SteelMill 领域代码 |

## 4. 新项目接入模型

接入一个新的数据流项目时，应按以下流程完成，而不是复制 SteelMill 目录。

```text
1. 创建项目 Adapter
   └─ project.yaml、环境模板、Secret 引用、认证/DB/外部系统差异

2. 导入接口资产
   └─ OpenAPI/Postman/源码/人工接口定义

3. 编写测试资产
   └─ API 用例、Flow、数据集、只读 SQL、必要领域脚本

4. 本地 IDE 调试
   └─ 使用同一个 Runner CLI 和 Manifest

5. TestPilot 管理与执行
   └─ 平台选择项目、环境、标签和风险策略

6. Docker / CI 执行
   └─ 使用同一个 Manifest，上传相同的结果和产物
```

新项目最少需要的文件示例：

```yaml
# projects/new-project/project.yaml
project_id: new-project
display_name: 新项目
adapter_version: 1

api:
  authentication:
    kind: bearer_login
    login_path: /auth/login
    token_path: data.accessToken
  envelope:
    success_code_range: [200, 299]

database:
  profile: primary_readonly

execution:
  default_timeout_seconds: 30
  allowed_markers: [api, smoke, flow]
  mutation_requires_approval: true
```

```yaml
# projects/new-project/environments/staging.yaml
environment_id: staging
base_url: https://staging.example.com
secret_refs: [new-project-staging-account, new-project-readonly-db]
capabilities:
  allow_mutation: false
  allow_database_observation: true
  allow_external_system: false
```

其中真实 Token、密码、数据库地址和私钥不能进入 Git；本地、TestPilot、Docker 和 CI 只通过 Secret 引用或运行时环境变量注入。

## 5. Runner v1 协议冻结

### 5.1 输入：Run Manifest

所有项目都由同一个 Runner 命令接收 Manifest：

```powershell
testpilot-runner run --manifest run-manifest.json
```

SteelMill 过渡期可以继续使用：

```powershell
steelmill-runner run --manifest run-manifest.json
```

Manifest 最小字段：

```json
{
  "schema_version": "1.0",
  "run_id": "run_20260826_001",
  "project_id": "steelmill",
  "runner": {"name": "steelmill-runner", "version": "0.1.0"},
  "environment_id": "staging",
  "selection": {
    "paths": ["tests/api"],
    "markers": ["api", "smoke"],
    "case_ids": []
  },
  "policy": {
    "allow_mutation": false,
    "timeout_seconds": 1800,
    "parallel_workers": 1,
    "retry_policy": "read_only_only"
  },
  "artifacts_dir": "/artifacts/run_20260826_001"
}
```

### 5.2 输出：Run Result 与 Artifacts

每次运行都必须输出：

```text
artifacts/<run_id>/
  manifest.json
  result.json
  junit.xml
  report.html
  runner.log
  cases/<case-id>/...
```

`result.json` 至少包含：运行状态、时间、项目/环境/Runner 版本、统计、每个用例状态、失败分类和产物相对路径。平台只读取该结构化文件，不解析控制台文本。

## 6. 测试分层和统一标签

以下标签跨项目统一，业务标签可以追加但不得改变语义：

| 标签 | 含义 | 默认运行场景 |
|---|---|---|
| `unit` | 框架和 Adapter 的离线测试 | 本地、PR |
| `api` | 单接口或小范围接口回归 | PR 后、测试环境 |
| `smoke` | 发布后快速验证 | 部署后门禁 |
| `flow` | 多接口数据流 | 测试环境、夜间 |
| `e2e` | 跨系统/模拟器/外部工艺 | 夜间、发布候选 |
| `mutation` | 创建、修改或删除数据 | 受控环境、审批后 |
| `nightly` | 耗时回归 | 定时任务 |
| `p0/p1/p2` | 用例业务优先级 | 门禁策略 |

## 7. Phase 0 验收结果

- [x] 定义多项目可复用的三层架构。
- [x] 明确 SteelMill 是参考项目和领域 Runner，不是全局框架本体。
- [x] 明确 TestPilot 是控制面与平台产品，不复制领域工艺。
- [x] 定义项目接入最小配置、环境能力和 Secret 使用方式。
- [x] 冻结 Runner Manifest、Result、Artifact 的最小协议。
- [x] 冻结跨项目标签与风险语义。
- [x] TestPilot 实现 `testpilot.contracts.runner`：Manifest/Result 的版本校验与序列化。
- [x] TestPilot 数据库 Migration 11：项目 Adapter、Runner 注册、外部 Runner 运行记录。
- [x] TestPilot 实现外部 Runner 入队/结果归档服务；此阶段只保存任务，不执行任意 Shell 命令。
- [x] 为环境增加 `capabilities` 与 `secret_refs` 元数据，真实密钥仍不保存到普通配置字段。
- [ ] Phase 1：把协议实现到 SteelMill Runner，并验证第一个端到端样例。

当前新增的 TestPilot 源码位置：

```text
src/testpilot/contracts/runner.py       RunManifest / RunResult v1
src/testpilot/engines/external_runner.py 外部 Runner 入队与结果归档
src/testpilot/storage/database.py        Migration 11 与平台存储接口
tests/test_runner_contracts.py           多项目协议与持久化离线测试
```

## 8. Phase 1 的唯一入口

Phase 1 不做“全部重构”。第一个可运行目标是：

```text
SteelMill API Smoke
  → 读取 Run Manifest
  → 校验 environment / mutation 策略
  → 执行 pytest
  → 写出 result.json + junit.xml + report.html
  → 可由 TestPilot 或 Docker 读取
```

这个闭环成功后，再依次加入数据台账、复杂 Flow、数据库/Redis/模拟器观察和多项目 Adapter。
