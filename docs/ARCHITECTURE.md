# 架构文档

> 最后更新：2026-06-04

## 项目概述

deepin Agent Teams 是运行在 deepin 25 操作系统上的多智能体协作系统，基于文心大模型 API。

### 架构演进

| 阶段 | 日期 | 内容 |
|------|------|------|
| v1 | 2026-05 | 基础三角架构（状态机 + Verifier + Worker） |
| v2 | 2026-06-04 | P0 安全增强（工具白名单 + Token 预算 + Confirming） |
| v2 | 2026-06-04 | P1 质量保障（离线评测 + 可观测性 + Red Teaming） |
| v2 | 2026-06-04 | P2 架构升级（Brain/Hands 分离 + 三级环境隔离） |

## 模块结构

```
deepin-agent-teams/
├── main.py                    # CLI 入口 + GUI 入口
├── config.py                  # 全局配置（模型、路径、参数）
├── model_router.py            # 多模型路由器（ernie-lite + ernie-3.5）
│
├── agents/
│   ├── registry.py            # Agent 注册中心（文件锁 + JSON）
│   ├── security_config.py     # 安全配置（工具白名单 + Token 预算 + 危险操作模式）
│   ├── task_state_machine.py  # 任务状态机引擎（集成安全校验）
│   ├── verifier.py            # 独立质检员（7 项检查，含安全检查）
│   ├── orchestrator_v3.py    # 状态机+Verifier 驱动的编排器
│   ├── orchestrator_v4.py    # MCP 驱动的编排器（P3）
│   ├── worker_base.py        # 通用 Worker 基类（14 种能力 + 安全守卫）
│   ├── worker_v2.py          # Worker 主循环
│   ├── lead.py               # Lead Agent
│   ├── hands_interface.py    # Brain/Hands 分离接口（P2）
│   ├── environment_isolation.py # 三级环境隔离（P2）
│   ├── eval_runner.py        # 离线评测框架（P1）
│   ├── metrics_collector.py  # 可观测性指标收集（P1）
│   └── red_team_tests.py     # Red Teaming 安全测试（P1）
│
├── mcp_servers/               # MCP 工具服务层（P3）
│   ├── mcp_protocol.py       # 轻量 MCP 协议实现（纯 Python）
│   ├── model_server.py       # 模型 MCP Server
│   ├── file_server.py        # 文件 MCP Server
│   └── system_server.py      # 系统 MCP Server
│
├── tools/
│   ├── tool_registry.py      # 统一工具注册表（P3）
│   ├── checkpoint_manager.py # 检查点管理（失败恢复）
│   ├── analyze_traces.py     # Trace 分析工具
│   └── analyze_capabilities.py # 能力正交化分析
│
├── docs/
│   ├── ARCHITECTURE.md       # 本文档
│   ├── CONVENTIONS.md        # 代码规范
│   ├── TECH_DECISIONS.md     # 技术选型决策
│   └── QUALITY.md            # 质量标准
│
├── tests/
│   ├── fixtures/              # AIMock 确定性 Fixture
│   ├── reports/               # 评测报告
│   ├── metrics/               # 指标数据（JSONL）
│   ├── test_tool_registry.py  # ToolRegistry 单元测试（8/8）
│   └── test_mcp_integration.py # MCP 集成测试（8/8）
│
└── skills/                    # （预留）技能扩展目录
```

## 核心架构

### 三角架构（状态机 + Verifier + Worker）

```
用户请求
    ↓
Lead（OrchestratorV3）拆解任务
    ↓
Worker 执行（PENDING → CLAIMED → RUNNING）
    ↓
Verifier 独立质检（RUNNING → VERIFIED）
    ↓
PASS → COMPLETED
FAIL → RETRY（≤3次）→ FAILED
超时 → FAILED
    ↓
状态机 trace 写入 /tmp/deepin_traces/{task_id}.jsonl
```

### 状态机引擎（TaskStateMachine）

| 状态 | 说明 | 合法前驱 |
|------|------|---------|
| PENDING | 入队，未分配 | — |
| CLAIMED | Worker 认领 | PENDING, FAILED |
| RUNNING | 执行中 | CLAIMED |
| VERIFIED | Verifier 通过 | RUNNING |
| COMPLETED | 流程终结 | VERIFIED |
| FAILED | 不可恢复失败 | PENDING, CLAIMED, RUNNING, RETRY |
| RETRY | 需重做 | RUNNING |

