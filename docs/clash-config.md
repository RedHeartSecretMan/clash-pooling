# Clash 侧配置

Clash 内部由两份文件定义行为，本体都在项目的 `clash/` 目录里维护，用 `clashctl sync` 推送。

```
clash/Script.js   →  ~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/profiles/Script.js
clash/Merge.yaml  →  同目录的 Merge.yaml
```

## 1. 执行顺序

Clash Verge 生成配置时的顺序（官方）：

```
订阅原文 → 应用设置 → 全局扩展配置（Merge.yaml）→ 全局扩展脚本（Script.js）
        → 订阅扩展配置 → 订阅扩展脚本 → 应用设置回写
```

本方案的定制全部落在前两步，订阅层保持空置，所以换订阅、订阅更新都不会影响它们。

## 2. Script.js 的结构

文件分三段：只改第一段，第二段由工具维护，第三段不要动：

```js
// 一、本地规则（本仓库 75 条；本机覆盖会再注入若干条）
var LOCAL_RULES = [ "DOMAIN-SUFFIX,chatgpt.com,AI", ... ];

// 二、实测清单（clashctl 维护，勿手改）
var VERIFIED = { "香港 01": ["HK", 210], ... };

// 三、生成逻辑
function main(config, profileName) { ... }
```

### 2.1 本地规则

仓库里内置 75 条，按用途分五节，顺序即匹配优先级：

| 节 | 目标 | 条数 | 说明 |
|---|---|---|---|
| 1 | `AI` | 35 | OpenAI / Anthropic / Google AI 接口 / Cursor / AI 杂项 |
| 2 | `DIRECT`、`REJECT` | 3 + 4 | Google 特定端点：更新与推送直连，遥测拦截 |
| 3 | `通用` | 15 | Google 日常域、流媒体长尾 |
| 4 | `AI` | 1 | Google Gemini 宽泛兜底，排在网页例外之后 |
| 5 | `DIRECT` | 17 | Microsoft 系 |

三条顺序依赖（改顺序会静默失效）：

- 第 2 节必须早于第 3 节，否则 `dl.google.com` 被代理、`*.l.google.com` 的拦截失效
- 第 3 节的 `google.com` 后缀覆盖面很广，任何更具体的 Google 规则都要排在它前面
- 第 5 节的 Microsoft 段必须晚于第 1 节，否则 `copilot.microsoft.com` 被一起直连

本机私有规则（例如公司内网）写在 `clash/local/rules.local.js`，`sync` 时注入到
`LOCAL-RULES-EXTRA` 区块，运行时排在最前，因此优先级高于上面五节。

### 2.2 实测清单

键是节点名，值是 `[出口地区代码, 实测延迟 ms]`。只由 `clashctl` 写入；`clashctl sync` 覆盖代码时会保留目标文件里已有的这份清单。

### 2.3 生成逻辑 main()

```
1. 建地区池
     遍历清单里出现的地区 → 挑该出口的节点（按延迟升序，取前 10）
     少于 3 个不建池；超过 8 个池时按 PREFER 优先保留
     池类型 url-test（探活 gstatic、900 秒、tolerance 200 ms）

2. 排服务组成员顺序
     香港强制第一，其余按「该池最快节点的延迟」升序（只影响 select 组的成员顺序，
     不影响地区池在配置里的先后；后者按 PREFER）

3. 建服务组
     AI   = 地区池去掉香港 + 其他 + DIRECT + REJECT
     通用 = 全部地区池（香港第一）+ 其他 + DIRECT + REJECT

4. 建「其他」组
     订阅里有、未被任何池收录、且清单里有记录、且不是落地页的节点

5. 重映射机场规则目标
     RENAME 表把机场组名映射到本方案的组
     不认识的按语义兜底：拦截类 → REJECT，直连类 → DIRECT，
     含地区线索 → 对应地区池（没建池则回通用），其余 → 通用

6. 注入规则
     config.rules = 本机私有规则（LOCAL_RULES_EXTRA）
                  + 内置本地规则（LOCAL_RULES）
                  + 机场规则
```

## 3. Merge.yaml 的内容

只放与订阅无关的覆写：

```yaml
profile:
  store-selected: true     # 记住界面里手动选的节点

dns:
  fake-ip-filter:          # 指定域名不做 fake-ip
    - '+.example.com'
  direct-nameserver:
    - system               # 直连流量用系统解析器
  direct-nameserver-follow-policy: true
  nameserver-policy:       # 指定域名交给专用 DNS
    '+.example.com': [192.0.2.10]
```

`direct-nameserver-follow-policy: true` 是关键：默认 `false` 时直连解析会绕过 `nameserver-policy`，指定域名的解析策略不会生效。

`clashctl doctor` 会从这份文件推导期望值并核对生成后的配置，不写死地址。

本机私有配置（内网域名、专用 DNS）放在 `clash/local/Merge.yaml`，已被 `.gitignore` 排除；
存在时 `clashctl sync` 会用它替代仓库里的这份示例。

## 4. 同步与回滚

```
改 clash/Script.js 或 clash/Merge.yaml
  → clashctl sync
  → 退出并重新打开 Clash Verge
```

`sync` 的行为：用项目里的源码覆盖 Clash 目录下的同名文件，**但保留目标里已有的清单块**。这样仓库只存代码，运行产生的大量测量数据不会污染版本历史。

回滚：

| 场景 | 做法 |
|---|---|
| 改坏了配置 | `git checkout -- clash/` 后重新 `clashctl sync` |
| 想回到某个历史版本 | 从 `backup-<时间戳>/` 取回 `profiles/` 下的文件 |
| 只想撤销清单 | 删掉 `VERIFIED` 块里的条目或重跑 `exit-check --refresh --full` |
