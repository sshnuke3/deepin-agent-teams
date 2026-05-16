# deepin-agent-teams

> 🤖 **多智能体协作系统** — 第十期飞桨黑客松 · 统信 × 百度飞桨 · 进阶任务 #27

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-deepin%2025-orange?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Hackathon](https://img.shields.io/badge/Hackathon-10th%20PaddlePaddle-red?style=flat-square)

> 在 deepin 25 操作系统上，基于 OpenClaw 多智能体框架和文心大模型 API，实现复杂任务的自动化拆解与协同执行。

---

## 🎯 项目简介

本项目实现了**多智能体（Multi-Agent）协作系统**，在 deepin 25 桌面环境中，通过自然语言交互完成复杂任务的自动拆解、多 Agent 协同执行和结果汇总。

**核心技术**：OpenClaw `sessions_spawn` 原生多 Agent 协作 + 文心大模型 API + 环境感知层

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                               │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│   │  悬浮球 GUI  │  │  对话窗口    │  │  系统托盘    │            │
│   └──────────────┘  └──────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       环境感知层（perception/）                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │
│  │ 屏幕截图    │ │ 剪贴板监控   │ │ 窗口管理     │             │
│  │ grim/scrot │ │   xclip      │ │  wmctrl      │             │
│  └──────────────┘ └──────────────┘ └──────────────┘             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │
│  │ 系统监控    │ │ deepin D-Bus│ │  OCR 识别   │             │
│  │ systemctl  │ │ 控制中心    │ │  PaddleOCR  │             │
│  └──────────────┘ └──────────────┘ └──────────────┘             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │
│  │ 上下文引擎  │ │ 行为追踪    │ │ 资源控制    │             │
│  │ 意图识别    │ │ 序列记录    │ │ 内存/CPU    │             │
│  └──────────────┘ └──────────────┘ └──────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      🎯 意图识别与路由                            │
│      检测关键词 + 置信度计算 → 路由到对应场景 Agent              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    场景层（scenarios/）                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │📧邮件助手│  │🩺系统诊断│  │🔍代码分析│  │📚文献阅读│        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                                 │
│  统一架构：detect_intent → collect_context → process →          │
│             generate_output → handle_command                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    多智能体协作层（agents/）                    │
│                                                                 │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐               │
│  │Lead Agent │   │SystemOper. │   │InfoCollector│              │
│  │  任务调度  │   │  系统操作   │   │  信息收集   │               │
│  └────────────┘   └────────────┘   └────────────┘               │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐               │
│  │ContentCr. │   │Researcher │   │  Coder    │               │
│  │  内容创作  │   │  研究分析  │   │  代码实现  │               │
│  └────────────┘   └────────────┘   └────────────┘               │
│                                                                 │
│  v4.1 生产级编排器（sessions_spawn）：                          │
│  · 超时控制 · 重试机制 · 错误隔离 · 优雅降级                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      文心大模型 API（model_router/）               │
│         ernie-lite（轻量任务）│ernie-3.5（复杂任务）              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 4大核心场景

| 场景 | 命令 | 核心能力 |
|------|------|---------|
| 📧 **智能邮件助手** | `python main.py -d email` | 意图识别 → 上下文收集 → 邮件生成 → 发送确认 |
| 🩺 **系统问题诊断** | `python main.py -d doctor` | 问题分类 → 多 Agent 协同诊断 → 自动修复 + 验证 |
| 🔍 **代码分析助手** | `python main.py -d code-analysis -p .` | 路径检测 → 项目扫描 → 核心分析 → 报告生成 |
| 📚 **文献阅读助手** | `python main.py -d literature -f a.pdf` | 文件检测 → 文献读取 → 关键提取 → 综述生成 |

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🤖 **OpenClaw 原生多 Agent** | 基于 `sessions_spawn` 创建真实独立的 OpenClaw 子 Agent，非伪多 Agent |
| 🔄 **双模型智能路由** | `ernie-lite` 处理轻量任务，`ernie-3.5` 处理复杂任务，自动调度 |
| 👁️ **deepin 25 环境感知** | D-Bus 接口 / 屏幕截图 / 剪贴板监控 / 窗口管理 / OCR |
| 🔒 **隐私保护机制** | 6 类敏感数据检测，自动脱敏，审计日志 |
| ⏱️ **行为序列记录** | 追踪用户操作序列，预测下一步行为 |
| 🛡️ **资源占用控制** | CPU/内存监控，超限自动降级 |
| 🤝 **冲突解决机制** | 多 Agent 任务冲突检测与协商 |
| 🎨 **deepin 风格 GUI** | PyQt5 悬浮球 + 对话窗口 + 系统托盘，匹配 deepin 25 UI |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- deepin 25 操作系统（其他 Linux 可运行部分功能）
- 文心大模型 API Key（[百度 AI Studio](https://aistudio.baidu.com)）

### 安装

```bash
# 克隆仓库
git clone https://github.com/sshnuke3/deepin-agent-teams.git
cd deepin-agent-teams

# deepin 25 一键部署（推荐）
bash deepin25_deploy.sh

# 或手动安装依赖
pip install -r requirements.txt
```

### 配置

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，填入你的 AI Studio Access Token
nano .env
# ERNIEBOT_ACCESS_TOKEN=your_token_here
```

### 运行

```bash
# 交互模式（自动路由到对应场景）
python main.py -i

# 单场景演示
python main.py -d email                              # 智能邮件助手
python main.py -d doctor                             # 系统问题诊断
python main.py -d code-analysis -p /path/to/project  # 代码分析
python main.py -d literature -f paper.pdf -q "研究方法"  # 文献阅读

# 批量演示所有场景
python main.py -d all

# v4.1 生产级编排器（sessions_spawn）
python main.py --v41 "帮我分析这个项目"

# 启动 GUI（deepin 25）
python main.py --gui
```

---

## 📁 项目结构

```
deepin-agent-teams/
├── main.py                          # CLI 入口 + GUI 入口
├── config.py                        # 全局配置
├── model_router.py                  # 双模型路由器
├── deepin_agent.py                  # Agent 主入口
├── deepin25_deploy.sh               # deepin 25 一键部署脚本
│
├── perception/                      # 🌟 环境感知层（8个模块）
│   ├── screen_capture.py            # 屏幕截图（grim/scrot）
│   ├── clipboard_monitor.py         # 剪贴板监控（xclip）
│   ├── window_manager.py            # 窗口管理（wmctrl/xdotool）
│   ├── system_monitor.py            # 系统监控（systemctl/诊断）
│   ├── deepin_dbus.py              # deepin D-Bus 接口
│   ├── screen_ocr.py               # OCR 识别（PaddleOCR）
│   ├── context_engine.py           # 上下文引擎（意图识别）
│   ├── behavior_tracker.py         # 行为序列追踪
│   ├── resource_guard.py            # 资源占用控制
│   └── privacy_guard.py            # 隐私保护（6类敏感数据检测）
│
├── agents/                          # 🌟 多智能体层
│   ├── base.py                     # Agent 基类
│   ├── lead.py                     # Lead Agent（总调度）
│   ├── researcher.py               # Researcher Agent
│   ├── coder.py                   # Coder Agent
│   ├── system_operator.py          # 系统操作员
│   ├── information_collector.py   # 信息收集员
│   ├── content_creator.py          # 内容创作员
│   ├── sessions_orchestrator_prod.py  # 🌟 v4.1 生产级编排器
│   ├── conflict_resolver.py        # 冲突解决器
│   └── registry.py                # Agent 注册中心
│
├── scenarios/                       # 🌟 4大场景
│   ├── email_assistant.py          # 📧 场景一：智能邮件助手（409行）
│   ├── system_doctor.py            # 🩺 场景二：系统诊断（376行）
│   ├── code_analysis.py           # 🔍 场景三：代码分析（410行）
│   └── literature_review.py        # 📚 场景四：文献阅读（430行）
│
├── gui/                             # 🌟 PyQt5 图形界面
│   ├── main_gui.py                 # GUI 主入口
│   ├── floating_ball.py           # 悬浮球（拖拽+边缘吸附+动画）
│   ├── chat_window.py             # 对话窗口（消息气泡+场景切换）
│   ├── tray_icon.py              # 系统托盘（右键菜单+通知）
│   └── styles.py                  # deepin 25 风格样式
│
├── tools/                           # 工具适配层
│   └── mcp_adapter.py             # MCP/Skills 框架适配器
│
├── tests/                           # 测试脚本
│   ├── test_perception_deepin25.py # 感知层实体机测试
│   └── analyze_results.py          # 测试结果分析
│
├── docs/                            # 技术文档
│   ├── ARCHITECTURE.md             # 架构文档
│   ├── CONVENTIONS.md             # 代码规范
│   ├── TECH_DECISIONS.md         # 技术决策记录
│   └── QUALITY.md                # 质量标准
│
├── tasks.json                       # 任务队列
├── PLAN.md                         # 项目规划
├── RFC.md                          # 技术请求评论
├── README.md                       # 本文件
└── requirements.txt                 # Python 依赖
```

---

## 🖥️ GUI 界面预览

> 💡 以下为 deepin 25 风格 UI 设计，实体机运行后截图补充

### 悬浮球
- 常驻桌面右下角
- 拖拽松手自动吸附屏幕边缘（带弹性动画）
- 单击打开对话窗口
- 右键显示快捷菜单

### 对话窗口
- 左侧：场景切换（邮件/诊断/代码/文献）
- 右侧：消息气泡流
- Enter 发送消息
- Agent 执行在后台线程，不阻塞 UI

### 系统托盘
- 龙虾 🦞 图标常驻托盘
- 左键：显示/隐藏悬浮球
- 右键：设置、关于、退出

---

## 🔧 感知层模块

| 模块 | 命令/工具 | 功能 |
|------|-----------|------|
| `screen_capture.py` | grim / scrot | 屏幕截图，支持全屏/区域 |
| `clipboard_monitor.py` | xclip | 监控剪贴板变化 |
| `window_manager.py` | wmctrl / xdotool | 获取窗口信息、控制焦点 |
| `system_monitor.py` | systemctl / journalctl | 系统状态监控、故障诊断 |
| `deepin_dbus.py` | D-Bus | deepin 控制中心 API 对接 |
| `screen_ocr.py` | PaddleOCR | 屏幕文字识别 |
| `context_engine.py` | — | 多源上下文融合、意图识别 |
| `behavior_tracker.py` | — | 用户行为序列追踪 |
| `resource_guard.py` | psutil | CPU/内存占用控制 |
| `privacy_guard.py` | — | 敏感数据检测（手机/身份证/密码等6类）|

---

## 📊 实施进度（2026-05-16 更新：所有任务已完成）

| 阶段 | 时间 | 状态 | 说明 |
|------|------|------|------|
| 第1周 部署+框架 | 4/1-4/7 | ✅ | |
| 第2周 Lead+Researcher | 4/8-4/14 | ✅ | |
| 第3周 Coder+场景一 | 4/15-4/21 | ✅ | |
| 第4周 架构重构+场景扩展 | 4/22-4/28 | ✅ | |
| 第5周 sessions_spawn v4 | 4/29-5/5 | ✅ | |
| 第6周 感知层+GUI完善 | 5/6-5/12 | ✅ | |
| 第7-8周 场景联动+实体机验证 | 5/13-5/26 | ✅ | 34/34测试通过 |
| 第9-10周 演示+提交 | 5/27-6/9 | ✅ | 视频+报告+提交清单 |

---

## 📝 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| Agent 框架 | OpenClaw | sessions_spawn 支持真正的进程隔离多 Agent |
| 大模型 | 文心 erinebot SDK | 赛题要求，国产化支持 |
| OCR | PaddleOCR | 飞桨生态，Linux 兼容性好 |
| GUI | PyQt5 | deepin 官方使用 Qt，兼容性最佳 |
| 系统工具 | systemctl / wmctrl / xclip | Linux 标准工具，跨发行版 |

---

## 🤝 参考资料

- [OpenClaw 文档](https://docs.openclaw.ai)
- [erniebot SDK](https://github.com/PaddlePaddle/ERNIE-SDK)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- [第十期飞桨黑客松任务列表](https://github.com/PaddlePaddle/community/tree/master/hackathon/hackathon_10th)

---

## ✅ deepin 25 实体机验证结果（2026-05-16）

**测试命令**：`python3 tests/test_perception_deepin25.py`

**测试结果**：34/34 通过 ✅

| 模块 | 结果 | 说明 |
|------|------|------|
| screen | ✅ 6/6 | 会话类型检测/屏幕信息/截图 |
| clipboard | ✅ 2/2 | 剪贴板读取/监控器初始化 |
| window | ✅ 2/2 | 活动窗口/窗口列表（wmctrl正常） |
| system | ✅ 6/6 | 服务检查/音频/网络/打印机诊断 |
| dbus | ✅ 5/5 | 检测到103个deepin服务 |
| ocr | ✅ 3/3 | PaddleOCR可用性检测 |
| context | ✅ 4/4 | 意图识别（email/system_fix/search） |
| agents | ✅ 3/3 | SystemOperator/InfoCollector/ContentCreator |
| scenarios | ✅ 2/2 | EmailAssistant/SystemDoctor |
| orchestrator | ✅ 1/1 | ProductionExecutor |

**演示视频**：已录制并加字幕（157秒）

---

## 📄 License

MIT License

---

🦞 **Powered by OpenClaw + ERNIE Bot API**