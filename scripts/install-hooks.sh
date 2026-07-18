#!/usr/bin/env bash
# install-hooks.sh — 把 scripts/pre-commit 安装到 .git/hooks/
#
# 用法：bash scripts/install-hooks.sh
# 触发场景：clone 仓库后第一次配置、或者 hook 误删后恢复

set -e

HOOK_SRC="$(cd "$(dirname "$0")" && pwd)/pre-commit"
HOOK_DST="$(git rev-parse --show-toplevel)/.git/hooks/pre-commit"

if [ ! -f "$HOOK_SRC" ]; then
  echo "❌ 找不到 $HOOK_SRC"
  exit 1
fi

cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"

echo "✅ Hook 已安装: $HOOK_DST"
echo "   现在 git commit 时会自动拦截 .env 和疑似 key"