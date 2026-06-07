# deepin Agent Teams — 架构文档

> PaddlePaddle 黑客马拉松第10期 · 统信 deepin Agent Teams 赛题  
> 最后更新：2026-06-07

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
10. [技术栈](#10-技术栈)

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
│   ├── orchestrator.py              # 统一编排器（927 行，合并 v3/v4/prod）
│   ├── task_state_machine.py        # 七状态有限状态机（697 行）
│   ├── verifier.py                  # 七项独立验证检查（587 行）
│   ├── security_config.py           # 安全配置：白名单/预算/确认（473 行）
│   ├── base_agent.py                # 智能体基类
│   ├── system_operator.py           # 系统运维智能体
│   ├── information_collector.py     # 信息采集智能体
│   └── content_creator.py           # 内容创作智能体
│
├── skills/                          # Skills 模块
│   └── __init__.py                  # SkillDef / SkillRegistry / SkillExecutor（750 行）
│
├── perception/                      # 环境感知层（10 个模块）
│   ├── screen_capture.py            # 屏幕截图
│   ├── screen_ocr.py                # OCR 文字识别
│   ├── clipboard_monitor.py         # 剪贴板监控
│   ├── window_manager.py            # 窗口元数据
│   ├── system_monitor.py            # 系统资源监控
│   ├── deepin_dbus.py               # D-Bus DDE 集成（615 行）
│   ├── context_engine.py            # 多模态融合意图引擎（430 行）
│   ├── behavior_tracker.py          # 行为轨迹追踪
│   ├── privacy_guard.py             # 隐私数据守护
│   └── resource_guard.py            # 资源使用监控
│
├── mcp_servers/                     # MCP 工具服务器
│   └── mcp_protocol.py              # 纯 Python JSON-RPC over stdio 实现
│
├── tools/                           # 工具实现
│   ├── shell_tool.py                # Shell 命令执行
│   ├── file_tool.py                 # 文件读写
│   ├── search_tool.py               # 信息检索
│   └── package_tool.py              # 包管理
│
├── scenarios/                       # 核心场景
│   ├── email_assistant.py           # 智能邮件助手
│   └── system_doctor.py             # 系统问题诊断
│
├── gui/                             # PyQt5 图形界面
│   ├── floating_ball.py             # 浮动球
│   ├── chat_window.py               # 聊天窗口
│   └── tray_icon.py                 # 系统托盘
│
├── main.py                          # 入口
└── config.py                        # 全局配置
```

代码统计：~17,000 行 Python，86 个文件。

---

## 3. 核心架构

### 3.1 七状态有限状态机

所有任务生命周期由 `TaskStateMachine` 管理，状态转移规则硬编码：

```
PENDING ──▶ CLAIMED ──▶ RUNNING ──▶ VERIFIED ──▶ COMPLETED
                │            │           │
                │            │           ▼
                │            │        FAILED ──▶ (retry) ──▶ RUNNING
                ▼            ▼
            CANCELLED     FAILED
```

RUNNING 状态内部细分为五个子阶段：

```
RUNNING:
  plan ──▶ gather ──▶ analyze ──▶ execute ──▶ respond
```

### 3.2 每阶段工具白名单

| 子阶段 | 允许的工具 |
|--------|-----------|
| plan | （无） |
| gather | search, file_read, ocr, clipboard_read, window_list |
| analyze | python_eval |
| execute | shell, package, dbus_call, file_write |
| respond | （无） |

### 3.3 每阶段 Token 预算

| 子阶段 | Token 预算 |
|--------|-----------|
| plan | 500 |
| gather | 2000 |
| analyze | 1500 |
| execute | 1000 |
| respond | 800 |

### 3.4 验证器（Verifier）

任务完成后由 Verifier 执行 7 项独立检查，全部通过才标记 COMPLETED：

1. **completeness** — 任务需求是否全部完成
2. **consistency** — 结果内部是否自洽
3. **no_hallucination** — 是否包含幻觉内容
4. **tool_usage** — 工具调用是否符合白名单
5. **security** — 是否存在越权行为
6. **privacy** — 输出是否包含未脱敏敏感数据
7. **format** — 输出格式是否符合规范

### 3.5 确认守卫（Confirming Guard）

以下操作在执行前必须获得用户显式确认：

- `shell` 中包含 `rm`、`kill`、`systemctl`、`apt`、`dpkg`
- `package` 中的 `remove`、`purge`
- `service_manage` 中的 `stop`、`restart`、`disable`
- `file_write` 目标路径包含 `/etc/`、`/var/`、`/usr/`

---

## 4. 统一编排器

`agents/orchestrator.py`（927 行）是合并了 v3/v4/prod 三个变体后的统一编排器。

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
  ├── 1. PENDING → CLAIMED: 选择 Agent
  ├── 2. CLAIMED → RUNNING: 进入子阶段循环
  │     ├── plan: 分析任务，制定计划
  │     ├── gather: 采集信息
  │     ├── analyze: 分析结果
  │     ├── execute: 执行操作
  │     └── respond: 生成报告
  ├── 3. RUNNING → VERIFIED: 验证结果
  ├── 4. VERIFIED → COMPLETED (或 FAILED → retry)
  └── 全程 Trace 记录 + Checkpoint
```

### 4.3 超时/重试/降级

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

`skills/__init__.py`（750 行）实现了基于能力的任务路由机制。

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
| 红队测试 | 16 种攻击向量覆盖 | verifier.py |

### 7.2 工具白名单

```python
TOOL_WHITELIST = {
    "SystemOperator":     ["shell", "system_monitor", "dbus_call", "package", "file_read", "service_manage"],
    "InformationCollector": ["search", "file_read", "ocr", "clipboard_read", "window_list", "web_fetch"],
    "ContentCreator":      ["file_read", "clipboard_read", "file_write", "ocr"],
}
```

### 7.3 红队攻击向量

覆盖 16 种攻击：prompt injection（3种）、tool abuse（2种）、data exfiltration（2种）、resource exhaustion（2种）、privilege escalation（2种）、social engineering（2种）、combined attacks（3种）。

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

系统采用双模型策略：

| 模型 | 用途 | 触发条件 |
|------|------|---------|
| ERNIE-Lite | 快速意图分类、简单问答 | 任务复杂度 < 0.4 |
| ERNIE-3.5 | 深度推理、代码生成、分析 | 任务复杂度 ≥ 0.4 |

```python
class ModelRouter:
    """根据任务复杂度自动路由"""
    async def route(self, prompt: str, model: Optional[str] = None) -> str:
        if model:
            return await self._call(model, prompt)
        complexity = self._estimate_complexity(prompt)
        target = "ernie-lite" if complexity < 0.4 else "ernie-3.5"
        return await self._call(target, prompt)
```

---

## 10. 技术栈

| 组件 | 技术选型 |
|------|---------|
| 编程语言 | Python 3.10+ |
| 桌面框架 | PyQt5 |
| 大模型 SDK | erniebot (百度 ERNIE) |
| OCR | PaddleOCR / Tesseract |
| 系统集成 | D-Bus (dbus-python / dbus-next) |
| 协议 | MCP — JSON-RPC 2.0 over stdio |
| 并发 | asyncio |
| 操作系统 | deepin 25 (Debian-based) |
| 桌面环境 | DDE (Deepin Desktop Environment) |
| 进程管理 | systemd |
| 包管理 | APT / dpkg |

---

> 本文档反映 v3（当前）架构状态。代码统计：~17,000 行 Python，86 个文件。
