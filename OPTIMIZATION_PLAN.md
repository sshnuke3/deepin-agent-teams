# deepin-agent-teams 优化执行计划

> 基于工程学评审（P0 生死线 → P1 可靠性 → P2 长期积累）
> **状态：全部完成 ✅（2026-05-22）**

---

## P0 · 核心架构补完 ✅

### P0-1：状态机驱动引擎 ✅

**实现**：`agents/task_state_machine.py`

```python
class TaskState(Enum):
    PENDING = "pending"      # 入队，未分配
    CLAIMED = "claimed"       # Worker 认领
    RUNNING = "running"       # 执行中
    VERIFIED = "verified"     # Verifier 通过
    COMPLETED = "completed"   # 流程终结
    FAILED = "failed"         # 不可恢复失败
    RETRY = "retry"          # 需重做
```

- ✅ 7 种状态，跳转规则全部写死代码
- ✅ 每次跳转写 trace → `/tmp/deepin_traces/{task_id}.jsonl`
- ✅ 状态机本身无状态，状态存在 Registry 层
- ✅ 单元测试：5/5 通过

**跳转规则（代码写死）：**
```python
(TaskState.PENDING, TaskState.CLAIMED):   lambda c: c.worker_id is not None
(TaskState.CLAIMED, TaskState.RUNNING):   lambda c: c.start_time is not None
(TaskState.RUNNING, TaskState.VERIFIED):  lambda c: c.verdict == "PASS"
(TaskState.RUNNING, TaskState.RETRY):     lambda c: c.verdict == "FAIL" and c.retry_count < MAX_RETRY
(TaskState.RETRY, TaskState.RUNNING):     lambda c: c.retry_count < MAX_RETRY
(TaskState.RETRY, TaskState.FAILED):      lambda c: c.retry_count >= MAX_RETRY
(TaskState.RUNNING, TaskState.FAILED):    lambda c: "timeout" in str(c.error_msg)
(TaskState.VERIFIED, TaskState.COMPLETED): lambda c: True
```

### P0-2：独立 Verifier 角色 ✅

**实现**：`agents/verifier.py`

- ✅ 不读 Worker 上下文，完全独立世界观
- ✅ 验收标准是清单（checklist），不是模型主观判断
- ✅ 决策只有三种：PASS / FAIL(causes[]) / RETRY(cause)
- ✅ 4 项检查：deliverable_exists / functional_correctness / trace_integrity / error_free
- ✅ 类型分叉验收：code_analysis/shell_executor/file_reader/web_search/ast_parser
- ✅ 单元测试：6/6 通过

---

## P1 · 系统可靠性 ✅

### P1-1：能力实现补坑 ✅

| Capability | 状态 | 说明 |
|-----------|------|------|
| web_search | ✅ 实现 | duckduckgo html，无需 API key |
| web_fetcher | ✅ 实现 | 结构化解析 + 错误分类 |
| shell_executor | ✅ 实现 | subprocess + timeout |
| file_reader | ✅ 实现 | max_chars 限制 |
| code_analyzer | ✅ 实现 | functions/classes/lines |
| ast_parser | ✅ 实现 | AST 节点提取 |

**错误码体系：** E_NETWORK / E_PARSE / E_TIMEOUT / E_BLOCKED / OK

### P1-2：检查点机制 ✅

**实现**：`tools/checkpoint_manager.py`

```
/tmp/deepin_checkpoints/{task_id}/
    metadata.json              # attempts / completed_steps
    {capability}-meta.json     # Checkpoint 元信息
    {capability}-result.json   # 执行结果
```

- ✅ save(capability, result) — 每步完成时写 checkpoint
- ✅ is_completed(capability) — 检查是否已完成
- ✅ last_checkpoint() — 重试时恢复
- ✅ verify() — hash 防篡改验证
- ✅ cleanup() — 成功后清理
- ✅ 单元测试：6/6 通过

### P1-3：Trace 日志结构化 ✅

**实现**：`tools/analyze_traces.py`

- ✅ 加载 `/tmp/deepin_traces/*.jsonl`
- ✅ 输出：任务摘要 / 高频 FAIL 原因 / 状态跳转统计 / Worker 分布
- ✅ 无需 API，纯本地分析

---

## P2 · 长期工程积累 ✅

### P2-1：多模型路由补充 ✅

**实现**：`agents/model_router.py`

```
请求 → ModelRouter.chat()
    ↓
MiniMax（优先，环境变量 MINIMAX_API_KEY）
    ↓ 失败
ERNIE-lite（备用，token 耗尽时降级）
    ↓ 失败
Fallback（返回错误信息）
```

- ✅ 统一 ModelResponse 格式（content/success/error/latency_ms/token_used）
- ✅ stats() 调用统计（total/success/failures/avg_latency）
- ✅ 自动降级，无需人工干预

### P2-2：Worker 能力正交化 ✅

**实现**：`tools/analyze_capabilities.py`

- ✅ 扫描所有 Worker 实现，检测 14 个能力定义
- ✅ 无重叠（每个能力只有一个实现）
- ✅ 无缺失（所有被调用的能力都有实现）
- ✅ 13 个孤立能力（实现了但未被主动调用）

### P2-3：架构文档同步 ✅

| 文档 | 状态 | 更新内容 |
|------|------|---------|
| README.md | ✅ | 三角架构图 + 快速开始 |
| ARCHITECTURE.md | ✅ | 全量架构详解 |
| TECH_DECISIONS.md | ✅ | 状态机/Verifier/Checkpoint/web_search |
| OPTIMIZATION_PLAN.md | ✅ | 标记全部完成 |

---

## 执行结果总览

| 阶段 | 内容 | 状态 | 测试 |
|------|------|------|------|
| **P0** | 状态机引擎 + 独立 Verifier + orchestrator_v3 | ✅ | 11/11 |
| **P1** | web_search 实现 + CheckpointManager + trace 分析 | ✅ | 12/12 |
| **P2** | 多模型路由 + 能力分析 + 文档同步 | ✅ | 冒烟 |

**所有代码已推送 GitHub**：`github.com/sshnuke3/deepin-agent-teams`

---

## 交付标准检查清单

每次 commit 前：

- [x] 状态机状态码全部覆盖，新增状态有对应跳转测试
- [x] Verifier 测试：故意传入错误数据 → 必须 FAIL
- [x] 新增 capability 有 stub 实现 + 标注 `TODO: implement`
- [x] checkpoint 文件格式校验通过
- [x] trace JSONL 每行是合法 JSON
- [x] 赛题合规性检查通过
- [x] README + 架构文档已同步更新
