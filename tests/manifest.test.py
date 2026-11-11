#!/usr/bin/env python3
"""clashctl 清单与增量刷新的规格测试

缝：~/.local/lib/clashctl/manifest.py 的纯函数
  - parse_manifest(script_text)     从 Script.js 还原 {节点名: (出口, 延迟ms)}
  - compute_todo(names, manifest, full)  决定这次要实测哪些节点
  - render_block(items)             生成写回 Script.js 的 VERIFIED 块
"""
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

LIB = os.environ.get("CLASHCTL_LIB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", "clashctl")
sys.path.insert(0, LIB)

from manifest import (parse_manifest, compute_todo, render_block,  # noqa: E402
                      needs_full_refresh, resolve_full, replace_block, splice_from,
                      replace_marked)

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  ✓ {name}")
    except AssertionError as e:
        failures.append(name)
        print(f"  ✗ {name}\n      {e}")


SCRIPT_SAMPLE = """var LOCAL_RULES = [];
// >>> VERIFIED-EXITS（自动生成，勿手改）
// 格式：节点名 -> [出口地区代码, 实测延迟 ms]
var VERIFIED = {
  "香港 01": ["HK", 217],
  "美国 01": ["US", 1563],
};
// <<< VERIFIED-EXITS
function main(c) { return c; }
"""


def test_parse():
    m = parse_manifest(SCRIPT_SAMPLE)
    assert m["香港 01"] == ("HK", 217), m
    assert m["美国 01"] == ("US", 1563), m
    assert len(m) == 2, m


def test_parse_empty():
    assert parse_manifest("var VERIFIED = {};") == {}


def test_parse_no_block():
    assert parse_manifest("function main(c){return c;}") == {}


def test_todo_only_missing():
    names = ["香港 01", "新加坡 01", "新节点 B"]
    manifest = {"香港 01": ("HK", 217)}
    todo = compute_todo(names, manifest)
    assert todo == ["新加坡 01", "新节点 B"], todo


def test_todo_full():
    names = ["A", "B"]
    manifest = {"A": ("HK", 1), "B": ("US", 2)}
    assert compute_todo(names, manifest, full=True) == ["A", "B"]


def test_todo_ignores_stale_manifest_entries():
    """清单里有、订阅里已不存在的节点，不该被再测一次（也不该出现在 todo）"""
    names = ["A"]
    manifest = {"A": ("HK", 1), "已下架的节点": ("US", 2)}
    assert compute_todo(names, manifest) == [], compute_todo(names, manifest)


def test_todo_empty_manifest_means_all():
    names = ["A", "B"]
    assert compute_todo(names, {}) == ["A", "B"]


def test_render_block_roundtrip():
    items = {"香港 A01": ("HK", 217), "美国 A01": ("US", 1563)}
    block = render_block(items)
    assert "// >>> VERIFIED-EXITS" in block and "// <<< VERIFIED-EXITS" in block, block
    parsed = parse_manifest(block)
    assert parsed == items, parsed


def test_render_block_stable_order():
    """输出顺序必须稳定，否则每次刷新都会产生无意义的大 diff"""
    a = render_block({"B": ("US", 2), "A": ("HK", 1)})
    b = render_block({"A": ("HK", 1), "B": ("US", 2)})
    assert a == b, "同样的内容产生了不同的输出顺序"


def test_needs_full_when_subscription_newer():
    assert needs_full_refresh(1000, 900) is True
    assert needs_full_refresh(1000, 1000) is False
    assert needs_full_refresh(1000, 1001) is False
    assert needs_full_refresh(1000, 0) is True
    assert needs_full_refresh(0, 0) is False


def test_resolve_full():
    # 抽查永远不是全量，即使加了 --full 或订阅刚变
    assert resolve_full(False, "美国") is False
    assert resolve_full(True, "美国") is False
    # 显式全量 / 订阅变更
    assert resolve_full(True, None) is True
    assert resolve_full(False, None) is False


def test_replace_block():
    assert replace_block("function main(){}", {"A": ("HK", 1)}) is None
    out = replace_block(SCRIPT_SAMPLE, {"新节点": ("SG", 5)})
    assert out is not None and "新节点" in out and "香港 A01" not in out, out
    # 内容相同也要能区分「写成功」和「没找到块」
    same = replace_block(SCRIPT_SAMPLE, parse_manifest(SCRIPT_SAMPLE))
    assert same is not None


def test_splice_from():
    """同步项目源码到 Clash 时，必须保留目标里已有的清单"""
    project = SCRIPT_SAMPLE.replace(
        'var VERIFIED = {\n  "香港 01": ["HK", 217],\n  "美国 01": ["US", 1563],\n};',
        "var VERIFIED = {};")
    live = SCRIPT_SAMPLE.replace('"香港 01": ["HK", 217]', '"香港 新节点": ["HK", 999]')
    out = splice_from(project, live)
    parsed = parse_manifest(out)
    assert parsed.get("香港 新节点") == ("HK", 999), parsed
    assert "香港 01" not in parsed, parsed
    # 目标没有清单时，原样使用源码
    assert splice_from(project, "function main(){}") == project


def test_replace_marked():
    """本地覆盖注入：只替换标记块，其余内容不动"""
    src = "var a = 1;\n// >>> X\nvar X = [];\n// <<< X\nvar b = 2;"
    out = replace_marked(src, "// >>> X", "// <<< X", "var X = [1, 2];")
    assert out is not None
    assert "var X = [1, 2];" in out and "var a = 1;" in out and "var b = 2;" in out, out
    # 没有标记时返回 None，调用方据此告警
    assert replace_marked("var a = 1;", "// >>> X", "// <<< X", "x") is None
    # 幂等：连续注入相同内容结果不变
    assert replace_marked(out, "// >>> X", "// <<< X", "var X = [1, 2];") == out


check("本地覆盖注入只替换标记块", test_replace_marked)
check("同步时保留目标文件里的清单", test_splice_from)
check("抽查永远不会被当成全量", test_resolve_full)
check("replace_block 区分「没找到块」与「内容相同」", test_replace_block)
check("订阅变更判定（只有全量推进的版本才算数）", test_needs_full_when_subscription_newer)
check("parse_manifest 能还原清单", test_parse)
check("parse_manifest 处理空清单", test_parse_empty)
check("parse_manifest 无标记块时返回空", test_parse_no_block)
check("compute_todo 只返回清单里没有的节点", test_todo_only_missing)
check("compute_todo --full 返回全部", test_todo_full)
check("compute_todo 忽略已下架节点", test_todo_ignores_stale_manifest_entries)
check("compute_todo 空清单时全测", test_todo_empty_manifest_means_all)
check("render_block 可被 parse_manifest 还原", test_render_block_roundtrip)
check("render_block 输出顺序稳定", test_render_block_stable_order)

print(f"\n  {14 - len(failures)}/14 通过")
sys.exit(1 if failures else 0)
