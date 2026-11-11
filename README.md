# clash-pooling

按**实测出口地区**自动划分 Clash 节点池的工具集。订阅只提供节点，分组、规则、地区分类全部由本项目维护，订阅更新不会覆盖。

## 解决什么问题

机场的节点名不可信——叫「美国 01」的可能走香港，叫「加拿大 01」的可能走美国。按名字分组会把非合规地区的节点塞进 AI 池，导致 ChatGPT / Gemini 报地区不支持。

本项目把「节点属于哪个地区」变成一次可复核的实测：

```
测量（外部工具）  →  清单（Script.js 里的数据）  →  分组（Clash 内生成）  →  择优（url-test）
```

Clash 内的脚本没有网络能力，所以测量必须放在外部——这是全部设计的起点。

## 目录结构

```
bin/clashctl              启动器（Python 脚本）：定位 lib/ 后进入 CLI
bin/clashctl.cmd          Windows 启动器：定位 Python 后进入同一个 CLI
lib/clashctl/
  __main__.py             参数分派
  commands.py             各子命令：查看、核验、同步、诊断
  measure.py              测量流水线：临时实例、切换、探测
  probe.py                HTTP 探测（标准库，不依赖 curl）
  api.py                  mihomo 控制接口（unix socket / TCP）
  platform.py             平台差异：路径、端点、内核、重启、调度
  scheduler.py            定时核验：launchd / 任务计划程序
  manifest.py             清单解析与增量决策（纯函数，可单测）
clash/Script.js           Clash 侧的分组脚本与规则（源文件，可直接改）
clash/Merge.yaml          Clash 侧的覆写配置（源文件）
clash/local/              本机私有配置，不进仓库（见下）
tests/                    规格测试：分组、清单、敏感内容
docs/                     设计与运维文档
install.sh / install.ps1  测试通过后安装工具并同步配置
```

Clash 侧的 `Script.js` / `Merge.yaml` 在本仓库维护，用 `clashctl sync` 推送到 Clash 配置目录；
同步时保留目标文件里已有的实测清单，仓库只存代码。

公司内网规则、内网 DNS 一类只在本机生效的配置放 `clash/local/`（已被 `.gitignore` 排除）：

| 文件 | 作用 |
|---|---|
| `clash/local/rules.local.js` | 注入到 `Script.js` 的 `LOCAL-RULES-EXTRA` 区块 |
| `clash/local/Merge.yaml` | 替代仓库里的通用 Merge |
| `clash/local/sensitive.txt` | 敏感内容守卫读的私有域名/关键字 |

没有这些文件时注入为空，工具照常工作。

## 平台支持

macOS 与 Windows 共用同一份 Python 实现，平台差异集中在 `lib/clashctl/platform.py`：

| 差异点 | macOS | Windows |
|---|---|---|
| 控制接口 | unix socket | TCP `external-controller` |
| 配置目录 | `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev` | `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev` |
| 内核 | `.app` 内 | `C:\ProgramData\clash-verge-service\cores\verge-mihomo.exe` |
| 定时任务 | launchd | 任务计划程序 |
| 重启应用 | `osascript` | `taskkill` + `start` |

需要 Python 3.10+。Node.js 只用于跑分组测试，没有也能装（该测试会跳过）。

## 快速开始

macOS：

```bash
./install.sh                 # 跑测试 → 安装工具 → 同步 Clash 配置 → 自检
clashctl sync                # 把 clash/ 下的配置推送到 Clash（改过配置时用）
clashctl status              # 看当前链路
clashctl regions             # 看地区池与当前节点
clashctl auto enable         # 安装定时核验（每天 01:00 全量 + 每小时巡检）
```

安装不会改 PATH；`clashctl` 报 command not found 时，用 `~/.local/bin/clashctl`
或把 `~/.local/bin` 加进 PATH。

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
clashctl sync
clashctl auto enable
```

## 分组模型

```
规则  →  服务组（AI / 通用 / 其他）  →  地区池（按实测出口）  →  节点
```

| 层 | 职责 |
|---|---|
| 规则 | 决定域名归哪个服务组。本仓库内置本地规则 68 条，机场自带规则由订阅决定 |
| 服务组 | 你在界面切换的地方；AI 组自动排除香港 |
| 地区池 | 由实测清单自动发现：某个地区验证节点达到 3 个就建池，池内 `url-test` 自动择优 |
| 其他 | 池外且实测通过的节点，手动指定冷门节点时用 |

规则与池的**具体数量取决于订阅**，不是固定值；用 `clashctl status` 与 `clashctl regions` 看当前实际情况。
本机私有规则（`clash/local/rules.local.js`）会在同步时注入到规则最前面（优先于内置规则），不计入上面的 68 条。

## 测试

```bash
./tests/run.sh
```

三个缝：`tests/groups.test.cjs` 验证分组与规则生成，`tests/manifest.test.py` 验证清单解析与增量决策，
`tests/check_sensitive.py` 守着仓库里不出现私网地址、订阅令牌与真实密钥。

分组测试默认读**本机已部署的** `Script.js`（即真正在跑的那份；不存在时回落到仓库里的源文件），可用 `CLASH_SCRIPT=<路径>` 指向其他副本；
清单测试同理支持 `CLASHCTL_LIB`。

## 定时核验

| 定时器 | 时间 | 行为 |
|---|---|---|
| `refresh-daily` | 每天 01:00 | 无条件全量核验 |
| `refresh-watch` | 每小时（跳过 01:00） | 订阅变了 → 全量；没变 → 只补测死节点 |

## 文档

| 文档 | 内容 |
|---|---|
| [docs/design.md](docs/design.md) | 分层模型、分组与规则、调度、决策记录 |
| [docs/clashctl.md](docs/clashctl.md) | 工具逻辑：命令分层、核验流水线、marker 语义、调度 |
| [docs/clash-config.md](docs/clash-config.md) | Clash 侧配置：Script.js 结构、Merge.yaml、同步流程 |
| [docs/operations.md](docs/operations.md) | 安装、命令速查、故障排查、回滚 |
| [docs/measurements.md](docs/measurements.md) | 测量方法与实测数据 |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更记录 |

## 许可

[MIT](LICENSE)