**跳转规则全部写死代码**，不靠模型主观判断：
- `(PENDING, CLAIMED)` — 找到 Worker 即跳转
- `(CLAIMED, RUNNING)` — Worker 开始执行即跳转
- `(RUNNING, VERIFIED)` — Verifier 通过即跳转
- `(RUNNING, RETRY)` — Verifier FAIL 且 retry_count < MAX_RETRY
- `(RETRY, RUNNING)` — 重试次数未耗尽
- `(RETRY, FAILED)` — 重试次数耗尽（≥3）
- `(RUNNING, FAILED)` — timeout in error_msg
- `(VERIFIED, COMPLETED)` — 自动完成

### 独立 Verifier

Verifier 是**独立的质量门**，不读 Worker 上下文，完全依赖自己的验收标准。

**7 项检查（含 3 项安全检查）：**
1. `deliverable_exists` — 交付物存在（非 None）
2. `functional_correctness` — 按 task type 分叉验收
3. `trace_integrity` — 需 `task_id` + `capabilities_used`
4. `error_free` — 无未预期 error（E_TIMEOUT/E_BLOCKED 除外）
5. `tool_compliance` — 工具白名单合规（P0 安全增强）
6. `token_budget` — Token 预算合规（P0 安全增强）
7. `dangerous_ops_confirmed` — 危险操作确认合规（P0 安全增强）

**3 种决策：**
- `PASS` — 全部检查通过
- `FAIL` — 至少一项检查失败，附 causes 列表
- `RETRY` — 可恢复错误（暂时性），附 cause

### CheckpointManager

失败恢复机制：

```
/tmp/deepin_checkpoints/
    {task_id}/
        metadata.json           # attempts / completed_steps
        {capability}-meta.json  # 能力级 checkpoint 元信息
        {capability}-result.json # 能力级执行结果
```

**使用流程：**
1. 每步能力执行完 → `cm.save(capability, result)`
2. 重试时 → `cm.last_checkpoint()` 恢复
3. 成功后 → `cm.cleanup()` 清理

## P0 安全增强

### 工具白名单隔离

每个状态/阶段有独立的工具白名单，Worker 只能使用当前白名单内的工具：

| 状态/阶段 | 允许的工具 |
|-----------|----------|
| PENDING | 无 |
| CLAIMED | 无 |
| RUNNING.plan | 无（纯思考） |
| RUNNING.gather | 只读工具（file_reader, dir_scanner, code_analyzer 等） |
| RUNNING.analyze | 分析工具（syntax_checker, dependency_analyzer, web_search 等） |
| RUNNING.execute | 所有工具（含写操作） |
| VERIFIED | 文档生成 |
| COMPLETED | 无 |
| FAILED | 无 |
| RETRY | 无 |

### Token 预算

每状态/阶段有独立的 Token 上限，全局上限 15000：

| 状态/阶段 | Token 上限 |
|-----------|----------|
| RUNNING（总体） | 6000 |
| RUNNING.plan | 500 |
| RUNNING.gather | 2000 |
| RUNNING.analyze | 2000 |
| RUNNING.execute | 1500 |
| VERIFIED | 500 |
| RETRY | 500 |
| 全局上限 | 15000 |

超限自动触发 FAILED 状态。

### 危险操作确认（Confirming 守卫）

危险操作（shell_executor 中的高危命令）必须经过用户确认：

- **allow** — 允许本次
- **always** — 允许同类（加入白名单）
- **deny** — 拒绝本次
- **exit** — 终止任务

危险模式匹配（正则）：
- critical：`rm -rf`, `mkfs`, `dd if=`, `chmod 777`, `/dev/sd`
- high：`kill -9`, `systemctl stop`, `| bash`, `curl ... | sh`
- medium：`sudo`, `> /dev/null`, `nohup`

### 安全架构图

```
用户请求
    ↓
Orchestrator 拆解任务
    ↓
StateTransition → 工具白名单校验
    ↓
Worker.execute_capability()
    ├── 白名单检查 → 拦截不允许的工具
    ├── 危险操作检查 → 触发 Confirming 守卫
    └── Token 预算检查 → 超限自动 FAILED
    ↓
Verifier 验收（7 项检查，含 3 项安全检查）
    ↓
PASS → COMPLETED / FAIL → RETRY / FAILED
```

## P1 质量保障

### 离线评测框架（eval_runner.py）

- **AIMock** — 确定性 Fixture，CI 零 API 消耗
- **EvalRunner** — 评测管道：定义用例 → 执行 Agent → 对比期望 → 生成报告
- **EvalAssert** — 评测断言工具集（state/verdict/token/tool_compliance 等）

### 可观测性（metrics_collector.py）

三大核心指标：
- **Token 消耗** — 按 state/phase/model 分维度
- **执行延迟** — histogram（状态跳转、工具调用、整体任务）
- **错误率** — 按 error_type 分维度

支持 Span 管理（类似 OpenTelemetry）和 TimerContext 自动计时。

### Red Teaming（red_team_tests.py）

