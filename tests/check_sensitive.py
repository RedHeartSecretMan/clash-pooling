#!/usr/bin/env python3
"""敏感内容守卫：防止把公司内网信息或凭据提交进仓库。

规则：
  - RFC1918 私网地址（文档保留段 192.0.2.0/24 等除外）
  - 订阅地址里的令牌片段（/sub/<长十六进制>）
  - 配置里的真实 secret
  - 本地 clash/local/sensitive.txt 里配置的私有域名/关键字

需要示例时用文档保留值：example.com、192.0.2.x、198.51.100.x、203.0.113.x。
确需保留某一行时，在该行加注释 `allow-sensitive`。

项目相关的私有域名/关键字不写在本文件里，放到 clash/local/sensitive.txt
（一行一个正则，已被 .gitignore 排除），避免守卫本身泄露内部信息。
"""

import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
SKIP_PREFIXES = ("clash/local",)
SUFFIXES = {".md", ".js", ".py", ".cjs", ".sh", ".ps1", ".yaml", ".yml", ".json", ".cmd"}
SCRIPT_NAMES = {"clashctl"}   # 无扩展名的启动器也要扫

PATTERNS = [
    ("私网地址", re.compile(r"\b(?:10(?:\.\d{1,3}){3}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|192\.168(?:\.\d{1,3}){2})\b")),
    ("订阅令牌", re.compile(r"/sub/[0-9a-fA-F]{12,}")),
    ("订阅令牌", re.compile(r"[?&]token=[0-9a-zA-Z]{12,}")),
    ("真实密钥", re.compile(r"^\s*secret:\s*(?!['\"]?set-your-secret|['\"]?)([0-9a-zA-Z]{8,})", re.M)),
]


def load_custom_patterns():
    """从本地文件读入私有域名/关键字，一行一个正则"""
    path = os.path.join(ROOT, "clash", "local", "sensitive.txt")
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(("私有关键字", re.compile(line, re.I)))
    return out

# 文档保留段与示例值不报警
ALLOW = re.compile(r"192\.0\.2\.|198\.51\.100\.|203\.0\.113\.|example\.(com|org|net)")


def scan(path, patterns):
    hits = []
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), 1):
        if "allow-sensitive" in line:
            continue
        for label, pattern in patterns:
            match = pattern.search(line)
            if match and not ALLOW.search(match.group(0)):
                hits.append((label, lineno, line.strip()[:100]))
                break
    return hits


def main():
    patterns = PATTERNS + load_custom_patterns()
    problems = 0
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != ".git"]
        for name in files:
            ext = os.path.splitext(name)[1]
            if ext not in SUFFIXES and name not in SCRIPT_NAMES:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            if rel.startswith(SKIP_PREFIXES):
                continue
            for label, lineno, line in scan(path, patterns):
                problems += 1
                print("  ✗ %s:%d [%s] %s" % (rel, lineno, label, line))
    if problems:
        print("\n  %d 处敏感内容；示例请用 example.com 与 192.0.2.x，私有内容放 clash/local/" % problems)
        return 1
    print("  ✓ 未发现私网地址、订阅令牌、真实密钥或本地配置的私有关键字")
    return 0


if __name__ == "__main__":
    sys.exit(main())
