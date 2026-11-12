"""各子命令的实现。"""

import json
import os
import unicodedata
import re
import shutil
import time

from . import api, manifest, platform, probe
from .measure import measure

TEST_URLS = {
    "AI": "https://chatgpt.com/cdn-cgi/trace",
    "通用": "https://www.cloudflare.com/cdn-cgi/trace",
    "其他": "https://www.cloudflare.com/cdn-cgi/trace",
}


# ------------------------------------------------------------------ 查看

def _pad(text, width):
    """按显示宽度补空格：中文占两列，ljust 按字符数会错位"""
    used = sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)
    return text + " " * max(0, width - used)


def pool_order(pools):
    """地区池的展示顺序：按 Script.js 的 PREFER 名单，未列出的排在后面

    接口返回的键序不可靠（按字典序），所以从脚本源码里读推荐顺序。
    """
    try:
        text = open(platform.script_path(), encoding="utf-8").read()
        alias_block = re.search(r"var REGION_NAME = \{(.*?)\};", text, re.S)
        prefer_block = re.search(r"var PREFER = \[(.*?)\];", text, re.S)
        alias = {}
        if alias_block:
            for cc, name in re.findall(r'(\w{2}):\s*"([^"]+)"', alias_block.group(1)):
                alias[cc] = name
        order = []
        if prefer_block:
            for cc in re.findall(r'"(\w{2})"', prefer_block.group(1)):
                order.append(alias.get(cc, cc))
        return [n for n in order if n in pools] + [n for n in pools if n not in order]
    except OSError:
        pass
    return list(pools)


def _chain(all_proxies, name):
    path = [name]
    for _ in range(4):
        nxt = all_proxies.get(name, {}).get("now")
        if not nxt or nxt in ("DIRECT", "REJECT"):
            break
        path.append(nxt)
        name = nxt
    return path


def status():
    proxies = api.proxies()
    services = api.service_groups(proxies)
    pools = pool_order(api.pool_groups(proxies))
    print("  " + _pad("服务分组", 14) + "链路")
    print("  " + "-" * 66)
    for name in services:
        chain = _chain(proxies, name)
        print("  " + _pad(name, 14) + (" -> ".join(chain[1:]) or str(proxies[name].get("now"))))
    print()
    print("  " + _pad("节点池", 14) + _pad("当前节点", 32) + "备选")
    print("  " + "-" * 66)
    for name in pools:
        value = proxies.get(name, {})
        print("  " + _pad(name, 14) + _pad(str(value.get("now")), 32)
              + str(len(value.get("all", []))) + " 个")


def regions():
    proxies = api.proxies()
    services = api.service_groups(proxies)
    pools = pool_order(api.pool_groups(proxies))
    print("  " + _pad("地区组", 14) + _pad("当前节点", 30) + "备选数")
    print("  " + "-" * 58)
    for name in services + pools:
        value = proxies.get(name, {})
        print("  " + _pad(name, 14) + _pad(str(value.get("now")), 30)
              + str(len(value.get("all", []))))
    print()
    labels = {"URLTest": "url-test 自动选最快", "Fallback": "fallback 取第一个可用",
              "Selector": "select 手动选择"}
    print("  节点池：" + "、".join("%s %s" % (n, labels.get(proxies[n]["type"], proxies[n]["type"]))
                                for n in pools))
    print("  其他：池外且实测通过的节点，select 手动挑选")
    print('  要钉死某个节点：clashctl use <服务组> "其他"，再 use "其他" <节点名>')


def nodes(target=""):
    proxies = api.proxies()
    if not target:
        print("  可用组：")
        for name in api.service_groups(proxies) + api.pool_groups(proxies):
            print("   - " + name)
        return
    value = proxies.get(target)
    if not value:
        print("  没有名为 %s 的组" % target)
        return
    members = value.get("all", [])
    print("  %s：当前 %s，共 %d 个" % (target, value.get("now"), len(members)))
    for index, name in enumerate(members[:40], 1):
        print("   %2d. %s%s" % (index, name, "   <- 当前" if name == value.get("now") else ""))
    if len(members) > 40:
        print("   ... 其余 %d 个省略" % (len(members) - 40))


