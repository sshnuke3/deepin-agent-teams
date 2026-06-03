#!/usr/bin/env python3
"""
tools/tool_registry.py - 统一工具注册与调用接口

核心设计原则：
1. 所有工具通过注册表访问，不硬编码
2. 工具定义包含 JSON Schema（供 LLM 选择）
3. 支持本地 handler 和远程 MCP Server 两种模式
4. 调用记录可追溯

使用方式：
    registry = ToolRegistry()
    registry.register("get_weather", handler=fn, schema={...})
    result = registry.call("get_weather", {"city": "北京"})
    tools = registry.list_for_llm()  # Function Calling 格式
"""
import json
import time
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class ToolDef:
    """工具定义"""
    name: str
    description: str
    handler: Optional[Callable] = None
    schema: Dict = field(default_factory=dict)  # JSON Schema
    source: str = "local"  # "local" 或 mcp server 名称
    requires_confirm: bool = False


@dataclass
class CallResult:
    """工具调用结果"""
    success: bool
    output: Any = None
    error: str = ""
    duration_ms: int = 0
    tool_name: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "tool_name": self.tool_name,
            "source": self.source,
        }


class ToolRegistry:
    """
    统一工具注册表

    支持两种工具来源：
    1. 本地 handler（Python 函数）
    2. 远程 MCP Server（通过 MCP Client 调用）

    所有工具统一通过 call() 调用，调用方不关心底层实现。
    """

    def __init__(self):
        self.tools: Dict[str, ToolDef] = {}
        self.call_history: List[Dict] = []
        self._mcp_clients: Dict[str, Any] = {}  # server_name → MCPClient

    # ========== 注册 ==========

    def register(self, name: str, handler: Callable = None,
                 schema: Dict = None, description: str = "",
                 source: str = "local", requires_confirm: bool = False):
        """
        注册工具

        Args:
            name: 工具名称（唯一标识）
            handler: 处理函数（本地工具必填，MCP 工具可选）
            schema: 参数 JSON Schema（供 LLM 选择工具时使用）
            description: 工具描述
            source: 工具来源（"local" 或 MCP server 名称）
            requires_confirm: 是否需要用户确认
        """
        self.tools[name] = ToolDef(
            name=name,
            description=description,
            handler=handler,
            schema=schema or {},
            source=source,
            requires_confirm=requires_confirm,
        )

    def unregister(self, name: str):
        """注销工具"""
        self.tools.pop(name, None)

    def register_from_mcp_server(self, server_name: str, tools: List[Dict]):
        """
        从 MCP Server 批量注册工具

        Args:
            server_name: MCP Server 名称
            tools: MCP Server 返回的工具列表
        """
        for tool in tools:
            name = tool["name"]
            self.tools[name] = ToolDef(
                name=name,
                description=tool.get("description", ""),
                handler=None,  # MCP 工具无本地 handler
                schema=tool.get("inputSchema", {}),
                source=server_name,
            )

    # ========== 发现 ==========

    def list_tools(self, source: str = None) -> List[Dict]:
        """列出所有工具"""
        tools = list(self.tools.values())
        if source:
            tools = [t for t in tools if t.source == source]
        return [
            {
                "name": t.name,
                "description": t.description,
                "schema": t.schema,
                "source": t.source,
                "requires_confirm": t.requires_confirm,
            }
            for t in tools
        ]

    def list_for_llm(self) -> List[Dict]:
        """
        生成 LLM Function Calling 格式的工具列表

        返回格式可直接用于 erniebot / OpenAI 的 tools 参数
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.schema,
                }
            }
            for t in self.tools.values()
            if t.description  # 没有描述的工具不暴露给 LLM
        ]

    def get_tool(self, name: str) -> Optional[ToolDef]:
        """获取工具定义"""
        return self.tools.get(name)

    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self.tools

    # ========== 调用 ==========

    def call(self, name: str, params: Dict = None,
             auto_confirm: bool = False) -> CallResult:
        """
        统一工具调用

        自动路由：
        - source="local" → 直接调用 handler
        - source="xxx"（MCP Server）→ 通过 MCP Client 调用

        Args:
            name: 工具名
            params: 参数
            auto_confirm: 是否自动确认（跳过危险操作确认）

        Returns:
            CallResult
        """
        tool = self.tools.get(name)
        if not tool:
            result = CallResult(
                success=False,
                error=f"工具不存在: {name}，可用: {list(self.tools.keys())}",
                tool_name=name,
            )
            self.call_history.append({
                "tool": name, "params": params,
                "success": False, "duration_ms": 0,
                "source": "unknown", "timestamp": time.time(),
            })
            return result

        # 危险操作确认
        if tool.requires_confirm and not auto_confirm:
            result = CallResult(
                success=False,
                error=f"需要确认: {tool.description}（设置 auto_confirm=True 跳过）",
                tool_name=name,
                source=tool.source,
            )
            self.call_history.append({
                "tool": name, "params": params,
                "success": False, "duration_ms": 0,
                "source": tool.source, "timestamp": time.time(),
            })
            return result

        params = params or {}
        start = time.time()

        try:
            if tool.source == "local":
                # 本地 handler 调用
                if tool.handler is None:
                    return CallResult(
                        success=False,
                        error=f"工具 {name} 未注册 handler",
                        tool_name=name,
                        source="local",
                    )
                output = tool.handler(**params)
            else:
                # MCP Server 调用
                output = self._call_mcp(tool.source, name, params)

            duration = int((time.time() - start) * 1000)
            result = CallResult(
                success=True,
                output=output,
                duration_ms=duration,
                tool_name=name,
                source=tool.source,
            )

        except Exception as e:
            duration = int((time.time() - start) * 1000)
            result = CallResult(
                success=False,
                error=str(e),
                duration_ms=duration,
                tool_name=name,
                source=tool.source,
            )

        # 记录调用历史
        self.call_history.append({
            "tool": name,
            "params": params,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "source": tool.source,
            "timestamp": time.time(),
        })

        return result

    # ========== MCP Client 集成 ==========

    def connect_mcp_server(self, server_name: str, client):
        """
        连接 MCP Server

        Args:
            server_name: Server 名称
            client: MCPClient 实例
        """
        self._mcp_clients[server_name] = client

    def _call_mcp(self, server_name: str, tool_name: str, params: Dict) -> Any:
        """通过 MCP Client 调用远程工具"""
        client = self._mcp_clients.get(server_name)
        if not client:
            raise RuntimeError(f"MCP Server 未连接: {server_name}")
        return client.call_tool(tool_name, params)

    # ========== 统计 ==========

    def get_stats(self) -> Dict:
        """获取调用统计"""
        total = len(self.call_history)
        success = sum(1 for c in self.call_history if c["success"])
        sources = {}
        for t in self.tools.values():
            sources[t.source] = sources.get(t.source, 0) + 1
        return {
            "total_calls": total,
            "success": success,
            "failed": total - success,
            "tools_registered": len(self.tools),
            "by_source": sources,
        }
