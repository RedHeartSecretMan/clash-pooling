"""平台差异集中在这里：路径、控制端点、内核二进制、重启应用、定时任务。

macOS、Windows 和 Linux 的环境差异由本模块吸收。
"""

import os
import re
import shutil
import subprocess
import sys
import time

APP_DIR = "io.github.clash-verge-rev.clash-verge-rev"
IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")


# ---------------------------------------------------------------- 路径

def config_root():
    """Clash Verge 的配置根目录"""
    if IS_WIN:
        return os.path.join(os.environ.get("APPDATA", ""), APP_DIR)
    if IS_LINUX:
        return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), APP_DIR)
    return os.path.join(os.path.expanduser("~/Library/Application Support"), APP_DIR)


def profiles_dir():
    return os.path.join(config_root(), "profiles")


def generated_config():
    return os.path.join(config_root(), "clash-verge.yaml")


def script_path():
    return os.environ.get("CLASH_SCRIPT") or os.path.join(profiles_dir(), "Script.js")


def merge_path():
    return os.environ.get("CLASH_MERGE") or os.path.join(profiles_dir(), "Merge.yaml")


def state_dir():
    return os.path.normpath(os.path.expanduser("~/.dsh-clashctl"))


def marker_path():
    return os.path.join(state_dir(), "last-refresh")


def auto_log():
    return os.path.join(state_dir(), "auto.log")


def profile_file():
    """当前订阅的 yaml 文件（从 profiles.yaml 的 current 推出）"""
    path = os.path.join(config_root(), "profiles.yaml")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return ""
    cur = re.search(r"^current:\s*(\S+)", text, re.M)
    if not cur:
        return ""
    m = re.search(r"- uid: " + re.escape(cur.group(1)) + r"\n(?:.*\n)*?\s+file: (\S+)", text)
    return os.path.join(profiles_dir(), m.group(1)) if m else ""


# ---------------------------------------------------------------- 控制端点