def test(services=None):
    proxies = api.proxies()
    targets = services or api.service_groups(proxies)
    port = platform.mixed_port()
    for name in targets:
        url = TEST_URLS.get(name, TEST_URLS["通用"])
        values = []
        for _ in range(3):
            try:
                _, _, ttfb = probe.fetch(url, proxy=("127.0.0.1", port), timeout=20)
                values.append(ttfb)
            except Exception:
                pass
        if values:
            values.sort()
            print("  " + _pad(name, 14) + " %6.2f s   %s" % (values[len(values) // 2] / 1000,
                                            [round(v / 1000, 2) for v in values]))
        else:
            print("  " + _pad(name, 14) + "   失败     （全部超时或不可达）")


def use(service, target):
    if not api.select(service, target):
        raise SystemExit("切换失败：%s -> %s" % (service, target))
    print("  %s -> %s" % (service, target))


# ------------------------------------------------------------------ 核验

def count_local_rules(text):
    """脚本里本地规则的条数：注入的 LOCAL_RULES_EXTRA + LOCAL_RULES（运行时私有规则排最前）"""
    total = 0
    for name in ("LOCAL_RULES", "LOCAL_RULES_EXTRA"):
        block = re.search(r"var %s = \[(.*?)\n\];" % name, text, re.S)
        if block:
            total += len(re.findall(r'^\s*"', block.group(1), re.M))
    return total


def _refresh(full=False, recheck=None):
    """核验入口：同一时刻只允许一个核验进程"""
    lock = platform.acquire_lock("refresh")
    if not lock:
        print("  已有核验在跑，本次跳过")
        return None
    try:
        return _refresh_locked(full=full, recheck=recheck)
    finally:
        platform.release_lock(lock)


def _refresh_locked(full=False, recheck=None):
    names = [n for n in api.node_names(api.proxies()) if not manifest.is_junk(n)]
    text = open(platform.script_path(), encoding="utf-8").read()
    old = manifest.parse_manifest(text)
    if not full and not recheck and _subscription_changed():
        print("  订阅比上次核验新，旧标签可能已失效 → 本次全量重测")
        full = True
    full = manifest.resolve_full(full, recheck)
    if recheck:
        todo = [n for n in names if recheck in n]
        print("  抽查模式：只重测名字含「%s」的 %d 个节点" % (recheck, len(todo)))
    else:
        todo = manifest.compute_todo(names, old, full=full)
    if not todo:
        print("  清单已覆盖全部 %d 个节点，无需重测（强制全量加 --full）" % len(names))
        return False
    print("  待测 %d 个（清单已有 %d 个，跳过 %d 个）\n" % (len(todo), len(old), len(names) - len(todo)))
    results, truncated = measure(todo, fast=True)
    ok = sum(1 for value in results.values() if value[0])
    alive = set(names)
    merged = {k: v for k, v in old.items() if k in alive and k not in results}
    merged.update({k: v for k, v in results.items() if v[0]})
    print("\n  本次有响应 %d / %d，清单合计 %d 条" % (ok, len(results), len(merged)))
    if truncated:
        full = False
        print("  注意：本次未跑完，订阅版本戳不推进（下次仍会补测）")
    written, changed = _write_manifest(merged, text)
    if not written:
        return False
    _write_marker(len(merged), len(names), full)
    if changed:
        print("  清单已变化，下一步：退出并重新打开 Clash Verge 使配置生效")
    return changed


def _write_manifest(items, current):
    """写回清单；返回 (是否写入, 内容是否变化)。current 是调用方已读到的脚本内容。"""
    out = manifest.replace_block(current, items)
    if out is None:
        print("  警告：脚本里没找到 VERIFIED-EXITS 标记块，未写入")
        return False, False
    open(platform.script_path(), "w", encoding="utf-8").write(out)
    print("  已写入 %d 个节点的实测结果 → %s" % (len(items), platform.script_path()))
    return True, out != current


def _subscription_changed():
    prof = platform.profile_file()
    if not prof or not os.path.exists(prof):
        return False
    try:
        data = json.load(open(platform.marker_path(), encoding="utf-8"))
    except Exception:
        return True
    return manifest.needs_full_refresh(os.path.getmtime(prof), data.get("profile_mtime", 0))


def _write_marker(verified, total, full):
    marker = platform.marker_path()
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    try:
        old = json.load(open(marker, encoding="utf-8"))
    except Exception:
        old = {}
    prof = platform.profile_file()
    mtime = int(os.path.getmtime(prof)) if prof and os.path.exists(prof) else 0
    data = {
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "profile_mtime": mtime if full else int(old.get("profile_mtime", 0)),
        "verified_count": verified,
        "node_count": total,
        "last_full": full,
    }
    open(marker, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False))


