# 架构文档

> 最后更新：2026-05-22

## 项目概述

deepin Agent Teams 是运行在 deepin 25 操作系统上的多智能体协作系统，基于文心大模型 API。

## 模块结构

```
deepin-agent-teams/
├── main.py                    # CLI 入口 + GUI 入口
├── config.py                  # 全局配置（模型、路径、参数）
├── model_router.py            # 多模型路由器（MiniMax + ERNIE）
│
├── agents/
│   ├── registry.py            # Agent 注册中心（文件锁 + JSON）
│   ├── task_state_machine.py  # 任务状态机引擎（P0-1）
│   ├── verifier.py            # 独立质检员（P0-2）
│   ├── orchestrator_v3.py    # 状态机+Verifier 驱动的编排器
│   ├── worker_base.py        # 通用 Worker 基类（14 种能力）
│   ├── worker_v2.py          # Worker 主循环
│   └── lead.py               # Lead Agent
│
├── tools/
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

**4 项检查：**
1. `deliverable_exists` — 交付物存在（非 None）
2. `functional_correctness` — 按 task type 分叉验收：
   - `code_analysis` → 需 `lines` 字段
   - `shell_executor` → 需 `command` + `exit_code`
   - `file_reader` → 需 `content` 或 `size`
   - `web_search` → 需 `results` 列表
   - `ast_parser` → 需 `ast` 字段
3. `trace_integrity` — 需 `task_id` + `capabilities_used`
4. `error_free` — 无未预期 error（E_TIMEOUT/E_BLOCKED 除外）

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
MiniMax（优先）
    ↓ 失败
ERNIE-lite（备用）
    ↓ 失败
Fallback（返回错误信息）
```

**当前配置：**
- MiniMax：从 `MINIMAX_API_KEY` 环境变量读取
- ERNIE：从 `ERNIE_TOKEN` 环境变量读取（token 已耗尽，当前不可用）

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
- **MiniMax API**（HTTP 调用）— 主力模型
- **PyQt5** — GUI（截图、行为追踪）
- **PaddleOCR** — 屏幕文字识别
- **文件锁（fcntl）** — 多进程安全