def _parse_generated():
    """从生成的配置里读 external-controller / secret / mixed-port"""
    out = {"controller": "", "secret": "", "mixed_port": 7897, "unix": ""}
    try:
        lines = open(generated_config(), encoding="utf-8").read().splitlines()
    except OSError:
        return out
    for line in lines:
        if line.startswith("external-controller:"):
            out["controller"] = line.split(":", 1)[1].strip().strip("'\"")
        elif line.startswith("external-controller-unix:"):
            out["unix"] = line.split(":", 1)[1].strip().strip("'\"")
        elif line.startswith("secret:"):
            out["secret"] = line.split(":", 1)[1].strip().strip("'\"")
        elif line.startswith("mixed-port:"):
            try:
                out["mixed_port"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return out


def _tcp_endpoint(cfg, secret):
    addr = os.environ.get("CLASH_CONTROLLER") or cfg["controller"] or "127.0.0.1:9097"
    host, _, port = addr.rpartition(":")
    return "tcp", (host or "127.0.0.1", int(port or 9097)), secret


def control():
    """返回 (kind, target, secret)；kind 为 'unix' 或 'tcp'

    优先级：CLASH_CONTROLLER（显式 TCP）> CLASH_SOCK（显式 socket）> 生成配置里的
    unix socket（文件存在才用）> 生成配置里的 TCP 地址。
    socket 文件不存在时退回 TCP，避免拿一个过期路径去连。
    """
    cfg = _parse_generated()
    secret = os.environ.get("CLASH_SECRET") or cfg["secret"]
    if os.environ.get("CLASH_CONTROLLER"):
        return _tcp_endpoint(cfg, secret)
    if IS_WIN:
        return _tcp_endpoint(cfg, secret)

    sock = os.environ.get("CLASH_SOCK")
    if not sock and IS_MAC:
        # macOS 的 service 模式会把 mihomo 的控制 socket 放到这里
        service = "/var/run/clash-verge-service/users/%d/verge-mihomo.sock" % os.getuid()
        if os.path.exists(service):
            sock = service
    if not sock:
        sock = cfg["unix"]
    if sock and os.path.exists(sock):
        return "unix", sock, secret
    return _tcp_endpoint(cfg, secret)


def system_proxy():
    """系统代理状态：{'enabled': bool, 'host': str, 'port': int}；读不到返回 None"""
    if IS_MAC:
        try:
            out = subprocess.run(["scutil", "--proxy"], capture_output=True, text=True, timeout=5).stdout
        except Exception:
            return None
        enabled = re.search(r"HTTPEnable\s*:\s*1", out) or re.search(r"SOCKSEnable\s*:\s*1", out)
        host = re.search(r"HTTPProxy\s*:\s*(\S+)", out) or re.search(r"SOCKSProxy\s*:\s*(\S+)", out)
        port = re.search(r"HTTPPort\s*:\s*(\d+)", out) or re.search(r"SOCKSPort\s*:\s*(\d+)", out)
        return {"enabled": bool(enabled), "host": host.group(1) if host else "",
                "port": int(port.group(1)) if port else 0}
    if IS_WIN:
        try:
            out = subprocess.run(
                ["reg", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"],
                capture_output=True, text=True, timeout=5).stdout
        except Exception:
            return None
        enabled = re.search(r"ProxyEnable\s+REG_DWORD\s+0x1", out)
        server = re.search(r"ProxyServer\s+REG_SZ\s+(\S+)", out)
        host, port = "", 0
        if server:
            value = server.group(1)
            host, _, tail = value.rpartition(":")
            if tail.isdigit():
                port = int(tail)
            else:
                host, port = value, 0
        return {"enabled": bool(enabled), "host": host, "port": port}
    if IS_LINUX:
        try:
            def setting(schema, key):
                return subprocess.check_output(["gsettings", "get", schema, key], text=True, timeout=5).strip().strip("'")
            return {"enabled": setting("org.gnome.system.proxy", "mode") == "manual",
                    "host": setting("org.gnome.system.proxy.http", "host"),
                    "port": int(setting("org.gnome.system.proxy.http", "port"))}
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    return None


def mixed_port():
    return _parse_generated()["mixed_port"]


# ---------------------------------------------------------------- 内核与应用

def core_binary():
    override = os.environ.get("CLASH_CORE")
    if override:
        return override
    if IS_MAC:
        return "/Applications/Clash Verge.app/Contents/MacOS/verge-mihomo"
    if IS_WIN:
        root = os.environ.get("ProgramData", r"C:\ProgramData")
        return os.path.join(root, "clash-verge-service", "cores", "verge-mihomo.exe")
    if IS_LINUX:
        # 不同打包方式放内核的位置不一样：服务模式与 deb/rpm；AppImage 用 CLASH_CORE 指定
        for candidate in (
            "/var/lib/clash-verge-service/cores/verge-mihomo",
            "/usr/lib/Clash Verge/resources/verge-mihomo",
            "/usr/lib/clash-verge/verge-mihomo",
        ):
            if os.access(candidate, os.X_OK):
                return candidate
    return shutil.which("verge-mihomo") or ""


def app_exe():
    """Clash Verge 主程序路径（用于重启）"""
    if IS_MAC:
        return "/Applications/Clash Verge.app"
    if IS_LINUX:
        return shutil.which("clash-verge") or ""
    if not IS_WIN:
        return ""

    roots = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
             os.environ.get("ProgramFiles(x86)", "")]
    names = ["clash-verge.exe", "Clash Verge.exe"]
    for root in roots:
        if not root:
            continue
        for sub in ("Programs\\clash-verge", "Clash Verge"):
            for name in names:
                path = os.path.join(root, sub, name)
                if os.path.exists(path):
                    return path

    # 兜底：问进程自己要路径
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process clash-verge -ErrorAction SilentlyContinue | Select-Object -First 1).Path"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        pass
    return ""


def restart_app(delay=4):
    """退出并重新打开 Clash Verge"""
    if IS_MAC:
        subprocess.run(["osascript", "-e", 'tell application "Clash Verge" to quit'], capture_output=True)
        time.sleep(delay)
        subprocess.run(["open", "-a", "Clash Verge"], capture_output=True)
        return True
    if IS_WIN:
        subprocess.run(["taskkill", "/IM", "clash-verge.exe", "/F"], capture_output=True)
        time.sleep(delay)
        exe = app_exe()
        if exe:
            subprocess.Popen(["cmd", "/c", "start", "", exe], shell=False)
            return True
        return False
    if IS_LINUX:
        exe = app_exe()
        if not exe:
            return False
        subprocess.run(["pkill", "-TERM", "-u", str(os.getuid()), "-x", "clash-verge"], capture_output=True)
        time.sleep(delay)
        subprocess.Popen([exe], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    return False


LOCK_STALE_SECONDS = 3 * 3600


def acquire_lock(name="auto"):
    """跨进程互斥：抢到返回锁文件路径，抢不到返回 None。

    用 O_EXCL 创建锁文件；超过 LOCK_STALE_SECONDS 的陈旧锁（进程被杀等）会被清掉。
    """
    path = os.path.join(state_dir(), name + ".lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return path
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(path)
            except OSError:
                age = LOCK_STALE_SECONDS + 1
            if age > LOCK_STALE_SECONDS:
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            return None
    return None


def release_lock(path):
    """释放锁；锁文件已消失时静默返回"""
    try:
        os.remove(path)
    except OSError:
        pass

def link_or_copy(src, dst):
    """geodata 在临时实例里需要可读；Windows 无权限建软链时退化为复制"""
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError):
        shutil.copy2(src, dst)
