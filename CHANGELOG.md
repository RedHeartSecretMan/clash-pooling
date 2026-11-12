# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [Unreleased]

### Changed

- CI 改为三端测试：push / PR 时在 Ubuntu、macOS、Windows 上各跑一遍完整测试集，
  不再对 Release 文案做正则校验（格式约定见 `docs/releasing.md`）。

## [0.1.2] - 2026-11-12

### Added

- AI 服务补 `GEOSITE` 兜底：OpenAI、Anthropic、Google Gemini、Cursor、Perplexity、Copilot、
  HuggingFace 各加一条宽泛规则；`cloudcode-pa` 关键字规则移到精确域名之后，保持具体规则优先。
  本地规则 68 → 75 条（AI 组 29 → 36 条）。
- 补 `DOMAIN-SUFFIX,cursor.sh,AI`：Cursor Agent 实际请求 `api2.cursor.sh`、
  `agentn.global.api5.cursor.sh`，此前只匹配 `cursor.com`，请求落到 `MATCH,通用`（香港），
  表现为模型列表缺 Claude、Magpie 返回 502。
- 地区名改为**内置完整对照表**（ISO 3166-1 两位代码 → 中文，264 条），不再需要为新增地区
  手改代码；超过 7 个字的地区用通行简称（阿联酋、波黑、特立尼达…），其余取 CLDR 中文名。
- 新增发布校验 workflow：`release: published` 时检查标题是否符合 `v<版本> — <主题>`、
  正文是否含 `## 摘要`、是否残留旧写法 `## 本版内容`，不合格开 issue 提醒并让运行失败。

### Changed

- **计划任务改名**：`work.dsh.clashctl-refresh-{watch,daily}` → `clash-pooling.refresh-{watch,daily}`，
  三端一致；`auto enable` 会先卸载旧任务再装新的，不会两套并存。
- **状态目录改名**：`~/.dsh-clashctl` → `~/.clash-pooling`，内容自动迁移。
- 状态目录迁移改为显式调用：`state_dir()` 变纯读，启动时调一次 `platform.migrate_state_dir()`。
- 旧任务清理合并为 `_drop_legacy_jobs()`，按平台分派。
- 新增 `docs/releasing.md`：版本、tag、Release 标题与正文的写法约定。

### Fixed

