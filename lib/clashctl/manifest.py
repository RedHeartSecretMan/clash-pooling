"""clashctl 的清单处理（纯函数，可脱离 Clash 单独测试）

VERIFIED 清单存在 Script.js 的标记块里：
    // >>> VERIFIED-EXITS
    var VERIFIED = { "节点名": ["HK", 217], ... };
    // <<< VERIFIED-EXITS
"""

import json
import re

MARK_START = "// >>> VERIFIED-EXITS"
MARK_END = "// <<< VERIFIED-EXITS"

_ENTRY = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*\[\s*"([A-Za-z]{2})"\s*,\s*(\d+)\s*\]')
_BLOCK = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), re.S)


def _block(script_text):
    m = _BLOCK.search(script_text)
    return m.group(0) if m else ""


# 与 clash/Script.js 里的 JUNK 保持一致：URL、IPv4 与常见中文词
JUNK_PATTERN = re.compile(r"https?:|tcp://|\d{1,3}(\.\d{1,3}){3}|官网|广告|推广", re.I)


def is_junk(name):
    """机场落地页 / 广告节点，不是真实出口"""
    return bool(JUNK_PATTERN.search(name))


def parse_manifest(script_text):
    """从 Script.js 源码里还原 {节点名: (出口地区代码, 延迟ms)}"""
    out = {}
    for name, cc, ms in _ENTRY.findall(_block(script_text)):
        try:
            key = json.loads('"' + name + '"')
        except ValueError:
            key = name
        out[key] = (cc.upper(), int(ms))
    return out


def compute_todo(names, existing, full=False):
    """决定这次要实测哪些节点：只测清单里没有的（full=True 时全测）

    清单里有、但订阅里已下架的节点不会被返回——不浪费时间在死条目上。
    existing 是上一次的清单 {节点名: (出口地区代码, 延迟 ms)}。
    """
    if full:
        return list(names)
    return [n for n in names if n not in existing]


def render_block(items):
    """生成写回 Script.js 的 VERIFIED 块（按节点名排序，保证输出稳定）"""
    lines = [
        MARK_START + "（由 `clashctl exit-check --refresh` 自动生成，勿手改）",
        "// 格式：节点名 -> [出口地区代码, 实测延迟 ms]",
        "var VERIFIED = {",
    ]
    for name in sorted(items):
        cc, ms = items[name]
        lines.append("  %s: [%s, %d]," % (json.dumps(name, ensure_ascii=False), json.dumps(cc), int(ms)))
    lines.append("};")
    lines.append(MARK_END)
    return "\n".join(lines)


def replace_block(script_text, items):
    """把清单块替换成 items 渲染结果；脚本里没有标记块时返回 None

    注意：内容完全相同时也会返回「与原文相同」的字符串——调用方不能靠
    字符串相等判断"没找到标记块"（那是两种不同的失败）。
    """
    if not _BLOCK.search(script_text):
        return None
    return _BLOCK.sub(lambda _m: render_block(items), script_text, count=1)


def splice_from(source_text, target_text):
    """用 source 的内容覆盖 target，但保留 target 里已有的清单块

    项目里的 clash/Script.js 只存代码（清单为空占位），
    同步到 Clash 时要把目标文件里已经测出来的清单一并带过去。
    """
    m = _BLOCK.search(target_text or "")
    if not m:
        return source_text
    return _BLOCK.sub(lambda _x: m.group(0), source_text, count=1)


def replace_marked(text, start_marker, end_marker, body):
    """把 start/end 标记之间的内容替换为 body；找不到标记返回 None"""
    pattern = re.compile(re.escape(start_marker) + r".*?" + re.escape(end_marker), re.S)
    if not pattern.search(text):
        return None
    block = "%s\n%s\n%s" % (start_marker, body.rstrip(), end_marker)
    return pattern.sub(lambda _m: block, text, count=1)


def needs_full_refresh(current_profile_mtime, verified_profile_mtime):
    """订阅是否比「整份清单所依据的订阅版本」更新

    只看全量核验推进的 profile_mtime —— 增量/抽查不能把它推进，
    否则会把过期条目洗白，旧标签永远不再被怀疑。
    """
    return int(current_profile_mtime or 0) > int(verified_profile_mtime or 0)


def resolve_full(explicit_full, recheck):
    """这次核验算不算「全量」

    --recheck 抽查永远不算全量：它只测命名匹配的节点，
    若因此推进订阅版本戳，未重测的过期条目就被洗白了。
    （订阅变更由调用方判断后并入 explicit_full。）
    """
    if recheck:
        return False
    return bool(explicit_full)


def pool_name_hints(script_text):
    """从 Script.js 源码还原地区池命名线索：(PREFER 代码列表, 代码→中文名, 池名后缀)

    命令行展示顺序要与配置生成用同一份名单；旧版脚本没有后缀声明时返回空串，
    调用方按裸名处理。
    """
    text = script_text or ""
    alias = {}
    m = re.search(r"var REGION_NAME = \{(.*?)\};", text, re.S)
    if m:
        for cc, name in re.findall(r'(\w{2}):\s*"([^"]+)"', m.group(1)):
            alias[cc] = name
    prefer = []
    m = re.search(r"var PREFER = \[(.*?)\];", text, re.S)
    if m:
        prefer = re.findall(r'"(\w{2})"', m.group(1))
    m = re.search(r'var POOL_SUFFIX = "([^"]+)";', text)
    suffix = m.group(1) if m else ""
    return prefer, alias, suffix


def region_stats(script_text, alias, suffix, alive=None):
    """按地区池名统计实测节点数与首次出现顺序：{池名: (节点数, 首次序号)}

    与 Script.js 的 byRegion 同源：跳过落地页节点；给了 alive 时还跳过
    已不在订阅中的条目。供命令行按同一份地区排序展示池列表。
    """
    stats = {}
    for idx, (name, (cc, _ms)) in enumerate(parse_manifest(script_text).items()):
        if is_junk(name):
            continue
        if alive is not None and name not in alive:
            continue
        key = alias.get(cc, cc) + suffix
        if key not in stats:
            stats[key] = [0, idx]
        stats[key][0] += 1
    return stats
