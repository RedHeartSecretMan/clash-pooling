// 分组与规则的规格测试
// 缝：Script.js 的 main(config) —— 输入合成 config + 受控 VERIFIED 清单，断言产出的代理组
//
// 默认读取线上部署的 Script.js（验证真正在跑的那份）；该文件不存在时回落到
// 仓库里的 clash/Script.js，因此新机器首次安装也能跑测试。
// 可用 CLASH_SCRIPT=<路径> 指向其他副本。
const fs = require("fs");
const path = require("path");

const APP_DIR = "io.github.clash-verge-rev.clash-verge-rev";

function deployedScript() {
  if (process.platform === "win32") {
    return path.join(process.env.APPDATA || "", APP_DIR, "profiles", "Script.js");
  }
  if (process.platform === "linux") {
    return path.join(process.env.XDG_DATA_HOME || path.join(process.env.HOME || "", ".local/share"), APP_DIR, "profiles", "Script.js");
  }
  return path.join(process.env.HOME || "", "Library/Application Support", APP_DIR, "profiles", "Script.js");
}

const SCRIPT_PATH =
  process.env.CLASH_SCRIPT ||
  (fs.existsSync(deployedScript()) ? deployedScript() : path.join(__dirname, "..", "clash", "Script.js"));

// 造一批节点：每个地区 4 个（够建池），外加 2 个池外的加拿大节点和 1 个落地页
function makeProxies() {
  const p = [];
  const regions = { HK: "香港池", SG: "新加坡池", TW: "台湾池", JP: "日本池", US: "美国池", IN: "印度池", AU: "澳大利亚池" };
  for (const [cc, zh] of Object.entries(regions)) {
    for (let i = 1; i <= 4; i++) p.push({ name: `${zh} T${i}`, cc });
  }
  p.push({ name: "加拿大 T1", cc: "CA" });
  p.push({ name: "加拿大 T2", cc: "CA" });
  p.push({ name: "加拿大 死节点", cc: "CA" });   // 无实测记录，应被排除
  p.push({ name: "1 官网 http://jump.example", cc: "CA" });
  return p;
}

const PROXIES = makeProxies();

const VERIFIED_FIXTURE = {};
const lat = { HK: 200, SG: 700, TW: 750, IN: 900, AU: 1000, US: 1100, JP: 1500, CA: 3000 };
for (const p of PROXIES) {
  if (p.name.includes("官网")) continue;      // 落地页从未被验证
  if (p.name.includes("死节点")) continue;    // 探测失败，无记录
  // 确定性延迟：同一夹具每次跑结果一致，避免测试随机失败
  VERIFIED_FIXTURE[p.name] = [p.cc, lat[p.cc] + (p.name.length % 5)];
}

function loadScriptWithManifest(manifest) {
  const src = fs.readFileSync(SCRIPT_PATH, "utf8");
  const fixture = "var VERIFIED = " + JSON.stringify(manifest) + ";";
  const replaced = src.replace(
    /\/\/ >>> VERIFIED-EXITS[\s\S]*?\/\/ <<< VERIFIED-EXITS/,
    "// >>> VERIFIED-EXITS\n" + fixture + "\n// <<< VERIFIED-EXITS"
  );
  if (replaced === src) throw new Error("Script.js 里找不到 VERIFIED-EXITS 标记块");
  const mod = { exports: {} };
  new Function("module", "exports", replaced + "\nmodule.exports = main;")(mod, mod.exports);
  return mod.exports;
}

function buildGroups(manifest = VERIFIED_FIXTURE, proxies = PROXIES) {
  const main = loadScriptWithManifest(manifest);
  const config = { proxies: proxies.slice(), rules: ["MATCH,某不存在的组"], "proxy-groups": [] };
  const out = main(config, "test");
  const names = out["proxy-groups"].map((g) => g.name);
  // byName 会静默折叠重复组名，先在这里把重复挡住
  assert(new Set(names).size === names.length, "生成的组名有重复：" + JSON.stringify(names));
  const nodeNames = new Set(out.proxies.map((p) => p.name));
  for (const n of names) assert(!nodeNames.has(n), `组名 ${n} 与节点重名`);
  const byName = {};
  for (const g of out["proxy-groups"]) byName[g.name] = g;
  return { config: out, groups: byName, order: Object.keys(byName) };
}

