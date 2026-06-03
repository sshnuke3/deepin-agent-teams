#!/usr/bin/env python3
"""
mcp_servers/mcp_protocol.py - 轻量级 MCP 协议实现

不依赖 mcp SDK，纯 Python 实现 MCP 协议核心功能。
基于 JSON-RPC over stdio（与官方 MCP 协议一致）。

支持：
- Server 端：工具注册、发现、调用
- Client 端：连接 Server、发现工具、调用工具

设计参考：https://modelcontextprotocol.io/specification
"""
import json
import sys
import os
import subprocess
import threading
import time
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass, field, asdict
from abc import ABC, abstractmethod


# ========== MCP 协议消息类型 ==========

def jsonrpc_request(method: str, params: Dict = None, req_id: int = 1) -> Dict:
    """构造 JSON-RPC 2.0 请求"""
    msg = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params:
        msg["params"] = params
    return msg


def jsonrpc_response(result: Any, req_id: int = 1) -> Dict:
    """构造 JSON-RPC 2.0 成功响应"""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    }


def jsonrpc_error(message: str, code: int = -32000, req_id: int = 1) -> Dict:
    """构造 JSON-RPC 2.0 错误响应"""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


# ========== MCP Tool 定义 ==========

@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    inputSchema: Dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    handler: Optional[Callable] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }


# ========== MCP Server ==========

class MCPServer:
    """
    轻量级 MCP Server

    使用方式：
        server = MCPServer("weather-service")

        @server.tool("get_weather", "查询天气", {"city": {"type": "string"}})
        def get_weather(city: str):
            return {"weather": "晴", "temp": 25}

        server.run()  # 启动 stdio 服务
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools: Dict[str, MCPTool] = {}

    def tool(self, name: str, description: str = "",
             input_schema: Dict = None) -> Callable:
        """装饰器：注册工具"""
        def decorator(fn: Callable) -> Callable:
            schema = input_schema or {"type": "object", "properties": {}}
            self.tools[name] = MCPTool(
                name=name,
                description=description or fn.__doc__ or "",
                inputSchema=schema,
                handler=fn,
            )
            return fn
        return decorator

    def register_tool(self, name: str, handler: Callable,
                      description: str = "", input_schema: Dict = None):
        """直接注册工具（非装饰器方式）"""
        schema = input_schema or {"type": "object", "properties": {}}
        self.tools[name] = MCPTool(
            name=name,
            description=description,
            inputSchema=schema,
            handler=handler,
        )

    def handle_request(self, request: Dict) -> Dict:
        """处理一个 JSON-RPC 请求"""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", 1)

        if method == "initialize":
            return jsonrpc_response({
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": self.name, "version": self.version},
            }, req_id)

        elif method == "notifications/initialized":
            # 客户端确认，无需响应
            return None

        elif method == "tools/list":
            tool_list = [t.to_dict() for t in self.tools.values()]
            return jsonrpc_response({"tools": tool_list}, req_id)

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            return self._call_tool(tool_name, arguments, req_id)

        elif method == "ping":
            return jsonrpc_response({}, req_id)

        else:
            return jsonrpc_error(f"Unknown method: {method}", -32601, req_id)

    def _call_tool(self, name: str, arguments: Dict, req_id: int) -> Dict:
        """执行工具调用"""
        tool = self.tools.get(name)
        if not tool:
            return jsonrpc_error(f"Tool not found: {name}", -32602, req_id)

        try:
            result = tool.handler(**arguments)
            # MCP 协议要求返回 content 数组
            if isinstance(result, str):
                content = [{"type": "text", "text": result}]
            elif isinstance(result, dict) or isinstance(result, list):
                content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
            else:
                content = [{"type": "text", "text": str(result)}]
            return jsonrpc_response({"content": content}, req_id)
        except Exception as e:
            return jsonrpc_response({
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            }, req_id)

    def run(self, input_stream=None, output_stream=None):
        """
        启动 stdio MCP Server

        默认从 stdin 读取，写到 stdout。
        """
        inp = input_stream or sys.stdin
        out = output_stream or sys.stdout

        for line in inp:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response is not None:
                    out.write(json.dumps(response) + "\n")
                    out.flush()
            except json.JSONDecodeError:
                err = jsonrpc_error("Parse error", -32700)
                out.write(json.dumps(err) + "\n")
                out.flush()


# ========== MCP Client ==========

class MCPClient:
    """
    轻量级 MCP Client

    连接 MCP Server 子进程，通过 stdio 通信。

    使用方式：
        client = MCPClient()
        client.connect("python", ["weather_server.py"])
        tools = client.list_tools()
        result = client.call_tool("get_weather", {"city": "北京"})
        client.disconnect()
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._server_name: str = ""
        self._req_id: int = 0
        self._tools: List[Dict] = []
        self._lock = threading.Lock()

    def connect(self, command: str, args: List[str] = None):
        """
        连接 MCP Server 子进程

        Args:
            command: 启动命令（如 "python"）
            args: 启动参数（如 ["weather_server.py"]）
        """
        args = args or []
        self._process = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # 发送 initialize
        resp = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "deepin-agent-teams", "version": "3.0"},
        })

        if resp and "result" in resp:
            self._server_name = resp["result"].get("serverInfo", {}).get("name", "unknown")
            # 发送 initialized 通知
            self._send_notification("notifications/initialized")
            # 获取工具列表
            self._refresh_tools()

    def disconnect(self):
        """断开连接"""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def list_tools(self) -> List[Dict]:
        """获取工具列表"""
        return self._tools

    def call_tool(self, name: str, arguments: Dict = None) -> Any:
        """
        调用远程工具

        Returns:
            工具返回的结果（自动解析 MCP content 格式）
        """
        resp = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })

        if not resp:
            raise RuntimeError(f"No response from MCP Server for tool: {name}")

        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")

        # 解析 MCP content 格式
        result = resp.get("result", {})
        contents = result.get("content", [])
        if not contents:
            return None

        # 取第一个 text content
        for c in contents:
            if c.get("type") == "text":
                text = c["text"]
                # 尝试 JSON 解析
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text

        return contents

    def _refresh_tools(self):
        """刷新工具列表"""
        resp = self._send_request("tools/list")
        if resp and "result" in resp:
            self._tools = resp["result"].get("tools", [])

    def _next_id(self) -> int:
        """生成请求 ID"""
        self._req_id += 1
        return self._req_id

    def _send_request(self, method: str, params: Dict = None) -> Optional[Dict]:
        """发送请求并等待响应"""
        if not self._process:
            raise RuntimeError("MCP Client 未连接")

        req_id = self._next_id()
        msg = jsonrpc_request(method, params, req_id)

        with self._lock:
            try:
                line = json.dumps(msg) + "\n"
                self._process.stdin.write(line)
                self._process.stdin.flush()

                # 读取响应（跳过通知消息）
                response_line = self._process.stdout.readline()
                if not response_line:
                    return None
                return json.loads(response_line.strip())
            except Exception as e:
                return jsonrpc_error(str(e))

    def _send_notification(self, method: str, params: Dict = None):
        """发送通知（无响应）"""
        if not self._process:
            return
        msg = {"jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params
        try:
            line = json.dumps(msg) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()
        except Exception:
            pass

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.poll() is None
