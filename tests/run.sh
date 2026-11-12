#!/usr/bin/env bash
# 运行全部测试（无需 Clash 运行，纯函数级）
# 用法：tests/run.sh
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1   # 不在项目里留 __pycache__
cd "$(dirname "$0")/.." || exit 1

fail=0

echo "== 分组与规则 =="
if command -v node >/dev/null 2>&1; then
  node tests/groups.test.cjs || fail=1
elif [ -n "${CI:-}" ]; then
  echo "  CI 环境缺少 Node.js：分组测试必须执行，不允许跳过"
  fail=1
else
  echo "  跳过：未安装 Node.js（该测试需要执行 Script.js 的分组逻辑）"
fi

echo
echo "== 清单与增量刷新 =="
python3 tests/manifest.test.py || fail=1

echo
echo "== 平台适配与 systemd 定时任务 =="
python3 tests/linux.test.py || fail=1

echo
echo "== 敏感内容 =="
python3 tests/check_sensitive.py || fail=1

echo
if [ "$fail" = 0 ]; then echo "全部通过"; else echo "有失败项"; fi
exit "$fail"