function membersOf(groups, name) {
  const g = groups[name];
  if (!g) return [];
  return g.proxies || [];
}

let failed = 0;
const results = [];
function check(name, fn) {
  try {
    fn();
    results.push([true, name]);
  } catch (e) {
    failed++;
    results.push([false, name, e.message]);
  }
}
function assert(c, m) {
  if (!c) throw new Error(m);
}

const built = buildGroups();
const { groups, order } = built;
const RULES = built.config.rules;          // 本地规则 + 测试用的 1 条机场规则
const M = (n) => membersOf(groups, n);

// 1. 服务组恰好三个
check("服务组是 AI / 通用 / 其他，且没有旧的影音/亚太/美国", () => {
  for (const n of ["AI", "通用", "其他"]) assert(groups[n], `缺少服务组 ${n}`);
  for (const n of ["影音", "亚太", "手动"]) assert(!groups[n], `不应存在旧组 ${n}`);
});

// 2. AI 组不含香港
check("AI 组不含香港池", () => {
  assert(!M("AI").includes("香港池"), "AI 组里出现了香港池：" + JSON.stringify(M("AI")));
});

// 3. AI 组按延迟排序（新加坡应排在台湾/日本/美国前面）
check("AI 组成员按实测延迟排序", () => {
  const m = M("AI").filter((x) => x !== "其他" && x !== "DIRECT" && x !== "REJECT");
  assert(m[0] === "新加坡池", "AI 组首个地区池应为新加坡池，实际：" + JSON.stringify(m));
});

// 4. 通用组首个是延迟最低的池
check("通用组首个是延迟最低的池", () => {
  assert(M("通用")[0] === "香港池", "通用组首个应为延迟最低的池：" + JSON.stringify(M("通用")));
});

// 5. 地区池按出口建，且成员出口一致
check("每个地区池的成员出口都一致", () => {
  const regions = { 香港池: "HK", 新加坡池: "SG", 台湾池: "TW", 日本池: "JP", 美国池: "US", 印度池: "IN", 澳大利亚池: "AU" };
  for (const [pool, cc] of Object.entries(regions)) {
    const g = groups[pool];
    assert(g, `缺少地区池 ${pool}`);
    assert(g.type === "url-test", `${pool} 应为 url-test，实际 ${g.type}`);
    for (const n of g.proxies) {
      assert(VERIFIED_FIXTURE[n][0] === cc, `${pool} 里混入了出口 ${VERIFIED_FIXTURE[n][0]} 的 ${n}`);
    }
  }
});

// 6. 节点数不足 3 的地区不建池
check("只有 2 个节点的地区不建池", () => {
  assert(!groups["加拿大池"], "加拿大只有 2 个验证节点，不应建池");
});

// 7. 其他组收纳池外节点
check("其他组收纳池外节点且不含池成员", () => {
  const m = M("其他");
  assert(m.includes("加拿大 T1"), "其他组缺少池外的加拿大节点");
  for (const n of m) {
    assert(!["香港池", "新加坡池", "台湾池", "日本池", "美国池", "印度池", "澳大利亚池"]
      .some((p) => (groups[p].proxies || []).includes(n)), `其他组混入了池成员 ${n}`);
  }
});

// 7b. 没有实测记录的节点不出现在任何组
check("未验证的节点不出现在任何组", () => {
  for (const [n, g] of Object.entries(groups)) {
    assert(!(g.proxies || []).includes("加拿大 死节点"), `${n} 里出现了未验证节点`);
  }
});

// 8. 落地页被过滤
check("落地页节点不出现在任何组", () => {
  for (const [n, g] of Object.entries(groups)) {
    assert(!(g.proxies || []).includes("1 官网 http://jump.example"), `${n} 里出现了落地页节点`);
  }
});

