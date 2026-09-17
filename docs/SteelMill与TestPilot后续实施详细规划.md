# SteelMill 与 TestPilot 后续实施详细规划

> 版本：2026-09-17（按当前代码与本机证据复核）
>
> 当前基线：阶段 A/B 的本地代码闭环已完成；L2/L3 工作流与回传元数据已就绪，但仍需真实 Gitea 审批验收；阶段 D/E 与最终发布收口未完成。
>
> 执行原则：测试资产保留在 `test/steelmill-api-automation` 分支；不向 `main` 合入该测试目录；所有真实写入仅允许作用于获批准的本机测试环境 `127.0.0.1`。

---

## 1. 当前能力基线

| 能力 | 状态 | 已有证据/实现 |
|---|---|---|
| 标准执行协议 | 完成 | `RunManifest v1`、`RunResult v1`、唯一 `run_id`、JSON/JUnit/HTML/日志 |
| SteelMill Runner | 完成 | `steelmill-runner run --manifest`、环境及 mutation 策略校验 |
| 复杂 Flow | 完成 | 本机真实受控 Flow、资源台账、逆序清理、Redis 工艺位置恢复 |
| 观察与证据 | 完成基础 | HTTP、PostgreSQL、Redis、模拟器观察时间线 |
| Docker | 完成核心验证 | `steelmill-runner:0.1.0`、Docker 只读 Smoke、挂载产物 |
| Gitea 本地质量门禁 | 完成 | Windows Runner 在线；Ruff、mypy、pytest/coverage、collect-only、证据上传已通过 |
| 审批式 Smoke / Mutation | 已部署、未验收 | 工作流、脚本、密钥配置存在；不默认触发 |
| TestPilot 平台接入 | 已实现大部分 | Runner 登记、Manifest 入队、结果归档、任务/产物查看、一键执行；已支持从 `config/test_suites.yaml` 动态加载模块与受控套件 |
| HTTPS、正式 Release | 后置 | 不影响当前测试闭环 |

### 阶段 A 已补齐：动态测试资产目录（2026-09-14）

- TestPilot 新增受控的 `config/test_suites.yaml` 加载器：仅接受 Runner 工作目录内、已存在的相对 Manifest；拒绝绝对路径、`..` 越界路径、重复 ID、缺失 Manifest 和未审批的 mutation 套件；
- 外部 Runner 页面中的模块和测试套件由目录动态加载，不再固定为两个页面选项；选择套件会同步 Manifest、风险、范围和清理策略预览；
- SteelMill 测试目录现已登记只读 Smoke、离线 Unit 与完整 Flow 三个套件；完整 Flow 使用专用本机 Manifest，并受 mutation、环回地址与人工授权三重约束；
- 新增动态目录单元测试；目录加载、Runner 任务与结果定向回归共 13 项通过。

## 2026-09-17 实施对齐记录

| 规划项 | 当前判定 | 本次落地/证据 |
|---|---|---|
| A 稳定运行 | 代码与本地门禁完成，周期性退出条件待时间验证 | SteelMill unit：17 passed；Ruff：通过；运行态/发布目录与测试资产分离提交 |
| B 平台端到端 | 本地代码闭环完成，正式人工验收待执行 | TestPilot：70 passed；正常 Flow 已有平台任务证据；补齐环回写入限制、初始化失败四件套、错误与 CI 元数据显示、受控失败探针和操作手册 |
| C L2/L3 CI | 实现完成，真实 Gitea Job 未验收 | 两条审批工作流统一走 Runner Manifest；Result 携带 Git SHA、Job ID/URL、执行节点；仍需真实 Secret、审批和制品留档 |
| D 发布候选门禁 | 未开始 | 需要先获得 L2/L3 稳定运行证据 |
| E 公共 Testkit/第二项目 | 未开始 | 需满足“稳定一个迭代周期”的启动前提 |
| HTTPS/Token/Tag/Release | 后置、未完成 | 需要维护窗口和外部系统权限 |

> 判定口径：代码、单测或工作流文件“已实现”与真实环境“已验收”分开记录；没有 CI Job/制品和审批记录时，不宣称 L2/L3 完成。

## 2. 总体路线和完成顺序

