"""
metrics_collector.py — 可观测性模块

核心思路（来自 Agent 生产级架构与质量保障实践）：
- 轻量级指标收集，不依赖 OpenTelemetry SDK
- 三大指标：Token 消耗、执行延迟、错误率
- 结构化日志输出（JSON Lines），可对接 Prometheus/Grafana
- 集成到状态机和 Worker，自动采集

为什么不用 OpenTelemetry SDK？
- 深度学习环境依赖复杂，pip 安装可能冲突
- 轻量方案够用，后续可平滑迁移到 OTel
"""

import json
import os
import sys
import time
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from pathlib import Path

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
METRICS_DIR = os.path.join(PROJECT_ROOT, "tests", "metrics")


# ============================================================
# 指标类型
# ============================================================

@dataclass
class MetricPoint:
    """单个指标点"""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp,
        }


@dataclass
class SpanInfo:
    """执行跨度信息（类似 OTel Span）"""
    span_id: str
    name: str
    start_time: float
    end_time: float = 0
    status: str = "ok"
    labels: Dict[str, str] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    def finish(self, status: str = "ok"):
        self.end_time = time.time()
        self.status = status

    def add_event(self, name: str, attributes: Dict = None):
        self.events.append({"name": name, "attributes": attributes or {}, "time": time.time()})

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "duration_ms": round(self.duration_ms, 1),
            "status": self.status,
            "labels": self.labels,
            "events": self.events,
        }


# ============================================================
# 指标收集器（单例）
# ============================================================

