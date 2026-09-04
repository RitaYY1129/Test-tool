# SteelMill Runner 与 Docker 离线验证操作说明

> 本文记录已完成的验证、每一步实际在做什么，以及后续如何接入 TestPilot。
> 不包含真实账号、密码、Token、数据库连接串或测试环境配置。

## 1. 先分清四个东西

```text
测试环境
  └─ 已部署的 SteelMill 服务、数据库、Redis 等

SteelMill 源码工程
  └─ D:\qingfeng\Demo\steel_mill

Python API 自动化 Runner
  └─ D:\qingfeng\Demo\steel_mill\src\SteelMill.Test\FieldOperationsTests\python_api_tests

TestPilot
  └─ 管理项目、环境、Runner 任务和测试报告的桌面平台
```

`D:\qingfeng\Demo\Docker` 中的 `docker-compose.yml` 用于启动业务测试环境。
它不是 Python 自动化测试 Runner 的 Docker 工程。

Python Runner 的 Dockerfile 位于 `python_api_tests` 目录，所以构建测试镜像时必须在该目录执行 Docker 命令。

## 2. 本次验证做了什么

### 2.1 C# 文件日志测试

执行过：

```powershell
dotnet run --project .\src\SteelMill.Test\SteelMill.Test.csproj -- --file-log-test
```

它执行的是 `SteelMill.Test\FileLogWriterTest.cs` 中的本地文件日志测试：定时刷新、批量写入、并发、轮转、过载统计、故障恢复和关闭并发。

它只在 `%TEMP%\SteelMill.FileLogWriterTests\<唯一ID>` 下创建临时文件，成功后自动清理；不访问 API、测试数据库或 Redis。

这个 C# 控制台测试与下面的 Python API Runner 是两套不同的测试体系。

### 2.2 Python 本机离线 Unit

Python Runner 目录：

```text
D:\qingfeng\Demo\steel_mill\src\SteelMill.Test\FieldOperationsTests\python_api_tests
```

该工程包含：

```text
runner/             Runner 入口
tests/              单元测试
examples/           Manifest 示例
Dockerfile          Runner 容器定义
pyproject.toml      Python 工程定义
.venv/              本机虚拟环境
```

原 `.venv` 指向已经不存在的 Python 安装目录，因此重建为当前机器可用 Python 后，执行了：

```powershell
.\.venv\Scripts\python.exe -m runner run --manifest .\examples\run-manifest.unit.example.json
```

返回码为 `0`，并在 `reports` 下产生标准产物。

### 2.3 Docker 离线 Unit

Docker 镜像已构建成功：

```text
steelmill-runner:0.1.0
```

为了让镜像可运行，Dockerfile 做了两项必要修正：

```dockerfile
COPY pyproject.toml README.md conftest.py ./
RUN pip install --no-cache-dir -e .
```

原因：

- `conftest.py` 注册 pytest 的 `--run-id`、`--artifacts-dir` 参数；不复制它，pytest 会拒绝这些参数。
- Runner 会从工程目录读取 `config`；editable 安装保证镜像中的 Runner 能从 `/app/config` 找到示例配置。

离线 Unit 的 Manifest 使用：

```json
"environment_id": "local"
```

因为 `config.example.yaml` 中定义的环境是 `local` 和 `simulator`，并不存在名为“测试环境”的环境。离线 Unit 使用 `local` 仅用于策略校验；容器通过 `--network none` 断网，不会访问 `127.0.0.1:5010` 或其他服务。

实际执行命令：

```powershell
docker run --rm --network none -v "${PWD}/examples/run-manifest.unit.example.json:/input/run-manifest.json:ro" -v "${PWD}/reports-docker:/reports" -v "${PWD}/config/accounts.example.yaml:/app/config/accounts.yaml:ro" steelmill-runner:0.1.0 run --manifest /input/run-manifest.json
```

命令含义：

