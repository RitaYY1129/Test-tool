# 使用说明

1. 在“项目与导入”新建项目。
2. 根据资料选择 OpenAPI、Postman、Apifox、cURL、HAR、文档或 Spring 源码。
3. 查看导入摘要和完整度；文档草稿需要在“接口管理”编辑确认。
4. 在“环境与请求”创建至少一套环境，填写 Base URL、公共 Header 和变量。
5. Token、password、secret 等变量会自动分离并本地加密。
6. 勾选“已授权的测试/预发布环境”后才能发送请求。
7. 在“用例与执行”输入测试要求并预览计划。
8. 模型配置留空时使用离线规则引擎；填写 OpenAI-compatible 配置时使用结构化模型输出。
9. 生成用例后检查 JSON。任何修改都会把用例重置为草稿。
10. 确认用例；POST、PUT、PATCH、DELETE 会再次提示高风险确认。
11. 执行后可停止任务，并实时查看用例结果和进度。
12. 在“历史报告”查看 HTML/JSON 文件路径和执行汇总。

认证变量约定：

```json
{
  "AUTH_TYPE": "bearer",
  "TOKEN": "token-value"
}
```

Basic Auth 使用 `AUTH_TYPE`、`USERNAME`、`PASSWORD`。API Key 使用
`AUTH_TYPE=api_key`、`API_KEY` 和可选的 `API_KEY_HEADER`。

