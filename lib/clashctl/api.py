"""mihomo 控制接口客户端：macOS 走 unix socket，Windows 走 TCP。"""

import http.client
import json
import socket
import urllib.parse

from . import platform


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=8):
        super().__init__("localhost", timeout=timeout)
        self._unix_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._unix_path)
        self.sock = sock


_override = None


def set_override(kind, target, secret):
    """临时把控制端点指向别处（测量用的临时实例）"""
    global _override
    _override = (kind, target, secret)


def clear_override():
    global _override
    _override = None


def _connection(timeout=8):
    kind, target, secret = _override or platform.control()
    if kind == "unix":
        conn = _UnixConnection(target, timeout=timeout)
    else:
        host, port = target
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    headers = {"Authorization": "Bearer " + secret} if secret else {}
    return conn, headers


def request(method, path, payload=None, timeout=8):
    """调用控制接口，返回 (status, body_bytes)"""
    conn, headers = _connection(timeout=timeout)
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def get_json(path, timeout=8):
    status, data = request("GET", path, timeout=timeout)
    if status != 200:
        raise RuntimeError("控制接口返回 %d：%s" % (status, path))
    return json.loads(data.decode("utf-8"))


def proxies():
    return get_json("/proxies")["proxies"]


def rules():
    return get_json("/rules")["rules"]


def version():
    return get_json("/version")


def select(group, name, timeout=6):
    """把 select 组切换到指定成员"""
    path = "/proxies/" + urllib.parse.quote(group)
    status, _ = request("PUT", path, {"name": name}, timeout=timeout)
    return status == 204


def group_now(group):
    path = "/proxies/" + urllib.parse.quote(group)
    try:
        return get_json(path, timeout=5).get("now")
    except Exception:
        return None



GROUP_TYPES = {
    "Selector", "Fallback", "URLTest", "LoadBalance", "Direct", "Reject",
    "Compatible", "Pass", "RejectDrop", "Dns", "PassRule",
}


def node_names(all_proxies):
    """订阅节点（排除组与内置出站）"""
    return [
        name for name, value in all_proxies.items()
        if value["type"] not in GROUP_TYPES and name not in ("GLOBAL", "DIRECT", "REJECT")
    ]


def service_groups(all_proxies):
    """服务组：select 类型的组，按 AI / 通用 / 其他 优先排序

    与 pool_groups 按类型互斥（select ↔ url-test），同一个组不会出现在两边。
    """
    order = ["AI", "通用", "其他"]
    names = [n for n, v in all_proxies.items()
             if v["type"] == "Selector" and n != "GLOBAL"]
    return [n for n in order if n in names] + [n for n in names if n not in order]


def pool_groups(all_proxies):
    """地区池：url-test 类型的组

    接口返回的键序不可靠（内核按字典序输出），展示顺序由 commands.pool_order
    从配置里的 PREFER 还原。
    """
    return [n for n, v in all_proxies.items() if v["type"] == "URLTest"]
