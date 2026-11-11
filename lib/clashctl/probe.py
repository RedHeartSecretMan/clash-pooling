"""HTTP 探测：全部用标准库，不依赖 curl，macOS / Windows 行为一致。"""

import http.client
import ssl
import time
import urllib.parse

TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
TRACE_TIMEOUT = 8


def fetch(url, proxy=None, timeout=8):
    """请求 url。

    proxy=(host, port) 时走 HTTP 代理（CONNECT 隧道），否则直连。
    返回 (status, body_text, ttfb_ms)；失败抛异常。
    """
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query

    if proxy:
        if parts.scheme == "https":
            conn = http.client.HTTPSConnection(proxy[0], proxy[1], timeout=timeout)
            conn.set_tunnel(host, port)
        else:
            conn = http.client.HTTPConnection(proxy[0], proxy[1], timeout=timeout)
            path = url  # 明文代理直接请求绝对地址
    else:
        if parts.scheme == "https":
            conn = http.client.HTTPSConnection(host, port, timeout=timeout,
                                               context=ssl.create_default_context())
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)

    started = time.perf_counter()
    try:
        conn.request("GET", path, headers={"User-Agent": "clashctl"})
        resp = conn.getresponse()
        ttfb = (time.perf_counter() - started) * 1000
        body = resp.read(8192).decode("utf-8", "replace")
        return resp.status, body, ttfb
    finally:
        conn.close()


def trace(proxy, timeout=TRACE_TIMEOUT):
    """读出口地区与延迟，返回 (cc, ttfb_ms)；失败返回 ("", 0)"""
    try:
        status, body, ttfb = fetch(TRACE_URL, proxy=proxy, timeout=timeout)
    except Exception:
        return "", 0
    if status != 200:
        return "", 0
    cc = ""
    for line in body.splitlines():
        if line.startswith("loc="):
            cc = line[4:].strip().upper()
            break
    return cc, int(ttfb)
