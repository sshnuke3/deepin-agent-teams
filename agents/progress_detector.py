#!/usr/bin/env python3
"""
agents/progress_detector.py — Agent进展检测

防止Agent间循环推诿：
1. 跟踪每轮输出的hash
2. 检测连续重复输出
3. 检测长时间无进展
4. 触发熔断机制
"""
import time
import hashlib
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ProgressRecord:
    """一次执行记录"""
    ts: float
    output_hash: str
    token_used: int
    phase: str = ""
    summary: str = ""  # 摘要（用于调试）


class ProgressDetector:
    """
    进展检测器

    使用方式：
        detector = ProgressDetector(max_idle_turns=3, max_stale_seconds=120)
        for turn in range(max_turns):
            output = agent.execute(...)
            record = detector.record(output, tokens=100)
            if detector.should_abort():
                break
    """

    def __init__(
        self,
        max_idle_turns: int = 3,
        max_stale_seconds: int = 120,
        similarity_threshold: float = 0.9,
    ):
        """
        Args:
            max_idle_turns: 连续无进展轮次上限（触发熔断）
            max_stale_seconds: 最大停滞时间（秒）
            similarity_threshold: 输出相似度阈值（0-1，超过视为重复）
        """
        self.max_idle_turns = max_idle_turns
        self.max_stale_seconds = max_stale_seconds
        self.similarity_threshold = similarity_threshold

        self._records: List[ProgressRecord] = []
        self._idle_count: int = 0
        self._last_progress_ts: float = time.time()
        self._abort: bool = False
        self._abort_reason: str = ""

    def record(
        self,
        output: str,
        tokens: int = 0,
        phase: str = "",
        summary: str = "",
    ) -> ProgressRecord:
        """
        记录一次执行输出

        Args:
            output: Agent输出内容
            tokens: 消耗的token数
            phase: 当前阶段
            summary: 摘要

        Returns:
            ProgressRecord
        """
        output_hash = hashlib.md5(output.encode()).hexdigest()[:12]
        record = ProgressRecord(
            ts=time.time(),
            output_hash=output_hash,
            token_used=tokens,
            phase=phase,
            summary=summary,
        )
        self._records.append(record)

        # 检测进展
        is_progress = self._check_progress(output, output_hash)
        if is_progress:
            self._idle_count = 0
            self._last_progress_ts = time.time()
        else:
            self._idle_count += 1

        # 检查熔断条件
        self._check_abort()

        return record

    def _check_progress(self, output: str, output_hash: str) -> bool:
        """检测本轮是否有进展"""
        if len(self._records) <= 1:
            return True

        # 1. 完全重复（与上一轮比较）
        prev_hash = self._records[-2].output_hash
        if output_hash == prev_hash:
            return False

        # 2. 空输出或极短输出
        if len(output.strip()) < 10:
            return False

        return True

    def _check_abort(self):
        """检查是否需要熔断"""
        # 条件1：连续无进展轮次
        if self._idle_count >= self.max_idle_turns:
            self._abort = True
            self._abort_reason = f"连续 {self._idle_count} 轮无进展（max={self.max_idle_turns}）"
            return

        # 条件2：停滞时间过长
        stale_seconds = time.time() - self._last_progress_ts
        if stale_seconds > self.max_stale_seconds:
            self._abort = True
            self._abort_reason = f"停滞 {stale_seconds:.0f}s（max={self.max_stale_seconds}s）"
            return

    def should_abort(self) -> bool:
        """是否应该熔断"""
        return self._abort

    def abort_reason(self) -> str:
        """熔断原因"""
        return self._abort_reason

    def idle_count(self) -> int:
        """连续无进展轮次"""
        return self._idle_count

    def total_records(self) -> int:
        """总记录数"""
        return len(self._records)

    def summary(self) -> dict:
        """检测器状态摘要"""
        return {
            "total_records": len(self._records),
            "idle_count": self._idle_count,
            "max_idle_turns": self.max_idle_turns,
            "should_abort": self._abort,
            "abort_reason": self._abort_reason,
            "stale_seconds": round(time.time() - self._last_progress_ts, 1),
        }

    def reset(self):
        """重置检测器（新任务开始时）"""
        self._records.clear()
        self._idle_count = 0
        self._last_progress_ts = time.time()
        self._abort = False
        self._abort_reason = ""


# ========== 单元测试 ==========

def _test():
    print("\n=== ProgressDetector 单元测试 ===\n")

    # Test 1: 正常进展
    print("Test 1: 正常进展（无熔断）")
    det = ProgressDetector(max_idle_turns=3, max_stale_seconds=60)
    det.record("第一步：分析代码结构", tokens=100, phase="analyze")
    det.record("第二步：发现3个问题", tokens=150, phase="analyze")
    det.record("第三步：生成修复方案", tokens=200, phase="execute")
    assert not det.should_abort()
    assert det.idle_count() == 0
    print("  ✅ PASS\n")

    # Test 2: 连续重复触发熔断
    print("Test 2: 连续重复触发熔断")
    det2 = ProgressDetector(max_idle_turns=2, max_stale_seconds=60)
    det2.record("分析结果", tokens=100)
    det2.record("分析结果", tokens=100)  # 重复
    assert det2.idle_count() == 1
    assert not det2.should_abort()
    det2.record("分析结果", tokens=100)  # 再次重复
    assert det2.idle_count() == 2
    assert det2.should_abort()
    assert "连续 2 轮无进展" in det2.abort_reason()
    print(f"  熔断原因: {det2.abort_reason()}")
    print("  ✅ PASS\n")

    # Test 3: 空输出视为无进展
    print("Test 3: 空输出视为无进展")
    det3 = ProgressDetector(max_idle_turns=2)
    det3.record("正常输出", tokens=100)
    det3.record("", tokens=50)  # 空输出
    assert det3.idle_count() == 1
    det3.record("  ", tokens=50)  # 空白
    assert det3.idle_count() == 2
    assert det3.should_abort()
    print("  ✅ PASS\n")

    # Test 4: summary
    print("Test 4: summary")
    s = det2.summary()
    assert s["should_abort"] == True
    assert s["idle_count"] == 2
    assert s["total_records"] == 3
    print(f"  summary={s}")
    print("  ✅ PASS\n")

    # Test 5: reset
    print("Test 5: reset")
    det2.reset()
    assert not det2.should_abort()
    assert det2.idle_count() == 0
    assert det2.total_records() == 0
    print("  ✅ PASS\n")

    print("=== 所有测试通过 ===\n")


if __name__ == "__main__":
    _test()
