# Linux 安装与维护

适用于桌面会话中的 Clash Verge Rev。已在 Ubuntu 26.04.1 LTS 上验证；定时核验使用 systemd 用户定时器。
需要 Python 3.10+、`clash-verge` 和可执行的 mihomo 内核。Node.js 用于分组测试。

## 安装

先打开 Clash Verge，选择并加载订阅，然后运行：

```bash
./install.sh
~/.local/bin/clashctl exit-check --refresh --full
```

核验完成后，退出并重新打开 Clash Verge，运行 `~/.local/bin/clashctl status` 确认地区池已生成。
首次安装会写入分组脚本，重开应用前应先完成出口核验。随后可启用定时任务：

```bash
~/.local/bin/clashctl auto enable
~/.local/bin/clashctl auto status
```

工具安装到 `~/.local/bin/` 和 `~/.local/lib/clashctl/`。将 `~/.local/bin` 加入 PATH 后可直接运行 `clashctl`。

## 文件与控制接口

| 用途 | 默认位置 |
|---|---|
| Clash 数据 | `~/.local/share/io.github.clash-verge-rev.clash-verge-rev/`；支持 `XDG_DATA_HOME` |
| systemd unit | `~/.config/systemd/user/`；支持 `XDG_CONFIG_HOME` |
| 日志与核验状态 | `~/.dsh-clashctl/` |

控制接口从 Clash Verge 生成的配置里读：有 `external-controller-unix` 就走 unix socket，
没有就退回 `external-controller` 的 TCP 地址。需要临时指定时用 `CLASH_SOCK`（socket）
或 `CLASH_CONTROLLER`（`host:port`）。

内核查找顺序：`CLASH_CORE`（显式指定，优先级最高）→ `/var/lib/clash-verge-service/cores/verge-mihomo`
（服务模式）→ `/usr/lib/Clash Verge/resources/verge-mihomo`（官方包）→ `/usr/lib/clash-verge/verge-mihomo`
→ PATH 里的 `verge-mihomo`。用 AppImage 或自定义布局时，直接设 `CLASH_CORE=/path/to/verge-mihomo` 即可。

GNOME 系统代理状态通过 `gsettings` 读取。其他桌面环境的系统代理检查会显示跳过。

## 定时任务

启用后 1 分钟先跑一次巡检，之后每小时一次；每日全量在本机时区 01:00 执行，带 `Persistent=true`——
关机或休眠错过时间点，会在下次开机后补跑一次。Windows 的 `StartWhenAvailable` 行为一致；
macOS launchd 只在唤醒后补跑，关机期间错过的不执行。
`auto disable` 会停用两个 timer 并移除 unit 文件；已经开始的核验会完成本轮。

```bash
systemctl --user list-timers 'work.dsh.clashctl-refresh-*'
journalctl --user -u work.dsh.clashctl-refresh-watch.service
~/.local/bin/clashctl auto disable
```

用户管理器需要处于运行状态。电脑关机或休眠时不会执行核验。
清单变化后，定时任务会退出并重新打开当前用户的 Clash Verge，连接可能短暂中断。
应用重启需要用户管理器中有效的桌面会话环境，可通过以下命令检查：

```bash
systemctl --user show-environment
```

若 `systemctl --user` 报无法连接总线，请在已登录的桌面用户终端运行。
Flatpak、容器、无桌面的服务器，以及使用其他配置布局的安装方式需要单独适配。

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `auto enable` 提示「需要在已登录的桌面用户里执行」 | 用户管理器连不上（SSH 会话、没有 lingering） | 在桌面终端执行，或 `loginctl enable-linger $USER` 后重新登录 |
| `auto status` 显示「未知（systemctl 不可用）」 | 机器上没有 systemd 用户管理器 | 退回手动执行 `~/.local/bin/clashctl auto run`，或用系统级 timer |
| 定时核验跑完，但 Clash Verge 没被重开 | 用户管理器里没有图形会话环境变量 | `systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY` 后重试 |
| `doctor` 报找不到内核 | AppImage 或非标准布局 | `export CLASH_CORE=/path/to/verge-mihomo`，或把 `verge-mihomo` 加进 PATH |
| 控制接口连不上 | socket 已失效，或 Clash 只开了 TCP | 用 `CLASH_SOCK` / `CLASH_CONTROLLER` 指定；`doctor` 会打印当前端点 |
| 想看核验日志 | 定时任务的输出不写入文件 | `journalctl --user -u work.dsh.clashctl-refresh-watch.service`；手动执行时日志在 `~/.dsh-clashctl/auto.log` |

## 测试

```bash
./tests/run.sh
```

`tests/linux.test.py` 的 14 项用例全部用打补丁的临时环境，覆盖 XDG 路径、控制接口回退、
应用重启、内核查找、GNOME 代理、systemd 注册/查询/停用与转义，因此在 macOS 上也会执行，
非 Linux 机器也能拦住 Linux 分支的回归。
