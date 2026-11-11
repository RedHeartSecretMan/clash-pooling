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
  return path.join(process.env.HOME || "", "Library/Application Support", APP_DIR, "profiles", "Script.js");
}

const SCRIPT_PATH =
  process.env.CLASH_SCRIPT ||
  (fs.existsSync(deployedScript()) ? deployedScript() : path.join(__dirname, "..", "clash", "Script.js"));

// 造一批节点：每个地区 4 个（够建池），外加 2 个池外的加拿大节点和 1 个落地页
function makeProxies() {
  const p = [];
  const regions = { HK: "香港", SG: "新加坡", TW: "台湾", JP: "日本", US: "美国", IN: "印度", AU: "澳大利亚" };
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
const RULES = built.config.rules;          // 本地 70 条 + 测试用的 1 条机场规则
const M = (n) => membersOf(groups, n);

// 1. 服务组恰好三个
check("服务组是 AI / 通用 / 其他，且没有旧的影音/亚太/美国", () => {
  for (const n of ["AI", "通用", "其他"]) assert(groups[n], `缺少服务组 ${n}`);
  for (const n of ["影音", "亚太", "手动"]) assert(!groups[n], `不应存在旧组 ${n}`);
});

// 2. AI 组不含香港
check("AI 组不含香港池", () => {
  assert(!M("AI").includes("香港"), "AI 组里出现了香港：" + JSON.stringify(M("AI")));
});

// 3. AI 组按延迟排序（新加坡应排在台湾/日本/美国前面）
check("AI 组成员按实测延迟排序", () => {
  const m = M("AI").filter((x) => x !== "其他" && x !== "DIRECT" && x !== "REJECT");
  assert(m[0] === "新加坡", "AI 组首个地区池应为新加坡，实际：" + JSON.stringify(m));
});

// 4. 通用组香港排第一
check("通用组以香港开头", () => {
  assert(M("通用")[0] === "香港", "通用组首个应为香港：" + JSON.stringify(M("通用")));
});

// 5. 地区池按出口建，且成员出口一致
check("每个地区池的成员出口都一致", () => {
  const regions = { 香港: "HK", 新加坡: "SG", 台湾: "TW", 日本: "JP", 美国: "US", 印度: "IN", 澳大利亚: "AU" };
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
  assert(!groups["加拿大"], "加拿大只有 2 个验证节点，不应建池");
});

// 7. 其他组收纳池外节点
check("其他组收纳池外节点且不含池成员", () => {
  const m = M("其他");
  assert(m.includes("加拿大 T1"), "其他组缺少池外的加拿大节点");
  for (const n of m) {
    assert(!["香港", "新加坡", "台湾", "日本", "美国", "印度", "澳大利亚"]
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
  assert(mapped[0] === "美国", "美国节点应映射到美国池，实际 " + mapped[0]);
  assert(mapped[1] === "日本", "日本专线应映射到日本池，实际 " + mapped[1]);
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
