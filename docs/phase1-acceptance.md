# 第一阶段验收清单

> 本清单只描述当前原型的已实现范围。工业项目的数据流、隐藏工艺、数据库副本和 AI 受控对话的后续目标，以 [V4.0 落地规划](project-plan-v4.0.md) 为准；不要把本清单中的“路线 A 业务流程基础”理解为完整源码驱动测试。

## 已实现并自动化验证

- 项目创建、切换、删除和 SQLite 持久化
- 多套环境切换，公共 Header、变量和本地加密敏感变量
- OpenAPI 3.x、Swagger 2.0 JSON/YAML，本地文件和在线 URL
- Postman Collection v2.1、Environment 和脚本安全分级
- Apifox OpenAPI/Postman 导出及常见原生 JSON 基础解析
- cURL、HAR、Markdown、HTML、Excel、Word、PDF 和手工接口草稿
- 后端源码自动识别：支持 ASP.NET Core 与 Spring Boot 的 Controller、路由、
  请求参数、DTO、权限注解和显式异常
- 路线 A 源码项目分析基础：记录源码文件哈希、版本指纹、类符号、保守依赖证据、
  接口源码位置和分析运行记录；不保存源码正文，也不执行被测项目代码
- 两份接口来源的端点、参数、必填和鉴权差异
- 资料完整度评分、缺失项和补充建议
- 离线规则引擎及 OpenAI-compatible 结构化模型适配器
- JSON Schema、接口存在性和写操作风险校验
- 测试计划预览、用例生成、编辑、复制、删除和人工确认
- Path、Query、Header、Cookie/Header 鉴权、JSON、表单、multipart、文本请求
- Basic、Bearer/JWT、API Key 和自定义 Header
- 动态变量、响应提取、前置依赖、依赖失败跳过和停止任务
- 数据驱动、后置清理和 1～8 有限并发
- 状态码、响应时间、JSONPath 和响应 JSON Schema 断言
- 请求、响应、断言、耗时、来源和风险证据持久化
- HTML/JSON 报告、模块统计和历史报告
- 路线 A 业务流程基础：源码流程草稿、人工确认、SQLite 测试库配置、夹具、
  多步骤 HTTP/数据库断言、逆序补偿和流程审计记录
- 可见/隐藏工艺数据流模型：节点、边、状态观察、证据可信度和人工确认状态
- SQLite 测试库只读 schema 快照、完整性检查、查询观测和流程前后状态对比
- 受控 AI 对话：会话、消息、结构化 artifact、证据引用、人工审批和白名单工具调用留痕
- 历史报告类型、路线、环境、生成/执行时间元数据
- 源码方法、事务边界和 SQL 写入的保守静态证据
- 流程运行时 Trace、A/B 差异报告和脱敏可重放测试包
- PostgreSQL/MySQL DB-API 适配器入口（未安装驱动或未配置连接时安全阻断）
- 未确认测试环境、高风险写操作和危险 Postman 脚本拦截
- PySide6 GUI 无窗口冒烟测试

## 基础支持，需要人工确认

- Apifox 原生私有 JSON：私有结构会随版本变化，官方 OpenAPI 导出优先
- Markdown/HTML/Word/PDF：只提取明确出现的 HTTP Method 和 URL，不猜业务规则
- Excel：按中英文常见列名映射
- HAR：恢复已经发生的请求，不保存捕获到的 Authorization/Cookie 明文
- Postman JavaScript：只分类安全常见规则，不执行任意 JavaScript
- Spring Service 深层业务分支：只识别 Controller 可见的显式异常

路线 A 尚未达到“完整源码驱动测试”验收：Service 深层分支、Repository/数据模型约束、
跨方法调用依赖、代码 Diff 回归范围和更完整的异常链仍需继续实现。当前界面明确标记为基础支持。

当前流程执行器仅支持 SQLite 和显式补偿动作；生产数据库、消息队列、第三方系统副作用
和自动事务快照仍需通过专用适配器实现。

路线 A 已接入统一 AI 模型配置：静态分析提供可追溯源码证据，AI 使用加密保存的 API Token
补充测试计划和结构化用例，之后仍需人工确认并由确定性执行器运行。

## 发布验证

`scripts/build_windows.ps1` 使用 PyInstaller one-folder 模式。本次已在 Windows 11
和 Python 3.14 上成功生成 `TestPilotAI.exe`，并完成后台启动存活检查。正式发布前仍应在
干净的 Windows 10/11 虚拟机中验证中文路径、空格路径、无 Python 环境和离线启动。
