# 发布流程

每次发版要做什么、发出去之后会被检查什么。适用对象是本仓库的维护者。

## 版本号

- 0.x 阶段只递增 patch 号：`0.1.2` → `0.1.3`。功能、修复、文档改动都走 patch，不跳 minor。
- 下面三处必须一致，发版前逐一核对：
  - `lib/clashctl/__init__.py` 的 `__version__`
  - `CHANGELOG.md` 顶部条目 `## [x.y.z] - YYYY-MM-DD`
  - git tag：`v` + 版本号，例如 `v0.1.2`
`--verify-tag` 保证 tag 已存在时才建 Release；`--target` 把 Release 绑定到该 tag 的提交。
少了这两个参数，Release 的 target 会被记成仓库默认分支（GitHub 页面显示 `main`），
源码包虽然仍按 tag 生成，但元数据看起来像"跟着分支走"。

- tag 一旦发布不再移动。发布内容有误时，改代码或文档后用下一个 patch 修正；
  只有 Release 的标题和正文可以直接编辑。
- 0.x 阶段的例外：发布当天发现内容问题（错字、漏记、规范本身要改），可以覆盖重发一次——
  改完直接 `git tag -f` 并强推 tag，Release 正文用 `gh release edit` 更新。重发后不再移动；
  1.0 之后取消这个例外。

## 发布步骤

```bash
# 1. 改版本号与变更记录
$EDITOR lib/clashctl/__init__.py CHANGELOG.md

# 2. 跑测试
./tests/run.sh

# 3. 提交（一个版本一个提交）
git commit -am "feat: ..."

# 4. 打 tag 并推送
git tag -a v0.1.2 -m "clash-pooling 0.1.2"
git push origin main v0.1.2

# 5. 建 Release（用文件传正文，避免 shell 转义问题）
gh release create v0.1.2 \
  --verify-tag \
  --target "$(git rev-parse v0.1.2^{commit})" \
  --title "v0.1.2 — 一句话主题" \
  --notes-file /tmp/notes.md
```

## Release 标题

格式固定为 `v<版本> — <主题>`：

```text
v0.1.2 — AI 规则兜底与命名空间清理
v0.1.1 — Linux 支持
```

- 破折号是全角 `—`，不是 `-`
- 不在标题里重复仓库名，也不只写版本号
- 主题用一句话概括，尽量控制在 10 个字内

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
- 不出现 `## 本版内容`、`### Added / Changed / Fixed` 这类旧写法。
- 有破坏性变更（改名、路径变化、需要手工迁移）时，必须在摘要里点明。

## 发布后校验

`.github/workflows/release-check.yml` 在 `release: published` 时运行，检查三项：

| 检查 | 规则 |
|---|---|
| 标题 | 匹配 `v<版本> — <主题>` |
| 摘要 | 正文含 `## 摘要` |
| 旧写法 | 正文不含 `## 本版内容` |
| 版本一致 | `lib/clashctl/__init__.py` 的 `__version__` 与 tag 相同 |
| 变更记录 | `CHANGELOG.md` 有对应的 `## [<版本>]` 条目 |

也可以在 Actions 页面手动触发这个 workflow（`workflow_dispatch`），复查当前最新 Release。

不合格时开一个 `[发布检查] <tag>` 的 issue（同一 tag 只开一个，重复触发改为追加评论），
并让该次运行失败。GitHub Release 不支持评论，所以提醒落在 issue 上。

修法：在 Release 页面点 Edit 改标题或正文，改完关掉 issue 即可。

## 常见误区

| 情况 | 正确做法 |
|---|---|
| 发完发现正文写错 | 直接编辑 Release；tag 不动 |
| 发完发现代码有 bug | 发下一个 patch，不回滚 tag |
| 标题用了半角 `-` | 改成全角 `—`，否则 CI 判不合格 |
| 忘了改 `__version__` | 发布的 tag 与代码版本会不一致，发版前先核对三处 |