```text
A. 稳定运行测试分支
        ↓
B. TestPilot 平台端到端验收
        ↓
C. 内部 CI 分层执行（只读 Smoke → 审批 Mutation）
        ↓
D. 多项目公共内核复用
        ↓
E. 最终安全与发布收口（HTTPS / Tag / Release）
```

前一阶段应留下可重复的证据后，再进入下一阶段。不要因为已有工作流文件就把未真正执行的 Smoke/Mutation 宣布完成。

---

## 3. 阶段 A：稳定运行与日常维护

### 目标

让测试分支能够持续跟随后端主干，而不污染 `main`，并保持每次测试脚本变更都经过本地和 Gitea 质量门禁。

### A1. 分支模型

| 分支 | 用途 | 是否保存测试脚本 |
|---|---|---|
| `main` | 后端业务开发主干 | 否，保持后端代码主干干净 |
| `test/steelmill-api-automation` | SteelMill 自动化测试资产与 CI 工作流 | 是 |
| 临时修复分支 | 单个测试脚本或工作流改动 | 是，完成后合并到测试分支 |

### A2. 每次后端主干更新后的操作

在 `D:\qingfeng\steel_mill`：

```powershell
git switch test/steelmill-api-automation
git fetch origin
git merge origin/main
git push
```

含义：将最新后端代码同步到测试分支，然后由 Gitea 自动运行 **Quality Gate**。这不是把测试脚本并回 `main`。

如遇冲突：只处理测试分支中与后端变化直接相关的文件；先运行本地门禁，再提交合并结果。禁止使用 `git add .`，避免误提交发布目录、缓存、环境文件或测试报告。

### A3. 本地提交前门禁

在 `python_api_tests` 目录执行项目现有 `scripts/quality_gate.ps1`。它应至少检查：

1. Ruff 静态检查；
2. mypy 类型检查；
3. pytest 与覆盖率下限；
4. YAML/pytest collect-only；
5. 不提交账号、密码、Token、报告、虚拟环境和本机配置。

### A4. 通过条件

- 测试分支能同步 `main`；
- 本地门禁和 Gitea Quality Gate 均成功；
- Git 状态仅包含本次测试资产改动；
- 不因普通 push 访问 API、数据库、Redis 或模拟器。

### A5. 退出条件

至少连续一个后端迭代周期稳定完成“同步主干 → Quality Gate → 修复 → 再通过”。

---

## 4. 阶段 B：TestPilot 平台端到端验收

### 目标

确认 TestPilot 不只是能保存结果，而是能受控地创建 SteelMill 任务、传递 Manifest、启动已登记的 Runner、读取结果并展示证据。

### B1. 不变的安全边界

- 平台不得拼接任意 Shell 命令；只允许已登记 Runner 的固定入口；
- 平台只存 Secret 引用或密文，不存账号密码明文；
- 平台默认 `allow_mutation=false`；
- 只读 Smoke 与 Mutation 必须是不同任务类型；
- 真实环境仍只限获批本机 `127.0.0.1`，不能指向公司共享环境或生产环境。

### B2. 验收步骤

1. 在 TestPilot 注册 SteelMill Runner：名称、版本、Python/镜像、工作目录、支持标签；
2. 创建本机测试环境：仅保存环境名称、Base URL、能力开关和 Secret 引用；
3. 选择 `api + smoke` 套件，生成 Manifest；
4. 发起一次只读任务；
5. TestPilot 等待 Runner 结束并导入同一 `run_id` 的 `result.json`；
6. 在任务详情验证：用例状态、JUnit、HTML、日志、HTTP 时间线和产物路径；
7. 人工制造一次安全的断言失败，验证平台显示失败分类和证据链接；
8. 确认失败不会覆盖上一次 `run_id` 的报告。

### B3. 通过条件

- 平台任务状态与 `result.json.status` 一致；
- 可从平台定位到 HTML、JUnit 和失败日志；
- 正常、失败、初始化失败三类结果均能归档；
- 平台无法绕过环境能力控制来执行 mutation。

### B4. 交付物

- 一份平台端到端运行记录；
- 一份失败样例及证据；
- Runner 注册与环境配置说明；
- 平台使用人操作手册。

---

## 5. 阶段 C：内部 CI 分层执行与审批

### 目标

