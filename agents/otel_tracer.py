#!/usr/bin/env python3
"""
agents/otel_tracer.py — OpenTelemetry 可观测性封装

核心设计原则：
1. 优雅降级：OTel SDK 不可用时回退到 metrics_collector
2. GenAI 语义约定：使用 gen_ai.* 属性名（OpenLLMetry 兼容）
3. 关键节点埋点：Agent Loop / LLM 调用 / 工具调用 / 状态机跳转
4. 开发环境 Console 导出，生产环境 OTLP 导出

使用方式：
    tracer = get_tracer(service_name="deepin-agent-teams")
    with tracer.start_span("task_execution", {"task_id": "t-001"}) as span:
        span.set_attribute("gen_ai.system", "ernie")
        # ... 执行逻辑 ...
        span.add_event("tool_call", {"tool": "file_reader"})

降级：
    如果 OTel SDK 未安装，Tracer 自动回退到 metrics_collector，
    所有 API 签名保持一致，调用方无需感知差异。
"""

import json
import os
import sys
import time
import uuid
import threading
from typing import Dict, List, Any, Optional, ContextManager
from dataclasses import dataclass, field
from contextlib import contextmanager

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
sys.path.insert(0, AGENT_DIR)

# 尝试导入 OpenTelemetry
_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import StatusCode, Status
    _OTEL_AVAILABLE = True
except ImportError:
    pass

# 回退到 metrics_collector
from metrics_collector import MetricsCollector, SpanInfo


# ============================================================
# 跨度抽象（兼容 OTel 和本地模式）
# ============================================================

class Span:
    """
    跨度抽象层

    OTel 可用时包装 OTel Span，否则使用本地 SpanInfo。
    """

    def __init__(
        self,
        name: str,
        attributes: Dict[str, Any] = None,
        otel_span=None,
        local_span: SpanInfo = None,
        collector: MetricsCollector = None,
    ):
        self.name = name
        self.attributes = attributes or {}
        self._otel_span = otel_span
        self._local_span = local_span
        self._collector = collector
        self._start_time = time.time()

    def set_attribute(self, key: str, value: Any) -> "Span":
        """设置属性"""
        self.attributes[key] = value
        if self._otel_span:
            self._otel_span.set_attribute(key, value)
        return self

    def set_status(self, status: str, description: str = "") -> None:
        """设置状态：ok / error"""
        if self._otel_span:
            if status == "error":
                self._otel_span.set_status(Status(StatusCode.ERROR, description))
            else:
                self._otel_span.set_status(Status(StatusCode.OK))
        if self._local_span:
            self._local_span.status = status

    def add_event(self, name: str, attributes: Dict = None) -> None:
        """添加事件"""
        if self._otel_span:
            self._otel_span.add_event(name, attributes or {})
        if self._local_span:
            self._local_span.add_event(name, attributes)

    def record_exception(self, exception: Exception) -> None:
        """记录异常"""
        if self._otel_span:
            self._otel_span.record_exception(exception)
        self.set_status("error", str(exception))
        self.add_event("exception", {
            "type": type(exception).__name__,
            "message": str(exception),
        })

    def finish(self, status: str = "ok") -> None:
        """结束跨度"""
        if self._local_span:
            self._local_span.finish(status)
            # 从 active_spans 移到 spans
            if self._collector and self._local_span.span_id in self._collector._active_spans:
                self._collector._active_spans.pop(self._local_span.span_id, None)
                self._collector._spans.append(self._local_span)
                self._collector.record_latency(self._local_span.name, self._local_span.duration_ms, self._local_span.labels)
        if self._otel_span:
            if status == "ok":
                self._otel_span.set_status(Status(StatusCode.OK))
            self._otel_span.end()

    @property
    def duration_ms(self) -> float:
        return (time.time() - self._start_time) * 1000

    @property
    def span_id(self) -> str:
        if self._local_span:
            return self._local_span.span_id
        return f"span-{uuid.uuid4().hex[:8]}"

    def __enter__(self) -> "Span":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.record_exception(exc_val)
            self.finish("error")
        else:
            self.finish("ok")
        return False  # 不吞异常


# ============================================================
# Tracer 抽象层
# ============================================================