| 参数 | 作用 |
|---|---|
| `--rm` | 结束后删除临时容器，不删除镜像和报告 |
| `--network none` | 容器完全断网，不能访问 API、数据库、Redis 或互联网 |
| 第一个 `-v` | 以只读方式传入 Unit Manifest |
| 第二个 `-v` | 将容器中的 `/reports` 保存到本机 `reports-docker` |
| 第三个 `-v` | 以只读方式传入无密钥的 `accounts.example.yaml`，不传入真实账号 |

> Manifest 中的 `artifacts_dir` 是相对于 `/input/run-manifest.json` 解析的，最终为 `/reports/run_unit_example_001`，所以报告必须挂载到容器 `/reports`，不能挂到 `/app/reports`。

最终结果：

```text
退出码：0
Python：3.13.15
pytest：16 passed
```

`reports-docker/run_unit_example_001` 中已生成：

```text
manifest.json
result.json
junit.xml
report.html
runner.log
execution.db
logs/
```

## 3. 当前已经完成与尚未执行的内容

| 项目 | 状态 |
|---|---|
| C# 文件日志本机测试 | 已通过 |
| Python 本机离线 Unit | 已通过 |
| Docker 镜像构建 | 已通过 |
| Docker 内离线 Unit（断网） | 已通过，16 passed |
| TestPilot 登记本机 Python Runner | 待执行 |
| 只读 API Smoke | 未执行 |
| Docker 访问真实测试环境 | 未执行 |
| 跨电脑自动调度 Agent | Phase 2，未实现 |

## 4. 下一步：在 TestPilot 中登记本机 Runner

打开：

```text
接口测试
  → 路线 A：外部工程测试
    → 外部 Runner
```

填写：

```text
项目 Adapter Key：steelmill
Runner 名称：steelmill-runner
Runner 版本：0.1.0
SteelMill Python：
D:\qingfeng\Demo\steel_mill\src\SteelMill.Test\FieldOperationsTests\python_api_tests\.venv\Scripts\python.exe

工作目录：
D:\qingfeng\Demo\steel_mill\src\SteelMill.Test\FieldOperationsTests\python_api_tests

镜像标识：可先留空
启用此 Runner：勾选
```

保存后，日常先只选择“离线 Unit”。TestPilot 会创建平台任务、生成受控 Manifest、运行固定 Python + Runner 命令，并归档结果。

## 5. 暂时不要执行的内容

暂时不要执行：

```text
readonly-smoke
mutation
压力测试
```

它们可能访问测试 API、使用账号或写入测试数据。只有在 TestPilot 的“环境校验”里明确配置并授权测试环境后，才允许执行只读 Smoke。

不要将下列文件提交到 Git、复制到 TestPilot 或打进镜像：

```text
config/accounts.yaml
config/config.yaml
.env
数据库连接串
测试账号、密码、Token
```

## 6. 跨电脑执行的边界

当前阶段，TestPilot 的“一键执行”只能启动**当前电脑**已登记的 Python 和工作目录。

若要跨电脑：

```text
电脑 A：TestPilot 登记/导入 Manifest 并创建平台任务
电脑 B：使用同一份 Manifest 执行 Python Runner 或 Docker Runner
电脑 B：生成 result.json、JUnit、HTML、日志
电脑 A：导入同 run_id 的 result.json 归档
```

只传递脱敏后的报告产物；不要共享 TestPilot 的 SQLite 数据库，也不要复制真实 `accounts.yaml`。

“在电脑 A 点击、电脑 B 自动执行”需要后续增加受控 Runner Agent/Worker，属于 Phase 2。

## 7. 需要提交到 SteelMill 源码仓库的改动

以下改动是 Docker Runner 可重复运行所必需的，应在确认无误后提交到 **SteelMill 源码仓库**：

```text
1. Dockerfile：复制 conftest.py
2. Dockerfile：使用 pip install -e .
3. examples/run-manifest.unit.example.json：environment_id 改为 local
```

`reports-docker` 属于运行产物，不应提交。
