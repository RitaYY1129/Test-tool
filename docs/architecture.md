# 架构说明

- `domain`：统一接口模型。
- `parsers`：资料与 Spring 源码解析，输出统一接口模型。
- `cases`：测试计划、离线用例生成和结构校验。
- `model_providers`：离线规则及 OpenAI-compatible 模型适配。
- `engines`：变量、HTTP、断言和批量执行。
- `storage`：SQLite 数据、迁移和审计记录。
- `reports`：独立 HTML/JSON 报告。
- `ui`：PySide6 桌面交互，不承载解析或执行规则。

大模型只生成结构化草稿。确定性代码负责校验、风险拦截、HTTP 执行、证据记录与报告。

