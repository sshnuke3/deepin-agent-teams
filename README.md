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

**核心架构**：三角架构（状态机引擎 + 独立 Verifier + Worker 池）

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
│  screen_capture · screen_ocr · clipboard_monitor · window_manager │
│  system_monitor · deepin_dbus · context_engine · behavior_tracker │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    🎯 三角架构（核心引擎）                        │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ TaskState   │    │  Verifier   │    │   Worker    │         │
│  │  Machine   │ +  │ (独立质检)  │ +  │   (执行者)  │         │
│  │ 状态机引擎  │    │  ≠ 执行者   │    │  14 种能力  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                  │                   │                 │
│         ▼                  ▼                   ▼                 │
│  /tmp/deepin_traces/  →  验收清单  ←  /tmp/deepin_checkpoints/  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    多智能体协作层（agents/）                      │
│                                                                 │
│  Lead Agent ← 任务拆解 → OrchestratorV3 ← 编排 → Worker 池      │
│                                 ↓                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  researcher  │  │     coder    │  │   general    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    四大场景（scenarios/）                         │
│  📧邮件助手 · 🩺系统诊断 · 🔍代码分析 · 📚文献阅读              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三角架构（核心设计）

### 状态机引擎（TaskStateMachine）

所有状态跳转写死在代码中，不靠模型主观判断：

```
PENDING → CLAIMED → RUNNING → VERIFIED → COMPLETED
                          ↓ FAIL
                        RETRY（≤3次）
                          ↓ 超次
                        FAILED
```

| 状态 | 说明 | 关键规则 |
|------|------|---------|
| PENDING | 入队，未分配 | — |
| CLAIMED | Worker 认领 | worker_id 存在 |
| RUNNING | 执行中 | start_time 记录 |
| VERIFIED | Verifier 通过 | verdict == PASS |
| COMPLETED | 流程终结 | 自动完成 |
| RETRY | 需重做 | FAIL 且 retry < 3 |
| FAILED | 不可恢复 | 超时 / 重试耗尽 |

**每次跳转写 trace** → `/tmp/deepin_traces/{task_id}.jsonl`

### 独立 Verifier

Verifier ≠ 执行者，独立世界观，验收标准是清单：

- `deliverable_exists` — 交付物非空
- `functional_correctness` — 按 task type 分叉验收
- `trace_integrity` — task_id + capabilities_used 存在
- `error_free` — 无未预期错误（E_TIMEOUT/E_BLOCKED 除外）

**决策**：PASS / FAIL(causes[]) / RETRY(cause)

### CheckpointManager

失败恢复，不整体重来：

```python
cm = CheckpointManager("task-xxx")
cm.save("code_analyzer", result)    # 每步完成时
cm.last_checkpoint()               # 重试时恢复
cm.cleanup()                       # 成功后清理
```

---

## 📁 目录结构

```
deepin-agent-teams/
├── agents/
│   ├── task_state_machine.py  # 状态机引擎（P0-1）
│   ├── verifier.py            # 独立质检员（P0-2）
│   ├── orchestrator_v3.py     # 编排器（状态机+Verifier驱动）
│   ├── model_router.py        # 多模型路由（MiniMax + ERNIE）
│   ├── worker_base.py         # Worker 基类（14 种能力）
│   ├── worker_v2.py           # Worker 主循环
│   ├── registry.py            # Agent 注册中心
│   └── lead.py / researcher.py / coder.py  # 各型 Agent
├── perception/                # 环境感知层（截图/OCR/剪贴板/D-Bus）
├── scenarios/                 # 四大场景（邮件/诊断/代码/文献）
├── gui/                       # PyQt5 交互界面
├── tools/
│   ├── checkpoint_manager.py  # 检查点管理
│   ├── analyze_traces.py      # Trace 分析工具
│   └── analyze_capabilities.py # 能力正交化分析
├── docs/                      # 架构/技术/质量文档
├── tests/                     # 测试脚本
└── main.py                    # CLI/GUI 入口
```

---

## 🚀 快速开始

### 运行编排器

```bash
cd ~/.openclaw/workspace/deepin-agent-teams
python3 agents/orchestrator_v3.py
```

### 作为模块调用

```python
from agents.orchestrator_v3 import OrchestratorV3

orch = OrchestratorV3(verbose=True)
result = orch.run(
    "分析 deepin-agent-teams 项目的代码结构",
    project_path="/root/.openclaw/workspace/deepin-agent-teams"
)
print(result["final_report"])
```

### 启动 GUI

```bash
python3 main.py --gui
```

---

## 🧪 测试

```bash
# 状态机测试
python3 agents/task_state_machine.py

# Verifier 测试
python3 agents/verifier.py

# Checkpoint 测试
python3 tools/checkpoint_manager.py

# Trace 分析
python3 tools/analyze_traces.py
```

---

## 📋 赛题完成度

| 赛题要求 | 实现 | 状态 |
|---------|------|------|
| 基于 deepin 25 + 文心 API | `perception/` + `model_router.py` | ✅ |
| 状态机驱动（停止条件写死） | `task_state_machine.py` | ✅ |
| 独立 Verifier（≠ 执行者） | `verifier.py` | ✅ |
| 多模型路由（≥2款） | `model_router.py`（MiniMax + ERNIE） | ✅ |
| 任务可追溯（trace） | `/tmp/deepin_traces/*.jsonl` | ✅ |
| 检查点恢复（失败不整体重来） | `checkpoint_manager.py` | ✅ |
| 多智能体协作 | `orchestrator_v3.py` + `sessions_spawn` | ✅ |
| 四大场景完整 | `scenarios/` | ✅ |
| GUI 交互 | `main.py --gui` | ✅ |
| 部署文档可复现 | `deepin25_deploy.sh` | ✅ |

---

## 📄 文档

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — 系统架构详解
- [TECH_DECISIONS.md](docs/TECH_DECISIONS.md) — 技术选型决策
- [QUALITY.md](docs/QUALITY.md) — 质量标准
- [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md) — 优化执行计划
- [RFC.md](RFC.md) — 技术请求评论文档

---

## 🔧 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 主语言 | Python 3 | — |
| 大模型 | MiniMax（主）+ ERNIE（备） | `model_router.py` |
| OCR | PaddleOCR | 中文识别 |
| GUI | PyQt5 | deepin 25 适配 |
| 文件锁 | fcntl.flock | 多进程安全 |
| 多 Agent | OpenClaw `sessions_spawn` | 进程隔离 |