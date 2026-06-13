#!/usr/bin/env python3
"""
agents/task_state_machine.py - 任务状态机引擎

核心设计原则：
1. 状态跳转条件用代码写死，不靠模型主观判断
2. 每次跳转写 trace，可追溯
3. 状态机本身无状态，所有状态存在 Registry 层
"""
import os
import sys
import json
import time
import hashlib
from enum import Enum
from typing import Optional, Callable, Dict, Any, List, Tuple
from dataclasses import dataclass, field

# 路径
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
TRACE_DIR = "/tmp/deepin_traces"
os.makedirs(TRACE_DIR, exist_ok=True)

# 安全配置（工具白名单 + Token 预算 + Confirming 守卫）
from security_config import (
    is_tool_allowed,
    TokenTracker,
    get_token_budget,
    ConfirmationGuard,
    ConfirmRequest,
    ConfirmResponse,
    ConfirmAction,
    check_dangerous_operation,
    GLOBAL_TASK_TOKEN_LIMIT,
)


class TaskState(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 入队，未分配
    CLAIMED = "claimed"       # Worker 认领
    PLANNING = "planning"     # 规划阶段：生成步骤计划
    RUNNING = "running"       # 执行中
    VERIFIED = "verified"     # Verifier 通过
    COMPLETED = "completed"   # 流程终结
    FAILED = "failed"         # 不可恢复失败
    RETRY = "retry"           # 打回重做


# 超时常量
DEFAULT_TIMEOUT = 60          # 默认任务超时（秒）
MAX_RETRY = 3                 # 最大重试次数
HEARTBEAT_INTERVAL = 5        # 心跳间隔（秒）

# RUNNING 内部分阶段
RUNNING_PHASES = ["plan", "gather", "analyze", "execute"]
PHASE_ORDER = {name: i for i, name in enumerate(RUNNING_PHASES)}


@dataclass
class TransitionContext:
    """状态跳转的上下文数据"""
    worker_id: Optional[str] = None
    start_time: Optional[float] = None
    verdict: Optional[str] = None  # PASS / FAIL
    verdict_causes: Optional[List[str]] = None
    retry_count: int = 0
    error_msg: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    # 安全相关字段
    current_phase: Optional[str] = None     # RUNNING 内部阶段（plan/gather/analyze/execute）
    tokens_used: int = 0                    # 本轮消耗的 Token 数
    tool_name: Optional[str] = None         # 当前要执行的工具名
    tool_input: Optional[str] = None        # 工具输入（用于危险操作检测）


@dataclass
class StateTransition:
    """一次状态跳转记录"""
    task_id: str
    from_state: TaskState
    to_state: TaskState
    ts: float
    worker_id: Optional[str] = None
    verdict: Optional[str] = None
    causes: Optional[List[str]] = None
    error_msg: Optional[str] = None
    # 安全增强字段
    phase: Optional[str] = None
    tool_name: Optional[str] = None
    tokens_used: int = 0
    cumulative_tokens: int = 0
    token_budget: int = 0
    budget_exceeded: bool = False

    def to_dict(self) -> dict:
        d = {
            "task_id": self.task_id,
            "from": self.from_state.value,
            "to": self.to_state.value,
            "ts": self.ts,
            "worker_id": self.worker_id,
            "verdict": self.verdict,
            "causes": self.causes,
            "error_msg": self.error_msg,
        }
        # 安全字段只在有值时写入（保持向后兼容）
        if self.phase:
            d["phase"] = self.phase
            d["tokens_used"] = self.tokens_used
            d["cumulative_tokens"] = self.cumulative_tokens
            d["token_budget"] = self.token_budget
            if self.budget_exceeded:
                d["budget_exceeded"] = True
        if self.tool_name:
            d["tool"] = self.tool_name
        return d


class TransitionRule:
    """
    状态跳转规则

    每个 (from, to) 组合对应一个条件函数。
    条件函数接收 TransitionContext，返回 bool。
    全部用代码写死，不依赖模型判断。
    """

    @staticmethod
    def can_transition(from_: TaskState, to: TaskState, ctx: TransitionContext) -> bool:
        rules: Dict[tuple, Callable] = {
            # PENDING → CLAIMED: 必须有 worker_id
            (TaskState.PENDING, TaskState.CLAIMED):
                lambda c: c.worker_id is not None,

            # CLAIMED → PLANNING: 必须有 start_time（计时开始）
            (TaskState.CLAIMED, TaskState.PLANNING):
                lambda c: c.start_time is not None,

            # PLANNING → RUNNING: 必须有 plan（计划已生成）
            (TaskState.PLANNING, TaskState.RUNNING):
                lambda c: c.extra.get("plan_ready") is True,

            # PLANNING → FAILED: 规划超时或失败
            (TaskState.PLANNING, TaskState.FAILED):
                lambda c: c.error_msg is not None,

            # RUNNING → VERIFIED: Verifier 给出 PASS
            (TaskState.RUNNING, TaskState.VERIFIED):
                lambda c: c.verdict == "PASS",

            # RUNNING → RETRY: Verifier 给出 FAIL，重试次数未满
            (TaskState.RUNNING, TaskState.RETRY):
                lambda c: c.verdict == "FAIL" and c.retry_count < MAX_RETRY,

            # RETRY → PENDING: 回到待认领状态，让编排器重新分配
            (TaskState.RETRY, TaskState.PENDING):
                lambda c: c.retry_count < MAX_RETRY,

            # RETRY → FAILED: 重试次数耗尽
            (TaskState.RETRY, TaskState.FAILED):
                lambda c: c.retry_count >= MAX_RETRY,

            # VERIFIED → COMPLETED: 通过即完成（无后续验证流程）
            (TaskState.VERIFIED, TaskState.COMPLETED):
                lambda c: True,

            # RUNNING → FAILED: 重试耗尽 OR 超时 OR Token 预算超限
            (TaskState.RUNNING, TaskState.FAILED):
                lambda c: (c.verdict == "FAIL" and c.retry_count >= MAX_RETRY) \
                          or (c.error_msg and "timeout" in c.error_msg) \
                          or (c.error_msg and "超限" in c.error_msg),
        }
        key = (from_, to)
        if key not in rules:
            return False
        return rules[key](ctx)

    @staticmethod
    def get_valid_next_states(current: TaskState) -> List[TaskState]:
        """获取当前状态的所有合法下一状态"""
        return {
            TaskState.PENDING:  [TaskState.CLAIMED, TaskState.FAILED],
            TaskState.CLAIMED:  [TaskState.PLANNING, TaskState.FAILED],
            TaskState.PLANNING: [TaskState.RUNNING, TaskState.FAILED],
            TaskState.RUNNING:  [TaskState.VERIFIED, TaskState.RETRY, TaskState.FAILED],
            TaskState.VERIFIED: [TaskState.COMPLETED],
            TaskState.RETRY:    [TaskState.PENDING, TaskState.FAILED],
            TaskState.FAILED:   [],
            TaskState.COMPLETED: [],
        }.get(current, [])


class TaskStateMachine:
    """
    任务状态机（生产级安全增强版）

    新增安全能力：
    1. 工具白名单校验 — 每个状态/阶段只允许特定工具
    2. Token 预算追踪 — 每状态独立预算，超限强制退出
    3. RUNNING 内部分阶段 — plan → gather → analyze → execute
    4. Confirming 守卫 — 危险操作自动触发确认

    使用方式：
    sm = TaskStateMachine(task_id)

    # 状态操作（自动写 trace）
    sm.transition(to=TaskState.CLAIMED, ctx=TransitionContext(worker_id="coder-123"))
    sm.transition(to=TaskState.RUNNING, ctx=TransitionContext(start_time=time.time()))
    sm.transition(to=TaskState.VERIFIED, ctx=TransitionContext(verdict="PASS"))
    sm.transition(to=TaskState.COMPLETED, ctx=TransitionContext())

    # 安全操作
    sm.can_use_tool("shell_executor")           # 检查工具白名单
    sm.record_tokens(500, "gather")              # 记录 Token 消耗
    sm.check_token_budget()                      # 检查是否超预算
    sm.advance_phase("gather")                   # 推进 RUNNING 内部阶段
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._state: TaskState = TaskState.PENDING
        self._ctx: TransitionContext = TransitionContext()
        self._trace: List[StateTransition] = []
        self._trace_file = os.path.join(TRACE_DIR, f"{task_id}.jsonl")

        # 安全组件
        self._token_tracker = TokenTracker(task_id=task_id)
        self._confirm_guard = ConfirmationGuard()
        self._current_phase: Optional[str] = None  # RUNNING 内部阶段

    @property
    def state(self) -> TaskState:
        """当前任务状态"""
        return self._state

    @property
    def trace(self) -> List[StateTransition]:
        """状态跳转历史记录列表"""
        return self._trace

    def transition(self, to: TaskState, ctx: Optional[TransitionContext] = None) -> bool:
        """
        执行状态跳转

        Returns:
            True = 跳转成功
            False = 跳转被拒绝（条件不满足）
        """
        if ctx is not None:
            self._ctx = ctx

        # 检查跳转是否合法
        if not TransitionRule.can_transition(self._state, to, self._ctx):
            valid = [s.value for s in TransitionRule.get_valid_next_states(self._state)]
            print(f"[StateMachine] {self.task_id}: {self._state.value} → {to.value} 被拒绝 (valid: {valid})")
            return False

        # 执行跳转
        old = self._state
        self._state = to

        # 如果进入 PLANNING，标记阶段
        if to == TaskState.PLANNING:
            self._current_phase = "plan"
        # 如果进入 RUNNING，初始化阶段为 gather（plan 已在 PLANNING 完成）
        elif to == TaskState.RUNNING and old == TaskState.PLANNING:
            self._current_phase = "gather"
        elif to == TaskState.RUNNING:
            self._current_phase = "plan"
        # 离开 RUNNING/PLANNING，清除阶段
        if old in (TaskState.RUNNING, TaskState.PLANNING) and to not in (TaskState.RUNNING, TaskState.PLANNING):
            self._current_phase = None

        # 构建记录（含安全字段）
        budget_ok, budget_used, budget_limit = self._token_tracker.check_budget(
            old.value, self._current_phase
        )
        record = StateTransition(
            task_id=self.task_id,
            from_state=old,
            to_state=to,
            ts=time.time(),
            worker_id=self._ctx.worker_id,
            verdict=self._ctx.verdict,
            causes=self._ctx.verdict_causes,
            error_msg=self._ctx.error_msg,
            phase=self._current_phase,
            tokens_used=self._ctx.tokens_used,
            cumulative_tokens=self._token_tracker.total_tokens,
            token_budget=budget_limit,
            budget_exceeded=not budget_ok,
        )
        self._trace.append(record)
        self._write_trace_record(record)

        print(f"[StateMachine] {self.task_id}: {old.value} → {to.value}" +
              (f" (phase={self._current_phase})" if self._current_phase else "") +
              (f" (verdict={self._ctx.verdict})" if self._ctx.verdict else "") +
              (f" (tokens={self._token_tracker.total_tokens})" if self._token_tracker.total_tokens > 0 else ""))
        return True

    def check_timeout(self, timeout: float = DEFAULT_TIMEOUT) -> Optional[TaskState]:
        """
        超时检查。如果当前状态是 CLAIMED/PLANNING/RUNNING 且超时就转换为 FAILED。

        Returns:
            TaskState.FAILED 如果超时，None 如果未超时
        """
        if self._state not in (TaskState.CLAIMED, TaskState.PLANNING, TaskState.RUNNING):
            return None
        if self._ctx.start_time is None:
            return None

        if time.time() - self._ctx.start_time > timeout:
            self._ctx.error_msg = f"timeout after {timeout}s"
            self._ctx.verdict = "FAIL"
            self.transition(TaskState.FAILED, self._ctx)
            return TaskState.FAILED
        return None

    def retry_with_increment(self) -> bool:
        """
        RETRY 状态时调用，自动 increment retry_count 后跳回 PENDING
        以便编排器重新认领任务。
        如果次数耗尽则跳转 FAILED。

        Returns:
            True = 成功跳转（PENDING 或 FAILED）
            False = 跳转被拒绝（状态不是 RETRY）
        """
        if self._state != TaskState.RETRY:
            return False

        self._ctx.retry_count += 1
        self._ctx.verdict = None  # 清除上次的 FAIL
        self._ctx.error_msg = None

        # 回到 PENDING，让编排器重新认领
        if self._ctx.retry_count < MAX_RETRY:
            return self.transition(TaskState.PENDING, self._ctx)
        else:
            # 次数耗尽，直接 FAILED
            self._ctx.error_msg = f"max retry ({MAX_RETRY}) exceeded"
            return self.transition(TaskState.FAILED, self._ctx)

    # ========================================
    # 安全方法：工具白名单 + Token 预算 + Confirming
    # ========================================

    def can_use_tool(self, tool_name: str) -> Tuple[bool, str]:
        """
        检查工具在当前状态/阶段是否允许使用

        Returns:
            (is_allowed, reason)
        """
        allowed = is_tool_allowed(tool_name, self._state.value, self._current_phase)
        if allowed:
            return True, ""
        reason = f"工具 '{tool_name}' 在状态 '{self._state.value}'"
        if self._current_phase:
            reason += f" (阶段 '{self._current_phase}')"
        reason += " 的白名单中不存在"
        return False, reason

    def record_tokens(self, tokens: int, phase: str = None) -> None:
        """
        记录 Token 消耗

        Args:
            tokens: 本次消耗的 Token 数
            phase: RUNNING 内部阶段（可选）
        """
        effective_phase = phase or self._current_phase
        self._token_tracker.record(self._state.value, tokens, effective_phase)
        self._ctx.tokens_used = tokens

    def check_token_budget(self) -> Tuple[bool, int, int]:
        """
        检查当前状态/阶段是否超 Token 预算

        Returns:
            (is_within_budget, used, budget)
        """
        return self._token_tracker.check_budget(self._state.value, self._current_phase)

    def check_and_enforce_token_budget(self) -> Optional[str]:
        """
        检查 Token 预算，超限则自动失败

        Returns:
            None = 预算充足
            error_msg = 超限错误信息（状态已转为 FAILED）
        """
        ok, used, budget = self.check_token_budget()
        if ok:
            return None

        error_msg = f"Token 预算超限: {used}/{budget}"
        if self._current_phase:
            error_msg += f" (阶段: {self._current_phase})"
        print(f"[StateMachine] {self.task_id}: ⚠️ {error_msg}")

        self._ctx.error_msg = error_msg
        self._ctx.verdict = "FAIL"
        self.transition(TaskState.FAILED, self._ctx)
        return error_msg

    def advance_phase(self, new_phase: str) -> bool:
        """
        推进 RUNNING 内部阶段

        合法的阶段转换：
        plan → gather → analyze → execute
        也允许回退：analyze → gather（数据不足时）

        Returns:
            True = 阶段转换成功
        """
        if self._state != TaskState.RUNNING:
            print(f"[StateMachine] {self.task_id}: 阶段推进被拒绝，当前状态不是 RUNNING")
            return False

        if new_phase not in RUNNING_PHASES:
            print(f"[StateMachine] {self.task_id}: 未知阶段 '{new_phase}'")
            return False

        old_phase = self._current_phase
        self._current_phase = new_phase
        self._ctx.current_phase = new_phase

        # 写一条阶段转换 trace
        record = StateTransition(
            task_id=self.task_id,
            from_state=TaskState.RUNNING,
            to_state=TaskState.RUNNING,
            ts=time.time(),
            worker_id=self._ctx.worker_id,
            phase=new_phase,
            cumulative_tokens=self._token_tracker.total_tokens,
        )
        self._trace.append(record)
        self._write_trace_record(record)

        print(f"[StateMachine] {self.task_id}: phase {old_phase} → {new_phase}")
        return True

    def request_confirmation(self, tool_name: str, command: str) -> Optional[ConfirmRequest]:
        """
        请求危险操作确认

        Returns:
            None = 不需要确认（工具不在危险列表或已 always 允许）
            ConfirmRequest = 需要用户确认
        """
        return self._confirm_guard.check(tool_name, command)

    def record_confirmation(self, request: ConfirmRequest, response: ConfirmResponse) -> None:
        """记录用户确认结果"""
        self._confirm_guard.record(request, response)

    @property
    def current_phase(self) -> Optional[str]:
        """当前 RUNNING 内部阶段"""
        return self._current_phase

    @property
    def token_tracker(self) -> TokenTracker:
        """Token 追踪器（只读访问）"""
        return self._token_tracker

    @property
    def confirm_guard(self) -> ConfirmationGuard:
        """确认守卫（只读访问）"""
        return self._confirm_guard

    def get_trace(self) -> List[dict]:
        """获取结构化跳转链路"""
        return [t.to_dict() for t in self._trace]

    def _write_trace_record(self, record: StateTransition):
        """将单条跳转记录追加写入 JSONL 文件"""
        try:
            with open(self._trace_file, "a") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[StateMachine] trace write error: {e}")

    def summary(self) -> dict:
        """状态机当前快照（含安全信息）"""
        return {
            "task_id": self.task_id,
            "state": self._state.value,
            "phase": self._current_phase,
            "retry_count": self._ctx.retry_count,
            "worker_id": self._ctx.worker_id,
            "verdict": self._ctx.verdict,
            "transitions": len(self._trace),
            "tokens": self._token_tracker.summary(),
            "confirmations": self._confirm_guard.summary(),
        }


# ========== 单元测试 ==========

def _test():
    """状态机测试（含安全增强）"""
    print("\n=== 状态机单元测试 ===\n")

    # Test 1: 正常流程
    print("Test 1: 正常完成流程")
    sm = TaskStateMachine("test-task-001")
    assert sm.state == TaskState.PENDING

    sm.transition(TaskState.CLAIMED, TransitionContext(worker_id="coder-001"))
    assert sm.state == TaskState.CLAIMED

    sm.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
    assert sm.state == TaskState.PLANNING
    assert sm.current_phase == "plan"

    sm.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))
    assert sm.state == TaskState.RUNNING
    assert sm.current_phase == "gather"  # 从 PLANNING 进入 RUNNING 应该是 gather

    sm.transition(TaskState.VERIFIED, TransitionContext(verdict="PASS"))
    assert sm.state == TaskState.VERIFIED
    assert sm.current_phase is None  # 离开 RUNNING，阶段清除

    sm.transition(TaskState.COMPLETED, TransitionContext())
    assert sm.state == TaskState.COMPLETED
    print("  ✅ PASS\n")

    # Test 2: FAIL → RETRY → 重试成功
    print("Test 2: FAIL → RETRY 循环")
    sm2 = TaskStateMachine("test-task-002")
    sm2.transition(TaskState.CLAIMED, TransitionContext(worker_id="coder-002"))
    sm2.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
    sm2.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))
    sm2.transition(TaskState.RETRY, TransitionContext(verdict="FAIL", retry_count=0))

    assert sm2.state == TaskState.RETRY
    sm2.retry_with_increment()  # count = 1
    assert sm2.state == TaskState.PENDING

    sm2.transition(TaskState.CLAIMED, TransitionContext(worker_id="coder-002"))
    sm2.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
    sm2.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))
    sm2.transition(TaskState.RETRY, TransitionContext(verdict="FAIL", retry_count=1))
    sm2.retry_with_increment()  # count = 2
    assert sm2.state == TaskState.PENDING

    sm2.transition(TaskState.CLAIMED, TransitionContext(worker_id="coder-002"))
    sm2.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
    sm2.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))
    sm2.transition(TaskState.RETRY, TransitionContext(verdict="FAIL", retry_count=2))
    sm2.retry_with_increment()  # count = 3，触发 FAILED
    assert sm2.state == TaskState.FAILED
    print("  ✅ PASS\n")

    # Test 3: 非法跳转被拒绝
    print("Test 3: 非法跳转拒绝")
    sm3 = TaskStateMachine("test-task-003")
    ok = sm3.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))
    assert ok == False
    assert sm3.state == TaskState.PENDING
    # 不能跳过 PLANNING 直接到 RUNNING
    sm3.transition(TaskState.CLAIMED, TransitionContext(worker_id="c-003"))
    ok = sm3.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))
    assert ok == False
    assert sm3.state == TaskState.CLAIMED
    print("  ✅ PASS\n")

    # Test 4: trace 记录
    print("Test 4: trace 记录")
    trace = sm.get_trace()
    assert len(trace) == 5  # PENDING→CLAIMED→PLANNING→RUNNING→VERIFIED→COMPLETED
    assert trace[0]["to"] == "claimed"
    assert trace[1]["to"] == "planning"
    assert trace[-1]["to"] == "completed"
    print("  ✅ PASS\n")

    # Test 5: 超时检测
    print("Test 5: 超时检测")
    sm5 = TaskStateMachine("test-task-005")
    sm5.transition(TaskState.CLAIMED, TransitionContext(worker_id="c-005"))
    sm5.transition(TaskState.PLANNING, TransitionContext(start_time=time.time() - 999))
    result = sm5.check_timeout(timeout=60)
    assert result == TaskState.FAILED
    assert sm5.state == TaskState.FAILED
    print("  ✅ PASS\n")

    # ---- 安全增强测试 ----

    # Test 6: 工具白名单校验
    print("Test 6: 工具白名单校验")
    sm6 = TaskStateMachine("test-task-006")

    # PENDING 状态：不允许任何工具
    ok, reason = sm6.can_use_tool("file_reader")
    assert ok == False
    assert "pending" in reason

    sm6.transition(TaskState.CLAIMED, TransitionContext(worker_id="c-006"))
    sm6.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))

    # PLANNING 阶段：不允许任何工具（纯推理）
    ok, reason = sm6.can_use_tool("file_reader")
    assert ok == False
    assert "planning" in reason

    sm6.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))
    assert sm6.current_phase == "gather"

    # gather 阶段：允许只读工具
    ok, _ = sm6.can_use_tool("file_reader")
    assert ok == True  # gather 允许只读工具
    ok, reason = sm6.can_use_tool("shell_executor")
    assert ok == False  # gather 不允许 shell

    # 推进到 execute 阶段
    sm6.advance_phase("execute")
    ok, _ = sm6.can_use_tool("shell_executor")
    assert ok == True  # execute 允许 shell
    print("  ✅ PASS\n")

    # Test 7: RUNNING 内部阶段推进
    print("Test 7: RUNNING 阶段推进")
    sm7 = TaskStateMachine("test-task-007")
    sm7.transition(TaskState.CLAIMED, TransitionContext(worker_id="c-007"))
    sm7.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
    sm7.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))

    assert sm7.current_phase == "gather"  # 从 PLANNING 进入是 gather
    sm7.advance_phase("analyze")
    assert sm7.current_phase == "analyze"
    # 回退到 gather（数据不足）
    sm7.advance_phase("gather")
    assert sm7.current_phase == "gather"
    sm7.advance_phase("execute")
    assert sm7.current_phase == "execute"

    # 非 RUNNING 状态不能推进阶段
    sm7.transition(TaskState.VERIFIED, TransitionContext(verdict="PASS"))
    ok = sm7.advance_phase("gather")
    assert ok == False
    print("  ✅ PASS\n")

    # Test 8: Token 预算追踪
    print("Test 8: Token 预算追踪")
    sm8 = TaskStateMachine("test-task-008")
    sm8.transition(TaskState.CLAIMED, TransitionContext(worker_id="c-008"))
    sm8.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
    sm8.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))

    sm8.advance_phase("gather")
    sm8.record_tokens(500)
    ok, used, budget = sm8.check_token_budget()
    assert ok == True
    assert used == 500

    sm8.record_tokens(1800)
    ok, used, budget = sm8.check_token_budget()
    assert ok == False  # 2300 > 2000 gather 预算
    print("  ✅ PASS\n")

    # Test 9: Token 预算超限自动失败
    print("Test 9: Token 预算超限自动失败")
    sm9 = TaskStateMachine("test-task-009")
    sm9.transition(TaskState.CLAIMED, TransitionContext(worker_id="c-009"))
    sm9.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
    sm9.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))
    sm9.advance_phase("gather")

    # 模拟大量 Token 消耗
    sm9._token_tracker.record("RUNNING", 2500, "gather")
    error_msg = sm9.check_and_enforce_token_budget()
    assert error_msg is not None
    assert sm9.state == TaskState.FAILED
    assert "超限" in error_msg
    print("  ✅ PASS\n")

    # Test 10: Confirming 守卫
    print("Test 10: Confirming 守卫")
    sm10 = TaskStateMachine("test-task-010")
    sm10.transition(TaskState.CLAIMED, TransitionContext(worker_id="c-010"))
    sm10.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
    sm10.transition(TaskState.RUNNING, TransitionContext(start_time=time.time(), extra={"plan_ready": True}))
    sm10.advance_phase("execute")

    # 安全命令不需要确认
    req = sm10.request_confirmation("shell_executor", "ls -la /tmp")
    assert req is None

    # 危险命令需要确认
    req = sm10.request_confirmation("shell_executor", "rm -rf /tmp/test")
    assert req is not None
    assert req.level == "critical"

    # 用户选择 always
    from security_config import ConfirmAction as CA
    sm10.record_confirmation(req, ConfirmResponse(action=CA.ALWAYS))

    # 同类操作自动放行
    req2 = sm10.request_confirmation("shell_executor", "rm -rf /tmp/other")
    assert req2 is None
    print("  ✅ PASS\n")

    # Test 11: trace 包含安全字段
    print("Test 11: trace 安全字段")
    trace8 = sm8.get_trace()
    # 找到 RUNNING 阶段的 trace 记录
    running_records = [t for t in trace8 if t.get("phase")]
    assert len(running_records) > 0
    assert "tokens_used" in running_records[0]
    assert "cumulative_tokens" in running_records[0]
    print("  ✅ PASS\n")

    # Test 12: summary 包含安全信息
    print("Test 12: summary 安全信息")
    s = sm8.summary()
    assert "tokens" in s
    assert "confirmations" in s
    assert "phase" in s
    assert s["tokens"]["total_tokens"] > 0
    print("  ✅ PASS\n")

    print("=== 所有测试通过 ===\n")


if __name__ == "__main__":
    _test()
