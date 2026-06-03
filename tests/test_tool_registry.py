#!/usr/bin/env python3
"""
tests/test_tool_registry.py - ToolRegistry 单元测试

覆盖：
- 工具注册/注销
- 本地 handler 调用
- LLM Function Calling 格式输出
- 危险操作确认
- 调用历史统计
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.tool_registry import ToolRegistry, CallResult


def test_register_and_call():
    """注册工具并调用"""
    print("Test 1: 注册 + 调用")
    registry = ToolRegistry()

    def add(a: int, b: int) -> int:
        return a + b

    registry.register("add", handler=add, description="两数相加", schema={
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
    })

    result = registry.call("add", {"a": 3, "b": 5})
    assert result.success, f"调用失败: {result.error}"
    assert result.output == 8
    assert result.tool_name == "add"
    print("  ✅ PASS\n")


def test_list_for_llm():
    """LLM Function Calling 格式"""
    print("Test 2: LLM 工具列表")
    registry = ToolRegistry()

    registry.register("weather", handler=lambda city: {"temp": 25},
                      description="查天气", schema={
                          "type": "object",
                          "properties": {"city": {"type": "string"}},
                      })
    registry.register("no_desc", handler=lambda: None)  # 无描述，不暴露

    tools = registry.list_for_llm()
    assert len(tools) == 1, f"期望 1 个工具，实际 {len(tools)}"
    assert tools[0]["function"]["name"] == "weather"
    assert tools[0]["type"] == "function"
    print("  ✅ PASS\n")


def test_nonexistent_tool():
    """调用不存在的工具"""
    print("Test 3: 不存在的工具")
    registry = ToolRegistry()
    result = registry.call("nonexistent", {})
    assert not result.success
    assert "不存在" in result.error
    print("  ✅ PASS\n")


def test_requires_confirm():
    """危险操作确认"""
    print("Test 4: 危险操作确认")
    registry = ToolRegistry()
    registry.register("delete_all", handler=lambda: "deleted",
                      description="删除所有", requires_confirm=True)

    # 未确认 → 拒绝
    result = registry.call("delete_all", {})
    assert not result.success
    assert "确认" in result.error

    # 确认 → 通过
    result = registry.call("delete_all", {}, auto_confirm=True)
    assert result.success
    assert result.output == "deleted"
    print("  ✅ PASS\n")


def test_call_history():
    """调用历史记录"""
    print("Test 5: 调用历史")
    registry = ToolRegistry()
    registry.register("echo", handler=lambda text: text, description="回显")

    registry.call("echo", {"text": "hello"})
    registry.call("echo", {"text": "world"})
    registry.call("nonexistent", {})  # 失败调用

    stats = registry.get_stats()
    assert stats["total_calls"] == 3
    assert stats["success"] == 2
    assert stats["failed"] == 1
    print("  ✅ PASS\n")


def test_handler_exception():
    """handler 抛出异常"""
    print("Test 6: 异常处理")
    registry = ToolRegistry()

    def bad_handler():
        raise ValueError("something went wrong")

    registry.register("bad", handler=bad_handler, description="会报错")
    result = registry.call("bad", {})
    assert not result.success
    assert "something went wrong" in result.error
    print("  ✅ PASS\n")


def test_unregister():
    """注销工具"""
    print("Test 7: 注销工具")
    registry = ToolRegistry()
    registry.register("temp", handler=lambda: "ok", description="临时工具")
    assert registry.has("temp")

    registry.unregister("temp")
    assert not registry.has("temp")
    print("  ✅ PASS\n")


def test_mcp_source():
    """MCP Server 来源的工具注册"""
    print("Test 8: MCP 工具注册")
    registry = ToolRegistry()

    # 模拟 MCP Server 返回的工具列表
    mcp_tools = [
        {"name": "get_weather", "description": "查天气", "inputSchema": {"type": "object"}},
        {"name": "get_forecast", "description": "查预报", "inputSchema": {"type": "object"}},
    ]
    registry.register_from_mcp_server("weather-service", mcp_tools)

    assert registry.has("get_weather")
    assert registry.has("get_forecast")
    tools = registry.list_tools()
    assert len(tools) == 2
    assert tools[0]["source"] == "weather-service"
    print("  ✅ PASS\n")


if __name__ == "__main__":
    print("\n=== ToolRegistry 单元测试 ===\n")
    test_register_and_call()
    test_list_for_llm()
    test_nonexistent_tool()
    test_requires_confirm()
    test_call_history()
    test_handler_exception()
    test_unregister()
    test_mcp_source()
    print("=== 所有测试通过 ✅ ===\n")
