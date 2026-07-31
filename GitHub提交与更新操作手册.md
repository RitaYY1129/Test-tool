# GitHub 提交与更新操作手册

## 1. 当前项目的 Git 情况

- Git 仓库目录：`D:\qingfeng\ZIYAN\Love\love-diary`
- GitHub 地址：`https://github.com/RitaYY1129/RitaYY1129.git`
- GitHub 默认分支：`main`
- 本地当前使用分支：`release-sync`
- 当前代码已经与 GitHub 的 `main` 同步
- `love-diary-backend` 目前不是 Git 仓库，也没有上传到这个仓库

目前本地旧 `main` 和 GitHub 的 `main` 提交历史不同，当前真正与 GitHub 同步的是 `release-sync` 分支。

因此，后续不要直接在本地旧 `main` 上提交，继续使用 `release-sync` 最安全。

> 注意：当前远程仓库名是 `RitaYY1129/RitaYY1129`。仓库名和用户名相同，在 GitHub 中通常是个人主页仓库。如果希望项目拥有独立仓库，可以以后新建 `love-diary` 仓库再迁移。

## 2. 日常更新代码到 GitHub

每次先进入前端仓库：

```powershell
cd D:\qingfeng\ZIYAN\Love\love-diary
```

确认当前分支：

```powershell
git branch --show-current
```

正常应该输出：

```text
release-sync
```

查看本地有哪些修改：

```powershell
git status
```

拉取 GitHub 上的最新提交：

```powershell
git pull --rebase origin main
```

添加全部修改和新文件：

```powershell
git add .
```

再次检查准备提交的内容：

```powershell
git status
git diff --cached
```

创建提交：

```powershell
git commit -m "feat: 描述本次修改内容"
```

推送到 GitHub 的 `main`：

```powershell
git push origin HEAD:main
```

完整日常流程：

```powershell
cd D:\qingfeng\ZIYAN\Love\love-diary
git status
git pull --rebase origin main
git add .
git status
git commit -m "feat: 完成本次功能"
git push origin HEAD:main
```

由于本地分支叫 `release-sync`，GitHub 分支叫 `main`，建议始终使用：

```powershell
git push origin HEAD:main
```

不要只写 `git push`，否则可能因为本地和远程分支名称不同而报错。

## 3. 只提交部分文件

不使用 `git add .`，改为指定文件：

```powershell
git add src/App.vue
git add src/components/Diary.vue
```

检查即将提交的内容：

```powershell
git status
git diff --cached
```

确认后提交并推送：

```powershell
git commit -m "fix: 修复日记页面问题"
git push origin HEAD:main
```

## 4. 提交信息写法

常用格式：

```text
feat: 添加新功能
fix: 修复问题
style: 调整页面样式
refactor: 重构代码
docs: 更新说明文档
chore: 更新依赖或配置
```

示例：

```powershell
git commit -m "feat: 添加照片上传功能"
git commit -m "fix: 修复登录失败问题"
git commit -m "style: 优化首页手机端布局"
```

提交信息应该清楚描述本次修改，不建议长期使用 `update`、`修改一下` 等模糊信息。

## 5. GitHub 和本地同时有新修改

如果本地修改已经完成，先提交：

```powershell
git add .
git commit -m "feat: 保存本地修改"
```

然后拉取并推送：

```powershell
git pull --rebase origin main
git push origin HEAD:main
```

如果本地修改还不想提交，可以临时保存：

```powershell
git stash push -m "临时保存"
git pull --rebase origin main
git stash pop
```

恢复修改后，检查并正常提交：

```powershell
git status
git add .
git commit -m "feat: 完成本次修改"
git push origin HEAD:main
```

## 6. 发生代码冲突

拉取时如果出现冲突：

```powershell
git pull --rebase origin main
```

先查看冲突文件：

```powershell
git status
```

冲突文件中通常会出现：

```text
<<<<<<< HEAD
一边的代码
=======
另一边的代码
>>>>>>> 提交编号
```

手动保留正确内容，并删除冲突标记，然后执行：

```powershell
git add 冲突文件路径
git rebase --continue
```

如果还有冲突，继续重复：

```powershell
git status
git add 冲突文件路径
git rebase --continue
```

全部解决后推送：

```powershell
git push origin HEAD:main
```

如果不想继续本次变基，可以取消：

```powershell
git rebase --abort
```

