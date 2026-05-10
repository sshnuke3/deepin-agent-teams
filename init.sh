#!/bin/bash
# init.sh — 环境健康检查
# 每次会话开始运行，验证依赖和配置

set -e

echo "🦞 deepin Agent Teams — 环境检查"
echo "================================"

ERRORS=0

# 1. Python 版本
echo -n "Python 3.8+ ... "
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)'; then
        echo "✅ $PY_VER"
    else
        echo "❌ $PY_VER (需要 3.8+)"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "❌ python3 未安装"
    ERRORS=$((ERRORS + 1))
fi

# 2. 依赖包检查
echo -n "erniebot ... "
python3 -c 'import erniebot' 2>/dev/null && echo "✅" || { echo "❌ 未安装"; ERRORS=$((ERRORS + 1)); }

echo -n "PyQt5 ... "
python3 -c 'from PyQt5.QtWidgets import QApplication' 2>/dev/null && echo "✅" || { echo "⚠️  未安装（GUI 不可用）"; }

echo -n "paddleocr ... "
timeout 10 python3 -c 'from paddleocr import PaddleOCR' 2>/dev/null && echo "✅" || { echo "⚠️  未安装或超时（OCR 降级）"; }

echo -n "pillow ... "
python3 -c 'from PIL import Image' 2>/dev/null && echo "✅" || { echo "❌ 未安装"; ERRORS=$((ERRORS + 1)); }

# 3. 配置文件
echo -n "config.py ... "
[ -f config.py ] && echo "✅" || { echo "❌ 缺失"; ERRORS=$((ERRORS + 1)); }

echo -n ".env ... "
[ -f .env ] && echo "✅" || { echo "⚠️  不存在（使用默认配置）"; }

# 4. ERNIE token
echo -n "ERNIEBOT_ACCESS_TOKEN ... "
if [ -n "$ERNIEBOT_ACCESS_TOKEN" ]; then
    echo "✅ 已设置"
elif grep -q "ERNIEBOT_ACCESS_TOKEN" .env 2>/dev/null; then
    echo "✅ 在 .env 中"
else
    echo "⚠️  未设置（需要 AI Studio token）"
fi

# 5. 模块导入检查
echo -n "项目模块导入 ... "
if python3 -c '
import sys
sys.path.insert(0, ".")
from config import get_config
cfg = get_config()
print(f"model={cfg.ernie_model}")
' 2>/dev/null; then
    echo "✅"
else
    echo "⚠️  导入失败"
fi

echo ""
echo "================================"
if [ $ERRORS -eq 0 ]; then
    echo "✅ 环境检查通过，可以开始工作！"
else
    echo "❌ 发现 $ERRORS 个问题，请先修复"
fi
