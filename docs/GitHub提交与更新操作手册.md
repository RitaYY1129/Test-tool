# TestPilot AI：GitHub 提交、更新与发行版本手册

适用项目目录：

```text
D:\qingfeng\ZIYAN\Test-tool
```

远程仓库：`https://github.com/RitaYY1129/Test-tool.git`
默认分支：`main`

> 约定：Git 仓库只保存源码、测试、文档和脚本；Windows 可运行包发布到 GitHub **Release** 附件，不提交 `release/` 目录。

## 1. 每次操作前先检查

```powershell
cd D:\qingfeng\ZIYAN\Test-tool
git status
git branch --show-current
git remote -v
```

正常情况下当前分支应为 `main`，远程应显示 `origin` 指向 Test-tool 仓库。

## 2. 日常提交源码并推送 GitHub

如果本地和远程都可能有更新，按这个顺序执行：

```powershell
cd D:\qingfeng\ZIYAN\Test-tool
git status
git pull --rebase origin main
git add .
git diff --cached
git commit -m "feat: 描述本次功能"
git push origin main
git status
```

常用提交说明：

```text
feat: 新增功能
fix: 修复问题
style: 调整界面样式
docs: 更新说明文档
refactor: 重构代码
test: 增加或修复测试
chore: 更新构建或配置
```

例如：

```powershell
git commit -m "fix: 修复导航高亮和页面卡顿"
```

### 只提交指定文件

```powershell
git add src/testpilot/ui/main_window.py
git add src/testpilot/ui/theme.py
git commit -m "style: 优化导航样式"
git push origin main
```

## 3. `git add`、`commit`、`push` 分别是什么意思

```powershell
git add .
```

将修改放进“待提交区”，**还没有上传 GitHub**。

```powershell
git commit -m "说明"
```

在本地创建一个版本记录，**还没有上传 GitHub**。

```powershell
git push origin main
```

将本地提交上传到 GitHub。执行后在 GitHub 仓库网页才能看到该提交。

查看是否还有未推送提交：

```powershell
git status -sb
```

如果出现 `ahead 1`，表示还有 1 个本地提交尚未推送；执行 `git push origin main`。

## 4. 拉取时报“有未提交修改”

报错示例：

```text
error: cannot pull with rebase: You have unstaged changes.
```

推荐做法是先提交本地修改：

```powershell
git add .
git commit -m "chore: 保存本地修改"
git pull --rebase origin main
git push origin main
```

如果修改暂时不想提交：

```powershell
git stash push -m "临时保存"
git pull --rebase origin main
git stash pop
```

恢复后检查、提交、推送：

```powershell
git status
git add .
git commit -m "feat: 完成本次修改"
git push origin main
```

## 5. 发生冲突时怎么处理

先查看冲突文件：

```powershell
git status
```

在冲突文件中会看到：

```text
<<<<<<< HEAD
本地内容
=======
远程内容
>>>>>>> 提交编号
```

手工保留正确内容并删除这些标记后：

```powershell
git add 冲突文件路径
git rebase --continue
```

全部完成后：

```powershell
git push origin main
```

不想继续这次拉取时：

```powershell
git rebase --abort
```

## 6. 发布 Windows 发行版本（GitHub Release）

### 6.1 构建当前最新版

先确保源码已提交并推送，然后在项目根目录执行：

```powershell
python -m PyInstaller --noconfirm --clean --windowed --name TestPilotAI --paths src --distpath release --workpath build-pyinstaller src/testpilot/main.py
```

构建完成后的程序是：

```text
release\TestPilotAI\TestPilotAI.exe
```

> `release/` 是本地运行包目录，`build-pyinstaller/` 是构建缓存。它们都不提交到 Git。

### 6.2 打包为 ZIP

在项目根目录执行：

```powershell
Compress-Archive -Path .\release\TestPilotAI\* -DestinationPath .\TestPilotAI-v1.0.0-windows.zip -Force
```

版本号请按实际情况修改，例如 `v1.0.1`、`v1.1.0`。

### 6.3 在 GitHub 网页发布

1. 打开 `https://github.com/RitaYY1129/Test-tool`。
2. 点击右侧 **Releases**，再点击 **Create a new release**。
3. 填写 Tag，例如 `v1.0.0`。
4. 填写标题，例如 `TestPilot AI v1.0.0`。
5. 在说明中填写本次新增功能和修复内容。
6. 上传 `TestPilotAI-v1.0.0-windows.zip`。
7. 点击 **Publish release**。

用户下载 ZIP 后，解压并运行：

```text
TestPilotAI.exe
```

### 6.4 发布后清理本地 ZIP

ZIP 上传完成后可删除，避免根目录堆积：

```powershell
Remove-Item -LiteralPath .\TestPilotAI-v1.0.0-windows.zip
```

## 7. 为什么不能 `git add release`

`release/` 内包含 EXE 和大量运行依赖，直接提交会让 Git 仓库迅速膨胀。项目 `.gitignore` 已忽略这些目录：

```gitignore
release/
build-pyinstaller/
build/
*.spec
```

正确分工：

| 内容 | 保存位置 |
| --- | --- |
| 源码、测试、文档 | GitHub 仓库提交 |
| Windows EXE 运行包 | GitHub Release 附件 |
| 构建缓存、测试缓存 | 本地临时文件，不上传 |

## 8. 常见提示说明

### `git: 'add.' is not a git command`

少了空格。正确命令：

```powershell
git add .
```

### `LF will be replaced by CRLF`

这是 Windows 换行符提示，不是错误，不影响提交或程序运行。可继续执行提交。

如需采用 Windows 换行符策略，可执行一次：

```powershell
git config --global core.autocrlf true
```

### `nothing to commit, working tree clean`

表示本地没有未提交修改。

### GitHub 没看到刚提交的内容

通常是只执行了 `git add` 或 `git commit`，但没有执行推送：

```powershell
git push origin main
```

## 9. 谨慎使用的命令

以下命令可能丢失修改或覆盖远程历史，未确认前不要使用：

```powershell
git reset --hard
git push --force
git clean -fd
```

如果只是想取消暂存，不会丢失文件内容：

```powershell
git restore --staged .
```

## 10. 最常用速查

### 提交并推送源码

```powershell
cd D:\qingfeng\ZIYAN\Test-tool
git pull --rebase origin main
git add .
git commit -m "feat: 描述本次修改"
git push origin main
```

### 查看问题但不修改内容

```powershell
git status
git status -sb
git branch -vv
git remote -v
git log --oneline --decorate -10
git diff
git diff --cached
```
