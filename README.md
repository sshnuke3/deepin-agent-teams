# deepin-agent-teams

> 🤖 **多智能体协作系统** — [第十期飞桨黑客松](https://www.deepin.org/zh/paddle-hackathon-10th-deepin/) · 统信 × 百度飞桨 · [进阶任务 #27](https://github.com/PaddlePaddle/community/blob/master/hackathon/hackathon_10th/%E3%80%90Hackathon_10th%E3%80%91%E6%96%87%E5%BF%83%E5%90%88%E4%BD%9C%E4%BC%99%E4%BC%B4%E4%BB%BB%E5%8A%A1%E5%90%88%E9%9B%86.md#%E7%BB%9F%E4%BF%A1deepin-agent-teams-%E6%99%BA%E8%83%BD%E4%BD%93%E5%9B%A2%E9%98%9F%E5%8D%8F%E4%BD%9C%E7%B3%BB%E7%BB%9F)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-deepin%2025-orange?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Hackathon](https://img.shields.io/badge/Hackathon-10th%20PaddlePaddle-red?style=flat-square)

> 在 deepin 25 操作系统上，基于 OpenClaw 多智能体框架和文心大模型 API，实现复杂任务的自动化拆解与协同执行。

---

## 🎯 项目简介

本项目实现了**多智能体（Multi-Agent）协作系统**，在 deepin 25 桌面环境中，通过自然语言交互完成复杂任务的自动拆解、多 Agent 协同执行和结果汇总。

**核心架构**：三角架构（状态机引擎 + 独立 Verifier + Worker 池）

**模型方案**：仅使用百度文心系列（ernie-lite + ernie-3.5），无任何第三方模型。

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
│  data/traces/  →  验证清单(11项)  ←  data/checkpoints/          │
│  (JSONL)                              (SQLite)                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              安全防线（agents/ 三层防护）                         │
│                                                                 │
│  input_scanner ─→ 注入攻击/PII/危险指令检测                      │
│  security_config ─→ 工具白名单 + 危险操作正则 + 四值确认          │
│  progress_detector ─→ 循环推诿检测 + 连续重复自动熔断             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  模型层（百度文心）                                               │
│                                                                 │
│  model_router ──13种task_type路由──→ ernie-3.5（复杂推理）       │
│                                    → ernie-lite（轻量快速）      │
│  降级链：ernie-3.5 → ernie-lite → 本地 fallback                  │
│  ContextAwareLLM ──响应缓存──→ 低温任务相同输入自动命中           │
│  Token预算 ──per-state/per-phase──→ 超预算自动降级 strong→lite   │
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

**每次跳转写 trace** → `data/traces/{task_id}.jsonl`

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

### 检查点持久化（CheckpointManager / checkpoint.py）

SQLite 持久化，失败恢复不整体重来：

```python
from agents.checkpoint import CheckpointManager

cm = CheckpointManager()
cm.save("task-xxx", "code_analyzer", result, state="RUNNING", phase="analyze")  # 保存
checkpoint = cm.load("task-xxx")                                                  # 恢复
cm.cleanup(max_age_hours=24)                                                      # 清理
```

存储位置：`data/checkpoints/checkpoints.db`

### 进展检测器（ProgressDetector）

防止 Agent 间循环推诿：

```python
from agents.progress_detector import ProgressDetector

detector = ProgressDetector(max_history=10, repeat_threshold=3)
detector.record(output, token_used=150, phase="analyze")
if detector.is_stalled():
    # 连续 3 次输出相同 → 熔断，切换策略或终止
    ...
```

### 输入扫描器（InputScanner）

Agent 间通信安全扫描，在 Agent A 的输出注入 Agent B 之前检查：

- **注入攻击检测**：prompt injection 模式匹配
- **PII 泄露检测**：手机号/身份证/密码/token 等敏感信息
- **危险指令检测**：伪装系统提示、危险 shell 命令

```python
from agents.input_scanner import InputScanner

scanner = InputScanner()
result = scanner.scan(agent_output)
if not result.safe:
    # 阻断注入内容，记录威胁类型
    print(f"威胁: {result.threat_type} ({result.threat_level})")
```

---

## 🛡️ 安全体系

四层纵深防御：

| 层级 | 组件 | 防护内容 |
|------|------|---------|
| **L1 输入扫描** | `input_scanner.py` | 注入攻击 / PII / 危险指令检测 |
| **L2 工具白名单** | `security_config.py` | 工具调用合规检查，正则匹配危险操作 |
| **L3 确认机制** | `ConfirmationGuard` | 四值确认（YES/NO/CANCEL/MODIFY），危险操作需人工审批 |
| **L4 隐私保护** | `perception/privacy_guard.py` | PII 脱敏，屏幕内容过滤 |

### 模型路由（model_router.py）

13 种 task_type 自动路由到 lite 或 strong：

| task_type | 模型 | 场景 |
|-----------|------|------|
| intent / summary / classify / entity / translate / general | ernie-lite | 轻量快速 |
| email / diagnosis / code / literature / reasoning / task_plan / report | ernie-3.5 | 复杂推理 |

- 降级链：ernie-3.5 → ernie-lite → 本地 fallback
- 每次调用超时 30s，超时自动切换
- 记录每步调用结果（成功/失败/耗时/token）
- `verbose` 参数控制日志输出（已修正）

### Token 预算管理

- **per-state 预算**：PLANNING 800 / RUNNING 动态 / VERIFIED 不限
- **per-phase 预算**：每个执行阶段独立限额
- **动态预算**：`budget = base + per_step × remaining_steps`
- **超预算降级**：strong → lite 自动切换

### Prompt Caching（ContextAwareLLM）

`context_manager.py` 内置响应缓存：

- 低温任务（temperature < 0.3）相同输入自动命中缓存
- 缓存 TTL 300 秒，上限 200 条
- LRU 淘汰策略，自动清理过期条目

---

## 📁 目录结构

```
deepin-agent-teams/
├── agents/
│   ├── orchestrator.py        # 统一编排器（fan_out 并行 + aggregate 聚合）
│   ├── orchestrator_v3.py     # v3 编排器（原版）
│   ├── orchestrator_v4.py     # v4 编排器（MCP 驱动）
│   ├── task_state_machine.py  # 八状态状态机引擎（含 PLANNING）
│   ├── verifier.py            # 独立质检员（11 项检查）
│   ├── planner.py             # Plan-and-Solve 规划模块
│   ├── context_manager.py     # 上下文窗口管理 + 子Agent摘要回传 + ContextAwareLLM 缓存
│   ├── prompt_loader.py       # Prompt 模板管理（热加载 + A/B 测试）
│   ├── debate.py              # 辩论模式（Pro/Con/Judge）
│   ├── scenario_classifier.py # 场景识别器（三道筛子 + 动态路由）
│   ├── otel_tracer.py         # OpenTelemetry 可观测性封装
│   ├── model_router.py        # 文心模型路由（ernie-lite + ernie-3.5，13种task_type）
│   ├── registry.py            # Agent 注册中心（Agent Card 自动发现）
│   ├── security_config.py     # 安全配置（白名单/预算/确认/动态预算）
│   ├── worker_base.py         # Worker 基类（14 种能力）
│   ├── checkpoint.py          # SQLite 检查点持久化（save/load/resume/cleanup）
│   ├── progress_detector.py   # 进展检测器（防循环推诿，连续重复自动熔断）
│   ├── input_scanner.py       # Agent间通信安全扫描（注入/PII/危险指令）
│   ├── hands_interface.py     # Brain/Hands 分离架构（LocalHands/DockerHands/MockHands）
│   ├── agent_cards/           # Agent Card 定义（A2A 协议）
│   │   └── 7 个 .json 文件
│   └── lead.py / researcher.py / coder.py  # 各型 Agent
├── data/
│   ├── traces/                # JSONL 任务追踪（每任务一文件）
│   └── checkpoints/           # SQLite 检查点数据库
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
│   ├── checkpoint_manager.py  # 检查点管理（旧版）
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
    ├── test_e2e.py            # 集成测试
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
# 集成测试
python3 tests/test_e2e.py

# 性能基准测试（8 模块）
python3 tests/benchmark.py

# 各模块单元测试
python3 agents/planner.py           # Planner
python3 agents/task_state_machine.py # 状态机
python3 agents/verifier.py          # Verifier
python3 agents/context_manager.py   # 上下文管理 + 缓存
python3 agents/prompt_loader.py     # Prompt 模板
python3 agents/debate.py            # 辩论模式
python3 agents/scenario_classifier.py # 场景识别
python3 agents/otel_tracer.py       # OTel 封装
python3 agents/checkpoint.py        # 检查点持久化
python3 agents/progress_detector.py # 进展检测
python3 agents/input_scanner.py     # 输入扫描
```

---

## 📋 赛题完成度

| 赛题要求 | 实现 | 状态 |
|---------|------|------|
| 基于 deepin 25 + 文心 API | `perception/` + `model_router.py` | ✅ |
| 状态机驱动（停止条件写死） | `task_state_machine.py` | ✅ |
| 独立 Verifier（≠ 执行者） | `verifier.py` | ✅ |
| 多模型路由（≥2款） | `model_router.py`（ernie-lite + ernie-3.5，13种task_type） | ✅ |
| 任务可追溯（trace） | `data/traces/*.jsonl` | ✅ |
| 检查点恢复（失败不整体重来） | `agents/checkpoint.py`（SQLite 持久化） | ✅ |
| 多智能体协作 | `orchestrator.py` + `fan_out` 并行扇出 + `debate.py` 辩论模式 | ✅ |
| MCP 工具解耦 | `orchestrator.py` + `mcp_servers/` + `tool_registry.py` | ✅ |
| Plan-and-Solve | `planner.py` + PLANNING 状态 + TodoManager | ✅ |
| 上下文管理 | `context_manager.py` 滑动窗口 + 子Agent摘要回传 + 缓存 | ✅ |
| Prompt 模板 | `prompt_loader.py` 热加载 + A/B 测试 | ✅ |
| 场景识别 | `scenario_classifier.py` 三道筛子 + 动态模型路由 | ✅ |
| A2A 协议 | Agent Card 自动发现 + AgentRegistry | ✅ |
| OpenTelemetry | `otel_tracer.py` + GenAI 语义约定 | ✅ |
| 四大场景完整 | `scenarios/` | ✅ |
| GUI 交互 | `main.py --gui` | ✅ |
| 部署文档可复现 | `deepin25_deploy.sh` | ✅ |
| 安全防护 | `input_scanner.py` + `security_config.py` + `ConfirmationGuard` | ✅ |
| 防循环推诿 | `progress_detector.py`（连续重复自动熔断） | ✅ |
| Docker 沙箱执行 | `hands_interface.py`（DockerHands 完整实现） | ✅ |

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
| 主语言 | Python 3 | 3.10+ |
| 大模型 | 百度文心 ernie-lite + ernie-3.5 | `model_router.py`，13种task_type自动路由 |
| 模型降级 | 三级降级链 | ernie-3.5 → ernie-lite → 本地 fallback |
| Prompt 缓存 | ContextAwareLLM | 低温任务相同输入自动命中，TTL 300s |
| Token 预算 | per-state / per-phase | 超预算自动降级 strong→lite |
| 检查点持久化 | SQLite | `agents/checkpoint.py`，支持任务恢复 |
| 工具协议 | MCP（JSON-RPC over stdio） | `mcp_servers/mcp_protocol.py` |
| 可观测性 | OpenTelemetry（降级：metrics_collector） | `otel_tracer.py` |
| 并发模型 | concurrent.futures ThreadPoolExecutor | `orchestrator.py` |
| OCR | PaddleOCR | 中文识别 |
| GUI | PyQt5 | deepin 25 适配 |
| 文件锁 | fcntl.flock | 多进程安全 |
| 多 Agent | OpenClaw `sessions_spawn` | 进程隔离 |
| 安全扫描 | input_scanner + security_config | 注入/PII/危险指令/工具白名单 |
| 执行沙箱 | DockerHands | Brain/Hands 分离，容器化隔离 |