class MetricsCollector:
    """
    轻量级指标收集器

    三大核心指标：
    1. Token 消耗 — counter（按 state/phase/model 分维度）
    2. 执行延迟 — histogram（状态跳转、工具调用、整体任务）
    3. 错误率 — counter（按 error_type 分维度）

    使用方式：
        collector = MetricsCollector.get_instance()
        collector.record_token("RUNNING", "gather", 1500)
        collector.record_latency("task_duration", 3500, labels={"task_type": "code_analysis"})
        collector.record_error("E_TIMEOUT", labels={"state": "RUNNING"})
    """

    _instance: Optional["MetricsCollector"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._metrics: List[MetricPoint] = []
        self._spans: List[SpanInfo] = []
        self._active_spans: Dict[str, SpanInfo] = {}
        self._counters: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)

    @classmethod
    def get_instance(cls) -> "MetricsCollector":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset(cls):
        """重置单例（测试用）"""
        with cls._lock:
            if cls._instance:
                cls._instance._metrics.clear()
                cls._instance._spans.clear()
                cls._instance._active_spans.clear()
                cls._instance._counters.clear()
                cls._instance._histograms.clear()
            cls._instance = None

    # ---- Token 消耗 ----

    def record_token(self, state: str, phase: str, tokens: int, model: str = "default"):
        """记录 Token 消耗"""
        labels = {"state": state, "phase": phase, "model": model}
        point = MetricPoint(name="agent.token.usage", value=tokens, labels=labels)
        self._metrics.append(point)

        key = f"token.{state}.{phase}"
        self._counters[key] += tokens

    # ---- 执行延迟 ----

    def record_latency(self, name: str, duration_ms: float, labels: Dict[str, str] = None):
        """记录执行延迟"""
        point = MetricPoint(name=f"agent.latency.{name}", value=duration_ms, labels=labels or {})
        self._metrics.append(point)

        self._histograms[f"latency.{name}"].append(duration_ms)

    # ---- 错误率 ----

    def record_error(self, error_type: str, labels: Dict[str, str] = None):
        """记录错误"""
        all_labels = {"error_type": error_type}
        if labels:
            all_labels.update(labels)
        point = MetricPoint(name="agent.error.count", value=1, labels=all_labels)
        self._metrics.append(point)

        self._counters[f"error.{error_type}"] += 1

    # ---- Span 管理 ----

    def start_span(self, name: str, labels: Dict[str, str] = None) -> str:
        """开始一个执行跨度"""
        span_id = f"span-{len(self._spans) + len(self._active_spans) + 1:04d}"
        span = SpanInfo(
            span_id=span_id,
            name=name,
            start_time=time.time(),
            labels=labels or {},
        )
        self._active_spans[span_id] = span
        return span_id

    def finish_span(self, span_id: str, status: str = "ok"):
        """结束一个执行跨度"""
        span = self._active_spans.pop(span_id, None)
        if span:
            span.finish(status)
            self._spans.append(span)
            self.record_latency(span.name, span.duration_ms, span.labels)

    def add_span_event(self, span_id: str, event_name: str, attributes: Dict = None):
        """给活跃 span 添加事件"""
        span = self._active_spans.get(span_id)
        if span:
            span.add_event(event_name, attributes)

    # ---- 汇总统计 ----

    def get_summary(self) -> Dict[str, Any]:
        """获取指标汇总"""
        token_total = sum(v for k, v in self._counters.items() if k.startswith("token."))
        error_total = sum(v for k, v in self._counters.items() if k.startswith("error."))

        latency_stats = {}
        for key, values in self._histograms.items():
            if values:
                latency_stats[key] = {
                    "count": len(values),
                    "avg_ms": round(sum(values) / len(values), 1),
                    "min_ms": round(min(values), 1),
                    "max_ms": round(max(values), 1),
                    "p50_ms": round(sorted(values)[len(values) // 2], 1),
                    "p99_ms": round(sorted(values)[int(len(values) * 0.99)], 1) if len(values) >= 100 else round(max(values), 1),
                }

        return {
            "token_total": token_total,
            "token_by_state": {k.replace("token.", ""): v for k, v in self._counters.items() if k.startswith("token.")},
            "error_total": error_total,
            "error_by_type": {k.replace("error.", ""): v for k, v in self._counters.items() if k.startswith("error.")},
            "latency": latency_stats,
            "spans_total": len(self._spans),
            "metrics_total": len(self._metrics),
        }

    # ---- 持久化 ----

    def save(self, filename: str = None):
        """保存指标到 JSON Lines 文件"""
        os.makedirs(METRICS_DIR, exist_ok=True)
        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"metrics_{timestamp}.jsonl"

        filepath = os.path.join(METRICS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            for m in self._metrics:
                f.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")
        print(f"[Metrics] 已保存 {len(self._metrics)} 条指标到 {filepath}")
        return filepath


# ============================================================
# 计时上下文管理器
# ============================================================

class TimerContext:
    """自动计时的上下文管理器"""

    def __init__(self, collector: MetricsCollector, name: str, labels: Dict[str, str] = None):
        self.collector = collector
        self.name = name
        self.labels = labels
        self.start = 0

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        duration_ms = (time.time() - self.start) * 1000
        self.collector.record_latency(self.name, duration_ms, self.labels)


# ============================================================
# 内置测试
# ============================================================

if __name__ == "__main__":
    print("=== metrics_collector.py 测试 ===\n")

    # 每个测试前重置单例
    MetricsCollector.reset()

    # Test 1: 单例模式
    print("Test 1: 单例模式")
    c1 = MetricsCollector.get_instance()
    c2 = MetricsCollector.get_instance()
    assert c1 is c2
    print("  ✅ PASS\n")

    # Test 2: Token 记录
    print("Test 2: Token 记录")
    c1.record_token("RUNNING", "gather", 1500, "ernie-lite")
    c1.record_token("RUNNING", "execute", 2000, "ernie-3.5")
    c1.record_token("RUNNING", "gather", 500, "ernie-lite")
    summary = c1.get_summary()
    assert summary["token_total"] == 4000
    assert summary["token_by_state"]["RUNNING.gather"] == 2000
    assert summary["token_by_state"]["RUNNING.execute"] == 2000
    print("  ✅ PASS\n")

    # Test 3: 延迟记录
    print("Test 3: 延迟记录")
    c1.record_latency("state_transition", 5.2, {"from": "PENDING", "to": "CLAIMED"})
    c1.record_latency("state_transition", 3.1, {"from": "CLAIMED", "to": "RUNNING"})
    c1.record_latency("task_duration", 15000, {"task_type": "code_analysis"})
    summary = c1.get_summary()
    assert summary["latency"]["latency.state_transition"]["count"] == 2
    assert summary["latency"]["latency.task_duration"]["avg_ms"] == 15000
    print("  ✅ PASS\n")

    # Test 4: 错误记录
    print("Test 4: 错误记录")
    c1.record_error("E_TIMEOUT", {"state": "RUNNING"})
    c1.record_error("E_TOOL_BLOCKED", {"state": "RUNNING"})
    c1.record_error("E_TIMEOUT", {"state": "RUNNING"})
    summary = c1.get_summary()
    assert summary["error_total"] == 3
    assert summary["error_by_type"]["E_TIMEOUT"] == 2
    assert summary["error_by_type"]["E_TOOL_BLOCKED"] == 1
    print("  ✅ PASS\n")

    # Test 5: Span 管理
    print("Test 5: Span 管理")
    span_id = c1.start_span("task_execution", {"task_id": "t-001"})
    c1.add_span_event(span_id, "tool_call", {"tool": "file_reader"})
    c1.add_span_event(span_id, "tool_call", {"tool": "code_analyzer"})
    time.sleep(0.01)
    c1.finish_span(span_id, "ok")
    summary = c1.get_summary()
    assert summary["spans_total"] == 1
    print("  ✅ PASS\n")

    # Test 6: TimerContext
    print("Test 6: TimerContext")
    with TimerContext(c1, "test_operation", {"type": "unit_test"}):
        time.sleep(0.01)
    summary = c1.get_summary()
    assert "latency.test_operation" in summary["latency"]
    assert summary["latency"]["latency.test_operation"]["count"] == 1
    print("  ✅ PASS\n")

    # Test 7: 保存到文件
    print("Test 7: 保存到文件")
    filepath = c1.save("test_metrics.jsonl")
    assert os.path.exists(filepath)
    with open(filepath) as f:
        lines = f.readlines()
    assert len(lines) > 0
    first_line = json.loads(lines[0])
    assert "name" in first_line
    assert "value" in first_line
    os.remove(filepath)
    print("  ✅ PASS\n")

    # Test 8: 重置
    print("Test 8: 重置单例")
    MetricsCollector.reset()
    c3 = MetricsCollector.get_instance()
    assert c3 is not c1
    summary = c3.get_summary()
    assert summary["metrics_total"] == 0
    print("  ✅ PASS\n")

    print("=== 所有测试通过 ===\n")