class Tracer:
    """
    可观测性 Tracer

    OTel 可用时使用 OTel SDK，否则回退到 metrics_collector。
    """

    def __init__(self, service_name: str = "deepin-agent-teams"):
        self.service_name = service_name
        self._otel_tracer = None
        self._collector = MetricsCollector.get_instance()

        if _OTEL_AVAILABLE:
            try:
                self._init_otel()
            except Exception as e:
                print(f"[Tracer] OTel 初始化失败，回退到 metrics_collector: {e}")

    def _init_otel(self):
        """初始化 OpenTelemetry SDK"""
        resource = Resource.create({
            "service.name": self.service_name,
            "service.version": "1.0.0",
        })
        provider = TracerProvider(resource=resource)

        # 开发环境：Console 导出
        if os.environ.get("OTEL_EXPORTER", "console") == "console":
            exporter = ConsoleSpanExporter()
        else:
            # 生产环境：OTLP 导出
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
                exporter = OTLPSpanExporter(endpoint=endpoint)
            except ImportError:
                print("[Tracer] OTLP exporter 不可用，使用 Console")
                exporter = ConsoleSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        self._otel_tracer = trace.get_tracer(self.service_name)
        print(f"[Tracer] OTel 初始化成功 (service={self.service_name})")

    @property
    def otel_available(self) -> bool:
        return self._otel_tracer is not None

    def start_span(self, name: str, attributes: Dict[str, Any] = None) -> Span:
        """
        开始一个跨度

        Args:
            name: 跨度名称
            attributes: 初始属性

        Returns:
            Span 实例（支持 context manager）
        """
        otel_span = None
        local_span = None

        if self._otel_tracer:
            otel_span = self._otel_tracer.start_span(name, attributes=attributes or {})
        else:
            span_id = self._collector.start_span(name, attributes)
            local_span = self._collector._active_spans.get(span_id)

        return Span(
            name=name,
            attributes=attributes or {},
            otel_span=otel_span,
            local_span=local_span,
            collector=self._collector,
        )

    @contextmanager
    def trace(self, name: str, attributes: Dict[str, Any] = None):
        """
        计时上下文管理器

        使用方式：
            with tracer.trace("llm_call", {"model": "ernie-lite"}) as span:
                result = call_llm(...)
                span.set_attribute("gen_ai.usage.input_tokens", 100)
        """
        span = self.start_span(name, attributes)
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.finish("error")
            raise
        else:
            span.finish("ok")

    # ---- 便捷方法：GenAI 语义约定 ----

    def trace_llm_call(
        self,
        model: str,
        task_type: str = "default",
        messages_count: int = 0,
    ) -> Span:
        """
        创建 LLM 调用跨度

        自动设置 GenAI 语义约定属性：
        - gen_ai.system: 模型提供方
        - gen_ai.request.model: 模型名
        - gen_ai.operation.name: "chat"
        """
        span = self.start_span("llm_call", {
            "gen_ai.system": self._infer_provider(model),
            "gen_ai.request.model": model,
            "gen_ai.operation.name": "chat",
            "agent.task_type": task_type,
            "agent.messages_count": messages_count,
        })
        return span

    def trace_tool_call(self, tool_name: str, params: Dict = None) -> Span:
        """
        创建工具调用跨度

        属性：
        - agent.tool.name: 工具名
        - agent.tool.params: 参数（截断）
        """
        span = self.start_span("tool_call", {
            "agent.tool.name": tool_name,
        })
        if params:
            # 截断参数避免过大
            params_str = json.dumps(params, ensure_ascii=False)[:500]
            span.set_attribute("agent.tool.params", params_str)
        return span

    def trace_state_transition(self, from_state: str, to_state: str, task_id: str = "") -> Span:
        """
        创建状态机跳转跨度

        属性：
        - agent.state.from: 来源状态
        - agent.state.to: 目标状态
        - agent.task.id: 任务 ID
        """
        span = self.start_span("state_transition", {
            "agent.state.from": from_state,
            "agent.state.to": to_state,
            "agent.task.id": task_id,
        })
        return span

    def trace_task_execution(self, task_id: str, task_type: str = "") -> Span:
        """
        创建任务执行跨度

        属性：
        - agent.task.id: 任务 ID
        - agent.task.type: 任务类型
        """
        span = self.start_span("task_execution", {
            "agent.task.id": task_id,
            "agent.task.type": task_type,
        })
        return span

    def trace_agent_loop(self, iteration: int) -> Span:
        """
        创建 Agent Loop 迭代跨度

        属性：
        - agent.loop.iteration: 迭代次数
        """
        span = self.start_span("agent_loop", {
            "agent.loop.iteration": iteration,
        })
        return span

    # ---- 汇总 ----

    def get_summary(self) -> Dict[str, Any]:
        """获取指标汇总"""
        summary = self._collector.get_summary()
        summary["otel_available"] = self.otel_available
        summary["service_name"] = self.service_name
        return summary

    def save(self, filename: str = None) -> str:
        """保存指标到文件"""
        return self._collector.save(filename)

    @staticmethod
    def _infer_provider(model: str) -> str:
        """从模型名推断提供方"""
        model_lower = model.lower()
        if "ernie" in model_lower or "baidu" in model_lower:
            return "baidu"
        if "minimax" in model_lower:
            return "minimax"
        if "gpt" in model_lower or "openai" in model_lower:
            return "openai"
        if "claude" in model_lower or "anthropic" in model_lower:
            return "anthropic"
        return "unknown"


# ============================================================
# 全局 Tracer 实例
# ============================================================

_global_tracer: Optional[Tracer] = None
_tracer_lock = threading.Lock()


def get_tracer(service_name: str = "deepin-agent-teams") -> Tracer:
    """获取全局 Tracer 实例"""
    global _global_tracer
    with _tracer_lock:
        if _global_tracer is None:
            _global_tracer = Tracer(service_name)
        return _global_tracer