- **Windows 定时核验从未真正跑起来过**：`C:\ProgramData\clash-verge-service\cores\` 只对管理员可读，
  计划任务以普通用户运行，`os.path.exists` 返回 False，每次巡检都报「找不到内核」。
  改为按**实际可读性**挑选内核：优先 `C:\Program Files\Clash Verge\verge-mihomo.exe`。
- Windows 的 `os.access(path, R_OK)` 不检查 ACL，新增 `_readable()` 以实际打开文件为准。
- 空的 `clash/local/rules.local.js`、缺 `LOCAL_RULES_EXTRA` 声明、空的本地 `Merge.yaml`
  不再把部署脚本写坏。

## [0.1.1] - 2026-11-12

### Added

- **Linux 支持**（#1、#2，贡献者 @AiKiAi-stack）：配置目录改用 XDG 数据目录、
  控制接口从生成配置读取、systemd 用户定时器、`clash-verge` 应用重启、GNOME 系统代理检查。
- 新增 `docs/linux.md`：路径、安装、systemd 命令、桌面会话要求与故障排查。
- 新增 `tests/linux.test.py`：17 项用例覆盖 XDG 路径、控制接口优先级与回退、应用重启、
  内核查找、GNOME 代理、systemd 注册/查询/停用与转义。全部用打补丁的临时环境，
  macOS、Windows、Linux 三端都会执行（Windows 上通过 `run.ps1` 一并运行）。
- 新增 `CLASH_CORE` 环境变量，用于指定 AppImage 等非常规布局下的内核路径。

### Changed

- 控制接口的取值顺序明确为：`CLASH_CONTROLLER` → `CLASH_SOCK` → 生成配置里的
  unix socket（文件存在才用）→ 生成配置里的 TCP 地址。socket 文件不存在时退回 TCP，
  不再拿过期路径去连。
- `auto status` 在 Linux 上与其他平台同一套输出；`systemctl` 不可用时显示「未知」而不是报错。
- `auto enable` / `auto disable` 失败时返回非零退出码，不再静默成功。

### Fixed

- systemd 单元补 `KillMode=process`：oneshot 结束时默认会清空整个 cgroup，
  把刚被重启拉起的 Clash Verge 一起 SIGTERM，重启等于没做。
- systemd 每日定时器补 `Persistent=true`：关机或休眠错过 01:00 会在开机后补跑；
  Windows 的 `StartWhenAvailable` 行为一致，launchd 只在唤醒后补跑、关机期间错过的不执行。
- 巡检首次触发从「启用后 1 小时」改为 1 分钟，与 macOS（RunAtLoad）、Windows（+1 分钟）对齐。
- `systemctl --user` 失败时不再抛 `CalledProcessError`；`disable` 失败时保留单元文件并说明原因。
- `-c` / `-m` 方式调用时启动器路径被误当成 `-c`，生成的 systemd 单元不可用；
  现在回退到安装位置，取不到时提示而不是抛栈。
- Linux 内核查找覆盖服务模式与官方包布局，不再只看一个路径。

## [0.1.0] - 2026-11-11

首个版本。

### Added

- **三层模型**：规则 → 服务组（AI / 通用 / 其他）→ 地区池 → 节点。
- **地区池自动发现**：不依赖预设名单，任意地区只要验证节点达到 3 个就自动建池；
  显示名由别名表提供，未列出的地区直接用代码（如 `DE`）；最多 8 个池，优选名单决定前几位。
- **实测清单** `VERIFIED`：记录每个节点的出口地区与延迟，由 `clashctl` 写入、`Script.js` 读取。
- **Clash 侧配置纳管**：`clash/Script.js`（分组与规则）与 `clash/Merge.yaml` 进入仓库，
  `clashctl sync` 推送到 Clash 并保留已有清单。
- **本地覆盖机制**：`clash/local/`（被 `.gitignore` 排除）承载内网规则与专用 DNS，
  `sync` 时注入；仓库里保持为空或通用示例，开源版开箱即用。
- **机场组名映射**：已知组名查表，其余按语义推断——拦截类 → `REJECT`、直连类 → `DIRECT`、
  含地区线索 → 对应地区池、其余 → `通用`。
- **定时核验**：每天 01:00 无条件全量；每小时巡检，订阅变了走全量、没变只补测死节点。
- **跨平台**：macOS（launchd）与 Windows（任务计划程序）共用同一份 Python 实现，
  平台差异集中在 `lib/clashctl/platform.py`。
- **命令行**：`status` `regions` `nodes` `test` `use` `sync` `exit-check` `audit` `doctor`
  `backup` `auto`，支持 `--version`。
- **测试**：分组生成 16 项、清单处理 14 项、敏感内容 1 项；macOS 全跑，
  Windows 未装 Node.js 时跳过分组生成（其余照跑）。
- **敏感内容守卫** `tests/check_sensitive.py`：扫描私网地址、订阅令牌、真实密钥与本地配置的
  私有域名，命中即失败；已接入两个测试入口。

### Fixed

开发期间发现并修复，均体现在首个版本中：

- `auto-run --full` 的参数未被解析，导致每日全量从未执行。
- Windows 上 `app_exe()` 找不到 `clash-verge.exe`（实际文件名无空格且小写），核验后无法重启应用。
- Windows 计划任务的默认设置会在电池供电时跳过或中断核验，且休眠期间错过不补跑。
- Windows 控制台 GBK 编码导致中文与符号乱码。
- 批处理与 PowerShell 脚本的行尾被 Git 归一为 LF，导致 Windows 无法解析 `.cmd`。
- PowerShell 脚本未带 BOM，PS 5.1 按 ANSI 解析导致引号被吞、报语法错误。
- `install.ps1` 测试失败后仍继续安装。
- PowerShell 写出的 UTF-8 BOM 使 `clashctl sync` 找不到项目路径。
- 敏感内容守卫用反斜杠路径做前缀匹配，Windows 上未跳过 `clash/local/`。
- 临时实例启动失败时残留进程与端口占用。
- 清单内容未变化时仍重启 Clash Verge。
- 规则顺序：`google.com` 的兜底规则排在前面，导致 `dl.google.com` 直连与
  `*.l.google.com` 遥测拦截被吃掉；现改为更具体的规则先行。
- `audit` 按规则类型前缀计数，`GEOSITE`、`DOMAIN` 类规则未被统计，本地与机场规则的
  分界线错位，遮蔽报告失真。
- 并发保护用进程名匹配，而定时任务的命令行里没有该名字，实际从未生效；改为锁文件
  （`~/.clash-pooling/refresh.lock`，陈旧锁 3 小时后自动清理）。
- 测量时未确认节点切换生效就开始探测，可能读到上一个节点的出口；现在确认后才测量。
- 整轮超时被截断时，`exit-check` 会因缺少结果抛 KeyError。
- Windows 上 `auto status` 只检查巡检任务，全量任务即使在也会显示「未启用」。
- 全新机器首次安装：分组测试默认读部署文件，装前不存在，导致 `install.sh` 中断；
  现在回落到仓库里的 `Script.js`。
- 内置规则与测试夹具里混入机场专有命名（排序键、节点名、实测文档里的订阅名）。
- 服务组与地区池都按 `Fallback` 类型判定，同一个组会同时出现在两处，与
  「select 是服务组、url-test 是地区池」的模型不符；改为按类型互斥。
- 控制接口不可用时 `doctor` 打印完友好提示仍会 traceback；现在跳过依赖接口的检查。
- `tests/run.sh` 无条件调用 `node`，没装 Node.js 的机器上会中断安装；改为跳过。
- 敏感内容守卫漏扫无扩展名的 `bin/clashctl`，且整行白名单会掩盖同行其它真实令牌。
- 中文按字符补空格导致表格列错位；改为按显示宽度对齐。
- 测试夹具用 `Math.random()` 生成延迟，规格测试不确定；改为确定性数值。
- `install.sh` 不提示 PATH，装完直接敲 `clashctl` 可能 command not found。
- 未验证节点混入地区池与「其他」组。
- 节点探针在切换后立即请求，可能读到上一个节点的出口。
