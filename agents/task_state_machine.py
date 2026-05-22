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
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field

# 路径
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
TRACE_DIR = "/tmp/deepin_traces"
os.makedirs(TRACE_DIR, exist_ok=True)


class TaskState(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 入队，未分配
    CLAIMED = "claimed"       # Worker 认领
    RUNNING = "running"       # 执行中
    VERIFIED = "verified"     # Verifier 通过
    COMPLETED = "completed"   # 流程终结
    FAILED = "failed"         # 不可恢复失败
    RETRY = "retry"           # 打回重做


# 超时常量
DEFAULT_TIMEOUT = 60          # 默认任务超时（秒）
MAX_RETRY = 3                 # 最大重试次数
HEARTBEAT_INTERVAL = 5        # 心跳间隔（秒）


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

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "from": self.from_state.value,
            "to": self.to_state.value,
            "ts": self.ts,
            "worker_id": self.worker_id,
            "verdict": self.verdict,
            "causes": self.causes,
            "error_msg": self.error_msg,
        }


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

            # CLAIMED → RUNNING: 必须有 start_time（计时开始）
            (TaskState.CLAIMED, TaskState.RUNNING):
                lambda c: c.start_time is not None,

            # RUNNING → VERIFIED: Verifier 给出 PASS
            (TaskState.RUNNING, TaskState.VERIFIED):
                lambda c: c.verdict == "PASS",

            # RUNNING → RETRY: Verifier 给出 FAIL，重试次数未满
            (TaskState.RUNNING, TaskState.RETRY):
                lambda c: c.verdict == "FAIL" and c.retry_count < MAX_RETRY,

            # RETRY → RUNNING: 重试次数未满
            (TaskState.RETRY, TaskState.RUNNING):
                lambda c: c.retry_count < MAX_RETRY,

            # RETRY → FAILED: 重试次数耗尽
            (TaskState.RETRY, TaskState.FAILED):
                lambda c: c.retry_count >= MAX_RETRY,

            # VERIFIED → COMPLETED: 通过即完成（无后续验证流程）
            (TaskState.VERIFIED, TaskState.COMPLETED):
                lambda c: True,

            # RUNNING → FAILED: 重试耗尽 OR 超时（timeout in error_msg）
            (TaskState.RUNNING, TaskState.FAILED):
                lambda c: (c.verdict == "FAIL" and c.retry_count >= MAX_RETRY) \
                          or (c.error_msg and "timeout" in c.error_msg),
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
            TaskState.CLAIMED:  [TaskState.RUNNING, TaskState.FAILED],
            TaskState.RUNNING:  [TaskState.VERIFIED, TaskState.RETRY, TaskState.FAILED],
            TaskState.VERIFIED: [TaskState.COMPLETED],
            TaskState.RETRY:    [TaskState.RUNNING, TaskState.FAILED],
            TaskState.FAILED:   [],
            TaskState.COMPLETED: [],
        }.get(current, [])


class TaskStateMachine:
    """
    任务状态机

    使用方式：
    sm = TaskStateMachine(task_id)

    # 状态操作（自动写 trace）
    sm.transition(to=TaskState.CLAIMED, ctx=TransitionContext(worker_id="coder-123"))
    sm.transition(to=TaskState.RUNNING, ctx=TransitionContext(start_time=time.time()))
    sm.transition(to=TaskState.VERIFIED, ctx=TransitionContext(verdict="PASS"))
    sm.transition(to=TaskState.COMPLETED, ctx=TransitionContext())

    # 查询
    sm.get_state()          # 当前状态
    sm.check_timeout(60)   # 超时检查，返回 TaskState.FAILED 如果超时
    sm.get_trace()         # 跳转链路
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._state: TaskState = TaskState.PENDING
        self._ctx: TransitionContext = TransitionContext()
        self._trace: List[StateTransition] = []
        self._trace_file = os.path.join(TRACE_DIR, f"{task_id}.jsonl")

    @property
    def state(self) -> TaskState:
        return self._state

    @property
    def trace(self) -> List[StateTransition]:
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

        # 构建记录
        record = StateTransition(
            task_id=self.task_id,
            from_state=old,
            to_state=to,
            ts=time.time(),
            worker_id=self._ctx.worker_id,
            verdict=self._ctx.verdict,
            causes=self._ctx.verdict_causes,
            error_msg=self._ctx.error_msg,
        )
        self._trace.append(record)
        self._write_trace_record(record)

        print(f"[StateMachine] {self.task_id}: {old.value} → {to.value}" +
              (f" (verdict={self._ctx.verdict})" if self._ctx.verdict else ""))
        return True

    def check_timeout(self, timeout: float = DEFAULT_TIMEOUT) -> Optional[TaskState]:
        """
        超时检查。如果当前状态是 CLAIMED 或 RUNNING 且超时就转换为 FAILED。

        Returns:
            TaskState.FAILED 如果超时，None 如果未超时
        """
        if self._state not in (TaskState.CLAIMED, TaskState.RUNNING):
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
        RETRY 状态时调用，自动 increment retry_count 后尝试跳回 RUNNING。
        如果次数耗尽则跳转 FAILED。

        Returns:
            True = 成功跳转（RUNNING 或 FAILED）
            False = 跳转被拒绝（状态不是 RETRY）
        """
        if self._state != TaskState.RETRY:
            return False

        self._ctx.retry_count += 1
        self._ctx.verdict = None  # 清除上次的 FAIL
        self._ctx.error_msg = None

        # 先试 RUNNING（还有重试机会）
        if self._ctx.retry_count < MAX_RETRY:
            return self.transition(TaskState.RUNNING, self._ctx)
        else:
            # 次数耗尽，直接 FAILED
            self._ctx.error_msg = f"max retry ({MAX_RETRY}) exceeded"
            return self.transition(TaskState.FAILED, self._ctx)

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
        """状态机当前快照"""
        return {
            "task_id": self.task_id,
            "state": self._state.value,
            "retry_count": self._ctx.retry_count,
            "worker_id": self._ctx.worker_id,
            "verdict": self._ctx.verdict,
            "transitions": len(self._trace),
        }