def exit_check(which=None):
    """核验池内节点的出口是否符合预期"""
    proxies = api.proxies()
    pools = pool_order(api.pool_groups(proxies))
    text = open(platform.script_path(), encoding="utf-8").read()
    verified = manifest.parse_manifest(text)
    expect = {}
    for pool in pools:
        ccs = {verified[n][0] for n in proxies[pool].get("all", []) if n in verified}
        expect[pool] = tuple(sorted(ccs))
    targets = pools if not which or which == "all" else [which]
    nodes = []
    for pool in targets:
        for node in proxies.get(pool, {}).get("all", []):
            if node not in nodes:
                nodes.append(node)
    if not nodes:
        print("  没有要检查的节点")
        return
    print("  检查 %d 个节点，启动临时实例测量\n" % len(nodes))
    results, _ = measure(nodes, fast=False)
    bad = 0
    for node in nodes:
        want = next((expect[p] for p in targets if node in proxies.get(p, {}).get("all", [])), ())
        cc, _ = results.get(node, ("", 0))   # 整轮超时被截断时该节点没有结果
        ok = cc in want
        bad += 0 if ok else 1
        print("  %-32s 出口=%-4s 期望=%-20s %s" % (node, cc or "失败", "/".join(want), "OK" if ok else "偏离"))
    print("\n  结论：%d/%d 符合预期%s" % (len(nodes) - bad, len(nodes), "" if bad == 0 else "，%d 个偏离" % bad))


# ------------------------------------------------------------------ 维护

def audit():
    text = open(platform.script_path(), encoding="utf-8").read()
    local_count = count_local_rules(text)
    if not local_count:
        raise SystemExit("无法从脚本里解析本地规则")
    rules = api.rules()
    local, airport = rules[:local_count], rules[local_count:]

    def matches(rule, domain):
        kind, payload = rule.get("type"), str(rule.get("payload", "")).lower()
        domain = domain.lower()
        if kind == "DomainSuffix":
            return domain == payload or domain.endswith("." + payload)
        if kind == "Domain":
            return domain == payload
        if kind == "DomainKeyword":
            return payload in domain
        return False

    shadow = []
    for index, rule in enumerate(airport, local_count):
        if rule.get("type") not in ("DomainSuffix", "Domain"):
            continue
        for one in local:
            if matches(one, str(rule.get("payload", ""))):
                if one.get("proxy") != rule.get("proxy"):
                    shadow.append((index + 1, rule.get("proxy"), rule.get("payload"), one.get("proxy")))
                break
    print("  本地规则 %d 条 | 机场规则 %d 条 | 合计 %d" % (local_count, len(airport), len(rules)))
    print()
    print("【1】本地规则吞掉机场规则（目标不同）: %d 条" % len(shadow))
    for row in shadow[:20]:
        print("      机场#%d %s (%s) ←被 本地 %s 抢先" % row)
    print("\n  结论：%s" % ("没有非预期的遮蔽，规则层次健康" if not shadow
                          else "上面列出的条目会让后置规则失效，确认是否为有意设计"))


def doctor():
    print("== 内核 ==")
    engine = None
    try:
        engine = api.version()
        print("  meta=%s version=%s" % (engine.get("meta"), engine.get("version")))
    except Exception as exc:
        print("  无法访问控制接口：%s" % exc)

    print("== 分组 ==")
    if engine is None:
        print("  跳过（控制接口不可用）")
    else:
        proxies = api.proxies()
        kinds = {}
        for value in proxies.values():
            kinds[value["type"]] = kinds.get(value["type"], 0) + 1
        print("  " + " | ".join("%s %d 个" % (k, kinds[k])
                                for k in ("Selector", "URLTest", "Fallback") if k in kinds))

    print("== 规则 ==")
    if engine is None:
        print("  跳过（控制接口不可用）")
    else:
        print("  %d 条" % len(api.rules()))
    print("== DNS（公司内网）==")
    _doctor_dns()
    print("== 系统代理 ==")
    _doctor_system_proxy()
    print("== 配置一致性 ==")
    print("  脚本：%s" % platform.script_path())
    print("  生成配置：%s" % platform.generated_config())
    kind, target, _ = platform.control()
    endpoint = target if kind == "unix" else "%s:%s" % target
    print("  控制端点：%s（%s）" % (endpoint, kind))


def _doctor_dns():
    def block_values(text, key):
        out, base = [], None
        for line in text.splitlines():
            if base is None:
                match = re.match(r"^(\s*)" + re.escape(key) + r":\s*$", line)
                if match:
                    base = len(match.group(1))
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            item = re.match(r"^\s+-\s+(\S.*)$", line)
            if item and indent >= base:
                out.append(item.group(1).strip().strip("'\""))
                continue
            break
        return out

    try:
        generated = open(platform.generated_config(), encoding="utf-8").read()
        merge_raw = open(platform.merge_path(), encoding="utf-8").read()
    except OSError as exc:
        print("  读不到配置：%s" % exc)
        return

    # 只看未注释的部分：示例写在注释里，不应当作已配置
    merge = "\n".join(line for line in merge_raw.splitlines()
                       if not line.strip().startswith("#"))
    if "dns:" not in merge:
        print("  未配置（使用订阅默认 DNS；需要自定义时参考 clash/Merge.yaml 的示例）")
        return

    want = block_values(merge, "fake-ip-filter")
    have = block_values(generated, "fake-ip-filter")
    checks = [
        ("fake-ip-filter 覆盖 Merge 的全部条目 (%d 个)" % len(want), set(want) <= set(have)),
        ("direct-nameserver: system", "system" in block_values(generated, "direct-nameserver")),
        ("direct-nameserver-follow-policy", "direct-nameserver-follow-policy: true" in generated),
    ]
    ips = sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", merge)))
    checks.append(("nameserver-policy 指定 DNS (%d 个)" % len(ips),
                   all(ip in generated for ip in ips) if ips else True))
    for label, ok in checks:
        print("  %s  %s" % ("OK  " if ok else "缺失", label))