将已经通过的 L1 质量门禁扩展为分层、可审计的内部 CI；但不让每次提交触发真实写入。

### C1. 分层模型

| 层级 | 触发方式 | 是否访问真实 API | 是否写数据 | 当前状态 |
|---|---|---:|---:|---|
| L0 本地质量门禁 | 开发者手动 | 否 | 否 | 已可用 |
| L1 Gitea Quality Gate | 测试分支 push | 否 | 否 | 已实际通过 |
| L2 Read-only Smoke | 人工批准、部署后 | 是，仅获批测试环境 | 否 | 工作流已部署，待验收 |
| L3 Mutation Flow | 人工批准、夜间/发布候选 | 是，仅获批测试环境 | 是，可清理 | 工作流已部署，待验收 |

### C2. L2：审批式只读 Smoke

前置条件：

- Windows Runner 在线；
- 本机 API、数据库、Redis 已启动；
- Gitea Secret 已配置且值指向本机获批环境；
- 手工触发入口稳定可用；
- 运行前确认 Base URL 不是生产或共享环境。

执行流程：

1. 人工发起 `Approved Read-only Smoke`；
2. 明确输入 `RUN_READONLY_SMOKE`；
3. Runner 读取 Secret，在运行时注入；
4. Docker/Runner 执行只读 Manifest；
5. 上传 `result.json`、JUnit、HTML、日志、Manifest；
6. 审核制品中的 URL 已脱敏、无密码、状态为 passed。

通过条件：核心只读接口通过，产物齐全，未产生写入数据，CI Job 成功。

### C3. L3：审批式 Mutation Flow

前置条件：

- L2 已稳定通过；
- `allow_mutation=true` 仅在本机测试环境启用；
- PostgreSQL 使用只读观察账号；
- Redis 权限受限；
- 有明确的恢复脚本和恢复前后快照；
- 无其他人同时使用该本机测试数据。

执行流程：

1. 人工批准 `Approved Mutation Flow` 并输入 `RUN_MUTATION_FLOW`；
2. 运行前写入 `run_id`、环境、Git SHA、初始状态；
3. 创建带 E2E 前缀的资源；
4. 执行工艺流转；
5. 观察 HTTP、PostgreSQL、Redis、模拟器状态；
6. 无论成功或失败，都运行 ResourceLedger 逆序清理与补偿；
7. 输出 `resource_ledger.json`、清理结果、残留项和完整制品；
8. 人工确认测试环境状态已恢复。

通过条件：流程断言通过；所有创建资源清理成功，或残留项被明确列出且人工处置；Redis 位置恢复；制品完整。

### C4. CI 到 TestPilot 回传

在 L2/L3 稳定后实施：

1. CI 生成包含 Git SHA、Runner 版本、环境、Job URL 的 `result.json`；
2. CI 通过 TestPilot 受控 CLI/API 归档结果；
3. TestPilot 保存 CI Job URL、制品路径、失败分类；
4. 失败时仅通知指定人员，不自动重试 mutation；
5. 对只读 flaky 测试记录重试次数和首次失败，不用“重试成功”掩盖问题。

---

## 6. 阶段 D：扩展回归、告警与发布候选门禁

### 目标

将成熟的测试从“能运行”变为“能参与发布决策”。

### D1. 测试分层扩展

- P0：登录、健康检查、关键只读接口；
- P1：核心作业接口与关键状态断言；
- P2：完整工艺 Flow、数据库不变量、模拟器联动；
- nightly：耗时长或需要独占数据的回归；
- release-candidate：人工批准的发布候选集合。

### D2. 发布候选门禁规则

发布候选不只判断“通过率”，还必须满足：

- P0/P1 全部通过；
- 不存在 `environment_error`、`runner_error` 或未解释的 timeout；
- 不存在未说明的脏数据或未恢复 Redis 位置；
- JUnit、HTML、`result.json`、资源台账均可追溯；
- 已记录被测服务 SHA/版本、测试脚本 SHA、Runner 镜像版本；
- 高风险 Flow 已有人工审批记录；
- 明确区分产品缺陷、环境故障、测试脚本问题和测试数据问题。

### D3. 失败处置