# ========== 单元测试 ==========

def _test():
    """状态机基本测试"""
    print("\n=== 状态机单元测试 ===\n")

    # Test 1: 正常流程
    print("Test 1: 正常完成流程")
    sm = TaskStateMachine("test-task-001")
    assert sm.state == TaskState.PENDING

    sm.transition(TaskState.CLAIMED, TransitionContext(worker_id="coder-001"))
    assert sm.state == TaskState.CLAIMED

    sm.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))
    assert sm.state == TaskState.RUNNING

    sm.transition(TaskState.VERIFIED, TransitionContext(verdict="PASS"))
    assert sm.state == TaskState.VERIFIED

    sm.transition(TaskState.COMPLETED, TransitionContext())
    assert sm.state == TaskState.COMPLETED
    print("  ✅ PASS\n")

    # Test 2: FAIL → RETRY → 重试成功
    print("Test 2: FAIL → RETRY 循环")
    sm2 = TaskStateMachine("test-task-002")
    sm2.transition(TaskState.CLAIMED, TransitionContext(worker_id="coder-002"))
    sm2.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))
    sm2.transition(TaskState.RETRY, TransitionContext(verdict="FAIL", retry_count=0))

    assert sm2.state == TaskState.RETRY
    sm2.retry_with_increment()  # count = 1
    assert sm2.state == TaskState.RUNNING

    sm2.transition(TaskState.RETRY, TransitionContext(verdict="FAIL", retry_count=1))
    sm2.retry_with_increment()  # count = 2
    assert sm2.state == TaskState.RUNNING

    sm2.transition(TaskState.RETRY, TransitionContext(verdict="FAIL", retry_count=2))
    sm2.retry_with_increment()  # count = 3，触发 FAILED
    assert sm2.state == TaskState.FAILED
    print("  ✅ PASS\n")

    # Test 3: 非法跳转被拒绝
    print("Test 3: 非法跳转拒绝")
    sm3 = TaskStateMachine("test-task-003")
    # PENDING 不能直接跳到 RUNNING（必须先 CLAIMED）
    ok = sm3.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))
    assert ok == False
    assert sm3.state == TaskState.PENDING
    print("  ✅ PASS\n")

    # Test 4: trace 记录
    print("Test 4: trace 记录")
    trace = sm.get_trace()
    assert len(trace) == 4  # PENDING→CLAIMED→RUNNING→VERIFIED→COMPLETED
    assert trace[0]["to"] == "claimed"
    assert trace[-1]["to"] == "completed"
    print("  ✅ PASS\n")

    # Test 5: 超时检测
    print("Test 5: 超时检测")
    sm5 = TaskStateMachine("test-task-005")
    sm5.transition(TaskState.CLAIMED, TransitionContext(worker_id="c-005"))
    sm5.transition(TaskState.RUNNING, TransitionContext(start_time=time.time() - 999))
    result = sm5.check_timeout(timeout=60)
    assert result == TaskState.FAILED
    assert sm5.state == TaskState.FAILED
    print("  ✅ PASS\n")

    print("=== 所有测试通过 ===\n")


if __name__ == "__main__":
    _test()
