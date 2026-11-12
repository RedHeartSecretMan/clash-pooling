"""定时核验：launchd、Windows 任务计划程序或 systemd 用户定时器。"""

import json
import os
import subprocess
import sys
import time

from . import commands, platform

TASK_WATCH = "work.dsh.clashctl-refresh-watch"
TASK_DAILY = "work.dsh.clashctl-refresh-daily"
PLIST_DIR = os.path.expanduser("~/Library/LaunchAgents")


def _systemctl(*args):
    """调用 systemctl --user；失败时打印可执行的下一步，返回是否成功"""
    try:
        result = subprocess.run(["systemctl", "--user"] + list(args),
                                capture_output=True, text=True)
    except OSError as exc:
        print("  无法运行 systemctl：%s" % exc)
        return False
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        print("  systemctl %s 失败：%s" % (" ".join(args), detail[0] if detail else "未知错误"))
        print("  提示：需要在已登录的桌面用户里执行；远程会话可先运行 systemctl --user status 自检")
        return False
    return True


def _systemd_dir():
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(root, "systemd", "user")


def _systemd_service(full=False):
    args = [sys.executable, _launcher(), "auto", "run"]
    if full:
        args.append("--full")
    command = " ".join('"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"' for a in args)
    # 使用用户管理器的当前桌面环境，避免把本次登录的 XAUTHORITY 固定在 unit 中。
    # KillMode=process：只杀本进程，不连带杀掉它拉起的 Clash Verge
    # （oneshot 结束时默认会清掉整个 cgroup，刚重启的 GUI 会被一起 SIGTERM）
    return ("[Unit]\nDescription=Clash pooling exit verification\n"
            "Wants=network-online.target\nAfter=network-online.target\n"
            "[Service]\nType=oneshot\nExecStart=" + command +
            "\nTimeoutStartSec=3600\nUMask=0077\nKillMode=process\n")


def _linux_enable():
    root = _systemd_dir()
    os.makedirs(root, exist_ok=True)
    for name, full, trigger in ((TASK_WATCH, False, "OnActiveSec=1min\nOnUnitActiveSec=1h"),
                                (TASK_DAILY, True, "OnCalendar=*-*-* 01:00:00")):
        with open(os.path.join(root, name + ".service"), "w", encoding="utf-8") as f:
            f.write(_systemd_service(full=full))
        with open(os.path.join(root, name + ".timer"), "w", encoding="utf-8") as f:
            body = "[Unit]\nDescription=Clash pooling scheduled verification\n[Timer]\n" + trigger
            if full:
                body += "\nPersistent=true"      # 关机/休眠错过 01:00 时，开机后补跑
            body += "\n[Install]\nWantedBy=timers.target\n"
            f.write(body)
    if not _systemctl("daemon-reload"):
        print("  单元文件已写入 %s，修好后执行 systemctl --user daemon-reload 并重试" % root)
        return False
    if not _systemctl("enable", "--now", TASK_WATCH + ".timer", TASK_DAILY + ".timer"):
        print("  单元文件已写入 %s，修好后执行 systemctl --user enable --now 重试" % root)
        return False
    print("已启用 systemd 用户定时器：每天 01:00 全量 + 每小时巡检")
    print("  日志：journalctl --user -u %s.service" % TASK_WATCH)
    return True


def _launcher():
    """入口脚本的绝对路径；被 python -c / -m 调用时回退到安装位置"""
    path = os.path.abspath(sys.argv[0])
    usable = os.path.isfile(path) and os.path.basename(path) not in ("-c", "__main__.py")
    if usable:
        return path
    fallback = os.path.expanduser("~/.local/bin/clashctl")
    if os.path.isfile(fallback):
        return fallback
    raise RuntimeError("找不到 clashctl 启动器路径，请直接运行 clashctl auto enable")


# ------------------------------------------------------------------ 安装/卸载

def enable():
    """安装定时核验；失败返回 False（调用方据此给非零退出码）"""
    try:
        return _enable()
    except RuntimeError as exc:
        print("  %s" % exc)
        return False


def disable():
    """停用定时核验；失败返回 False"""
    try:
        return _disable()
    except RuntimeError as exc:
        print("  %s" % exc)
        return False


def _plist(label, args, extra):
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{exe}</string>
{argv}
  </array>
{extra}
  <key>StandardErrorPath</key><string>/tmp/{label}.err</string>
