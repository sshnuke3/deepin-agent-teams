#!/usr/bin/env python3
"""
benchmark.py — 性能基准测试

测试各核心模块的吞吐量和延迟（不依赖真实 LLM）：
1. 场景分类器吞吐量
2. 上下文窗口管理
3. 状态机跳转
4. Verifier 检查
5. Planner 降级路径
6. Prompt 模板加载
7. OTel Tracer 跨度
"""

import sys
import os
import time
import statistics

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "agents"))

# ── Helpers ──────────────────────────────────────────────────

def bench(name: str, fn, iterations: int = 1000) -> dict:
    """运行基准测试，返回统计结果"""
    # 预热
    for _ in range(min(10, iterations)):
        fn()

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)

    result = {
        "name": name,
        "iterations": iterations,
        "total_ms": sum(times),
        "avg_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "p95_ms": sorted(times)[int(len(times) * 0.95)],
        "p99_ms": sorted(times)[int(len(times) * 0.99)],
        "min_ms": min(times),
        "max_ms": max(times),
        "ops_per_sec": 1000 / statistics.mean(times) if statistics.mean(times) > 0 else float('inf'),
    }
    return result


def print_result(r: dict):
    """打印单个测试结果"""
    print(f"  {r['name']}:")
    print(f"    {r['iterations']} 次 | 平均 {r['avg_ms']:.3f}ms | "
          f"P95 {r['p95_ms']:.3f}ms | P99 {r['p99_ms']:.3f}ms | "
          f"{r['ops_per_sec']:.0f} ops/s")


# ── Benchmark 1: ScenarioClassifier ──────────────────────────

def bench_scenario_classifier():
    from agents.scenario_classifier import ScenarioClassifier
    classifier = ScenarioClassifier()

    test_inputs = [
        "帮我写一封邮件给张三，讨论项目进展",
        "分析这段代码的性能瓶颈",
        "系统运行很慢，帮我排查问题",
        "搜索最新的 AI 研究论文",
        "帮我写一篇关于量子计算的综述文章",
        "全面分析代码架构和性能瓶颈，然后修改数据库配置，最后重启服务",
        "今天天气怎么样",
        "翻译这段英文",
    ]

    for text in test_inputs:
        r = bench(f"classify({text[:15]}...)", lambda t=text: classifier.classify(t), 10000)
        print_result(r)


# ── Benchmark 2: ContextWindow ────────────────────────────────

def bench_context_window():
    from agents.context_manager import ContextWindow
    cw = ContextWindow(max_recent_turns=10, max_tokens=8000)

    def add_and_get():
        cw.add_turn("user", "这是一个测试消息")
        cw.add_turn("assistant", "这是一个回复消息")
        cw.get_messages()

    r = bench("ContextWindow.add+get", add_and_get, 5000)
    print_result(r)

    def token_count():
        cw.get_token_usage()

    r = bench("ContextWindow.token_usage", token_count, 10000)
    print_result(r)


# ── Benchmark 3: StateMachine ─────────────────────────────────

def bench_state_machine():
    from agents.task_state_machine import TaskStateMachine, TaskState, TransitionContext
    import uuid

    def full_lifecycle():
        tid = str(uuid.uuid4())[:8]
        sm = TaskStateMachine(tid)
        sm.transition(TaskState.CLAIMED, TransitionContext(worker_id="w1"))
        sm.transition(TaskState.PLANNING, TransitionContext(start_time=time.time()))
        sm.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))
        sm.transition(TaskState.VERIFIED, TransitionContext(verdict="PASS"))
        sm.transition(TaskState.COMPLETED, TransitionContext())

    r = bench("StateMachine.full_lifecycle(5 transitions)", full_lifecycle, 10000)
    print_result(r)


# ── Benchmark 4: Verifier ─────────────────────────────────────

def bench_verifier():
    from agents.verifier import Verifier

    import io, contextlib
    v = Verifier()

    def verify_task():
        task = {"task_id": "bench-1", "type": "file_reader"}
        result = {
            "task_id": "bench-1",
            "capabilities_used": ["file_reader"],
            "error_type": "OK",
            "content": "file content here",
            "size": 100,
            "trace": {"task_id": "bench-1", "capabilities_used": ["file_reader"]},
        }
        with contextlib.redirect_stdout(io.StringIO()):
            v.verify(task, result)

    r = bench("Verifier.verify(11 checks)", verify_task, 5000)
    print_result(r)


# ── Benchmark 5: PromptLoader ─────────────────────────────────

def bench_prompt_loader():
    from agents.prompt_loader import PromptLoader

    loader = PromptLoader()

    def load_template():
        loader.render("orchestrator/system")

    r = bench("PromptLoader.render", load_template, 10000)
    print_result(r)


# ── Benchmark 6: OTel Tracer ──────────────────────────────────

def bench_otel_tracer():
    from agents.otel_tracer import Tracer

    tracer = Tracer("benchmark")

    def trace_span():
        span = tracer.trace_task_execution("bench-1", "file_reader")
        span.set_attribute("test", "value")
        span.finish("ok")

    r = bench("Tracer.span", trace_span, 10000)
    print_result(r)


# ── Benchmark 7: Planner (降级路径) ───────────────────────────

def bench_planner():
    from agents.planner import Planner

    planner = Planner()

    def plan_generate():
        planner.create_plan(
            task_description="分析项目代码质量",
            context="code_analysis",
        )

    r = bench("Planner.create_plan", plan_generate, 5000)
    print_result(r)


# ── Benchmark 8: Debate ───────────────────────────────────────

def bench_debate():
    from agents.debate import DebateJudge, DebateArgument

    args = [
        DebateArgument(side="pro", round=0, content="React componentization is better", evidence=["Higher component reuse rate"]),
        DebateArgument(side="con", round=0, content="Vue has a gentler learning curve", evidence=["Simpler API"]),
        DebateArgument(side="pro", round=1, content="React ecosystem is stronger", evidence=["npm download count"]),
        DebateArgument(side="con", round=1, content="Vue ecosystem is strong in China", evidence=["Better domestic documentation"]),
    ]

    def judge_decision():
        judge = DebateJudge()
        judge.judge("用 React 还是 Vue？", args)

    r = bench("Judge.judge", judge_decision, 10000)
    print_result(r)


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  deepin-agent-teams 性能基准测试")
    print("=" * 60)

    benchmarks = [
        ("ScenarioClassifier", bench_scenario_classifier),
        ("ContextWindow", bench_context_window),
        ("StateMachine", bench_state_machine),
        ("Verifier", bench_verifier),
        ("PromptLoader", bench_prompt_loader),
        ("OTelTracer", bench_otel_tracer),
        ("Planner", bench_planner),
        ("Debate", bench_debate),
    ]

    all_results = []
    for name, fn in benchmarks:
        print(f"\n── {name} {'─' * (50 - len(name))}")
        try:
            fn()
        except Exception as e:
            print(f"  ❌ 错误: {e}")

    print(f"\n{'=' * 60}")
    print("  基准测试完成")
    print(f"{'=' * 60}")
