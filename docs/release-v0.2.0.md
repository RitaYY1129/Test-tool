# TestPilot AI v0.2.0

第一阶段接口测试桌面版本。

## 交付物

- `release/TestPilotAI/`：Windows one-folder 绿色版
- `release/TestPilotAI-v0.2.0-win-x64.zip`：压缩包
- ZIP SHA-256：`CD2D78C258DE7436EE08E4F373F9B1C307AE84ED775C07EEAD56ACD84C3A1E4C`

## 已验证

- 13 项核心自动化测试通过
- PySide6 主窗口及 5 个导航页面启动通过
- 打包后的 `TestPilotAI.exe` 启动后保持运行

## 已知边界

- 文档和 Apifox 原生格式属于保守提取，结果必须人工确认。
- 不执行任意 Postman JavaScript。
- Spring Boot 深层 Service 动态业务逻辑仍需测试人员补充。
- 正式对外发布前应在干净 Windows 10/11 虚拟机复验。
