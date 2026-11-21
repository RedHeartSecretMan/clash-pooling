// 安装路径隔离的回归测试
//
// 背景：分组规格测试曾经默认读线上部署的 Script.js。升级时线上还是旧版，
// install.sh 先测试、后同步，于是测试必然失败；测试不通过就不部署，
// 不部署就永远测试不通过。这个测试锁住两件事：
//   1. 默认跑的是仓库里的 clash/Script.js —— 即使本机部署的是坏文件也不受影响
//   2. --deployed 才读部署副本 —— 安装脚本的部署后校验真的指向线上
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const APP_DIR = "io.github.clash-verge-rev.clash-verge-rev";
const GROUP_TEST = path.join(__dirname, "groups.test.cjs");
const REPO_SCRIPT = path.join(__dirname, "..", "clash", "Script.js");

let failed = 0;
function check(name, fn) {
  try {
    fn();
    console.log("  ✓ " + name);
  } catch (e) {
    failed++;
    console.log("  ✗ " + name + "\n      " + e.message);
  }
}
function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function deployedPathFor(root) {
  if (process.platform === "win32") {
    return path.join(root, "appdata", APP_DIR, "profiles", "Script.js");
  }
  if (process.platform === "linux") {
    return path.join(root, "xdg", APP_DIR, "profiles", "Script.js");
  }
  return path.join(root, "home", "Library", "Application Support", APP_DIR, "profiles", "Script.js");
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "clash-pooling-paths-"));
const env = Object.assign({}, process.env, {
  HOME: path.join(tmp, "home"),
  XDG_DATA_HOME: path.join(tmp, "xdg"),
  APPDATA: path.join(tmp, "appdata"),
});
const brokenDeployed = deployedPathFor(tmp);
fs.mkdirSync(path.dirname(brokenDeployed), { recursive: true });
fs.writeFileSync(brokenDeployed, "// 旧版占位：没有 VERIFIED-EXITS 标记块\n", "utf8");

function run(args) {
  return spawnSync(process.execPath, [GROUP_TEST].concat(args), { env, encoding: "utf8" });
}
function tail(result) {
  const text = ((result.stdout || "") + (result.stderr || "")).trim();
  return text.split("\n").slice(-3).join(" / ");
}

try {
  check("默认读仓库源文件，不受本机部署副本影响", () => {
    const r = run([]);
    assert(r.status === 0, "应通过，实际退出码 " + r.status + "：" + tail(r));
  });

  check("--deployed 指向本机部署副本", () => {
    const r = run(["--deployed"]);
    assert(r.status !== 0, "坏掉的部署副本不应通过");
    assert((r.stdout + r.stderr).includes("VERIFIED-EXITS"),
      "报错应说明部署副本缺少标记块：" + tail(r));
  });

  check("--script 可指定任意副本", () => {
    const r = run(["--script", REPO_SCRIPT]);
    assert(r.status === 0, "仓库副本应通过，实际退出码 " + r.status + "：" + tail(r));
  });
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

process.exit(failed ? 1 : 0);
