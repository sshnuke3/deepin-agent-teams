#!/usr/bin/env python3
"""
tools/analyze_traces.py - Trace 分析工具

分析 data/traces/*.jsonl，输出：
1. 任务级摘要：成功/失败/重试次数
2. 系统瓶颈：高频 FAIL 点
3. Worker 效率：每个 worker 的任务量/耗时
4. 状态机健康度：跳转链路统计
"""
import os
import sys
import json
import glob
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

TRACE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "traces")


@dataclass
class TaskTraceSummary:
    task_id: str
    transitions: List[dict] = field(default_factory=list)
    final_state: str = "unknown"
    retry_count: int = 0
    worker_id: Optional[str] = None
    error_msg: Optional[str] = None
    causes: List[str] = field(default_factory=list)

    @property
    def is_completed(self) -> bool:
        return self.final_state == "completed"

    @property
    def is_failed(self) -> bool:
        return self.final_state == "failed"

    @property
    def duration(self) -> float:
        if len(self.transitions) < 2:
            return 0.0
        return self.transitions[-1]["ts"] - self.transitions[0]["ts"]


def load_all_traces() -> Dict[str, TaskTraceSummary]:
    """加载所有 trace 文件"""
    summaries = {}
    files = glob.glob(os.path.join(TRACE_DIR, "*.jsonl"))

    for path in files:
        task_id = os.path.basename(path).replace(".jsonl", "")
        transitions = []
        with open(path) as f:
            for line in f:
                try:
                    transitions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not transitions:
            continue

        final = transitions[-1]
        retry_count = sum(1 for t in transitions if t.get("to") == "retry")
        fail_causes = [t.get("causes", []) for t in transitions if t.get("to") in ("failed", "retry")]
        causes = []
        for c in fail_causes:
            causes.extend(c if isinstance(c, list) else [])

        summaries[task_id] = TaskTraceSummary(
            task_id=task_id,
            transitions=transitions,
            final_state=final.get("to", "unknown"),
            retry_count=retry_count,
            worker_id=final.get("worker_id"),
            error_msg=final.get("error_msg"),
            causes=causes,
        )

    return summaries


def print_summary(summaries: Dict[str, TaskTraceSummary]):
    total = len(summaries)
    completed = sum(1 for s in summaries.values() if s.is_completed)
    failed = sum(1 for s in summaries.values() if s.is_failed)
    retry_tasks = sum(1 for s in summaries.values() if s.retry_count > 0)

    durations = [s.duration for s in summaries.values() if s.duration > 0]
    avg_duration = sum(durations) / len(durations) if durations else 0

    print(f"\n{'='*50}")
    print(f"Trace 分析报告（{total} 个任务）")
    print(f"{'='*50}")
    print(f"  完成: {completed} ({100*completed/total:.1f}%)")
    print(f"  失败: {failed} ({100*failed/total:.1f}%)")
    print(f"  重试过: {retry_tasks} ({100*retry_tasks/total:.1f}%)")
    print(f"  平均耗时: {avg_duration:.1f}s")
    print()

    # 瓶颈分析：高频 FAIL / RETRY 原因
    cause_count = defaultdict(int)
    for s in summaries.values():
        for c in s.causes:
            cause_count[c] += 1

    if cause_count:
        print("Top 失败原因（需要优先修）:")
        for cause, count in sorted(cause_count.items(), key=lambda x: -x[1])[:5]:
            print(f"  × {cause}: {count}次")
        print()

    # 跳转链路统计
    transition_count = defaultdict(int)
    for s in summaries.values():
        for t in s.transitions:
            transition_count[f"{t['from']}→{t['to']}"] += 1

    print("状态跳转频率:")
    for k, v in sorted(transition_count.items(), key=lambda x: -x[1])[:8]:
        print(f"  {k}: {v}次")
    print()

    # Worker 分布
    worker_count = defaultdict(int)
    for s in summaries.values():
        if s.worker_id:
            # 只取 role 前缀
            role = s.worker_id.split("-")[0] if "-" in s.worker_id else s.worker_id
            worker_count[role] += 1

    if worker_count:
        print("Worker 任务分布:")
        for w, c in sorted(worker_count.items(), key=lambda x: -x[1]):
            print(f"  {w}: {c}个任务")
    print(f"{'='*50}")


def print_detail(summaries: Dict[str, TaskTraceSummary], limit: int = 10):
    """打印失败任务详情"""
    failed_tasks = [s for s in summaries.values() if s.is_failed]
    if not failed_tasks:
        print("无失败任务 ✓")
        return

    print(f"\n失败任务详情（{len(failed_tasks)} 个）:")
    for s in sorted(failed_tasks, key=lambda x: -x.retry_count)[:limit]:
        print(f"\n  task: {s.task_id}")
        print(f"  重试: {s.retry_count}次 | 耗时: {s.duration:.1f}s")
        if s.causes:
            print(f"  原因: {'; '.join(s.causes[:3])}")
        if s.error_msg:
            print(f"  错误: {s.error_msg}")
        # 展示跳转链路
        path = " → ".join([t["to"] for t in s.transitions])
        print(f"  路径: {path}")


def analyze_checkpoints():
    """分析 checkpoint 文件"""
    cp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "checkpoints")
    if not os.path.exists(cp_dir):
        print("[trace] checkpoint 目录不存在（尚未实现 P1-2）")
        return

    task_checkpoints = glob.glob(os.path.join(cp_dir, "*/"))
    total_cp = sum(len(os.listdir(d)) for d in task_checkpoints if os.path.isdir(d))
    print(f"[trace] checkpoint 文件数: {total_cp}（{len(task_checkpoints)} 个任务）")


if __name__ == "__main__":
    summaries = load_all_traces()
    if not summaries:
        print(f"[trace] 暂无 trace 数据（目录: {TRACE_DIR}）")
        print("运行 orchestrator_v3 后才会生成 trace 文件")
        sys.exit(0)

    print_summary(summaries)
    print_detail(summaries)

    print()
    analyze_checkpoints()
