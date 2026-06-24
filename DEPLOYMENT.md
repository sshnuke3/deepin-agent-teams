# deepin-agent-teams 新机器部署指南

> 第十期飞桨黑客松 · 统信 × 百度飞桨 · 进阶任务 #27
> 更新日期：2026-06-25

---

## 一、环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | deepin 25（推荐）/ Ubuntu 22.04+ / 其他 Linux |
| Python | 3.10+（推荐 3.11） |
| 显示服务 | X11（GUI 模式需要，Wayland 下部分功能受限） |
| 磁盘空间 | ≥ 500MB（含依赖和数据） |
| 网络 | 需要访问百度 AI Studio API |

---

## 二、快速安装

### 2.1 克隆仓库

```bash
git clone https://github.com/sshnuke3/deepin-agent-teams.git
cd deepin-agent-teams
```

### 2.2 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2.3 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.4 配置 API Token

```bash
cp .env.example .env
# 编辑 .env，填入你的文心大模型 API Token
```

`.env` 文件内容：

```env
# 文心大模型 API Token（必填，从 AI Studio 获取）
ERNIEBOT_ACCESS_TOKEN=你的token

# 强模型 Token（可选，为空则与上面共用）
ERNIEBOT_STRONG_TOKEN=

# 模型配置（可选，有默认值）
MODEL_LITE=ernie-lite
MODEL_STRONG=ernie-3.5
```

**获取 Token**：
1. 访问 [百度 AI Studio](https://aistudio.baidu.com/)
2. 注册/登录 → 个人中心 → 访问令牌
3. 复制 Token 填入 `.env`

### 2.5 创建数据目录

```bash
mkdir -p data/checkpoints data/traces
```

---

## 三、验证安装

### 3.1 基础测试（CLI 模式）

```bash
# 激活虚拟环境
source venv/bin/activate

# 列出可用技能
python main.py --skills

# 执行简单任务
python main.py '你好，测试一下'

# 交互模式
python main.py -i
```

### 3.2 演示场景测试

```bash
# 代码分析演示
python main.py -d code-analysis -p .

# 邮件助手演示
python main.py -d email

# 系统诊断演示
python main.py -d doctor

# 文献阅读演示
python main.py -d literature

# 运行所有演示
python main.py -d all
```

### 3.3 GUI 模式测试

```bash
# 确保在桌面环境下运行
python main.py --gui
```

启动后应看到：
- 桌面右下角出现 🦞 悬浮球（带呼吸动画）
- 点击悬浮球展开对话窗口
- 输入文字自动识别场景并路由

---

## 四、可选依赖

### 4.1 OCR 能力（屏幕文字识别）

```bash
pip install paddlepaddle paddleocr
```

### 4.2 X11 窗口管理

```bash
pip install python-xlib
```

### 4.3 D-Bus 通信（deepin 系统集成）

```bash
pip install dbus-python
```

> **注意**：这些是可选依赖，不安装也能运行核心功能。

---

## 五、目录结构说明

```
deepin-agent-teams/
├── main.py                 # 主入口
├── config.py               # 配置（Token、模型路由）
├── .env                    # 环境变量（Token，不提交）
├── requirements.txt        # Python 依赖
├── agents/                 # 智能体核心
│   ├── orchestrator.py     # 统一编排器
│   ├── orchestrator_v3.py  # v3 编排器
│   ├── orchestrator_v4.py  # v4 编排器（MCP 驱动）
│   ├── task_state_machine.py  # 状态机引擎
│   ├── verifier.py         # 独立质检员
│   ├── scenario_classifier.py # 场景识别器
│   ├── model_router.py     # 模型路由
│   ├── worker_base.py      # Worker 基类
│   └── ...
├── gui/                    # GUI 界面
│   ├── main_gui.py         # GUI 入口
│   ├── chat_window.py      # 对话窗口（智能路由）
│   ├── floating_ball.py    # 悬浮球
│   ├── perception_bridge.py # 感知桥接
│   ├── decision_engine.py  # 决策引擎
│   └── auto_executor.py    # 自主执行器
├── perception/             # 环境感知
│   ├── clipboard_monitor.py
│   ├── window_manager.py
│   ├── system_monitor.py
│   └── ...
├── scenarios/              # 预设场景
│   ├── code_analysis.py
│   ├── email_assistant.py
│   ├── literature_review.py
│   └── system_doctor.py
├── data/                   # 运行时数据
│   ├── checkpoints/        # SQLite 检查点
│   └── traces/             # JSONL 执行日志
└── docs/                   # 文档
    ├── ARCHITECTURE.md
    ├── DEMO_RECORDING_GUIDE.md
    └── ...
```

---

## 六、常见问题

### Q1: `erniebot` 报错 "Invalid access token"

检查 `.env` 中的 `ERNIEBOT_ACCESS_TOKEN` 是否正确。Token 需要从 [AI Studio](https://aistudio.baidu.com/) 获取。

### Q2: GUI 启动后看不到悬浮球

- 确认在 X11 桌面环境下运行（非 Wayland）
- 检查 PyQt5 是否安装成功：`python -c "from PyQt5.QtWidgets import QApplication; print('OK')"`
- 查看终端输出是否有报错

### Q3: 剪贴板感知不工作

需要 X11 相关依赖：

```bash
pip install python-xlib
# 确保有 xclip 或 xsel
sudo apt install xclip
```

### Q4: 系统诊断场景报错

需要 `systemctl` 权限，部分操作需要 `sudo`：

```bash
# 确保当前用户在 sudo 组
sudo usermod -aG sudo $USER
```

### Q5: 模型调用超时

默认超时 30 秒，可在 `config.py` 中调整。如网络不稳定，建议使用国内镜像或 VPN。

---

## 七、演示录制

详细的演示录制步骤请参考：[DEMO_RECORDING_GUIDE.md](./DEMO_RECORDING_GUIDE.md)

快速开始：

```bash
# 录制演示视频
ffmpeg -f x11grab -r 30 -s 1280x800 -i :0.0 -c:v libx264 -preset fast ~/Desktop/deepin_demo.mp4

# 运行演示（另一个终端）
python main.py --gui
```

---

## 八、开发模式

### 运行测试

```bash
python -m pytest tests/ -v
```

### 查看日志

```bash
# 执行日志在 data/traces/ 目录
cat data/traces/*.jsonl | python -m json.tool
```

### 检查点查看

```bash
sqlite3 data/checkpoints/checkpoints.db "SELECT * FROM checkpoints LIMIT 10;"
```

---

🦞 deepin-agent-teams 部署指南 | 2026-06-25
