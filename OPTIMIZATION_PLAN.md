# deepin-agent-teams 优化执行计划

> 基于工程学评审（P0 生死线 → P1 可靠性 → P2 长期积累）

---

## P0 · 核心架构补完

### P0-1：状态机驱动引擎

**问题**：停止条件靠模型"感觉差不多"，不写死

**目标**：为任务生命周期建立确定性状态机

```python
# 新建 agents/task_state_machine.py

class TaskState(Enum):
    PENDING    = "pending"      # 入队，未分配
    CLAIMED    = "claimed"      # Worker 认领
    RUNNING     = "running"      # 执行中
    VERIFIED    = "verified"     # Verifier 通过
    COMPLETED   = "completed"    # 流程终结
    FAILED      = "failed"       # 不可恢复失败
    RETRY       = "retry"        # 打回重做

class TransitionRule:
    """每个跳转的条件必须是代码，不是模型判断"""
    @staticmethod
    def can_transition(from_: TaskState, to: TaskState, ctx: dict) -> bool:
        rules = {
            (TaskState.PENDING, TaskState.CLAIMED):    lambda c: c["worker_id"] is not None,
            (TaskState.CLAIMED, TaskState.RUNNING):    lambda c: c["start_time"] is not None,
            (TaskState.RUNNING, TaskState.VERIFIED):  lambda c: c["verdict"] == "PASS",
            (TaskState.RUNNING, TaskState.RETRY):      lambda c: c["verdict"] == "FAIL",
            (TaskState.RETRY, TaskState.RUNNING):     lambda c: c["retry_count"] < MAX_RETRY,
            (TaskState.VERIFIED, TaskState.COMPLETED): lambda c: True,  # 通过即完成
            (TaskState.RETRY, TaskState.FAILED):       lambda c: c["retry_count"] >= MAX_RETRY,
        }
        rule = rules.get((from_, to))
        return rule(ctx) if rule else False
```

**执行步骤**：
- [ ] 新建 `agents/task_state_machine.py`
- [ ] 定义 `TaskState` 枚举 + `TransitionRule`
- [ ] 每个状态跳转写 trace：`{"from": "PENDING", "to": "CLAIMED", "worker_id": "coder-123", "ts": 1747891200}`
- [ ] Registry 的 `submit_task` / `complete_task` 替换为状态机驱动
- [ ] 停止条件：`COMPLETED` 或 `FAILED` 才终止，`RETRY` 循环不终止主流程
- [ ] 单元测试：所有状态跳转覆盖

---

### P0-2：独立 Verifier 角色

**问题**：Lead 自己检查自己，裁判=选手

**目标**：Verifier 独立验收，Worker 不通过打回重做

```python
# 新建 agents/verifier.py

class Verifier:
    """
    独立质检员

    设计原则：
    - 不读 Worker 上下文，完全独立世界观
    - 验收标准是清单，不是模型主观判断
    - 决策只有三种：PASS / FAIL(reason) / RETRY(cause)
    """

    def __init__(self, model="ernie-lite"):
        self.model = model

    def verify(self, task: dict, worker_result: dict) -> dict:
        """
        验收 Worker 产出

        标准清单：
        1. 交付物存在性：文件/响应 非空
        2. 功能正确性：（根据 task type）对应检查
        3. 可追溯性：有 trace，无幻觉数据
        4. 边界处理：空输入/极端值/错误输入有处理
        """
        checks = [
            self._check_deliverable_exists(task, worker_result),
            self._check_functional_correctness(task, worker_result),
            self._check_trace_integrity(task, worker_result),
        ]
        # 所有 PASS 才算 PASS，一个 FAIL 即打回
        failed = [c for c in checks if c["result"] == "FAIL"]
        if failed:
            return {"verdict": "FAIL", "causes": failed}
        return {"verdict": "PASS"}

    def _check_deliverable_exists(self, task, result) -> dict:
        """交付物非空"""
        val = result.get("result") or result
        if not val or val == {} or val == []:
            return {"check": "deliverable_exists", "result": "FAIL", "reason": "交付物为空"}
        return {"check": "deliverable_exists", "result": "PASS"}

    def _check_functional_correctness(self, task, result) -> dict:
        """功能正确性（按 task type 分叉）"""
        task_type = task.get("type", "unknown")
        if task_type == "code_analysis":
            return self._verify_code_analysis(result)
        elif task_type == "file_scan":
            return self._verify_file_scan(result)
        # ...
        return {"check": "functional_correctness", "result": "PASS"}  # 兜底

    def _verify_code_analysis(self, result) -> dict:
        """代码分析验收：检查是否包含预期字段"""
        required = ["functions", "classes", "lines"]
        missing = [f for f in required if f not in result]
        if missing:
            return {"check": "code_analysis_fields", "result": "FAIL", "reason": f"缺少字段: {missing}"}
        return {"check": "code_analysis_fields", "result": "PASS"}

    def _check_trace_integrity(self, task, result) -> dict:
        """trace 记录完整性"""
        if "task_id" not in result or "capabilities_used" not in result:
            return {"check": "trace_integrity", "result": "FAIL", "reason": "缺少 trace 字段"}
        return {"check": "trace_integrity", "result": "PASS"}
```

