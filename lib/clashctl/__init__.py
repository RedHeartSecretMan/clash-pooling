"""clash-pooling：按实测出口地区划分 Clash 节点池。"""

__version__ = "0.1.2"


def setup_console():
    """Windows 控制台默认 GBK，把标准输出统一成 UTF-8；失败不影响运行"""
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
