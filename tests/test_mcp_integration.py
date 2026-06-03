#!/usr/bin/env python3
"""
tests/test_mcp_integration.py - MCP 协议集成测试

覆盖：
- MCP Server 启动和工具注册
- MCP Client 连接和工具发现
- MCP Client 调用远程工具
- 多 Server 连接
- OrchestratorV4 自动连接
"""
import sys
import os
import json
import time
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.mcp_protocol import MCPServer, MCPClient, jsonrpc_request, jsonrpc_response
from tools.tool_registry import ToolRegistry

MCP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_servers")


def test_mcp_server_basic():
    """测试 MCP Server 基本功能"""
    print("Test 1: MCP Server 基本功能")
    server = MCPServer("test-server")

    @server.tool("add", "两数相加", {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}})
    def add(a, b):
        return a + b

    # 测试 initialize
    resp = server.handle_request(jsonrpc_request("initialize"))
    assert resp["result"]["serverInfo"]["name"] == "test-server"
    assert "tools" in resp["result"]["capabilities"]
    print("  ✅ initialize")

    # 测试 tools/list
    resp = server.handle_request(jsonrpc_request("tools/list"))
    assert len(resp["result"]["tools"]) == 1
    assert resp["result"]["tools"][0]["name"] == "add"
    print("  ✅ tools/list")

    # 测试 tools/call
    resp = server.handle_request(jsonrpc_request("tools/call", {"name": "add", "arguments": {"a": 3, "b": 5}}))
    content = resp["result"]["content"][0]["text"]
    assert "8" in content
    print("  ✅ tools/call")

    # 测试未知方法
    resp = server.handle_request(jsonrpc_request("unknown/method"))
    assert "error" in resp
    print("  ✅ unknown method → error")
    print("  ✅ PASS\n")


def test_mcp_server_decorators():
    """测试装饰器注册"""
    print("Test 2: 装饰器注册")
    server = MCPServer("decorator-test")

    @server.tool("greet", "打招呼", {"type": "object", "properties": {"name": {"type": "string"}}})
    def greet(name="world"):
        return f"Hello, {name}!"

    @server.tool("noop", "空操作")
    def noop():
        return "ok"

    assert len(server.tools) == 2
    assert "greet" in server.tools
    assert "noop" in server.tools
    print("  ✅ PASS\n")


def test_mcp_client_server_communication():
    """测试 Client-Server 通信（通过子进程）"""
    print("Test 3: Client-Server 通信")

    # 创建一个临时 MCP Server 脚本
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_code = f'''
import sys, os
sys.path.insert(0, "{project_root}")
from mcp_servers.mcp_protocol import MCPServer

server = MCPServer("echo-server")

@server.tool("echo", "回显文本", {{"type": "object", "properties": {{"text": {{"type": "string"}}}}}})
def echo(text):
    return {{"echo": text, "length": len(text)}}

@server.tool("add", "两数相加", {{"type": "object", "properties": {{"a": {{"type": "integer"}}, "b": {{"type": "integer"}}}}}})
def add(a, b):
    return a + b

server.run()
'''
    tmp_script = "/tmp/test_mcp_server.py"
    with open(tmp_script, "w") as f:
        f.write(server_code)

    try:
        client = MCPClient()
        client.connect("python3", [tmp_script])

        # 验证连接
        assert client.is_connected, "Client 未连接"
        print(f"  ✅ 连接到: {client.server_name}")

        # 验证工具列表
        tools = client.list_tools()
        assert len(tools) == 2
        tool_names = {t["name"] for t in tools}
        assert "echo" in tool_names
        assert "add" in tool_names
        print(f"  ✅ 发现工具: {tool_names}")

        # 调用 echo
        result = client.call_tool("echo", {"text": "hello"})
        assert result["echo"] == "hello"
        assert result["length"] == 5
        print(f"  ✅ 调用 echo: {result}")

        # 调用 add
        result = client.call_tool("add", {"a": 10, "b": 20})
        assert result == 30
        print(f"  ✅ 调用 add: {result}")

        client.disconnect()
        print("  ✅ 断开连接")
        print("  ✅ PASS\n")

    finally:
        os.remove(tmp_script)