def reset_tracer():
    """重置全局 Tracer（测试用）"""
    global _global_tracer
    with _tracer_lock:
        _global_tracer = None
    MetricsCollector.reset()


# ========== 单元测试 ==========

def _test():
    """OTel Tracer 模块测试"""
    print("\n=== OTel Tracer 单元测试 ===\n")

    reset_tracer()

    # Test 1: Tracer 创建
    print("Test 1: Tracer 创建")
    tracer = get_tracer("test-service")
    assert tracer is not None
    print(f"  OTel 可用: {tracer.otel_available}")
    print("  ✅ PASS\n")

    # Test 2: start_span
    print("Test 2: start_span")
    span = tracer.start_span("test_span", {"key": "value"})
    assert span is not None
    assert span.name == "test_span"
    assert span.attributes["key"] == "value"
    span.finish("ok")
    print("  ✅ PASS\n")

    # Test 3: trace context manager（正常）
    print("Test 3: trace 正常流程")
    with tracer.trace("normal_operation", {"op": "test"}) as span:
        span.set_attribute("result", "success")
        time.sleep(0.01)
    assert span.duration_ms > 0
    print("  ✅ PASS\n")

    # Test 4: trace context manager（异常）
    print("Test 4: trace 异常流程")
    try:
        with tracer.trace("error_operation") as span:
            raise ValueError("测试异常")
    except ValueError:
        pass
    print("  ✅ PASS\n")

    # Test 5: trace_llm_call
    print("Test 5: trace_llm_call")
    span = tracer.trace_llm_call(model="ernie-lite", task_type="light", messages_count=5)
    assert span.attributes["gen_ai.system"] == "baidu"
    assert span.attributes["gen_ai.request.model"] == "ernie-lite"
    span.finish("ok")
    print("  ✅ PASS\n")

    # Test 6: trace_tool_call
    print("Test 6: trace_tool_call")
    span = tracer.trace_tool_call("file_reader", {"path": "/tmp/test.txt"})
    assert span.attributes["agent.tool.name"] == "file_reader"
    assert "/tmp/test.txt" in span.attributes["agent.tool.params"]
    span.finish("ok")
    print("  ✅ PASS\n")

    # Test 7: trace_state_transition
    print("Test 7: trace_state_transition")
    span = tracer.trace_state_transition("CLAIMED", "PLANNING", "task-001")
    assert span.attributes["agent.state.from"] == "CLAIMED"
    assert span.attributes["agent.state.to"] == "PLANNING"
    span.finish("ok")
    print("  ✅ PASS\n")

    # Test 8: trace_task_execution
    print("Test 8: trace_task_execution")
    span = tracer.trace_task_execution("task-001", "code_analysis")
    assert span.attributes["agent.task.id"] == "task-001"
    span.finish("ok")
    print("  ✅ PASS\n")

    # Test 9: trace_agent_loop
    print("Test 9: trace_agent_loop")
    span = tracer.trace_agent_loop(iteration=3)
    assert span.attributes["agent.loop.iteration"] == 3
    span.finish("ok")
    print("  ✅ PASS\n")

    # Test 10: add_event
    print("Test 10: add_event")
    span = tracer.start_span("event_test")
    span.add_event("tool_call", {"tool": "exec"})
    span.add_event("tool_result", {"success": "true"})
    span.finish("ok")
    print("  ✅ PASS\n")

    # Test 11: record_exception
    print("Test 11: record_exception")
    span = tracer.start_span("exception_test")
    try:
        raise RuntimeError("测试错误")
    except RuntimeError as e:
        span.record_exception(e)
    span.finish("error")
    print("  ✅ PASS\n")

    # Test 12: get_summary
    print("Test 12: get_summary")
    summary = tracer.get_summary()
    assert "otel_available" in summary
    assert "service_name" in summary
    assert summary["spans_total"] > 0
    print(f"  摘要: spans={summary['spans_total']}, metrics={summary['metrics_total']}")
    print("  ✅ PASS\n")

    # Test 13: _infer_provider
    print("Test 13: 模型提供方推断")
    assert Tracer._infer_provider("ernie-lite") == "baidu"
    assert Tracer._infer_provider("ernie-3.5") == "baidu"
    assert Tracer._infer_provider("minimax-text") == "minimax"
    assert Tracer._infer_provider("gpt-4") == "openai"
    assert Tracer._infer_provider("claude-3") == "anthropic"
    assert Tracer._infer_provider("unknown-model") == "unknown"
    print("  ✅ PASS\n")

    # Test 14: 全局单例
    print("Test 14: 全局单例")
    t1 = get_tracer()
    t2 = get_tracer()
    assert t1 is t2
    print("  ✅ PASS\n")

    # Test 15: save
    print("Test 15: 保存指标")
    filepath = tracer.save("test_otel_metrics.jsonl")
    assert os.path.exists(filepath)
    with open(filepath) as f:
        lines = f.readlines()
    assert len(lines) > 0
    os.remove(filepath)
    print("  ✅ PASS\n")

    reset_tracer()
    print("=== 所有 OTel Tracer 测试通过 ===\n")


if __name__ == "__main__":
    _test()