它会回到执行 `git pull --rebase` 前的状态。

## 7. 常见误操作处理

### 7.1 文件已暂存，但还没有提交

取消某个文件的暂存：

```powershell
git restore --staged 文件路径
```

取消全部文件的暂存：

```powershell
git restore --staged .
```

这不会删除文件中的修改，只是将文件移出待提交区域。

### 7.2 放弃尚未提交的文件修改

```powershell
git restore 文件路径
```

放弃所有已跟踪文件的本地修改：

```powershell
git restore .
```

> 警告：这会丢弃本地修改，执行前必须确认不再需要这些内容。

### 7.3 刚提交但还没有推送

遗漏文件时：

```powershell
git add 遗漏的文件
git commit --amend --no-edit
```

修改最近一次提交说明：

```powershell
git commit --amend -m "正确的提交说明"
```

### 7.4 错误提交已经推送到 GitHub

先查看历史：

```powershell
git log --oneline -10
```

创建一个反向提交：

```powershell
git revert 提交哈希
git push origin HEAD:main
```

不要轻易使用：

```powershell
git push --force
```

强制推送可能覆盖 GitHub 上已有的提交历史。

## 8. 新项目第一次上传 GitHub

先在 GitHub 创建一个空仓库。为了减少首次合并问题，建议不要勾选自动创建 README、`.gitignore` 或许可证。

进入本地项目目录后执行：

```powershell
git init
git branch -M main
git config user.name "RitaYY1129"
git config user.email "RitaYY1129@users.noreply.github.com"
git add .
git commit -m "feat: initial commit"
git remote add origin GitHub仓库地址
git push -u origin main
```

示例：

```powershell
git remote add origin https://github.com/RitaYY1129/love-diary.git
git push -u origin main
```

如果 GitHub 仓库创建时已经包含 README 等提交，第一次推送前执行：

```powershell
git pull --rebase origin main
git push -u origin main
```

## 9. 后端项目上传建议

后端目录：

```text
D:\qingfeng\ZIYAN\Love\love-diary-backend
```

它目前不是 Git 仓库。建议为后端单独创建一个私有仓库，例如 `love-diary-backend`。

创建 GitHub 私有空仓库后，进入后端目录：

```powershell
cd D:\qingfeng\ZIYAN\Love\love-diary-backend
git init
git branch -M main
git add .
git status
git commit -m "feat: initial backend commit"
git remote add origin 后端GitHub仓库地址
git push -u origin main
```

后端上传前，必须确保这些内容被 `.gitignore` 排除：

```gitignore
.env
.env.*
node_modules/
.npm-cache/
*.log
```

不要上传以下敏感内容：

- 数据库账号和密码
- 短信服务密钥
- 微信登录密钥
- JWT 密钥
- 服务器密码
- 私钥和证书
- 生产环境 `.env`

可以保留不含真实密码的示例文件，例如：

```text
.env.example
.env.production.example
```

上传前一定执行：

```powershell
git status
```

如果 `.env`、`node_modules` 或日志出现在待提交列表中，应先完善 `.gitignore`，不要直接提交。

## 10. 查看仓库信息

查看当前状态：

```powershell
git status
```

查看当前分支：

```powershell
git branch --show-current
```

查看本地和远程分支：

```powershell
git branch -vv
git branch -a
```

查看远程仓库：

```powershell
git remote -v
```

查看最近提交：

```powershell
git log --oneline --decorate -10
```

查看尚未暂存的修改：

```powershell
git diff
```

查看已经暂存、即将提交的修改：

```powershell
git diff --cached
```

## 11. 推送完成后的检查

执行：

```powershell
git status
```

理想结果应该包含：

```text
nothing to commit, working tree clean
```

还可以检查本地当前提交：

```powershell
git log -1 --oneline
```

最后打开 GitHub 仓库页面，确认最新提交已经出现。

## 12. 最常用命令速查

以后前端有更新，按照下面执行：

```powershell
cd D:\qingfeng\ZIYAN\Love\love-diary
git status
git pull --rebase origin main
git add .
git status
git diff --cached
git commit -m "feat: 清楚描述本次修改"
git push origin HEAD:main
git status
```

遇到不确定情况时，先执行以下只读命令：

```powershell
git status
git branch -vv
git remote -v
git log --oneline --decorate -10
```

在没有确认原因前，不要随意执行强制推送、重置历史或删除 Git 目录。
