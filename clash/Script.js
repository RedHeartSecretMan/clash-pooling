// ===========================================================================
// Clash Verge 全局扩展脚本
// ===========================================================================
// 作用
//   对任何订阅统一重建代理分组，并把本地规则注入到机场规则之前。
//   放在全局扩展层，所以切换订阅、订阅更新都不会丢失这里的自定义。
//
// 分层
//   规则  →  服务组（AI / 通用 / 其他）  →  地区池（按实测出口地区）  →  节点
//
//   规则     决定域名去哪一类服务组
//   服务组   你在界面里切地区，AI / 通用 / 其他 三选一
//   地区池   按实测出口地区建池，池内 url-test 自动选最快节点
//
// 文件结构
//   LOCAL-RULES   本地规则
//   VERIFIED      节点实测清单，由 clashctl exit-check --refresh 写入，勿手改
//   main()        重建分组、重映射规则目标、注入本地规则
//
// 修改约定
//   VERIFIED 区块由工具维护，勿手改。
//   LOCAL-RULES 与 main() 生成逻辑都可修改；改动后跑 tests/run.sh，
//   再 clashctl sync 并退出重开 Clash Verge 使配置生效。
// ===========================================================================

// >>> LOCAL-RULES（本文件维护，改这里即可）
var LOCAL_RULES = [
  // --- 1. AI → AI 组 ---
  //     官方支持地区都不含香港，所以 AI 组本身不含香港池
  // OpenAI 系
  "DOMAIN-SUFFIX,chatgpt.com,AI",
  "DOMAIN-SUFFIX,openai.com,AI",
  "DOMAIN-SUFFIX,oaiusercontent.com,AI",
  "DOMAIN-SUFFIX,oaistatic.com,AI",
  "DOMAIN-SUFFIX,openai.azure.com,AI",
  "DOMAIN-SUFFIX,sora.com,AI",
  "GEOSITE,openai,AI",
  // Anthropic 系
  "DOMAIN-SUFFIX,anthropic.com,AI",
  "DOMAIN-SUFFIX,claude.ai,AI",
  "DOMAIN-SUFFIX,claude.com,AI",
  "GEOSITE,anthropic,AI",
  // Google AI 接口
  "DOMAIN-SUFFIX,generativelanguage.googleapis.com,AI",
  "DOMAIN-SUFFIX,aistudio.google.com,AI",
  "DOMAIN-SUFFIX,aiplatform.googleapis.com,AI",
  // Antigravity / Cloud Code
  "DOMAIN-SUFFIX,daily-cloudcode-pa.googleapis.com,AI",
  "DOMAIN-SUFFIX,antigravity.google,AI",
  "DOMAIN-SUFFIX,cloudaicompanion.googleapis.com,AI",
  "DOMAIN-KEYWORD,cloudcode-pa,AI",
  // 其它 AI 服务与杂项
  "DOMAIN-SUFFIX,perplexity.ai,AI",
  "DOMAIN-SUFFIX,x.ai,AI",
  "DOMAIN-SUFFIX,grok.com,AI",
  "DOMAIN-SUFFIX,copilot.microsoft.com,AI",
  "DOMAIN-SUFFIX,api.githubcopilot.com,AI",
  "DOMAIN-SUFFIX,huggingface.co,AI",
  "DOMAIN-SUFFIX,hf.co,AI",
  "DOMAIN-SUFFIX,openrouter.ai,AI",
  "DOMAIN-SUFFIX,poe.com,AI",
  "DOMAIN-SUFFIX,cursor.com,AI",
  "DOMAIN-SUFFIX,cursor.sh,AI",
  "DOMAIN-SUFFIX,midjourney.com,AI",
  "DOMAIN-SUFFIX,suno.com,AI",
  "GEOSITE,cursor,AI",
  "GEOSITE,perplexity,AI",
  "GEOSITE,github-copilot,AI",
  "GEOSITE,huggingface,AI",

  // --- 2. Google 特定端点例外 → DIRECT / REJECT ---
  //     必须排在下面 google.com 之前：内核按顺序匹配，先命中先生效
  //     dl/mtalk 是更新与推送长连接，直连更快；遥测端点在机场那边也被拦截
  "DOMAIN,dl.google.com,DIRECT",
  "DOMAIN,mtalk.google.com,DIRECT",
  "DOMAIN-SUFFIX,googletraveladservices.com,DIRECT",
  "DOMAIN-SUFFIX,googleapis.l.google.com,REJECT",
  "DOMAIN-SUFFIX,clients.l.google.com,REJECT",
  "DOMAIN-SUFFIX,maps.l.google.com,REJECT",
  "DOMAIN-SUFFIX,khm.l.google.com,REJECT",

  // --- 3. Google 日常与流媒体 → 通用组 ---
  //     通用组默认选实测最快的池（当前为香港）；网页版 Gemini 在香港可用
  // Google 日常
  "DOMAIN-SUFFIX,gemini.google.com,通用",
  "DOMAIN-SUFFIX,bard.google.com,通用",
  "DOMAIN-SUFFIX,notebooklm.google.com,通用",
  "DOMAIN-SUFFIX,google.com,通用",
  "DOMAIN-SUFFIX,google.com.hk,通用",
  "DOMAIN-SUFFIX,gstatic.com,通用",
  "DOMAIN-SUFFIX,googleusercontent.com,通用",
  "DOMAIN-SUFFIX,gmail.com,通用",
  "DOMAIN-SUFFIX,ggpht.com,通用",
  // 流媒体长尾
  "DOMAIN-SUFFIX,twitch.tv,通用",
  "DOMAIN-SUFFIX,primevideo.com,通用",
  "DOMAIN-SUFFIX,hulu.com,通用",
  "DOMAIN-SUFFIX,disneyplus.com,通用",
  "DOMAIN-SUFFIX,max.com,通用",
  "DOMAIN-SUFFIX,tiktok.com,通用",

  // --- 4. AI 宽泛兜底（排在 Google 网页例外之后） ---
  "GEOSITE,google-gemini,AI",

  // --- 5. Microsoft 等直连 → DIRECT ---
  //     必须排在 AI 之后，否则 copilot.microsoft.com 会被一起直连
  "DOMAIN-SUFFIX,outlook.com,DIRECT",
  "DOMAIN-SUFFIX,outlookmobile.com,DIRECT",
  "DOMAIN-SUFFIX,office.com,DIRECT",
  "DOMAIN-SUFFIX,office.net,DIRECT",
  "DOMAIN-SUFFIX,office365.com,DIRECT",
  "DOMAIN-SUFFIX,cloud.microsoft,DIRECT",
  "DOMAIN-SUFFIX,microsoft.com,DIRECT",
  "DOMAIN-SUFFIX,microsoftonline.com,DIRECT",
  "DOMAIN-SUFFIX,msauth.net,DIRECT",
  "DOMAIN-SUFFIX,msftauth.net,DIRECT",
  "DOMAIN-SUFFIX,live.com,DIRECT",
  "DOMAIN-SUFFIX,sharepoint.com,DIRECT",
  "DOMAIN-SUFFIX,skype.com,DIRECT",
  "DOMAIN-SUFFIX,acompli.net,DIRECT",
  "DOMAIN-SUFFIX,login.windows.net,DIRECT",
  "DOMAIN-SUFFIX,sts.windows.net,DIRECT",
  "DOMAIN-SUFFIX,enterpriseregistration.windows.net,DIRECT",

];
// <<< LOCAL-RULES

