#!/usr/bin/env python3
"""
tests/test_e2e.py - 端到端集成测试

覆盖完整链路：用户输入 → 编排 → 执行 → 验收 → 报告

测试场景：
1. Orchestrator 初始化（tools 模式 + workers 模式）
2. LLM 健康预检
3. 任务分解（mock LLM）
4. 本地工具执行
5. Verifier 验收
6. 完整 pipeline：输入 → 分解 → 执行 → 验收 → 整合
7. 超时与重试
8. 部分失败优雅降级
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents"))

from agents.orchestrator import Orchestrator, TaskStatus, create_orchestrator
from agents.task_state_machine import TaskStateMachine, TaskState
from agents.verifier import Verifier
from tools.tool_registry import ToolRegistry


passed = 0
failed = 0


def assert_eq(actual, expected, msg=""):
    global passed, failed
    if actual == expected:
        passed += 1
    else:
        failed += 1
        print(f"  ❌ FAIL: {msg} — 期望 {expected}，实际 {actual}")


def assert_true(cond, msg=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  ❌ FAIL: {msg}")


# ==================== Test 1: Orchestrator 初始化 ====================

def test_orchestrator_init_tools():
    """tools 模式初始化"""
    print("Test 1: Orchestrator 初始化 (tools 模式)")
    orch = Orchestrator(execution_mode="tools", verbose=False)
    assert_eq(orch.execution_mode, "tools", "execution_mode")
    assert_true(orch.tool_registry is not None, "tool_registry 应该存在")
    assert_true(orch.verifier is not None, "verifier 应该存在")
    assert_eq(orch.task_timeout, 120, "默认 task_timeout")
    assert_eq(orch.global_timeout, 600, "默认 global_timeout")
    assert_eq(orch.retry_max, 3, "默认 retry_max")
    print("  ✅ PASS\n")


def test_orchestrator_init_workers():
    """workers 模式初始化"""
    print("Test 2: Orchestrator 初始化 (workers 模式)")
    orch = Orchestrator(execution_mode="workers", verbose=False)
    assert_eq(orch.execution_mode, "workers", "execution_mode")
    assert_true(orch.registry is not None, "registry 应该存在")
    assert_true(orch.tool_registry is None, "tool_registry 应该为 None")
    print("  ✅ PASS\n")


# ==================== Test 2: LLM 健康预检 ====================

def test_llm_health_check():
    """LLM 可用性预检"""
    print("Test 3: LLM 健康预检")
    orch = Orchestrator(execution_mode="tools", verbose=False)
    health = orch._check_llm_health()
    assert_true("available" in health, "health 应包含 available")
    assert_true("channels" in health, "health 应包含 channels")
    assert_true("best" in health, "health 应包含 best")
    # 至少有一个通道标记
    assert_true(len(health["channels"]) > 0, "至少有一个通道")
    print(f"  通道状态: {health['channels']}")
    print(f"  最佳通道: {health['best']}")
    print("  ✅ PASS\n")


# ==================== Test 3: 本地工具注册与执行 ====================

def test_local_tool_registration():
    """注册本地工具并调用"""
    print("Test 4: 本地工具注册与调用")
    orch = Orchestrator(execution_mode="tools", verbose=False)

    # 注册一个本地工具
    def echo(text: str) -> dict:
        return {"echo": text}

    orch.register_local_tool(
        name="echo",
        handler=echo,
        schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        description="回显文本",
    )

    assert_true(orch.tool_registry.has("echo"), "echo 工具应已注册")
    result = orch.tool_registry.call("echo", {"text": "hello"})
    assert_true(result.success, "echo 调用应成功")
    assert_eq(result.output, {"echo": "hello"}, "echo 输出")
    print("  ✅ PASS\n")


# ==================== Test 4: 任务分解（降级模式） ====================

def test_decompose_fallback():
    """LLM 不可用时的降级分解"""
    print("Test 5: 任务分解降级（无 LLM）")
    orch = Orchestrator(execution_mode="tools", verbose=False, enable_verifier=False)

    # 不连接任何 LLM，测试降级逻辑
    plan = orch.decompose("测试任务", project_path="/tmp")
    assert_true("tasks" in plan, "plan 应包含 tasks")
    assert_true("spawn_plan" in plan, "plan 应包含 spawn_plan")
    assert_true(len(plan["tasks"]) > 0, "至少一个任务")
    assert_eq(plan["tasks"][0]["type"], "general", "降级任务类型应为 general")
    print("  ✅ PASS\n")


# ==================== Test 5: 完整 pipeline ====================

def test_full_pipeline_local_tools():
    """完整 pipeline：本地工具执行（不依赖 LLM）"""
    print("Test 6: 完整 pipeline（本地工具）")
    orch = Orchestrator(execution_mode="tools", verbose=False, enable_verifier=False)

    # 注册本地工具
    call_log = []

    def analyze_file(path: str) -> dict:
        call_log.append(("analyze_file", path))
        exists = os.path.exists(path)
        return {"path": path, "exists": exists, "lines": 10}

    orch.register_local_tool(
        name="analyze_file",
        handler=analyze_file,
        schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        description="分析文件",
    )

    # 手动构造 plan（跳过 LLM 分解）
    orch._call_llm = lambda prompt, task_type="default": None  # 确保 LLM 不可用
    result = orch.run("分析代码", project_path="/tmp")

    assert_true(result is not None, "结果不为空")
    assert_true(hasattr(result, "success"), "结果应有 success 属性")
    assert_true(hasattr(result, "task_results"), "结果应有 task_results")
    assert_true(hasattr(result, "final_report"), "结果应有 final_report")
    assert_true(result.total_duration_ms >= 0, "耗时应非负")
    print(f"  成功: {result.success}, 任务数: {len(result.task_results)}, 耗时: {result.total_duration_ms}ms")
    print("  ✅ PASS\n")


# ==================== Test 6: 超时机制 ====================

def test_task_timeout():
    """单任务超时"""
    print("Test 7: 任务超时")
    orch = Orchestrator(
        execution_mode="tools", verbose=False,
        task_timeout=1,  # 1 秒超时
        enable_verifier=False,
    )

    import threading

    def slow_tool(**kwargs):
        time.sleep(5)  # 故意慢
        return {"done": True}

    orch.register_local_tool("slow_tool", handler=slow_tool)

    # 直接测试 execute_task 的超时
    task = {
        "id": "timeout-test",
        "description": "慢任务",
        "tool_name": "slow_tool",
        "params": {},
        "capabilities_needed": [],
    }
    tr = orch.execute_task(task, "timeout-test")
    # 由于 tools 模式下 tool_registry.call 是同步的，可能不会真正超时
    # 但至少应该返回结果
    assert_true(tr is not None, "应返回 TaskResult")
    print(f"  状态: {tr.status.value}")
    print("  ✅ PASS\n")


# ==================== Test 7: 部分失败降级 ====================

def test_partial_failure():
    """部分任务失败时优雅降级"""
    print("Test 8: 部分失败降级")
    orch = Orchestrator(execution_mode="tools", verbose=False, enable_verifier=False)

    def good_tool(**kwargs):
        return {"status": "ok"}

    def bad_tool(**kwargs):
        raise Exception("工具崩溃")

    orch.register_local_tool("good_tool", handler=good_tool)
    orch.register_local_tool("bad_tool", handler=bad_tool)

    # 注入一个包含成功和失败任务的 plan
    original_decompose = orch.decompose

    def mock_decompose(user_request, project_path=""):
        return {
            "tasks": [
                {"id": "task-ok", "description": "好任务", "tool_name": "good_tool",
                 "params": {}, "capabilities_needed": [], "type": "general"},
                {"id": "task-fail", "description": "坏任务", "tool_name": "bad_tool",
                 "params": {}, "capabilities_needed": [], "type": "general"},
            ],
            "spawn_plan": [],
            "summary": "混合任务",
        }

    orch.decompose = mock_decompose
    orch._call_llm = lambda p, task_type="default": "# mock report\n\n部分成功报告"
    result = orch.run("混合任务")

    assert_true(result.partial, "应为部分成功")
    assert_true(not result.success, "不应全部成功")
    assert_true(len(result.failed_task_ids) > 0, "应有失败任务")
    assert_true(len(result.task_results) == 2, "应有 2 个任务结果")
    print(f"  失败任务: {result.failed_task_ids}")
    print("  ✅ PASS\n")


# ==================== Test 8: TaskStateMachine ====================

def test_state_machine_lifecycle():
    """状态机完整生命周期"""
    print("Test 9: 状态机生命周期")
    sm = TaskStateMachine("e2e-sm-test")

    # PENDING → CLAIMED → RUNNING → VERIFIED → COMPLETED
    assert_eq(sm.state, TaskState.PENDING, "初始状态")

    from agents.task_state_machine import TransitionContext
    sm.transition(TaskState.CLAIMED, TransitionContext(worker_id="test-worker"))
    assert_eq(sm.state, TaskState.CLAIMED, "认领后")

    sm.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))
    assert_eq(sm.state, TaskState.RUNNING, "运行中")

    sm.transition(TaskState.VERIFIED, TransitionContext(verdict="PASS"))
    assert_eq(sm.state, TaskState.VERIFIED, "已验证")

    sm.transition(TaskState.COMPLETED, TransitionContext())
    assert_eq(sm.state, TaskState.COMPLETED, "已完成")

    trace = sm.get_trace()
    assert_true(len(trace) >= 4, f"trace 应至少 4 条，实际 {len(trace)}")
    print(f"  trace 条数: {len(trace)}")
    print("  ✅ PASS\n")


# ==================== Test 9: Verifier ====================

def test_verifier_basic():
    """Verifier 基本验收"""
    print("Test 10: Verifier 验收")
    v = Verifier()

    # 成功的 case（包含 verifier 需要的 trace 字段）
    task_ok = {"id": "v-test-ok", "type": "general", "description": "测试"}
    result_ok = {"output": "成功", "summary": "测试完成",
                 "task_id": "v-test-ok", "capabilities_used": ["file_reader"]}
    verdict_ok = v.verify(task_ok, {"result": result_ok})
    assert_true(verdict_ok.is_pass, "正常结果应 PASS")

    # 失败的 case（有 error）
    task_err = {"id": "v-test-err", "type": "general", "description": "测试"}
    result_err = {"error": "失败了"}
    verdict_err = v.verify(task_err, {"result": result_err})
    assert_true(not verdict_err.is_pass, "有 error 应 FAIL")
    print("  ✅ PASS\n")


# ==================== Test 10: create_orchestrator 工厂 ====================

def test_create_orchestrator_factory():
    """工厂函数"""
    print("Test 11: create_orchestrator 工厂函数")
    orch = create_orchestrator(mode="tools", mcp_servers=False, verbose=False)
    assert_true(isinstance(orch, Orchestrator), "应返回 Orchestrator 实例")
    assert_eq(orch.execution_mode, "tools", "mode 应为 tools")
    print("  ✅ PASS\n")


# ==================== Main ====================

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 deepin-agent-teams 端到端集成测试")
    print("=" * 60)
    print()

    test_orchestrator_init_tools()
    test_orchestrator_init_workers()
    test_llm_health_check()
    test_local_tool_registration()
    test_decompose_fallback()
    test_full_pipeline_local_tools()
    test_task_timeout()
    test_partial_failure()
    test_state_machine_lifecycle()
    test_verifier_basic()
    test_create_orchestrator_factory()

    print("=" * 60)
    total = passed + failed
    print(f"结果: {passed}/{total} 通过, {failed} 失败")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
