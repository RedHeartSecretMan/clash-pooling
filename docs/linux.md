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
| service 控制接口 | `/run/clash-verge-service/users/<uid>/verge-mihomo.sock` |
| 日志与核验状态 | `~/.dsh-clashctl/` |

控制接口优先使用当前用户的 service socket，再使用生成配置里的 `external-controller-unix`。
可用 `CLASH_SOCK` 指定其他 socket。内核优先使用可执行的
`/var/lib/clash-verge-service/cores/verge-mihomo`，否则查找 PATH 中的 `verge-mihomo`。

GNOME 系统代理状态通过 `gsettings` 读取。其他桌面环境的系统代理检查会显示跳过。

## 定时任务

每小时巡检从启用后一小时开始；每日全量在本机时区 01:00 执行。
`auto disable` 会停用两个 timer 并移除 unit 文件；已经开始的核验会完成本轮。

```bash
systemctl --user list-timers 'work.dsh.clashctl-refresh-*'
journalctl --user -u work.dsh.clashctl-refresh-watch.service
clashctl auto disable
```

用户管理器需要处于运行状态。电脑关机或休眠时不会执行核验。
清单变化后，定时任务会退出并重新打开当前用户的 Clash Verge，连接可能短暂中断。
应用重启需要用户管理器中有效的桌面会话环境，可通过以下命令检查：

```bash
systemctl --user show-environment
```

若 `systemctl --user` 报无法连接总线，请在已登录的桌面用户终端运行。
Flatpak、容器、无桌面的服务器，以及使用其他配置布局的安装方式需要单独适配。

## 测试

```bash
CLASH_SCRIPT="$PWD/clash/Script.js" bash tests/run.sh
```

Linux 回归测试使用临时目录和模拟进程，覆盖路径、应用重启、systemd 注册、查询和停用；
macOS / Windows 配置路径也通过模拟平台检查。