| 类型 | 默认动作 |
|---|---|
| 产品断言失败 | 阻断候选，创建缺陷或工单 |
| 环境不可用 | 标记环境错误，修复环境后重新运行 |
| Runner/脚本错误 | 修复脚本后先过 L0/L1，再重新运行 |
| 清理失败 | 阻断后续 Mutation，人工恢复并保留资源台账 |
| 只读偶发失败 | 允许有限重试，但记录首次失败与重试次数 |

---

## 7. 阶段 E：公共内核与多项目复用

### 启动前提

SteelMill 与 TestPilot 的 Manifest 集成、平台任务归档和 L2 Smoke 已稳定运行至少一个迭代周期。

### 工作项

1. 从 SteelMill `common/` 中盘点无领域依赖的模块；
2. 标记每项为“保留在 SteelMill / 抽取为 Testkit / 平台适配”；
3. 建立内部 `testpilot-testkit` 包，使用语义化版本；
4. 让第二个非 SteelMill 项目接入同一 Manifest/Result 协议；
5. 禁止复制 SteelMill 整个目录作为新项目模板；
6. 建立兼容性矩阵：Testkit 版本、Runner 版本、Manifest Schema 版本、TestPilot 版本。

### 通过条件

第二项目仅需环境配置、领域测试资产和适配层，即可生成与 SteelMill 相同格式的结果和报告。

---

## 8. 最终安全与发布收口（当前明确后置）

这部分不是当前 P1 或日常测试分支任务，等前述阶段稳定后统一处理。

### E1. Gitea HTTP → HTTPS

1. 申请或配置内部证书、域名、反向代理；
2. 备份 Gitea 配置与数据库；
3. 修改服务外部 URL 和 Git remote；
4. 验证 Web、Clone、Push、Actions Runner、Webhook；
5. 更新 Runner 的 instance URL，必要时重新注册；
6. 停用 HTTP 或仅保留受控跳转；
7. 留存迁移记录与回滚方案。

### E2. 两仓库版本与正式 Release

涉及 SteelMill 与 TestPilot 两仓库：

1. 冻结候选版本与对应 Git SHA；
2. 运行发布候选门禁；
3. 编写 Release Note：功能、兼容性、已知限制、升级/回滚说明；
4. 更新版本号；
5. 创建并推送受保护 Git Tag；
6. 在内部 Gitea 创建正式 Release，绑定产物和校验信息；
7. 验证部署版本、Runner 版本、报告中的版本信息一致；
8. 发布后观察并保留回滚 Tag。

### E3. 凭据安全收口

- PAT 已删除；
- 现有 Runner 注册 Token 暂时继续使用；
- 安全维护窗口内重新生成 Runner Token、重新注册 Runner、验证旧 Token 失效；
- 所有 Secret 保留在 Gitea Secret 或内部密钥库；
- 审计 Git 历史、报告、镜像和 CI 日志，确认不含账号、密码、Token 或连接串。

---

## 9. 推荐的近期优先级

### 现在开始做

1. 持续运行阶段 A：让测试分支稳定同步后端 `main`；
2. 每次测试脚本更新均通过本地与 Gitea Quality Gate；
3. 整理 TestPilot Runner 使用说明和一份平台端到端只读任务验收记录。

### 环境稳定后做

4. 触发并验收 L2 审批式只读 Smoke；
5. 将 CI 结果归档/回传至 TestPilot；
6. 在独占本机测试环境触发并验收 L3 Mutation Flow。

### 一个迭代周期稳定后做

7. 建立夜间回归、失败告警和发布候选门禁；
8. 开始公共 Testkit 的抽取与第二项目验证。

### 全项目最后做

9. Gitea HTTPS 迁移；
10. 两仓库版本、Release Note、Tag 和正式 Release；
11. Runner Token 轮换和凭据审计。

---

## 10. 当前阶段的完成判定

当前不应再以“是否把所有规划都做完”判断 P1。正确判定是：

- **P1：核心完成；**
- **Phase 2：已有实现，待平台端到端验收；**
- **Phase 3：核心完成，Compose 全环境 profile 按资源需要再补；**
- **Phase 4：L1 已完成，L2/L3 暂缓并保留工作流；**
- **Phase 5 与最终安全/发布收口：尚未开始，且不应提前插入日常开发。**