// >>> LOCAL-RULES-EXTRA（clashctl sync 从 clash/local/rules.local.js 注入；仓库中保持为空）
// 运行时排在最前，优先于下面的通用本地规则
var LOCAL_RULES_EXTRA = [];
// <<< LOCAL-RULES-EXTRA

// >>> VERIFIED-EXITS（由 clashctl 维护；sync 时保留目标文件里的清单）
var VERIFIED = {};
// <<< VERIFIED-EXITS

function main(config, profileName) {
  var proxies = config.proxies || [];
  if (!proxies.length) return config;

  // 当前订阅节点名（只读快照）：用于判断清单里的节点是否还在订阅中
  var proxyNames = {};
  for (var i = 0; i < proxies.length; i++) proxyNames[proxies[i].name] = true;

  // mihomo 要求节点名与代理组名在同一命名空间内全局唯一。机场订阅会出现裸地区名
  // 的节点（例如就叫「美国」），若地区池也叫「美国」，内核会报
  // "proxy group 美国: the duplicate name"，Clash Verge 验证失败后退回
  // 默认最小配置（没有任何节点），界面显示「未获取到代理信息」。
  //
  // 地区池统一以「池」结尾，占一个稳定的命名区间：名字不随订阅里有没有同名节点
  // 而变，`clashctl use` 与界面记住的选择也不会失效。服务组保持短名字。
  // uniqueName 是唯一的名字分配入口：地区池与三个服务组都走这里。
  // 原名可用就直接用；被节点占用时按 X → XYZ → XYZ 年月日 递进升级后缀
  // （每一级都更难与订阅节点撞名），保证内核不会因重名拒绝配置。
  // 已分配的名字：初始值同为节点名，但生成组名时继续追加，与 proxyNames 语义不同
  var used = {};
  for (var ui = 0; ui < proxies.length; ui++) used[proxies[ui].name] = true;
  used["DIRECT"] = true; used["REJECT"] = true; used["PASS"] = true;

  var FALLBACK_TAGS = ["X", "XYZ"];

  function dateTag() {
    try {
      var d = new Date();
      function pad(n) { return (n < 10 ? "0" : "") + n; }
      return "" + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate());
    } catch (e) {
      return "00000000";   // 沙箱里取不到时间也不能让整份配置失败
    }
  }

  function uniqueName(base) {
    if (!used[base]) { used[base] = true; return base; }
    for (var i = 0; i < FALLBACK_TAGS.length; i++) {
      var tagged = base + " " + FALLBACK_TAGS[i];
      if (!used[tagged]) { used[tagged] = true; return tagged; }
    }
    var stamp = dateTag();
    var name = base + " XYZ " + stamp;
    for (var n = 2; used[name]; n++) name = base + " XYZ " + stamp + " " + n;
    used[name] = true;
    return name;
  }

  // 服务组名也走同一套避让：机场也可能拿「AI」「其他」当节点名
  var SERVICE = {
    "AI": uniqueName("AI"),
    "通用": uniqueName("通用"),
    "其他": uniqueName("其他")
  };

  var HC = "https://www.gstatic.com/generate_204";
  var POOL_SUFFIX = "池";  // 组名后缀：与节点名隔开；clashctl 也从本文件读取
  var POOL_CAP = 10;      // 每个地区池最多收录多少个节点
  var MIN_POOL = 3;       // 少于这个数量就不建池，节点落「其他」
  var MAX_POOLS = 8;      // 最多建多少个地区池，避免组列表过长

  // 地区中文名：ISO 3166-1 两位代码 → 中文。未命中的代码直接显示代码本身。
  // 超过 7 个字的地区用通行简称（阿联酋、波黑、特立尼达…），面板一行放得下。
  // 覆盖全部常见代码，新增地区不需要改这里；面板顺序由 PREFER 决定。
  var REGION_NAME = {
    AC: "阿森松岛", AD: "安道尔", AE: "阿联酋", AF: "阿富汗",
    AG: "安提瓜和巴布达", AI: "安圭拉", AL: "阿尔巴尼亚", AM: "亚美尼亚",
    AO: "安哥拉", AQ: "南极洲", AR: "阿根廷", AS: "美属萨摩亚",
    AT: "奥地利", AU: "澳大利亚", AW: "阿鲁巴", AX: "奥兰群岛",
    AZ: "阿塞拜疆", BA: "波黑", BB: "巴巴多斯", BD: "孟加拉国",
    BE: "比利时", BF: "布基纳法索", BG: "保加利亚", BH: "巴林",
    BI: "布隆迪", BJ: "贝宁", BL: "圣巴泰勒米", BM: "百慕大",
    BN: "文莱", BO: "玻利维亚", BQ: "荷属加勒比区", BR: "巴西",
    BS: "巴哈马", BT: "不丹", BV: "布韦岛", BW: "博茨瓦纳",
    BY: "白俄罗斯", BZ: "伯利兹", CA: "加拿大", CC: "科科斯群岛",
    CD: "刚果（金）", CF: "中非共和国", CG: "刚果（布）", CH: "瑞士",
    CI: "科特迪瓦", CK: "库克群岛", CL: "智利", CM: "喀麦隆",
    CN: "中国", CO: "哥伦比亚", CP: "克利珀顿岛", CQ: "萨克岛",
    CR: "哥斯达黎加", CU: "古巴", CV: "佛得角", CW: "库拉索",
    CX: "圣诞岛", CY: "塞浦路斯", CZ: "捷克", DE: "德国",
    DG: "迪戈加西亚岛", DJ: "吉布提", DK: "丹麦", DM: "多米尼克",
    DO: "多米尼加", DZ: "阿尔及利亚", EA: "休达及梅利利亚", EC: "厄瓜多尔",
    EE: "爱沙尼亚", EG: "埃及", EH: "西撒哈拉", ER: "厄立特里亚",
    ES: "西班牙", ET: "埃塞俄比亚", EU: "欧盟", EZ: "欧元区",
    FI: "芬兰", FJ: "斐济", FK: "福克兰群岛", FM: "密克罗尼西亚",
    FO: "法罗群岛", FR: "法国", GA: "加蓬", GB: "英国",
    GD: "格林纳达", GE: "格鲁吉亚", GF: "法属圭亚那", GG: "根西岛",
    GH: "加纳", GI: "直布罗陀", GL: "格陵兰", GM: "冈比亚",
    GN: "几内亚", GP: "瓜德罗普", GQ: "赤道几内亚", GR: "希腊",
    GS: "南乔治亚", GT: "危地马拉", GU: "关岛", GW: "几内亚比绍",
    GY: "圭亚那", HK: "香港", HM: "赫德岛", HN: "洪都拉斯",
    HR: "克罗地亚", HT: "海地", HU: "匈牙利", IC: "加纳利群岛",
    ID: "印度尼西亚", IE: "爱尔兰", IL: "以色列", IM: "马恩岛",
    IN: "印度", IO: "英属印度洋领地", IQ: "伊拉克", IR: "伊朗",
    IS: "冰岛", IT: "意大利", JE: "泽西岛", JM: "牙买加",
    JO: "约旦", JP: "日本", KE: "肯尼亚", KG: "吉尔吉斯斯坦",
    KH: "柬埔寨", KI: "基里巴斯", KM: "科摩罗", KN: "圣基茨和尼维斯",
    KP: "朝鲜", KR: "韩国", KW: "科威特", KY: "开曼群岛",
    KZ: "哈萨克斯坦", LA: "老挝", LB: "黎巴嫩", LC: "圣卢西亚",
    LI: "列支敦士登", LK: "斯里兰卡", LR: "利比里亚", LS: "莱索托",
    LT: "立陶宛", LU: "卢森堡", LV: "拉脱维亚", LY: "利比亚",
    MA: "摩洛哥", MC: "摩纳哥", MD: "摩尔多瓦", ME: "黑山",
    MF: "法属圣马丁", MG: "马达加斯加", MH: "马绍尔群岛", MK: "北马其顿",
    ML: "马里", MM: "缅甸", MN: "蒙古", MO: "澳门",
    MP: "北马里亚纳群岛", MQ: "马提尼克", MR: "毛里塔尼亚", MS: "蒙特塞拉特",
    MT: "马耳他", MU: "毛里求斯", MV: "马尔代夫", MW: "马拉维",
    MX: "墨西哥", MY: "马来西亚", MZ: "莫桑比克", NA: "纳米比亚",
    NC: "新喀里多尼亚", NE: "尼日尔", NF: "诺福克岛", NG: "尼日利亚",
    NI: "尼加拉瓜", NL: "荷兰", NO: "挪威", NP: "尼泊尔",
    NR: "瑙鲁", NU: "纽埃", NZ: "新西兰", OM: "阿曼",
    PA: "巴拿马", PE: "秘鲁", PF: "法属波利尼西亚", PG: "巴布亚新几内亚",
    PH: "菲律宾", PK: "巴基斯坦", PL: "波兰", PM: "圣皮埃尔",
    PN: "皮特凯恩群岛", PR: "波多黎各", PS: "巴勒斯坦领土", PT: "葡萄牙",
    PW: "帕劳", PY: "巴拉圭", QA: "卡塔尔", QO: "大洋洲边远群岛",
    RE: "留尼汪", RO: "罗马尼亚", RS: "塞尔维亚", RU: "俄罗斯",
    RW: "卢旺达", SA: "沙特阿拉伯", SB: "所罗门群岛", SC: "塞舌尔",
    SD: "苏丹", SE: "瑞典", SG: "新加坡", SH: "圣赫勒拿",
    SI: "斯洛文尼亚", SJ: "斯瓦尔巴", SK: "斯洛伐克", SL: "塞拉利昂",
    SM: "圣马力诺", SN: "塞内加尔", SO: "索马里", SR: "苏里南",
    SS: "南苏丹", ST: "圣多美", SV: "萨尔瓦多", SX: "荷属圣马丁",
    SY: "叙利亚", SZ: "斯威士兰", TA: "特里斯坦", TC: "特克斯",
    TD: "乍得", TF: "法属南部领地", TG: "多哥", TH: "泰国",
    TJ: "塔吉克斯坦", TK: "托克劳", TL: "东帝汶", TM: "土库曼斯坦",
    TN: "突尼斯", TO: "汤加", TR: "土耳其", TT: "特立尼达",
    TV: "图瓦卢", TW: "台湾", TZ: "坦桑尼亚", UA: "乌克兰",
    UG: "乌干达", UM: "美国离岛", UN: "联合国", US: "美国",
    UY: "乌拉圭", UZ: "乌兹别克斯坦", VA: "梵蒂冈", VC: "圣文森特",
    VE: "委内瑞拉", VG: "英属维尔京群岛", VI: "美属维尔京群岛", VN: "越南",
    VU: "瓦努阿图", WF: "瓦利斯和富图纳", WS: "萨摩亚", XA: "伪地区",
    XB: "伪双向语言地区", XK: "科索沃", YE: "也门", YT: "马约特",
    ZA: "南非", ZM: "赞比亚", ZW: "津巴布韦", ZZ: "未知地区",
  };
  // 优选顺序：列出的地区排在前面，其余按验证节点数从多到少
  var PREFER = ["HK", "SG", "TW", "JP", "IN", "US", "AU"];

  function sel(name, members) { return { name: name, type: "select", proxies: members }; }

  // 落地页 / 广告节点的通用特征：URL、IPv4 与常见中文词
  // 宁可漏过滤也不误杀——真正的兜底是「测量失败自然排除」
  var JUNK = /(https?:|tcp:\/\/|\d{1,3}(\.\d{1,3}){3}|官网|广告|推广)/i;

  // 按实测清单把节点分到出口地区，同地区内按延迟升序
  var byRegion = {};
  for (var nm in VERIFIED) {
    if (!proxyNames[nm] || JUNK.test(nm)) continue;
    var v = VERIFIED[nm];
    if (!byRegion[v[0]]) byRegion[v[0]] = [];
    byRegion[v[0]].push([nm, v[1]]);
  }
  for (var rc in byRegion) {
    byRegion[rc].sort(function (a, b) { return a[1] - b[1]; });
  }

  // 建池：任意地区只要验证节点数达到 MIN_POOL 就建池，不依赖预设名单
  // 池名统一加「池」后缀，对所有动态发现的地区一视同仁（含对照表外的代码）
  var pools = [];
  var inPool = {};
  var poolCc = {};
  var latency = {};
  var codes = [];
  for (var code in byRegion) {
    if (byRegion[code].length >= MIN_POOL) codes.push(code);
  }

  // 地区排序规则：PREFER 优先，其余按该地区实测节点数降序。
  // 建池顺序与「其他」组的地区桶顺序共用这一份，避免两处漂移。
  function regionCompare(a, b) {
    var pa = PREFER.indexOf(a), pb = PREFER.indexOf(b);
    if (pa >= 0 && pb >= 0) return pa - pb;
    if (pa >= 0) return -1;
    if (pb >= 0) return 1;
    var la = byRegion[a] ? byRegion[a].length : 0;
    var lb = byRegion[b] ? byRegion[b].length : 0;
    return lb - la;
  }
  codes.sort(regionCompare);
  if (codes.length > MAX_POOLS) codes = codes.slice(0, MAX_POOLS);

  for (var ci = 0; ci < codes.length; ci++) {
    var ccode = codes[ci];
    var poolName = uniqueName((REGION_NAME[ccode] || ccode) + POOL_SUFFIX);
    var members = [];
    for (var mi = 0; mi < byRegion[ccode].length && mi < POOL_CAP; mi++) {
      members.push(byRegion[ccode][mi][0]);
    }
    pools.push({
      name: poolName, type: "url-test", proxies: members,
      url: HC, interval: 900, tolerance: 200, lazy: false, "max-failed-times": 2
    });
    poolCc[poolName] = ccode;
    latency[poolName] = byRegion[ccode][0][1];
    for (var mj = 0; mj < members.length; mj++) inPool[members[mj]] = true;
  }

  // 服务组成员一律按该池最快节点的实测延迟升序：初始默认选表现最好的池。
  // AI 与通用的唯一区别是前者不含香港（合规硬约束，与延迟无关）。
  var hkName = null;
  for (var pk in poolCc) if (poolCc[pk] === "HK") hkName = pk;
  var generalNames = [];
  for (var pi = 0; pi < pools.length; pi++) generalNames.push(pools[pi].name);
  generalNames.sort(function (a, b) { return latency[a] - latency[b]; });
  var aiNames = generalNames.filter(function (n) { return n !== hkName; });

  // 其他：池外节点按实测出口地区分桶，与建池同源，不再按节点名前缀猜地区。
  // 桶顺序沿用 regionCompare（PREFER 优先 + 其余按节点数降序）；
  // 与建池不同：不设 MIN_POOL 阈值、不做 MAX_POOLS 截断，每个节点都要有桶。
  // 桶内按实测延迟升序，快的排前面。
  var byExit = {};
  for (var p = 0; p < proxies.length; p++) {
    var pn = proxies[p].name;
    if (inPool[pn] || JUNK.test(pn)) continue;
    if (!VERIFIED[pn]) continue;   // 没有实测记录 = 探测失败过，只收确认活着的节点
    var exitCode = VERIFIED[pn][0];
    if (!byExit[exitCode]) byExit[exitCode] = [];
    byExit[exitCode].push({ name: pn, latency: VERIFIED[pn][1] });
  }
  var exitCodes = [];
  for (var code2 in byExit) exitCodes.push(code2);
  exitCodes.sort(regionCompare);
  var leftover = [];
  for (var e = 0; e < exitCodes.length; e++) {
    var items = byExit[exitCodes[e]];
    items.sort(function (a, b) { return a.latency - b.latency; });
    for (var it = 0; it < items.length; it++) leftover.push(items[it].name);
  }

  var other = { name: SERVICE["其他"], type: "select", proxies: leftover.concat(["DIRECT", "REJECT"]) };

  // 服务组：AI 与通用共用同一份延迟排序，AI 只少一个香港池
  var services = [
    sel(SERVICE["AI"], aiNames.concat([SERVICE["其他"], "DIRECT", "REJECT"])),
    sel(SERVICE["通用"], generalNames.concat([SERVICE["其他"], "DIRECT", "REJECT"]))
  ];

  config["proxy-groups"] = services.concat([other]).concat(pools);

  // 订阅组名和旧版组名到新组名的映射
  var RENAME = {
    "🔰 手动选择": "通用",
    "🌍 主流媒体": "通用",
    "🐟 漏网之鱼": "通用",
    "🐟 默认": "通用",
    "🎥 Netflix": "通用",
    "📲 Telegram": "通用",
    "🌐 Google": "通用",
    "Ⓜ️ Microsoft": "DIRECT",
    "🍎 Apple": "DIRECT",
    "📺 BiliBili": "DIRECT",
    "🎯 Direct": "DIRECT",
    "🛑 Block": "REJECT",
    "Block": "REJECT",
    "🚀 代理": "通用",
    "🤖 AI": "AI",
    "🤖 OpenAI": "AI",
    "🧠 Anthropic": "AI",
    "✨ Gemini API": "AI",
    "✨ Gemini 网页": "通用",
    "🎬 流媒体": "通用",
    "非港": "AI",
    "♻️ 非港AI": "AI",
    // 地区池名由 poolNameOf() 动态解析，不写死后缀（改名后仍有效）
    "♻️ 香港": "香港",
    "♻️ 美国": "美国",
    "🔧 手动节点": "其他",
    "🖐 指定节点": "其他",
    "直连": "DIRECT",
    "拦截": "REJECT",
    "Direct": "DIRECT",
    "Reject": "REJECT"
  };

  // 组名避让节点后，规则里写的旧服务组名要跟着改指向
  var ALIAS = {};
  ALIAS["AI"] = SERVICE["AI"];
  ALIAS["通用"] = SERVICE["通用"];
  ALIAS["其他"] = SERVICE["其他"];

  // 收集已知目标，用于判断机场规则指到的组是否还存在
  var known = {};
  for (var k = 0; k < config["proxy-groups"].length; k++) known[config["proxy-groups"][k].name] = true;
  known["DIRECT"] = true; known["REJECT"] = true; known["PASS"] = true;

  // 地区线索：机场组名里出现这些词时，尽量映射到对应的地区池
  var REGION_HINTS = [
    [/香港|\bhk\b|hong ?kong/i, "HK"],
    [/台湾|\btw\b|taiwan/i, "TW"],
    [/新加坡|\bsg\b|singapore/i, "SG"],
    [/日本|\bjp\b|japan/i, "JP"],
    [/韩国|\bkr\b|korea/i, "KR"],
    [/印度|\bin\b|india/i, "IN"],
    [/美国|\bus\b|united ?states/i, "US"],
    [/澳大利亚|澳洲|\bau\b|australia/i, "AU"]
  ];

  function poolNameOf(cc) {
    for (var pn in poolCc) if (poolCc[pn] === cc) return pn;
    return null;
  }

  // 不认识的组名按语义猜测：拦截类 → REJECT，直连类 → DIRECT，
  // 含地区线索 → 对应地区池（池不存在则回落通用），其余 → 通用
  function guessTarget(name) {
    if (/(拦截|广告|屏蔽|Block|Advert|\bAD\b)/i.test(name)) return "REJECT";
    if (/(直连|Direct)/i.test(name)) return "DIRECT";
    for (var gi = 0; gi < REGION_HINTS.length; gi++) {
      if (REGION_HINTS[gi][0].test(name)) {
        var pn2 = poolNameOf(REGION_HINTS[gi][1]);
        if (pn2) return pn2;
        break;
      }
    }
    return SERVICE["通用"];
  }

  // 规则尾部可能带选项（no-resolve、src），目标取它们前一个字段
  function targetIndex(parts) {
    var idx = parts.length - 1;
    if (parts[idx] === "no-resolve" || parts[idx] === "src") idx--;
    return idx;
  }

  // 把规则目标解析成实际存在的组名（组名可能因避让节点而改名）
  function resolveTarget(target) {
    var mapped = RENAME[target] || target;
    if (ALIAS[mapped]) mapped = ALIAS[mapped];
    if (!known[mapped]) mapped = guessTarget(mapped);
    return mapped;
  }

  // 把机场规则的目标重映射到本脚本重建的组；不认识的按语义兜底
  var rules = config.rules || [];
  for (var ri = 0; ri < rules.length; ri++) {
    if (typeof rules[ri] !== "string") continue;
    var parts = rules[ri].split(",");
    var idx = targetIndex(parts);
    if (idx < 1) continue;
    parts[idx] = resolveTarget(parts[idx]);
    rules[ri] = parts.join(",");
  }

  // 本机私有规则只映射服务组名，不做语义猜测：私有规则可能直接指向某个节点名，
  // guessTarget 会把「美国 01」这类节点名误判成地区池，改变用户本意。
  function retargetPrivate(rule) {
    if (typeof rule !== "string") return rule;
    var parts = rule.split(",");
    var idx = targetIndex(parts);
    if (idx >= 1 && ALIAS[parts[idx]]) parts[idx] = ALIAS[parts[idx]];
    return parts.join(",");
  }

  // 本地规则里的 AI / 通用 也要跟着改名，否则会指向不存在的组
  function retarget(rule) {
    if (typeof rule !== "string") return rule;
    var parts = rule.split(",");
    var idx = targetIndex(parts);
    if (idx < 1) return rule;
    parts[idx] = resolveTarget(parts[idx]);
    return parts.join(",");
  }

  // 本地规则拼在机场规则之前，等价于原来 rules 覆盖文件的 prepend
  // 顺序：本机私有规则 → 通用本地规则 → 机场规则
  // 私有规则排最前，才能覆盖通用规则（例如把某个域名改成直连）
  config.rules = LOCAL_RULES_EXTRA.map(retargetPrivate)
    .concat(LOCAL_RULES.map(retarget)).concat(rules);

  return config;
}