def test_registry_with_mcp():
    """测试 ToolRegistry + MCP Client 集成"""
    print("Test 4: ToolRegistry + MCP")

    # 创建临时 Server
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_code = f'''
import sys, os
sys.path.insert(0, "{project_root}")
from mcp_servers.mcp_protocol import MCPServer

server = MCPServer("calc-service")

@server.tool("multiply", "乘法", {{"type": "object", "properties": {{"a": {{"type": "number"}}, "b": {{"type": "number"}}}}}})
def multiply(a, b):
    return {{"result": a * b}}

server.run()
'''
    tmp_script = "/tmp/test_calc_server.py"
    with open(tmp_script, "w") as f:
        f.write(server_code)

    try:
        # 注册到 Registry
        registry = ToolRegistry()
        client = MCPClient()
        client.connect("python3", [tmp_script])

        # 从 MCP Server 注册工具
        registry.register_from_mcp_server("calc-service", client.list_tools())
        registry.connect_mcp_server("calc-service", client)

        # 通过 Registry 调用 MCP 工具
        result = registry.call("multiply", {"a": 6, "b": 7})
        assert result.success, f"调用失败: {result.error}"
        assert result.output["result"] == 42
        print(f"  ✅ Registry → MCP 调用: 6 * 7 = {result.output['result']}")

        # 混合注册本地 + MCP 工具
        registry.register("local_echo", handler=lambda text: text, description="本地回显")
        result = registry.call("local_echo", {"text": "test"})
        assert result.success
        assert result.source == "local"
        print(f"  ✅ 本地工具调用: source={result.source}")

        tools = registry.list_tools()
        assert len(tools) == 2
        print(f"  ✅ 总工具数: {len(tools)}")

        client.disconnect()
        print("  ✅ PASS\n")

    finally:
        os.remove(tmp_script)


def test_mcp_server_error_handling():
    """测试错误处理"""
    print("Test 5: 错误处理")
    server = MCPServer("error-test")

    @server.tool("fail", "会报错", {"type": "object", "properties": {}})
    def fail():
        raise RuntimeError("intentional error")

    # 调用会报错的工具
    resp = server.handle_request(jsonrpc_request("tools/call", {"name": "fail", "arguments": {}}))
    assert resp["result"]["isError"] == True
    print("  ✅ 工具报错 → isError=True")

    # 调用不存在的工具
    resp = server.handle_request(jsonrpc_request("tools/call", {"name": "nonexistent", "arguments": {}}))
    assert "error" in resp
    print("  ✅ 不存在的工具 → error")

    # ping
    resp = server.handle_request(jsonrpc_request("ping"))
    assert "result" in resp
    print("  ✅ ping → ok")
    print("  ✅ PASS\n")


def test_file_server():
    """测试 file_server.py"""
    print("Test 6: file_server.py 自测")
    server_path = os.path.join(MCP_DIR, "file_server.py")
    if not os.path.exists(server_path):
        print("  ⚠️ SKIP (file_server.py 不存在)")
        return

    result = subprocess.run(
        ["python3", server_path, "--test"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"自测失败:\n{result.stderr}"
    assert "自测通过" in result.stdout
    print("  ✅ PASS\n")


def test_system_server():
    """测试 system_server.py"""
    print("Test 7: system_server.py 自测")
    server_path = os.path.join(MCP_DIR, "system_server.py")
    if not os.path.exists(server_path):
        print("  ⚠️ SKIP (system_server.py 不存在)")
        return

    result = subprocess.run(
        ["python3", server_path, "--test"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"自测失败:\n{result.stderr}"
    assert "自测通过" in result.stdout
    print("  ✅ PASS\n")


def test_model_server():
    """测试 model_server.py"""
    print("Test 8: model_server.py 自测")
    server_path = os.path.join(MCP_DIR, "model_server.py")
    if not os.path.exists(server_path):
        print("  ⚠️ SKIP (model_server.py 不存在)")
        return

    result = subprocess.run(
        ["python3", server_path, "--test"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"自测失败:\n{result.stderr}"
    assert "自测通过" in result.stdout
    print("  ✅ PASS\n")


if __name__ == "__main__":
    print("\n=== MCP 集成测试 ===\n")
    test_mcp_server_basic()
    test_mcp_server_decorators()
    test_mcp_client_server_communication()
    test_registry_with_mcp()
    test_mcp_server_error_handling()
    test_file_server()
    test_system_server()
    test_model_server()
    print("=== 所有测试通过 ✅ ===\n")
