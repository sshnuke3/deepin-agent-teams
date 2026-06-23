# deepin Agent Teams — 架构文档

> PaddlePaddle 黑客马拉松第10期 · 统信 deepin Agent Teams 赛题  
> 最后更新：2026-06-10

---

## 目录

1. [项目概述](#1-项目概述)
2. [模块结构](#2-模块结构)
3. [核心架构](#3-核心架构)
4. [统一编排器](#4-统一编排器)
5. [MCP 工具层](#5-mcp-工具层)
6. [Skills 模块](#6-skills-模块)
7. [安全架构](#7-安全架构)
8. [隐私保护](#8-隐私保护)
9. [模型路由](#9-模型路由)
10. [场景识别与动态路由](#10-场景识别与动态路由)
11. [可观测性](#11-可观测性)
12. [技术栈](#12-技术栈)

---

## 1. 项目概述

deepin Agent Teams 是面向 deepin 25 桌面操作系统的多智能体团队协作系统。系统通过多模态感知融合识别用户意图，经统一编排器调度三个专职智能体协同完成任务，涵盖智能邮件助手、系统问题诊断等核心场景。

### 架构演进

| 版本 | 核心特性 | 架构模式 |
|------|---------|---------|
| v1 | 基础三角架构：单一 Orchestrator + 两个 Agent + 基础工具 | 线性调用 |
| v2 | 安全增强 + 质量保障 + Brain/Hands 分离 | 双层分离 |
| **v3（当前）** | **统一编排器 + Skills 模块 + 隐私保护 + MCP 协议** | **状态机驱动** |

v3 版本合并了 v3/v4/prod 三个编排器变体的最佳特性，引入 Skills-first 路由、隐私守护模块和完整 MCP 工具层。

---

## 2. 模块结构

```
deepin-agent-teams/
├── agents/                          # 智能体与编排核心
│   ├── orchestrator.py              # 统一编排器（含 fan_out 并行扇出 + aggregate 聚合）
│   ├── task_state_machine.py        # 八状态有限状态机（含 PLANNING 状态）
│   ├── verifier.py                  # 11 项独立验证检查
│   ├── security_config.py           # 安全配置：白名单/预算/确认/动态预算
│   ├── planner.py                   # Plan-and-Solve 规划模块（TodoManager + nag reminder）
│   ├── context_manager.py           # 上下文窗口管理（滑动窗口 + 子Agent摘要回传）
│   ├── prompt_loader.py             # Prompt 模板管理（热加载 + A/B 测试）
│   ├── debate.py                    # 辩论模式（Pro/Con/Judge）
│   ├── scenario_classifier.py       # 场景识别器（三道筛子 + 动态模型路由）
│   ├── otel_tracer.py               # OpenTelemetry 可观测性封装
│   ├── model_router.py              # 双文心模型路由器
│   ├── registry.py                  # Agent 注册中心（支持 Agent Card 自动发现）
│   ├── base.py                      # 智能体基类
│   ├── system_operator.py           # 系统运维智能体
│   ├── information_collector.py     # 信息采集智能体
│   ├── content_creator.py           # 内容创作智能体
│   ├── worker_base.py               # 通用 Worker 基类
│   ├── metrics_collector.py         # 轻量级指标收集器
│   ├── hands_interface.py           # Brain/Hands 分离接口
│   ├── eval_runner.py               # 离线评测框架
│   ├── agent_cards/                 # Agent Card 定义（A2A 协议）
│   │   ├── system_operator.json
│   │   ├── content_creator.json
│   │   ├── information_collector.json
│   │   ├── coder.json
│   │   ├── researcher.json
│   │   ├── lead.json
│   │   └── general_worker.json
│   └── ...                          # 其他智能体模块
│
├── prompts/                         # Prompt 模板（热加载）
│   ├── planner/plan_generation.md
│   ├── orchestrator/
│   │   ├── decompose.md
│   │   ├── integrate.md
│   │   └── system.md
│   ├── content_creator/
│   │   ├── email.md
│   │   └── summary.md
│   ├── information_collector/summarize.md
│   └── agents/
│       ├── researcher.md
│       ├── coder.md
│       └── general.md
│
├── skills/                          # Skills 模块
│   └── __init__.py                  # SkillDef / SkillRegistry / SkillExecutor（778 行）
│
├── perception/                      # 环境感知层（10 个模块）
│   ├── screen_capture.py            # 屏幕截图
│   ├── screen_ocr.py                # OCR 文字识别
│   ├── clipboard_monitor.py         # 剪贴板监控
│   ├── window_manager.py            # 窗口元数据
│   ├── system_monitor.py            # 系统资源监控
│   ├── deepin_dbus.py               # D-Bus DDE 集成（615 行）
│   ├── context_engine.py            # 多模态融合意图引擎（454 行）
│   ├── behavior_tracker.py          # 行为轨迹追踪
│   ├── privacy_guard.py             # 隐私数据守护
│   └── resource_guard.py            # 资源使用监控
│
├── mcp_servers/                     # MCP 工具服务器
│   └── mcp_protocol.py              # 纯 Python JSON-RPC over stdio 实现
│
├── tools/                           # 工具实现
│   ├── tool_registry.py             # 工具注册中心
│   ├── checkpoint_manager.py        # Checkpoint 管理
│   ├── analyze_traces.py            # Trace 分析
│   ├── analyze_capabilities.py      # 能力分析
│   └── mcp_adapter.py               # MCP 适配器
│
├── scenarios/                       # 核心场景
│   ├── email_assistant.py           # 智能邮件助手
│   ├── system_doctor.py             # 系统问题诊断
│   ├── code_analysis.py             # 代码分析
│   └── literature_review.py         # 文献综述
│
├── gui/                             # PyQt5 图形界面
│   ├── floating_ball.py             # 浮动球
│   ├── chat_window.py               # 聊天窗口
│   ├── tray_icon.py                 # 系统托盘
│   ├── auto_executor.py             # 自动执行器
│   ├── decision_engine.py           # 决策引擎
│   ├── feedback_tracker.py          # 反馈追踪器
│   ├── main_gui.py                  # 主界面
│   ├── perception_bridge.py         # 感知桥接
│   └── styles.py                    # 样式定义
│
├── main.py                          # 入口
└── config.py                        # 全局配置
```

代码统计：~26,500 行 Python，81 个文件；~230 行 JSON（8 个文件）；154 行 Prompt 模板（10 个文件）。

---

## 3. 核心架构

### 3.1 八状态有限状态机

所有任务生命周期由 `TaskStateMachine` 管理，状态转移规则硬编码：

```
PENDING ──▶ CLAIMED ──▶ PLANNING ──▶ RUNNING ──▶ VERIFIED ──▶ COMPLETED
              │            │            │           │
              │            │            │           ▼
              │            │            │        FAILED
              ▼            ▼            ▼
           FAILED       FAILED       RETRY ──▶ PENDING
```

**PLANNING 状态**（新增）：Worker 认领后必须先生成结构化执行计划才能进入 RUNNING。
- 工具白名单：空（纯推理，不调用任何工具）
- Token 预算：800
- 超时：30秒，超时自动降级
- Planner 模块：生成步骤列表 + TodoManager 跟踪进度 + nag reminder

RUNNING 状态内部细分为四个子阶段：

```
RUNNING:
  plan ──▶ gather ──▶ analyze ──▶ execute
```

> 注：从 PLANNING 进入 RUNNING 时当前阶段初始化为 `gather`（`plan` 阶段已在 PLANNING 完成），从其他状态进入时初始化为 `plan`

### 3.2 每阶段工具白名单

| 状态/子阶段 | 允许的工具 |
|--------|--------|
| PLANNING | （无，纯推理） |
| RUNNING:plan | （无，纯推理） |
| RUNNING:gather | file_reader, dir_scanner, code_analyzer, ast_parser, syntax_checker, dependency_analyzer, git_analyzer, web_search, web_fetcher |
| RUNNING:analyze | 所有只读工具 + code_analyzer, ast_parser, syntax_checker, dependency_analyzer |
| RUNNING:execute | 所有只读工具 + file_writer, shell_executor, process_manager, markdown_writer, doc_generator |

### 3.3 每阶段 Token 预算

| 子阶段 | Token 预算 |
|--------|-----------|
| plan | 500 |
| gather | 2000 |
| analyze | 2000 |
| execute | 1500 |

### 3.4 验证器（Verifier）

任务完成后由 Verifier 执行 11 项独立检查，全部通过才标记 COMPLETED：

**基础检查（1-4）：**
1. **deliverable_exists** — 交付物存在
2. **functional_correctness** — 功能正确性（按 task type 分叉）
3. **trace_integrity** — trace 字段完整
4. **error_free** — 无异常错误标记

**安全检查（5-7）：**
5. **tool_compliance** — 工具白名单合规（状态/阶段级别）
6. **token_budget** — Token 预算合规（动态计算）
7. **dangerous_ops_confirmed** — 危险操作确认

**规划检查（8-9）：**
8. **plan_completeness** — 计划中所有步骤是否标记完成
9. **plan_coherence** — 计划步骤依赖关系是否自洽（无循环依赖）

**上下文检查（10-11）：**
10. **context_overflow** — 上下文 token 是否超出窗口
11. **summary_quality** — 子Agent摘要是否包含关键信息（非空、非过长）

### 3.5 确认守卫（Confirming Guard）

以下操作在执行前必须获得用户显式确认：

- `shell` 中包含 `rm`、`kill`、`systemctl`、`apt`、`dpkg`
- `package` 中的 `remove`、`purge`
- `service_manage` 中的 `stop`、`restart`、`disable`
- `file_write` 目标路径包含 `/etc/`、`/var/`、`/usr/`

---

## 4. 统一编排器

`agents/orchestrator.py`（1326 行）是合并了 v3/v4/prod 三个变体后的统一编排器。

### 4.1 两种执行模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| **tools** | 通过 MCP ToolRegistry 调用工具 | 标准工具调用（shell、file、search） |
| **workers** | 子进程 Worker 池模式 | 长时间运行的后台任务 |

```python
class OrchestratorMode(Enum):
    TOOLS   = "tools"    # MCP ToolRegistry
    WORKERS = "workers"  # subprocess pool
```

### 4.2 核心流程

```
execute_task(task)
  │
  ├── 1. PENDING → CLAIMED: 选择 Agent/工具
  ├── 2. CLAIMED → PLANNING: 生成结构化执行计划（Planner）
  ├── 3. PLANNING → RUNNING: 进入子阶段循环
  │     ├── gather: 采集信息
  │     ├── analyze: 分析结果
  │     └── execute: 执行操作
  ├── 4. RUNNING → VERIFIED: 11 项验证检查
  ├── 5. VERIFIED → COMPLETED (或 FAILED → retry)
  └── 全程 Trace 记录 + Checkpoint + OTel Span
```

### 4.3 并行扇出（fan_out）

新增 `fan_out()` 方法，支持并行执行多个子任务：

```python
results = orchestrator.fan_out(tasks, max_workers=4)
merged = orchestrator.aggregate(results, strategy="concat")
```

支持 4 种聚合策略：`concat`（拼接）、`vote`（投票）、`best`（取最高置信度）、`merge`（深度合并）。

### 4.4 辩论模式（Debate）

技术方案选型等决策场景使用辩论模式：

```python
debate = create_debate("用 React 还是 Vue？", model_router=router, max_rounds=2)
result = debate.run(topic, context)
# result.winner, result.decision, result.confidence
```

流程：Pro 论点 → Con 反驳 → Pro 回应 → Con 再反驳 → Judge 裁决

### 4.5 超时/重试/降级

- 每个子阶段独立超时（30s ~ 120s）
- 失败后可重试（默认 max_retries=2）
- Token 超预算自动终止并报告
- 模型调用失败自动降级（ernie-3.5 → ernie-lite）

---

## 5. MCP 工具层

系统采用 MCP（Model Context Protocol）协议实现工具层解耦。

### 5.1 协议规格

- 传输层：stdio（JSON-RPC 2.0）
- 纯 Python 实现，无外部依赖
- 支持 `initialize`、`tools/list`、`tools/call` 三个核心方法

### 5.2 注册的 MCP 工具

| 工具名 | 功能 |
|--------|------|
| shell_exec | 执行 Shell 命令 |
| file_read | 读取文件内容 |
| file_write | 写入文件 |
| search | 信息检索 |
| package_manage | APT 包管理 |
| dbus_call | D-Bus 方法调用 |

---

## 6. Skills 模块

`skills/__init__.py`（778 行）实现了基于能力的任务路由机制。

### 6.1 核心组件

```python
@dataclass
class SkillDef:
    name: str                    # 技能名称
    description: str             # 技能描述
    intent_pattern: str          # 意图匹配模式
    agent_name: str              # 负责的 Agent
    required_tools: List[str]    # 所需工具
    estimated_tokens: int        # 预估 Token
    timeout_sec: int = 120       # 超时
    priority: int = 5            # 优先级

class SkillRegistry:
    """技能注册中心 — 管理所有 SkillDef"""

class SkillExecutor:
    """技能执行器 — 匹配意图 → 选择 Skill → 调度 Agent → 执行"""
```

### 6.2 内置 Skills

| Skill | 意图 | Agent | 工具 |
|-------|------|-------|------|
| email.compose | 邮件撰写 | ContentCreator | clipboard_read, ocr |
| email.reply | 邮件回复 | ContentCreator | clipboard_read, ocr, file_read |
| system.diagnose | 系统诊断 | SystemOperator | shell, system_monitor, dbus_call |
| system.fix | 系统修复 | SystemOperator | shell, package, dbus_call |
| info.search | 信息检索 | InformationCollector | search, file_read, ocr |
| info.summarize | 信息摘要 | ContentCreator | file_read, clipboard_read |

### 6.3 Skill-first 路由

```
用户意图 → ContextEngine 识别
              │
              ▼
         SkillRegistry.match(intent)
              │
              ├── 匹配成功 → SkillExecutor.execute()
              │                  → Agent.execute(Task)
              │
              └── 匹配失败 → 回退到默认 Agent
```

---

## 7. 安全架构

### 7.1 四层安全机制

| 层级 | 机制 | 文件 |
|------|------|------|
| 工具白名单 | 每个 Agent 只能调用预定义的工具集 | security_config.py |
| Token 预算 | 每阶段/每任务独立 Token 上限 | security_config.py |
| 确认守卫 | 高危操作前强制用户确认 | security_config.py |
| 红队测试 | 19 种攻击向量覆盖 | red_team_tests.py |

### 7.2 工具白名单

```python
# 按状态定义工具白名单
STATE_TOOL_WHITELIST = {
    "PENDING":   [],                          # 无工具
    "CLAIMED":   [],                          # 无工具
    "PLANNING":  [],                          # 纯推理，无工具
    "RUNNING":   READONLY_TOOLS + WRITE_TOOLS, # 全部可用
    "VERIFIED":  [],                          # 无工具
    "COMPLETED": [],                          # 无工具
    "FAILED":    [],                          # 无工具
    "RETRY":     [],                          # 无工具
}

# 按 RUNNING 内部分阶段的工具白名单
RUNNING_PHASE_TOOLS = {
    "plan":    [],                            # 纯推理，无工具
    "gather":  READONLY_TOOLS,                # 信息收集：只读
    "analyze": READONLY_TOOLS + ANALYSIS_TOOLS, # 分析：只读 + 分析
    "execute": READONLY_TOOLS + WRITE_TOOLS,  # 执行：全部
}
```

### 7.3 红队攻击向量

覆盖 19 种攻击：prompt injection（3种）、tool bypass（2种）、token bypass（2种）、state bypass（2种）、confirm bypass（2种）、combined attacks（8种）。

---

## 8. 隐私保护

### 8.1 PrivacyGuard 模块

`perception/privacy_guard.py` 提供敏感数据检测与脱敏功能。

### 8.2 敏感数据类型

| 类型 | 正则模式 | 脱敏方式 |
|------|---------|---------|
| 身份证号 | `\d{17}[\dX]` | `[ID_CARD_MASKED]` |
| 手机号 | `1[3-9]\d{9}` | `[PHONE_MASKED]` |
| 邮箱地址 | `[\w.-]+@[\w.-]+\.\w+` | `[EMAIL_ADDR_MASKED]` |
| 银行卡号 | `\d{16,19}` | `[BANK_CARD_MASKED]` |
| 密码 | `(password|passwd|密码)\s*[:=]\s*\S+` | `[PASSWORD_MASKED]` |
| IP 地址 | `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` | `[IP_ADDR_MASKED]` |

### 8.3 审计日志

每次脱敏操作记录审计日志（时间戳、操作类型、脱敏条数、涉及类别），存储于本地 JSONL 文件。

---


## 9. 模型路由

系统采用双模型策略 + 动态路由：

| 模型 | 用途 | 触发条件 |
|------|------|---------|
| ERNIE-Lite | 快速意图分类、简单问答 | 任务复杂度 = simple |
| ERNIE-3.5 | 深度推理、代码生成、分析 | 任务复杂度 = complex |
| MiniMax | 第三方备选 | ERNIE 全部不可用时降级 |

### 9.1 静态路由（config.py MODEL_ROUTING 表）

| task_type | 模型级别 | 模型名 |
|-----------|---------|--------|
| intent / summary / classify / entity / translate | lite | ernie-lite |
| email / diagnosis / code / literature / reasoning / task_plan / report | strong | ernie-3.5 |

### 9.2 动态路由（DynamicModelRouter）

新增场景识别器（`scenario_classifier.py`）+ 动态模型路由：

```python
router = DynamicModelRouter(classifier=ScenarioClassifier())

# 基于用户输入
model = router.route("全面分析代码架构和性能瓶颈")  # → "strong"
model = router.route("帮我查一下天气")               # → "lite"

# 基于计划步数
model = router.route_from_plan(steps_count=5)        # → "strong"
```

三道筛子判断是否适合 Agent 化：
1. **模糊性筛**：输入是否有多种理解方式？
2. **跨系统筛**：是否需要多个工具/系统配合？
3. **多步骤筛**：是否需要分解为多个子步骤？

三道都不过 → 直接 LLM 对话，不进状态机。

---

## 10. 上下文管理

`context_manager.py` 提供滑动窗口 + 子Agent摘要回传能力。

### 10.1 滑动窗口

- 保留最近 K 轮完整对话（默认 10 轮）
- 早期对话压缩为摘要
- Token 计数器实时跟踪上下文 token 量
- 超过阈值（默认 20 轮）自动触发压缩

### 10.2 子Agent摘要回传

Worker 执行完毕后，只回传压缩摘要到父上下文：

```python
SubagentSummary(
    task_id="task-001",
    conclusion="发现 3 个潜在问题",
    key_findings=["函数 A 缺少异常处理"],
    duration_ms=1500,
)
```

### 10.3 动态 Token 预算

预算公式：`budget = base_budget + per_step_budget * remaining_steps`

---

## 11. Prompt 模板管理

`prompt_loader.py` 提供从文件加载 prompt + 热加载 + A/B 测试能力。

- **热加载**：修改 `.md` 文件后下次调用自动生效，无需重启
- **A/B 测试**：`loader.register_ab_test(path, ["v1", "v2"], weights=[0.7, 0.3])`
- **向后兼容**：PromptLoader 不可用时降级到硬编码 prompt

---

## 12. 可观测性

`otel_tracer.py` 封装 OpenTelemetry，提供统一的 trace 接口。

### 12.1 降级策略

OTel SDK 不可用时自动回退到 `metrics_collector.py`，API 签名一致。

### 12.2 关键埋点

| Span 名称 | 属性 | 说明 |
|-----------|------|------|
| task_execution | agent.task.id, agent.task.type | 整个任务执行 |
| llm_call | gen_ai.system, gen_ai.request.model | LLM 调用 |
| tool_call | agent.tool.name, agent.tool.params | 工具调用 |
| state_transition | agent.state.from, agent.state.to | 状态机跳转 |
| agent_loop | agent.loop.iteration | Agent Loop 迭代 |

### 12.3 GenAI 语义约定

使用 `gen_ai.*` 属性名（OpenLLMetry 兼容）：
- `gen_ai.system`: 模型提供方
- `gen_ai.request.model`: 模型名
- `gen_ai.operation.name`: 操作类型
- `gen_ai.usage.input_tokens`: 输入 token 数

---

## 13. Agent Card（A2A 协议）

每个 Agent 实现 `agent_card.json`，支持自动发现：

```json
{
  "name": "coder",
  "version": "1.0",
  "description": "代码分析智能体",
  "capabilities": ["code_analyzer", "ast_parser", "syntax_checker"],
  "agent_type": "coder",
  "security_level": "normal",
  "model_preference": "ernie-3.5"
}
```

`AgentRegistry.auto_discover()` 扫描 `agent_cards/` 目录，自动注册所有 Agent。

---

## 14. 技术栈

| 组件 | 技术选型 |
|------|---------|
| 编程语言 | Python 3.10+ |
| 桌面框架 | PyQt5 |
| 大模型 SDK | erniebot (百度 ERNIE) + MiniMax |
| OCR | PaddleOCR / Tesseract |
| 系统集成 | D-Bus (dbus-python / dbus-next) |
| 协议 | MCP — JSON-RPC 2.0 over stdio |
| 可观测性 | OpenTelemetry SDK（降级：metrics_collector） |
| 并发 | concurrent.futures + asyncio |
| 操作系统 | deepin 25 (Debian-based) |
| 桌面环境 | DDE (Deepin Desktop Environment) |
| 进程管理 | systemd |
| 包管理 | APT / dpkg |

---

> 本文档反映 v3（当前）架构状态。最后更新：2026-06-10。