**执行步骤**：
- [ ] 新建 `agents/verifier.py`
- [ ] 实现 `verify()` 主方法 + 按 task type 的验收标准
- [ ] 修改 `ExtensibleOrchestrator.run()`：Worker 执行后强制走 Verifier
- [ ] FAIL 打回时写入重做原因到 trace
- [ ] VERIFIED 状态才允许进入 integrate 阶段
- [ ] 单元测试：PASS / FAIL / RETRY 三种决策覆盖

---

## P1 · 系统可靠性

### P1-1：能力实现补坑

**问题**：`web_search` 等 capability 是空壳 stub

**执行步骤**：
- [ ] `web_search`：对接 MiniMax MCP 或 searxng 本地搜索
- [ ] `web_fetcher`：结构化解析（BeautifulSoup），错误分类（网络/解析/超时）
- [ ] 每个能力加异常日志，记录 error type + stack
- [ ] 统一 capability 错误码体系（`E_NETWORK` / `E_PARSE` / `E_TIMEOUT` / `E_NOTFOUND`）

---

### P1-2：检查点机制

**问题**：失败从头重来，无中间恢复点

**执行步骤**：
- [ ] 每个 capability 执行完写 checkpoint：`/tmp/checkpoints/{task_id}/{capability}.json`
- [ ] 主循环启动时扫描 checkpoint，已有则跳过已完成的 capability
- [ ] 定义 checkpoint 格式：`{"capability": "code_analyzer", "completed_at": ts, "result_hash": "sha256"}`
- [ ] 任务成功完成后清理 checkpoint 目录（或保留 N 个历史）

---

### P1-3：Trace 日志结构化

**问题**：Registry 只记录状态，不记录决策链路

**执行步骤**：
- [ ] 新建 `/tmp/traces/{task_id}/state_transitions.jsonl`
- [ ] 每条记录：`{"from": "PENDING", "to": "CLAIMED", "ts": unix, "worker_id": "...", "verdict": null}`
- [ ] Verdict 打回时记录：`{"from": "RUNNING", "to": "RETRY", "verdict": "FAIL", "cause": "缺少 ast_nodes 字段"}`
- [ ] N 个任务后分析 trace：高频 FAIL 点 → 系统瓶颈 → 改进原料

---

## P2 · 长期工程积累

### P2-1：多模型路由补充

**现状**：ernie-3.5 耗尽，只有 lite

**执行步骤**：
- [ ] 新增 MiniMax 作为备选模型（env `MINIMAX_API_KEY`）
- [ ] 在 `model_router.py` 实现自动降级策略
- [ ] 各 task type 对应模型分级建议：
  - 意图识别 → lite
  - 代码分析 → 强模型
  - 整合报告 → 强模型

---

### P2-2：Worker 能力正交化

**问题**：能力列表看起来全但互相重叠

**执行步骤**：
- [ ] 重构 capability 清单，每项职责单一
- [ ] 禁止一个 capability 做多件事（如 `_analyze_code` 里不要塞 `ast_parser` 逻辑）
- [ ] 绘制 capability 关系图：正交 = 独立调用，依赖 = 显式声明

---

### P2-3：架构文档同步

**执行步骤**：
- [ ] 将 P0/P1 的变更同步到 `docs/ARCHITECTURE.md`（加状态机章节）
- [ ] 将验收标准同步到 `docs/QUALITY.md`（Verifier checklist）
- [ ] 补充 `docs/TECH_DECISIONS.md`：为什么选状态机驱动 vs 模型判断

---

## 执行顺序总览

```
第1轮（Sprint 1-2周）
  P0-1 状态机驱动引擎 ←←← 最优先，核心骨架
  P0-2 独立 Verifier  ←←← 质量门禁，补完三角架构

第2轮（Sprint 3-4周）
  P1-1 能力实现补坑
  P1-2 检查点机制
  P1-3 Trace 结构化

第3轮（Sprint 5-6周）
  P2-1 多模型路由
  P2-2 Worker 正交化
  P2-3 文档同步
```

---

## 交付标准检查清单

每次 commit 前：

- [ ] 状态机状态码全部覆盖，新增状态有对应跳转测试
- [ ] Verifier 测试：故意传入错误数据 → 必须 FAIL
- [ ] 新增 capability 有 stub 实现 + 标注 `TODO: implement`
- [ ] checkpoint 文件格式校验通过
- [ ] trace JSONL 每行是合法 JSON