19 个攻击向量，5 类攻击：
- **Prompt 注入**（3 个）— 直接覆盖、间接注入、角色扮演
- **工具白名单绕过**（5 个）— 各状态/阶段尝试调用不允许的工具
- **Token 预算绕过**（3 个）— 单阶段超限、全局超限、跨阶段累计
- **状态机非法跳转**（4 个）— 跳过中间状态、状态回退
- **确认机制绕过**（4 个）— 不确认执行、编码绕过

当前防御率：**100%**（19/19 DEFENDED）

## P2 架构升级

### Brain/Hands 分离（hands_interface.py）

```
Brain（编排层）          Hands（执行层）
├── 理解用户意图          ├── 代码写入
├── 拆解任务步骤          ├── 文件读取
├── 决定调用哪些工具       ├── 命令执行
└── 流式输出思考过程       └── 结果回传
```

- **HandsInterface** — 抽象接口（execute / health_check / get_capabilities）
- **LocalHands** — 本地执行实现（向后兼容）
- **DockerHands** — Docker 容器执行（预留接口）
- **MockHands** — 测试用 Mock（确定性输出）
- **HandsFactory** — 工厂模式创建实例

### 三级环境隔离（environment_isolation.py）

| 级别 | 说明 | 适用场景 |
|------|------|----------|
| shared | 所有人共用一个环境 | 个人项目 |
| isolated | 每 Worker 独立环境 | 团队项目 |
| task | 每任务独立环境 + 独立配额 | 多租户 SaaS |

**EnvironmentManager** — 环境生命周期管理（创建/销毁/查询/配额检查）
**ResourceQuota** — 资源配额限制（文件数/大小/进程数/CPU/内存/超时）
**IsolationPolicy** — 按场景预设策略

## Worker 能力清单

| Capability | 实现方法 | error handling | timeout |
|------------|---------|---------------|---------|
| file_reader | _read_file | ✅ | ✅ |
| dir_scanner | _scan_dir | ✅ | ✅ |
| code_analyzer | _analyze_code | ✅ | ✅ |
| ast_parser | _parse_ast | ✅ | ❌ |
| syntax_checker | _syntax_check | ✅ | ✅ |
| dependency_analyzer | _analyze_deps | ✅ | ✅ |
| shell_executor | _run_shell | ✅ | ✅ |
| git_analyzer | _analyze_git | ✅ | ✅ |
| web_search | _web_search | ✅ | ✅ |
| web_fetcher | _fetch_url | ✅ | ✅ |
| file_writer | _write_file | ✅ | ✅ |
| doc_generator | _generate_doc | ❌ | ❌ |
| markdown_writer | _write_markdown | ✅ | ✅ |
| process_manager | _manage_process | ✅ | ❌ |

> 注：web_search 使用 duckduckgo html 端，无需 API key。

## 模型路由

```
请求 → ModelRouter.chat()
    ↓
ernie-3.5（强力，优先用于复杂任务）
    ↓ 失败
ERNIE-lite（备用）
    ↓ 失败
Fallback（返回错误信息）
```

**当前配置：**
- ernie-3.5：复杂推理任务使用
- ERNIE：从 `ERNIEBOT_ACCESS_TOKEN` 环境变量读取

**响应格式（ModelResponse）：**
```python
{
    "content": str,       # 模型输出
    "model": str,          # 实际使用的模型
    "success": bool,       # 是否成功
    "error": Optional[str], # 错误信息
    "latency_ms": int,     # 耗时
    "token_used": int,     # token 消耗
}
```

## Trace 系统

每次状态跳转写入：
```
/tmp/deepin_traces/{task_id}.jsonl
```

每行格式：
```json
{
    "from": "running",
    "to": "verified",
    "ts": 1747891234.567,
    "worker_id": "researcher-001",
    "verdict": "PASS",
    "retry_count": 0,
    "error_msg": null,
    "causes": []
}
```

**分析工具：** `python3 tools/analyze_traces.py`

## 目录约定

| 目录 | 说明 |
|------|------|
| `/tmp/deepin_traces/` | 状态机 trace（JSONL） |
| `/tmp/deepin_checkpoints/` | 检查点文件 |
| `/tmp/agent_registry.json` | Agent 注册表 |
| `/tmp/agent_results/` | Worker 执行结果 |
| `/tmp/deepin_tasks/` | 任务队列文件 |

## 技术栈

- **Python 3**（主语言）
- **ERNIE BOT SDK**（erniebot）— AI Studio 认证
- **ernie-3.5**（via erniebot SDK）— 复杂推理任务
- **PyQt5** — GUI（截图、行为追踪）
- **PaddleOCR** — 屏幕文字识别
- **文件锁（fcntl）** — 多进程安全