</dict>
</plist>
""".format(
        label=label,
        exe=_launcher(),
        argv="\n".join("    <string>%s</string>" % a for a in args),
        extra=extra,
    )


def _write_plist(path, content):
    open(path, "w", encoding="utf-8").write(content)
    subprocess.run(["launchctl", "unload", path], capture_output=True)
    subprocess.run(["launchctl", "load", path], capture_output=True)


def _win_register(name, arguments, trigger_script):
    """用 ScheduledTask cmdlet 注册任务：允许电池运行、限制并发、放宽执行时限"""
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        "$action = New-ScheduledTaskAction -Execute '{exe}' -Argument '\"{script}\" {args}'\n"
        "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable "
        "-ExecutionTimeLimit (New-TimeSpan -Hours 2)\n"
        "{trigger}\n"
        "Register-ScheduledTask -TaskName '{name}' -Action $action -Trigger $trigger "
        "-Settings $settings -Force | Out-Null\n"
    ).format(exe=sys.executable, script=_launcher(), args=arguments,
             trigger=trigger_script, name=name)
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("  注册任务失败：%s" % (result.stderr.strip() or result.stdout.strip()))


def _enable():
    if platform.IS_LINUX:
        return _linux_enable()
    if platform.IS_WIN:
        _win_register(
            TASK_WATCH, "auto run",
            "$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) "
            "-RepetitionInterval (New-TimeSpan -Hours 1)",
        )
        _win_register(
            TASK_DAILY, "auto run --full",
            "$trigger = New-ScheduledTaskTrigger -Daily -At 01:00",
        )
        print("已启用：每天 01:00 全量 + 每小时巡检")
        print("  日志：%s" % platform.auto_log())
        return True

    os.makedirs(PLIST_DIR, exist_ok=True)
    watch_path = os.path.join(PLIST_DIR, TASK_WATCH + ".plist")
    daily_path = os.path.join(PLIST_DIR, TASK_DAILY + ".plist")
    _write_plist(watch_path, _plist(
        TASK_WATCH, ["auto", "run"],
        "  <key>StartInterval</key><integer>3600</integer>\n  <key>RunAtLoad</key><true/>",
    ))
    _write_plist(daily_path, _plist(
        TASK_DAILY, ["auto", "run", "--full"],
        "  <key>StartCalendarInterval</key>\n  <dict><key>Hour</key><integer>1</integer>"
        "<key>Minute</key><integer>0</integer></dict>",
    ))
    print("已启用：每天 01:00 全量 + 每小时巡检")
    print("  日志：%s" % platform.auto_log())
    return True


def _disable():
    if platform.IS_LINUX:
        if not _systemctl("disable", "--now", TASK_WATCH + ".timer", TASK_DAILY + ".timer"):
            print("  未停用：单元文件保留在 %s，修好 systemctl 后重试" % _systemd_dir())
            return False
        for name in (TASK_WATCH, TASK_DAILY):
            for suffix in (".timer", ".service"):
                try:
                    os.remove(os.path.join(_systemd_dir(), name + suffix))
                except FileNotFoundError:
                    pass
        _systemctl("daemon-reload")
        print("已停用定时核验")
        return True
    if platform.IS_WIN:
        for task in (TASK_WATCH, TASK_DAILY):
            subprocess.run("schtasks /Delete /F /TN %s" % task, shell=True, capture_output=True)
        print("已停用定时核验")
        return True
    for task in (TASK_WATCH, TASK_DAILY):
        path = os.path.join(PLIST_DIR, task + ".plist")
        if os.path.exists(path):
            subprocess.run(["launchctl", "unload", path], capture_output=True)
            os.remove(path)
    print("已停用定时核验")
    return True


def status():
    if platform.IS_LINUX:
        def running(name):
            try:
                out = subprocess.run(["systemctl", "--user", "is-active", name + ".timer"],
                                     capture_output=True, text=True).stdout
            except OSError:
                return None          # 没有 systemctl：调用方按「未知」显示
            return out.strip() == "active"

        watch, daily = running(TASK_WATCH), running(TASK_DAILY)

        def label(state):
            return "未知（systemctl 不可用）" if state is None else ("每小时巡检" if state else "未启用")

        print("  定时任务：%s ｜ %s" % (
            label(watch),
            "未知（systemctl 不可用）" if daily is None else ("每天 01:00 全量" if daily else "未启用")))
    elif platform.IS_WIN:
        def installed(task):
            out = subprocess.run("schtasks /Query /TN %s" % task, shell=True,
                                 capture_output=True, text=True).stdout
            return bool(out.strip())

        print("  定时任务：%s ｜ %s" % ("每小时巡检" if installed(TASK_WATCH) else "未启用",
                                     "每天 01:00 全量" if installed(TASK_DAILY) else "未启用"))
    else:
        watch = os.path.exists(os.path.join(PLIST_DIR, TASK_WATCH + ".plist"))
        daily = os.path.exists(os.path.join(PLIST_DIR, TASK_DAILY + ".plist"))
        print("  定时任务：%s ｜ %s" % ("每小时巡检" if watch else "未启用",
                                     "每天 01:00 全量" if daily else "未启用"))
    prof = platform.profile_file()
    print("  订阅文件：%s" % (prof or "未知"))
    if prof and os.path.exists(prof):
        print("    更新于 %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(prof))))
    try:
        data = json.load(open(platform.marker_path(), encoding="utf-8"))
    except Exception:
        print("  上次核验：从未")
        print("  状态：从未核验过，下次检查会执行一次")
        return
    print("  上次核验：%s（已验 %s 个 / 订阅 %s 个）"
          % (data.get("verified_at", "?"), data.get("verified_count", "?"), data.get("node_count", "?")))
    missing = int(data.get("node_count", 0)) - int(data.get("verified_count", 0))
    if missing <= 0:
        print("  状态：清单覆盖全部节点")
    else:
        print("  状态：%d 个节点本轮无响应（每小时巡检会补测，恢复后自动进池）" % missing)


# ------------------------------------------------------------------ 定时执行

def run(mode="watch"):
    marker = platform.marker_path()
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    log = platform.auto_log()

    def note(text):
        with open(log, "a", encoding="utf-8") as handle:
            handle.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))

    if mode != "full" and time.strftime("%H") == "01":
        return
    try:
        if mode == "full":
            note("每日 01:00 全量核验开始")
            changed = commands._refresh(full=True)
        else:
            note("每小时巡检开始")
            changed = commands._refresh()
    except Exception as exc:  # 定时任务里不能抛出去
        note("核验失败：%s" % exc)
        return
    if changed is None:
        note("已有核验在跑，本次跳过")
        return
    if not changed:
        note("清单无变化，跳过重启")
        return
    note("清单已更新，重启 Clash Verge")
    try:
        ok = platform.restart_app()
    except Exception as exc:
        note("重启失败：%s" % exc)
        return
    if not ok:
        note("重启失败：找不到 Clash Verge 主程序，请手动重开")
