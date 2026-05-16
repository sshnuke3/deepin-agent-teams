#!/bin/bash
# deepin25_deploy.sh - deepin-agent-teams 环境部署脚本
# =============================================================
# 在 deepin 25 实体机上运行，一键安装所有依赖
#
# 用法: bash deepin25_deploy.sh
# =============================================================

set -e

echo "============================================"
echo "deepin-agent-teams 部署脚本"
echo "============================================"

# 1. 安装系统依赖
sudo apt update -qq

# python3-venv（虚拟环境必需）
sudo apt install -y python3.12-venv python3-venv 2>/dev/null || sudo apt install -y python3-venv || true

# 截图工具
if ! command -v grim &> /dev/null && ! command -v scrot &> /dev/null; then
    echo "安装截图工具..."
    sudo apt install -y grim scrot 2>/dev/null || sudo apt install -y scrot
fi

# 窗口管理工具
if ! command -v wmctrl &> /dev/null; then
    echo "安装窗口管理工具..."
    sudo apt install -y wmctrl xdotool
fi

# 剪贴板工具
if ! command -v xclip &> /dev/null; then
    echo "安装剪贴板工具..."
    sudo apt install -y xclip
fi

# DBus 工具
if ! command -v gdbus &> /dev/null; then
    echo "安装 D-Bus 工具..."
    sudo apt install -y gdbus 2>/dev/null || sudo apt install -y libdbus-glib-1-2 2>/dev/null || true
fi

# 图像处理（OCR依赖）
if ! command -v convert &> /dev/null; then
    echo "安装 ImageMagick..."
    sudo apt install -y imagemagick
fi

echo "✅ 系统依赖安装完成"

# 2. 创建虚拟环境（推荐）
echo "[2/6] 创建Python虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# pip 镜像加速
mkdir -p ~/.config/pip
echo -e "[global]\ntimeout = 120\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\n" > ~/.config/pip/pip.conf

# 3. 安装Python依赖（加速模式）
echo "[3/6] 安装Python依赖..."
pip install --upgrade pip -q --prefer-binary
pip install -r requirements.txt -q --prefer-binary

# 4. 安装 OpenClaw（如果需要）
echo "[4/6] 检查 OpenClaw..."
if ! command -v openclaw &> /dev/null; then
    echo "安装 OpenClaw..."
    npm install -g openclaw 2>/dev/null || true
fi

# 5. 安装 PaddleOCR（可选，使用镜像加速）
echo "[5/6] 安装 PaddleOCR（可选）..."
pip install paddlepaddle paddleocr -q --prefer-binary -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || echo "⚠️ PaddleOCR 安装失败，跳过"

# 6. 生成结果目录
echo "[6/6] 创建测试结果目录..."
mkdir -p tests

echo ""
echo "============================================"
echo "✅ 部署完成！"
echo "============================================"
echo ""
echo "下一步："
echo "  1. 激活虚拟环境: source venv/bin/activate"
echo "  2. 配置 ERNIE Token: cp .env.example .env && nano .env"
echo "  3. 运行测试: python3 tests/test_perception_deepin25.py"
echo "  4. 拷贝结果文件回本机分析"
echo ""
