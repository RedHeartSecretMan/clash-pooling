"""测量流水线：起临时实例，逐节点切换后读取出口地区与延迟。"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time

from . import api, platform, probe

PORT = 17981
CTL_PORT = 18181
SECRET = "exitcheck"
DEADLINE_SECONDS = 3000
SETTLE_SECONDS = 0.6


def port_busy(port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _proxies_block():
    """从生成的配置里切出 proxies: 段（保持原样文本）"""
    lines = open(platform.generated_config(), encoding="utf-8").read().splitlines()
    keep, inside = [], False
    for line in lines:
        if line.startswith("proxies:"):
            inside = True
            keep.append(line)
            continue
        if inside and line.startswith("proxy-groups:"):
            break
        if inside:
            keep.append(line)
    return keep


def build_config(tmpdir, nodes):
    body = [
        "mixed-port: %d" % PORT,
        "external-controller: 127.0.0.1:%d" % CTL_PORT,
        'secret: "%s"' % SECRET,
        "log-level: warning",
        "ipv6: true",
        "mode: rule",
    ]
    body += _proxies_block()
    body.append("proxy-groups:")
    body.append("- name: TEST")
    body.append("  type: select")
    body.append("  proxies:")
    for name in nodes:
        body.append("  - " + json.dumps(name, ensure_ascii=False))
    body.append("rules:")
    body.append("- MATCH,TEST")
    path = os.path.join(tmpdir, "cfg.yaml")
    open(path, "w", encoding="utf-8").write("\n".join(body) + "\n")
    return path


class _TempInstance:
    def __init__(self, nodes):
        self.nodes = nodes
        self.proc = None
        self.tmpdir = None

    def __enter__(self):
        for port in (PORT, CTL_PORT):
            if port_busy(port):
                raise RuntimeError("端口 %d 已被占用（可能有其它核验在跑）" % port)
        core = platform.core_binary()
        if not core or not os.path.exists(core):
            raise RuntimeError("找不到内核：%s" % core)
        self.tmpdir = tempfile.mkdtemp(prefix="exitcheck-")
        try:
            for name in ("Country.mmdb", "geosite.dat", "geoip.dat", "ASN.mmdb"):
                src = os.path.join(platform.config_root(), name)
                if os.path.exists(src):
                    platform.link_or_copy(src, os.path.join(self.tmpdir, name))
            cfg = build_config(self.tmpdir, self.nodes)
            self.proc = subprocess.Popen(
                [core, "-d", self.tmpdir, "-f", cfg],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            self.__exit__()
            raise
        api.set_override("tcp", ("127.0.0.1", CTL_PORT), SECRET)
        try:
            for _ in range(30):
                time.sleep(0.4)
                if self._alive():
                    return self
            raise RuntimeError("临时实例启动失败")
        except Exception:
            self.__exit__()
            raise

    def _alive(self):
        try:
            status, _ = api.request("GET", "/version", timeout=3)
            return status == 200
        except Exception:
            return False

    def __exit__(self, *exc):
        api.clear_override()
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        if self.tmpdir:
            shutil.rmtree(self.tmpdir, ignore_errors=True)


def _select(node):
    """切换测量组到指定节点，并确认生效"""
    for _ in range(3):
        if api.select("TEST", node):
            for _ in range(4):
                if api.group_now("TEST") == node:
                    time.sleep(SETTLE_SECONDS)
                    return True
                time.sleep(0.2)
        time.sleep(0.3)
    return False


def measure(nodes, fast=True):
    """返回 ({节点: (cc, ms)}, 是否因超时截断)"""
    results = {}
    truncated = False
    with _TempInstance(nodes) as inst:
        proxy = ("127.0.0.1", PORT)
        deadline = time.time() + DEADLINE_SECONDS
        for index, node in enumerate(nodes, 1):
            if time.time() > deadline:
                print("  超过 %d 秒上限，剩余 %d 个节点跳过" % (DEADLINE_SECONDS, len(nodes) - index + 1))
                truncated = True
                break
            if not _select(node):
                results[node] = ("", 0)
                continue
            time.sleep(0.2)
            cc, ms = probe.trace(proxy, timeout=7 if fast else 12)
            if cc:
                cc2, _ = probe.trace(proxy, timeout=5 if fast else 8)
                if cc2 and cc2 != cc:
                    cc = ""
            elif not fast:
                time.sleep(1.2)
                cc, ms = probe.trace(proxy, timeout=12)
            results[node] = (cc, ms)
            print("  %3d/%d  %-34s %s" % (index, len(nodes), node, cc or "失败"), flush=True)
    return results, truncated
