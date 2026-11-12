# 运维手册

## 1. 安装与升级

```bash
./install.sh                      # macOS / Linux
```

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1   # Windows
```

流程：跑测试（全绿才继续）→ 安装工具 → 同步 Clash 配置 → 自检 → 环境诊断。
macOS 端 5 步，Windows 端多一步「把安装目录加入用户 PATH」。

macOS 不自动改 PATH；如果 `clashctl` 提示 command not found，把下面这行加进 shell 配置，
或直接用绝对路径 `~/.local/bin/clashctl`：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

| 步骤 | 落点 |
|---|---|
| 工具（macOS / Linux） | `~/.local/bin/clashctl`、`~/.local/lib/clashctl/` |
| 工具（Windows） | `%LOCALAPPDATA%\clash-pooling\bin\clashctl.cmd`、`...\lib\clashctl\` |
| 配置 | Clash 配置目录下的 `Script.js`、`Merge.yaml`（保留目标已有的实测清单） |

改代码或配置后都跑一次 `./install.sh` 即可；只想更新配置时用 `clashctl sync`，不必重装工具。

## 2. 命令速查

| 命令 | 作用 |
|---|---|
| `clashctl status` | 看服务组链路与各地区池当前节点 |
| `clashctl regions` | 列出所有组及其成员数 |
| `clashctl nodes <组名>` | 列出某组的节点与候选 |
| `clashctl test [服务名…]` | 实测延迟 |
| `clashctl use <服务> <目标>` | 切换服务组到指定组或节点 |
| `clashctl sync` | 把项目 `clash/` 下的配置同步到 Clash（保留清单） |
| `clashctl exit-check` | 核验池内节点的出口是否符合预期（约 1 分钟） |
| `clashctl exit-check --refresh` | 增量补测缺失节点 |
| `clashctl exit-check --refresh --full` | 全量重测（约 10~15 分钟） |
| `clashctl exit-check --refresh --recheck <子串>` | 只重测名字匹配的节点（抽查） |
| `clashctl audit` | 检查本地规则是否遮蔽了机场规则 |
| `clashctl doctor` | 体检：内核、分组、规则、DNS、系统代理 |
| `clashctl auto enable\|disable\|status` | 定时核验的安装、停用、状态 |
| `clashctl backup` | 备份 Clash 配置到 `backup-<时间戳>/` |

## 3. 定时任务

```bash
clashctl auto status     # 查看两个任务与最近一次核验
tail -f ~/.clash-pooling/auto.log
```

| 任务 | 时间 | 行为 |
|---|---|---|
| `refresh-daily` | 每天 01:00 | 无条件全量核验 |
| `refresh-watch` | 每小时（跳过 01:00） | 订阅变了 → 全量；没变 → 只补测死节点 |

两个任务都在核验结束后重启 Clash Verge（断连数秒）；若清单没有变化则跳过重启。

状态文件 `~/.clash-pooling/last-refresh` 记录：最近核验时间、订阅版本戳、已验节点数、订阅节点数、上次是否全量。

## 4. 日常操作

**切换某个服务组的地区**

```bash
clashctl use "AI" "美国"
```

**钉死某个具体节点**（池外节点只能通过「其他」访问）

```bash
clashctl use "AI" "其他"
clashctl use "其他" "韩国 01"
```

**订阅更新后想立刻刷新**（不必等 01:00 或下一次巡检）

```bash
clashctl exit-check --refresh     # 会检测到订阅变化，自动升级为全量
```

## 5. 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| Antigravity 报 `User location is not supported` | AI 组被切到了香港 | `clashctl use "AI" "新加坡"` |
| 某个地区池为空 / 变成 `DIRECT` | 该地区没有实测通过的节点 | `clashctl exit-check --refresh` 补测；查看 `clashctl regions` |
| 订阅更新后池子明显变小 | 新节点还没实测，清单里没有记录 | 属预期，下一次巡检（≤1 小时）自动补上 |
| 节点恢复了但没进池 | 巡检还没轮到 | 最长 1 小时；急用跑 `--refresh` |
| 规则改了但没生效 | Clash 只在启动/应用时生成配置 | 退出并重新打开 Clash Verge |
| `exit-check` 报端口占用 | 有另一个核验在跑 | 等它结束，或 `pkill -f exitcheck-` |
| `auto status` 显示两个任务未启用 | plist 被删或未加载 | `clashctl auto disable && clashctl auto enable` |
| PowerShell 脚本报「字符串缺少终止符」或中文乱码 | `.ps1` 未以 UTF-8 BOM 保存，PowerShell 5.1 按 ANSI 解析 | 保存为 UTF-8 with BOM（仓库内已带 BOM） |
| Windows 上 `python` 报 `uv trampoline failed to spawn Python child process` | uv 的 shim 指向已不存在的 Python，或 scoop 的 `current` junction 失效 | `scoop reset uv` 修复 junction；`uv python install --force <版本>` 重建 shim；或直接装官方 Python 并把它的目录排在 PATH 前面 |
| 内网域名解析失败 | `enable_dns_settings` 被打开，覆盖了 Merge.yaml | 在界面关闭「DNS 设置覆盖」 |

## 6. 回滚

| 场景 | 做法 |
|---|---|
| 分组/规则改坏了 | `cp <备份目录>/Script.js ~/Library/Application\ Support/io.github.clash-verge-rev.clash-verge-rev/profiles/`，重启 Verge |
| 配置整体回滚 | 从 `backup-<时间戳>/` 拷回 `profiles/` 与 `clash-verge.yaml` |
| 工具本身回滚 | 重新检出上一版 `bin/` `lib/`，跑 `./install.sh` |

`clashctl backup` 每次改动前先跑一次，备份保留在 Clash 配置目录下。

## 7. 文件位置

| 用途 | 路径 |
|---|---|
| 工具本体 | `~/.local/bin/clashctl` |
| 清单模块 | `~/.local/lib/clashctl/manifest.py` |
| 分组与规则 | `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/profiles/Script.js` |
| DNS 覆写 | 同上目录的 `Merge.yaml` |
| 运行配置 | 同上目录的 `clash-verge.yaml` |
| 定时任务（macOS） | `~/Library/LaunchAgents/clash-pooling.refresh-{daily,watch}.plist` |
| 定时任务（Windows） | 任务计划程序里的 `clash-pooling.refresh-{watch,daily}` |
| 定时任务（Linux） | `~/.config/systemd/user/clash-pooling.refresh-{watch,daily}.{service,timer}`；支持 `XDG_CONFIG_HOME` |
| 状态与日志 | `~/.clash-pooling/`（Windows 为 `%USERPROFILE%\.clash-pooling`） |

从 0.1.1 及更早升级：任务名与状态目录都改了。重新执行一次 `clashctl auto enable` 即可——
它会卸载旧任务再装新的；状态目录在首次运行时自动从 `~/.dsh-clashctl` 迁移过来，无需手动搬。

Linux 的 Clash 配置默认位于 `~/.local/share/io.github.clash-verge-rev.clash-verge-rev/`，
支持 `XDG_DATA_HOME`。安装与排查命令见 [Linux 安装说明](linux.md)。
