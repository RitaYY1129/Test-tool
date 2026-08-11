# love-diary-backend 测试报告

测试目标：`D:\qingfeng\ZIYAN\Love\love-diary-backend`

测试日期：2026-08-06

## 结果摘要

| 项目 | 结果 |
|---|---|
| Node.js 语法检查 | 通过，应用源码 JavaScript 全部通过 `node --check` |
| 服务启动 | 通过，独立端口 `3138` 启动成功 |
| `GET /api/health` | 200，返回 `status: ok` |
| 未授权访问 `GET /api/diaries` | 401，鉴权拦截生效 |
| 空参数 `POST /api/auth/login` | 400，参数校验生效 |
| 源码接口识别 | Node.js Express，识别 54 个接口、39 个源码文件、99 个符号、76 条调用/写入边 |
| 完整 `npm run test:mobile-auth` | 被数据库依赖阻断 |

## 数据库阻断

后端配置连接 `localhost:3306/love_diary`。测试时本机 `MySQL80` 服务为 `Stopped`，连接结果为 `ECONNREFUSED`，因此验证码登录、用户注册、聊天、共享状态、通话和冷静模式等需要数据库的链路无法继续执行。

已有 Smoke 脚本本身没有被修改，也没有删除测试文件。脚本在数据库不可用时会在清理阶段再次连接数据库并产生 Node.js 异步连接错误，这是环境阻断后的清理异常，不应误判为业务接口断言失败。

## 未执行的范围

- 未执行 `scripts/init-db.js`，避免未经确认初始化或修改本机数据库。
- 未执行生产环境配置、微信、腾讯云短信和第三方服务调用。
- 未删除或覆盖后端目录内任何测试脚本、日志或源码。

## 下一步

启动并准备 `MySQL80`，确认 `love_diary` 数据库和表结构后，重新运行：

```powershell
npm.cmd run test:mobile-auth
```

然后再补充数据库前后状态、共享数据一致性、通话信令和失败补偿检查。
