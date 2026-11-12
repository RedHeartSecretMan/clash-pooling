# 发布流程

每次发版要做什么、按什么格式写。适用于本仓库的维护者。

## 版本号

- 0.x 阶段只递增 patch 号：`0.1.2` → `0.1.3`。功能、修复、文档改动都走 patch，不跳 minor。
- 下面三处必须一致，发版前逐一核对：
  - `lib/clashctl/__init__.py` 的 `__version__`
  - `CHANGELOG.md` 顶部条目 `## [x.y.z] - YYYY-MM-DD`
  - git tag：`v` + 版本号，例如 `v0.1.2`
- tag 一旦发布不再移动。发布内容有误时，改代码或文档后用下一个 patch 修正；
  Release 的标题和正文可以直接编辑。
- 0.x 阶段的例外：发布当天发现内容问题（错字、漏记、规范本身要改），允许覆盖重发一次——
  改完 `git tag -f` 并强推 tag，正文用 `gh release edit` 更新。重发后不再移动，1.0 之后取消该例外。

## 发布步骤

```bash
# 1. 改版本号与变更记录
$EDITOR lib/clashctl/__init__.py CHANGELOG.md

# 2. 跑测试（CI 也会跑，但本地先确认一次更快）
./tests/run.sh

# 3. 提交（一个版本一个提交）
git add -A
git commit -m "feat: ..."

# 4. 打 tag 并推送
git tag -a v0.1.2 -m "clash-pooling 0.1.2"
git push origin main v0.1.2

# 5. 建 Release（正文用文件传入，避免 shell 转义问题）
gh release create v0.1.2 \
  --verify-tag \
  --target "$(git rev-parse v0.1.2^{commit})" \
  --title "v0.1.2 — 一句话主题" \
  --notes-file /tmp/notes.md
```

第 5 步的两个参数不能省：

- `--verify-tag`：tag 不存在时直接失败，避免建出指向分支的 Release。
- `--target`：把 Release 绑到该 tag 的提交。少了它，GitHub 页面的 target 会显示成 `main`，
  源码包仍按 tag 生成，但元数据看起来像"跟着分支走"。

## Release 标题

格式固定为 `v<版本> — <主题>`：

```text
v0.1.2 — AI 规则兜底与命名空间清理
v0.1.1 — Linux 支持
```

- 破折号是全角 `—`，不是 `-`。
- 不在标题里重复仓库名，也不只写版本号。
- 主题一句话，尽量控制在 10 个字内。

## Release 正文

首节固定是 `## 摘要`，其余小节按需保留、没有内容就删掉：

```markdown
## 摘要

一两句话说明这个版本解决了什么问题、影响谁。

## 变更

### 新增
- …

### 改进
- …

### 修复
- …

## 边界

不在本版范围的内容、已知限制。

## 安装与升级

升级命令；首版写安装步骤。

## 验证

测试数量、实机验证结论。

## 链接

许可、相关文档。
```

写法要求：

- **面向使用者**，不是 `CHANGELOG.md` 的复制。CHANGELOG 记全部改动，Release 只讲影响。
- 不写 `## 本版内容`、`### Added / Changed / Fixed` 这类旧写法。
- 有破坏性变更（改名、路径变化、需要手工迁移）时，必须在摘要里点明。
- 不写"由哪几次提交合并而来"之类的维护者视角内容。

## CI

`.github/workflows/tests.yml` 在 push 到 `main`、开 PR、或手动触发时，
在 Ubuntu、macOS、Windows 三端各跑一遍 `tests/run.sh` / `tests/run.ps1`。

## 常见误区

| 情况 | 正确做法 |
|---|---|
| 发完发现正文写错 | 直接编辑 Release；tag 不动 |
| 发完发现代码有 bug | 发下一个 patch，不回滚 tag |
| 标题用了半角 `-` | 改成全角 `—` |
| 忘了改 `__version__` | 发布前核对三处；不一致会导致 `clashctl --version` 与 Release 对不上 |
| 正文从 CHANGELOG 整段粘过来 | 只保留对使用者有影响的部分，删掉内部改动 |