def _doctor_system_proxy():
    """系统代理是否指向 Clash 的混合端口"""
    state = platform.system_proxy()
    if not state:
        print("  读不到系统代理设置（跳过）")
        return
    if not state.get("enabled"):
        print("  未开启（用 TUN 模式或只有部分应用走代理时属正常）")
        return
    expected = platform.mixed_port()
    port = state.get("port")
    ok = port == expected
    print("  %s  已开启，指向 %s:%s（Clash 混合端口 %d）"
          % ("OK  " if ok else "注意", state.get("host", ""), port, expected))


def backup():
    root = platform.config_root()
    dest = os.path.join(root, "backup-" + time.strftime("%Y%m%d-%H%M"))
    os.makedirs(dest, exist_ok=True)
    failed = 0
    for name in sorted(os.listdir(platform.profiles_dir())):
        src = os.path.join(platform.profiles_dir(), name)
        if os.path.isfile(src):
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                failed += 1
                print("  跳过 %s：%s" % (name, exc))
    for name in ("profiles.yaml", "clash-verge.yaml"):
        src = os.path.join(root, name)
        if os.path.exists(src):
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                failed += 1
                print("  跳过 %s：%s" % (name, exc))
    print("已备份到：%s%s" % (dest, "" if not failed else "（%d 个文件跳过）" % failed))


# ------------------------------------------------------------------ 同步

def project_root():
    """仓库根目录：环境变量 → 安装时写入的路径 → 从当前目录向上找"""
    env = os.environ.get("CLASH_POOLING_HOME")
    if env:
        return env
    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".project_root")
    if os.path.exists(marker):
        path = open(marker, encoding="utf-8-sig").read().strip()
        if path and os.path.isdir(path):
            return path
    cur = os.getcwd()
    for _ in range(6):
        if os.path.exists(os.path.join(cur, "clash", "Script.js")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ""


def sync():
    root = project_root()
    src_script = os.path.join(root, "clash", "Script.js")
    src_merge = os.path.join(root, "clash", "Merge.yaml")
    local_rules = os.path.join(root, "clash", "local", "rules.local.js")
    local_merge = os.path.join(root, "clash", "local", "Merge.yaml")
    for path in (src_script, src_merge):
        if not os.path.exists(path):
            raise SystemExit("找不到 %s" % path)

    source = open(src_script, encoding="utf-8").read()
    try:
        target = open(platform.script_path(), encoding="utf-8").read()
    except OSError:
        target = ""
    out = manifest.splice_from(source, target)

    if os.path.exists(local_rules):
        body = open(local_rules, encoding="utf-8").read().strip()
        if not body:
            print("  提示：clash/local/rules.local.js 为空，按未配置处理")
        elif "LOCAL_RULES_EXTRA" not in body:
            print("  警告：rules.local.js 里没有 LOCAL_RULES_EXTRA 声明，已跳过（否则脚本会引用未定义变量）")
        else:
            injected = manifest.replace_marked(
                out, "// >>> LOCAL-RULES-EXTRA", "// <<< LOCAL-RULES-EXTRA", body)
            if injected is None:
                print("  警告：脚本里没找到 LOCAL-RULES-EXTRA 标记块，本地规则未注入")
            else:
                out = injected
                print("  已注入本地规则：%s" % local_rules)

    open(platform.script_path(), "w", encoding="utf-8").write(out)
    print("  已同步 Script.js（保留清单 %d 条）" % len(manifest.parse_manifest(target)))

    if os.path.exists(local_merge) and open(local_merge, encoding="utf-8").read().strip():
        shutil.copy2(local_merge, platform.merge_path())
        print("  已同步 Merge.yaml（本地覆盖）")
    else:
        shutil.copy2(src_merge, platform.merge_path())
        print("  已同步 Merge.yaml")
    print("  下一步：退出并重新打开 Clash Verge 使配置生效")
