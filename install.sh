#!/usr/bin/env bash
# 测试通过后安装：工具 + Clash 侧配置
#   bin/clashctl              → ~/.local/bin/clashctl
#   lib/clashctl/             → ~/.local/lib/clashctl/
#   clash/Script.js、Merge.yaml → Clash 配置目录（保留已有清单）
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1. 测试 =="
./tests/run.sh

echo
echo "== 2. 安装 =="
mkdir -p "$HOME/.local/bin" "$HOME/.local/lib"
install -m 755 bin/clashctl "$HOME/.local/bin/clashctl"
rm -rf "$HOME/.local/lib/clashctl"
cp -R lib/clashctl "$HOME/.local/lib/"
find "$HOME/.local/lib/clashctl" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
printf '%s\n' "$PWD" > "$HOME/.local/lib/clashctl/.project_root"
echo "  ~/.local/bin/clashctl"
echo "  ~/.local/lib/clashctl/"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "  提示：$HOME/.local/bin 不在 PATH，先执行：export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

echo
echo "== 3. 同步 Clash 配置 =="
if [ -d clash ]; then
  "$HOME/.local/bin/clashctl" sync | sed 's/^/  /'
else
  echo "  跳过：仓库里没有 clash/ 目录"
fi

echo
echo "== 4. 安装后自检 =="
"$HOME/.local/bin/clashctl" auto status | sed 's/^/  /'
echo
echo "== 5. 环境诊断 =="
"$HOME/.local/bin/clashctl" doctor | sed 's/^/  /'
