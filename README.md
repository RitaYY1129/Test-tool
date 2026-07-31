# TestPilot AI

第一阶段桌面版本：双路线接口导入、资料完整度、测试计划、结构化用例、
人工确认、确定性执行、证据记录和独立报告。

## 运行

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
testpilot-ai
```

也可以执行：

```powershell
$env:PYTHONPATH="src"
python -m testpilot.main
```

数据默认保存在 `%LOCALAPPDATA%\TestPilotAI\testpilot.db`。运行测试：

```powershell
pytest
```

## 当前范围

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

详细能力边界与验收状态见 [第一阶段验收清单](docs/phase1-acceptance.md)，操作流程见
[使用说明](docs/user-guide.md)。

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
