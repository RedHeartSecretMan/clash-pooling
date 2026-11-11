# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

项目从 `0.1.0` 起步；此前的内部演进不单独记版本。

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
  （`~/.dsh-clashctl/refresh.lock`，陈旧锁 3 小时后自动清理）。
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
