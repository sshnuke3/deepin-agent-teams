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
│                  感知桥接层（gui/perception_bridge.py）           │
│  剪贴板轮询(2s) · 窗口轮询(3s) · 系统监控(10s)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               决策引擎（gui/decision_engine.py）                  │
│  置信度评估 · 风险分级(low/medium/high) · 自动/手动判断           │
│  → confidence>0.8+low=自动执行 · 0.5~0.8=等确认 · high=只告警    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               自主执行器（gui/auto_executor.py）                  │
│  低风险自动执行：翻译/总结/代码分析/诊断                          │
│  结果推送到对话窗口（绿色边框）· 写入剪贴板                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               反馈闭环（gui/feedback_tracker.py）                 │
│  用户行为追踪(accepted/dismissed/ignored/blocked)                │
│  → 动态调整置信度 · 抑制被频繁拒绝的建议类型                      │
│  → 悬浮球变色+呼吸灯 · 对话窗口弹出 · 托盘通知                   │
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
│                  🔌 MCP 工具层（mcp_servers/）                   │
│                                                                 │
│  OrchestratorV4 ──MCP Client──→ model-service  (模型调用)       │
│                 ──MCP Client──→ file-service   (文件操作)       │
│                 ──MCP Client──→ system-service (系统操作)       │
│                 ──MCP Client──→ [自定义Server] (零侵入扩展)     │
│                                                                 │
│  协议：JSON-RPC over stdio · 纯 Python 实现 · 无外部依赖        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    多智能体协作层（agents/）                      │
│                                                                 │
│  Lead Agent ← 任务拆解 → OrchestratorV4 ← 编排 → Worker 池      │
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
PENDING → CLAIMED → PLANNING → RUNNING → VERIFIED → COMPLETED
                                  ↓ FAIL
                                RETRY（≤3次）
                                  ↓ 超次
                                FAILED
```

| 状态 | 说明 | 关键规则 |
|------|------|---------|
| PENDING | 入队，未分配 | — |
| CLAIMED | Worker 认领 | worker_id 存在 |
| PLANNING | 生成执行计划 | 纯推理，工具白名单为空，Token 预算 800 |
| RUNNING | 执行中 | start_time 记录 |
| VERIFIED | Verifier 通过 | verdict == PASS |
| COMPLETED | 流程终结 | 自动完成 |
| RETRY | 需重做 | FAIL 且 retry < 3 |
| FAILED | 不可恢复 | 超时 / 重试耗尽 |

**每次跳转写 trace** → `/tmp/deepin_traces/{task_id}.jsonl`

### 独立 Verifier

Verifier ≠ 执行者，独立世界观，验收标准是清单（11 项检查）：

**基础检查（1-4）：**
- `deliverable_exists` — 交付物非空
- `functional_correctness` — 按 task type 分叉验收
- `trace_integrity` — task_id + capabilities_used 存在
- `error_free` — 无未预期错误（E_TIMEOUT/E_BLOCKED 除外）

**安全检查（5-7）：**
- `tool_compliance` — 工具白名单合规
- `token_budget` — Token 预算合规
- `dangerous_ops_confirmed` — 危险操作确认

**规划检查（8-9）：**
- `plan_completeness` — 计划中所有步骤标记完成
- `plan_coherence` — 计划依赖关系自洽（无循环依赖）

**上下文检查（10-11）：**
- `context_overflow` — 上下文 token 未超出窗口
- `summary_quality` — 子Agent摘要包含关键信息

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
│   ├── orchestrator.py        # 统一编排器（fan_out 并行 + aggregate 聚合）
│   ├── task_state_machine.py  # 八状态状态机引擎（含 PLANNING）
│   ├── verifier.py            # 独立质检员（11 项检查）
│   ├── planner.py             # Plan-and-Solve 规划模块
│   ├── context_manager.py     # 上下文窗口管理 + 子Agent摘要回传
│   ├── prompt_loader.py       # Prompt 模板管理（热加载 + A/B 测试）
│   ├── debate.py              # 辩论模式（Pro/Con/Judge）
│   ├── scenario_classifier.py # 场景识别器（三道筛子 + 动态路由）
│   ├── otel_tracer.py         # OpenTelemetry 可观测性封装
│   ├── model_router.py        # 多模型路由（ernie-lite + ernie-3.5 + MiniMax）
│   ├── registry.py            # Agent 注册中心（Agent Card 自动发现）
│   ├── security_config.py     # 安全配置（白名单/预算/确认/动态预算）
│   ├── worker_base.py         # Worker 基类（14 种能力）
│   ├── agent_cards/           # Agent Card 定义（A2A 协议）
│   │   └── 7 个 .json 文件
│   └── lead.py / researcher.py / coder.py  # 各型 Agent
├── prompts/                   # Prompt 模板（热加载，10 个 .md 文件）
│   ├── planner/               # plan_generation.md
│   ├── orchestrator/          # decompose.md / integrate.md / system.md
│   ├── content_creator/       # email.md / summary.md
│   ├── information_collector/ # summarize.md
│   └── agents/                # researcher.md / coder.md / general.md
├── mcp_servers/               # MCP 工具服务
│   ├── mcp_protocol.py        # 轻量 MCP 协议实现（纯 Python）
│   ├── model_server.py        # 模型 MCP Server
│   ├── file_server.py         # 文件 MCP Server
│   └── system_server.py       # 系统 MCP Server
├── tools/
│   ├── tool_registry.py       # 统一工具注册表
│   ├── checkpoint_manager.py  # 检查点管理
│   ├── analyze_traces.py      # Trace 分析工具
│   └── analyze_capabilities.py # 能力正交化分析
├── perception/                # 环境感知层（截图/OCR/剪贴板/D-Bus）
├── scenarios/                 # 四大场景（邮件/诊断/代码/文献）
├── gui/                       # PyQt5 交互界面
│   ├── main_gui.py            # GUI 入口
│   ├── floating_ball.py       # 悬浮球（感知状态指示）
│   ├── chat_window.py         # 对话窗口（主动建议+自动结果）
│   ├── tray_icon.py           # 系统托盘
│   ├── perception_bridge.py   # 感知桥接层（轮询+信号分发）
│   ├── decision_engine.py     # 决策引擎（置信度+风险分级）
│   ├── auto_executor.py       # 自主执行器（低风险自动执行）
│   ├── feedback_tracker.py    # 反馈闭环（用户行为追踪）
│   └── styles.py              # 样式定义
├── docs/                      # 架构/技术/质量文档
└── tests/
    ├── test_e2e.py            # 集成测试（41/41 通过）
    └── benchmark.py           # 性能基准测试（8 模块）
```