// 9. 规则目标都存在
check("所有规则目标都是已知组或内置出站", () => {
  const known = new Set(Object.keys(groups));
  known.add("DIRECT");
  known.add("REJECT");
  for (const r of RULES) {
    const parts = String(r).split(",");
    let i = parts.length - 1;
    if (parts[i] === "no-resolve" || parts[i] === "src") i--;
    assert(known.has(parts[i]), "规则目标不存在：" + r);
  }
});

// 10. 规则数量与分布（源文件里的本地规则 + 测试用的 1 条机场规则）
function localRuleCount() {
  const src = fs.readFileSync(SCRIPT_PATH, "utf8");
  const count = (name) => {
    const m = src.match(new RegExp("var " + name + " = \\[([\\s\\S]*?)\\n\\];"));
    return m ? (m[1].match(/^\s*"/gm) || []).length : 0;
  };
  return count("LOCAL_RULES") + count("LOCAL_RULES_EXTRA");
}

check("本地规则数量与源文件一致，目标只落在 AI/通用/DIRECT/REJECT", () => {
  const expected = localRuleCount() + 1;   // +1 是测试注入的机场规则
  assert(RULES.length === expected, "应为 " + expected + " 条，实际 " + RULES.length);
  const targets = new Set(RULES.slice(0, expected - 1).map((r) => String(r).split(",").pop()));
  for (const t of targets) assert(["AI", "通用", "DIRECT", "REJECT"].includes(t), "意外的规则目标：" + t);
});

// 10b. 机场规则里不认识的组名兜底到「通用」
check("机场规则的未知目标兜底到通用组", () => {
  const last = String(RULES[RULES.length - 1]);
  assert(last.endsWith(",通用"), "未知目标应兜底到通用，实际：" + last);
});

// 10c. 机场组名映射：已知表 + 语义兜底
check("机场组名按语义映射到对应组", () => {
  const main = loadScriptWithManifest(VERIFIED_FIXTURE);
  const airportRules = [
    "DOMAIN-SUFFIX,a.example,🇺🇸 美国节点",
    "DOMAIN-SUFFIX,b.example,🇯🇵 日本专线",
    "DOMAIN-SUFFIX,c.example,🛑 广告拦截",
    "DOMAIN-SUFFIX,d.example,🏠 国内直连",
    "DOMAIN-SUFFIX,e.example,🎬 流媒体",
    "MATCH,🐟 兜底",
  ];
  const out = main({ proxies: PROXIES.slice(), rules: airportRules.slice(), "proxy-groups": [] }, "t");
  const mapped = out.rules.slice(-airportRules.length).map((r) => r.split(",").pop());
  assert(mapped[0] === "美国池", "美国节点应映射到美国池，实际 " + mapped[0]);
  assert(mapped[1] === "日本池", "日本专线应映射到日本池，实际 " + mapped[1]);
  assert(mapped[2] === "REJECT", "广告拦截应映射到 REJECT，实际 " + mapped[2]);
  assert(mapped[3] === "DIRECT", "国内直连应映射到 DIRECT，实际 " + mapped[3]);
  assert(mapped[4] === "通用", "流媒体应回落通用，实际 " + mapped[4]);
  assert(mapped[5] === "通用", "兜底组应回落通用，实际 " + mapped[5]);
});

// 10d. 规则顺序：更具体的 Google 规则必须排在 google.com 之前
check("Google 例外与遥测拦截早于 google.com 兜底", () => {
  const main = loadScriptWithManifest(VERIFIED_FIXTURE);
  const out = main({ proxies: PROXIES.slice(), rules: [], "proxy-groups": [] }, "t");
  const idx = (pred) => out.rules.findIndex(pred);
  const generic = idx((r) => r === "DOMAIN-SUFFIX,google.com,通用");
  assert(generic > 0, "找不到 google.com 规则");
  for (const payload of ["dl.google.com", "clients.l.google.com", "maps.l.google.com", "khm.l.google.com"]) {
    const at = out.rules.findIndex((r) => r.includes("," + payload + ","));
    assert(at >= 0, payload + " 规则缺失");
    assert(at < generic, payload + " 规则应排在 google.com 之前");
  }
});

// 10f. Cursor 的 Agent API 在 cursor.sh，不是 cursor.com；漏掉会落到 MATCH/通用
check("Cursor API 域名走 AI 组", () => {
  const rule = "DOMAIN-SUFFIX,cursor.sh,AI";
  const at = RULES.indexOf(rule);
  assert(at >= 0, "缺少 " + rule);
  const fallback = RULES.findIndex((r) => String(r).startsWith("MATCH,"));
  assert(fallback < 0 || at < fallback, rule + " 必须排在 MATCH 之前");
});

// 10g. 各 AI 服务有 GEOSITE 宽泛兜底，避免只覆盖手写域名
check("AI 服务有 GEOSITE 宽泛兜底", () => {
  for (const rule of [
    "GEOSITE,openai,AI",
    "GEOSITE,anthropic,AI",
    "GEOSITE,google-gemini,AI",
    "GEOSITE,cursor,AI",
    "GEOSITE,perplexity,AI",
    "GEOSITE,github-copilot,AI",
    "GEOSITE,huggingface,AI",
  ]) {
    assert(RULES.includes(rule), "缺少 " + rule);
  }
});

// 10h. Gemini 网页规则必须先于宽泛 GEOSITE，否则网页版会被切到 AI 组
check("Google Gemini 宽泛兜底不覆盖网页例外", () => {
  const web = RULES.indexOf("DOMAIN-SUFFIX,gemini.google.com,通用");
  const broad = RULES.indexOf("GEOSITE,google-gemini,AI");
  assert(web >= 0, "缺少 gemini.google.com 通用规则");
  assert(broad > web, "GEOSITE,google-gemini 应排在 gemini.google.com 通用规则之后");
});

// 10i. cloudcode-pa 是宽泛关键字，排在该组精确域名之后
check("cloudcode-pa 关键字规则排在该组末尾", () => {
  const exact = [
    "DOMAIN-SUFFIX,daily-cloudcode-pa.googleapis.com,AI",
    "DOMAIN-SUFFIX,antigravity.google,AI",
    "DOMAIN-SUFFIX,cloudaicompanion.googleapis.com,AI",
  ];
  const keyword = RULES.indexOf("DOMAIN-KEYWORD,cloudcode-pa,AI");
  assert(keyword >= 0, "缺少 cloudcode-pa 关键字规则");
  assert(keyword > Math.max(...exact.map((r) => RULES.indexOf(r))), "cloudcode-pa 关键字应排在精确域名之后");
});

// 10e. 落地页即使误入清单（例如旧版本写入），也不进池也不进「其他」
check("落地页即使出现在清单里也不进任何组", () => {
  const manifest = Object.assign({}, VERIFIED_FIXTURE);
  for (let i = 1; i <= 4; i++) manifest[`1 官网 http://jump.example`] = ["HK", 90 + i];
  const { groups } = buildGroups(manifest);
  for (const name of Object.keys(groups)) {
    const members = groups[name].proxies || [];
    assert(!members.includes("1 官网 http://jump.example"), `${name} 里出现了落地页节点`);
  }
});

// 10f. 未在 PREFER 中的地区也要有中文名
check("动态发现的新地区也用「池」后缀", () => {
  // 池数量上限 8，这里只加一个地区，确保它落在上限内
  const extra = ["韩国 X1", "韩国 X2", "韩国 X3"];
  const manifest = Object.assign({}, VERIFIED_FIXTURE);
  extra.forEach((n, i) => { manifest[n] = ["KR", 500 + i]; });
  const proxies = PROXIES.concat(extra.map((n) => ({ name: n })));
  const { groups } = buildGroups(manifest, proxies);
  assert(groups["韩国池"], "动态新地区也应生成「韩国池」");
  assert(!groups["韩国"], "不应再有裸地区名组");
  assert(!groups["KR池"], "对照表里有中文名时不用代码名");
});

// 10j. 组名统一走 uniqueName：地区池以「池」结尾，服务组用短名字；
//      被订阅节点占用时按 X → XYZ → XYZ 年月日 递进升级，仍冲突再加序号。
check("生成的组名互不重复，且地区池都以「池」结尾", () => {
  const { config } = buildGroups();
  const groups = config["proxy-groups"];
  const names = groups.map((g) => g.name);
  assert(new Set(names).size === names.length, "生成的组名有重复");
  const proxyNames = new Set(config.proxies.map((p) => p.name));
  for (const n of names) assert(!proxyNames.has(n), `组名 ${n} 与节点重名`);
  const pools = groups.filter((g) => g.type === "url-test");
  assert(pools.length > 0, "应生成地区池");
  for (const g of pools) assert(g.name.endsWith("池"), `地区池 ${g.name} 应以「池」结尾`);
});

check("订阅出现裸地区名节点时池名仍是固定后缀", () => {
  const collision = PROXIES.concat([{ name: "美国" }, { name: "AI" }]);
  const manifest = Object.assign({}, VERIFIED_FIXTURE);
  manifest["美国"] = ["US", 800];
  manifest["AI"] = ["US", 810];
  const { config, groups } = buildGroups(manifest, collision);
  const proxyNames = new Set(config.proxies.map((p) => p.name));
  assert(groups["美国池"], "美国池应保持固定名字");
  assert(groups["AI X"], "服务组也走同一套避让");
  for (const n of Object.keys(groups)) assert(!proxyNames.has(n), `组名 ${n} 与节点重名`);
  for (const member of groups["美国池"].proxies) {
    assert(manifest[member] && manifest[member][0] === "US", `美国池混入了非美国出口节点 ${member}`);
  }
});

check("冲突按 X → XYZ → XYZ 年月日 递进升级", () => {
  const main = loadScriptWithManifest(VERIFIED_FIXTURE);
  const levels = [
    ["美国池"],
    ["美国池", "美国池 X"],
    ["美国池", "美国池 X", "美国池 XYZ"],
  ];
  const expected = ["美国池 X", "美国池 XYZ", null];
  levels.forEach((extra, i) => {
    const out = main({
      proxies: PROXIES.concat(extra.map((n) => ({ name: n }))),
      rules: ["DOMAIN-SUFFIX,a.example,🇺🇸 美国节点"],
      "proxy-groups": []
    }, "t");
    const names = out["proxy-groups"].map((g) => g.name);
    const us = names.find((n) => n.indexOf("美国池") === 0);
    if (expected[i]) assert(us === expected[i], `第 ${i + 1} 层冲突应为 ${expected[i]}，实际 ${us}`);
    else assert(/^美国池 XYZ \d{8}/.test(us || ""), `第 3 层冲突应加 XYZ + 年月日，实际 ${us}`);
    const known = new Set(names.concat(["DIRECT", "REJECT"]));
    for (const r of out.rules) {
      const parts = String(r).split(",");
      let k = parts.length - 1;
      if (parts[k] === "no-resolve" || parts[k] === "src") k--;
      assert(known.has(parts[k]), "规则目标不存在：" + r);
    }
  });
});

check("AI 与通用成员顺序一致，只差香港池", () => {
  const strip = (g) => M(g).filter((x) => x !== "其他" && x !== "DIRECT" && x !== "REJECT");
  const ai = strip("AI"), general = strip("通用");
  assert(!ai.includes("香港池"), "AI 不应含香港池");
  assert(general.includes("香港池"), "通用应含香港池");
  assert(JSON.stringify(general.filter((n) => n !== "香港池")) === JSON.stringify(ai),
    "去掉香港后两组顺序应完全一致");
});

check("池外节点按实测出口分桶，桶内按延迟升序", () => {
  // 让 US 节点超过 POOL_CAP(10)，制造真实的「池溢出」场景
  const extra = [];
  for (let i = 1; i <= 8; i++) extra.push("专线 " + i);
  const manifest = Object.assign({}, VERIFIED_FIXTURE);
  extra.forEach((n, i) => { manifest[n] = ["US", 100 + i]; });
  manifest["VIP 慢 A"] = ["US", 5000];   // 名字里没有任何地区名，且延迟最高
  manifest["VIP 慢 B"] = ["US", 6000];
  const names = extra.concat(["VIP 慢 A", "VIP 慢 B"]);
  const proxies = PROXIES.concat(names.map((n) => ({ name: n })));
  const { groups } = buildGroups(manifest, proxies);
  const m = groups["其他"].proxies.filter((x) => x !== "DIRECT" && x !== "REJECT");
  assert(m.includes("VIP 慢 A") && m.includes("VIP 慢 B"), "池外节点应进「其他」，实际：" + JSON.stringify(m));
  assert(m.indexOf("VIP 慢 A") < m.indexOf("VIP 慢 B"), "桶内应按实测延迟升序");
  assert(m.indexOf("VIP 慢 B") < m.indexOf("加拿大 T1"),
    "US 桶排在未列出的 CA 桶之前，即使桶内节点延迟更高");
});

check("节点名误导时仍按实测出口分桶", () => {
  const extra = ["加拿大 伪装"];   // 名字像加拿大，实测出口却是 US
  const manifest = Object.assign({}, VERIFIED_FIXTURE);
  manifest["加拿大 伪装"] = ["US", 100];
  const proxies = PROXIES.concat(extra.map((n) => ({ name: n })));
  const { groups } = buildGroups(manifest, proxies);
  const m = groups["其他"].proxies.filter((x) => x !== "DIRECT" && x !== "REJECT");
  assert(m.indexOf("加拿大 伪装") < m.indexOf("加拿大 T1"),
    "应归到 US 桶，而不是按名字和加拿大节点挤在同一桶的末尾");
});

check("对照表外的地区代码也用「池」后缀", () => {
  // KR 在对照表里，用一个确实查不到的代码验证 (REGION_NAME[ccode] || ccode) + 后缀
  const manifest = {
    "QQ A1": ["QQ", 100], "QQ A2": ["QQ", 200], "QQ A3": ["QQ", 300],
    "香港 A1": ["HK", 400], "香港 A2": ["HK", 500], "香港 A3": ["HK", 600],
  };
  const proxies = Object.keys(manifest).map((n) => ({ name: n }));
  const { groups } = buildGroups(manifest, proxies);
  assert(groups["QQ池"], "表外代码应生成「QQ池」，而不是裸代码名");
  assert(!groups["QQ"], "不应出现裸代码名 QQ");
});

check("四级冲突加序号，三个服务组同时避让", () => {
  const d = new Date();
  const pad = (n) => (n < 10 ? "0" : "") + n;
  const stamp = "" + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate());
  const main = loadScriptWithManifest(VERIFIED_FIXTURE);
  const clash = ["美国池", "美国池 X", "美国池 XYZ", "美国池 XYZ " + stamp,
                 "AI", "通用", "其他"];
  const out = main({
    proxies: PROXIES.concat(clash.map((n) => ({ name: n }))),
    rules: ["MATCH,某组"],
    "proxy-groups": []
  }, "t");
  const names = out["proxy-groups"].map((g) => g.name);
  assert(names.includes("美国池 XYZ " + stamp + " 2"), "第四层冲突应加序号");
  for (const base of ["AI", "通用", "其他"]) {
    assert(names.includes(base + " X"), `${base} 也应走同一套避让`);
  }
  assert(new Set(names).size === names.length, "生成的组名有重复");
});

// 11. 组顺序
check("组顺序为 AI、通用、其他、地区池", () => {
  assert(order[0] === "AI" && order[1] === "通用" && order[2] === "其他", "组顺序不对：" + JSON.stringify(order.slice(0, 3)));
});

for (const [ok, name, msg] of results) {
  if (ok) console.log("  ✓ " + name);
  else console.log("  ✗ " + name + "\n      " + msg);
}
console.log(`\n  ${results.length - failed}/${results.length} 通过`);
process.exit(failed ? 1 : 0);