---

## 🚀 快速开始

### 运行编排器（v3 — 原版）

```bash
cd /path/to/deepin-agent-teams
python3 agents/orchestrator_v3.py
```

### 运行编排器（v4 — MCP 驱动）

```bash
cd /path/to/deepin-agent-teams
python3 agents/orchestrator_v4.py
```

### 作为模块调用

```python
# v4（推荐）
from agents.orchestrator_v4 import OrchestratorV4

orch = OrchestratorV4(verbose=True)
orch.auto_connect_servers()  # 自动连接所有 MCP Server
result = orch.run(
    "分析 deepin-agent-teams 项目的代码结构",
    project_path="/root/.openclaw/workspace/deepin-agent-teams"
)
print(result["final_report"])

# v3（兼容）
from agents.orchestrator_v3 import OrchestratorV3
orch = OrchestratorV3(verbose=True)
```

### 启动 GUI

```bash
python3 main.py --gui
```

### 单独测试 MCP Server

```bash
# 每个 Server 可独立运行和测试
python3 mcp_servers/model_server.py --test
python3 mcp_servers/file_server.py --test
python3 mcp_servers/system_server.py --test
```

---

## 🧪 测试

```bash
# 集成测试（41/41 通过）
python3 tests/test_e2e.py

# 性能基准测试（8 模块）
python3 tests/benchmark.py

# 各模块单元测试
python3 agents/planner.py           # Planner（9/9）
python3 agents/task_state_machine.py # 状态机（12/12）
python3 agents/verifier.py          # Verifier（13/13）
python3 agents/context_manager.py   # 上下文管理（11/11）
python3 agents/prompt_loader.py     # Prompt 模板（12/12）
python3 agents/debate.py            # 辩论模式（10/10）
python3 agents/scenario_classifier.py # 场景识别（15/15）
python3 agents/otel_tracer.py       # OTel 封装（15/15）
```

---

## 📋 赛题完成度

| 赛题要求 | 实现 | 状态 |
|---------|------|------|
| 基于 deepin 25 + 文心 API | `perception/` + `model_router.py` | ✅ |
| 状态机驱动（停止条件写死） | `task_state_machine.py` | ✅ |
| 独立 Verifier（≠ 执行者） | `verifier.py` | ✅ |
| 多模型路由（≥2款） | `model_router.py`（ernie-lite + ernie-3.5） | ✅ |
| 任务可追溯（trace） | `/tmp/deepin_traces/*.jsonl` | ✅ |
| 检查点恢复（失败不整体重来） | `checkpoint_manager.py` | ✅ |
| 多智能体协作 | `orchestrator.py` + `fan_out` 并行扇出 + `debate.py` 辩论模式 | ✅ |
| MCP 工具解耦 | `orchestrator.py` + `mcp_servers/` + `tool_registry.py` | ✅ |
| Plan-and-Solve | `planner.py` + PLANNING 状态 + TodoManager | ✅ |
| 上下文管理 | `context_manager.py` 滑动窗口 + 子Agent摘要回传 | ✅ |
| Prompt 模板 | `prompt_loader.py` 热加载 + A/B 测试 | ✅ |
| 场景识别 | `scenario_classifier.py` 三道筛子 + 动态模型路由 | ✅ |
| A2A 协议 | Agent Card 自动发现 + AgentRegistry | ✅ |
| OpenTelemetry | `otel_tracer.py` + GenAI 语义约定 | ✅ |
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
| 大模型 | ernie-lite + ernie-3.5 + MiniMax | `model_router.py` |
| 工具协议 | MCP（JSON-RPC over stdio） | `mcp_servers/mcp_protocol.py` |
| 可观测性 | OpenTelemetry（降级：metrics_collector） | `otel_tracer.py` |
| 并发模型 | concurrent.futures ThreadPoolExecutor | `orchestrator.py` |
| OCR | PaddleOCR | 中文识别 |
| GUI | PyQt5 | deepin 25 适配 |
| 文件锁 | fcntl.flock | 多进程安全 |
| 多 Agent | OpenClaw `sessions_spawn` | 进程隔离 |