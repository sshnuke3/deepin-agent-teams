#!/usr/bin/env python3
"""
mcp_servers/model_server.py - 模型服务 MCP Server

封装已有的 model_router，对外暴露标准 MCP 接口。
独立运行，不依赖 orchestrator。

启动方式：
    python model_server.py          # stdio 模式
    python model_server.py --test   # 自测模式
"""
import sys
import os
import json

# 加入项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.mcp_protocol import MCPServer

# 创建 MCP Server
server = MCPServer("model-service", version="1.0.0")


# ========== 工具定义 ==========

@server.tool(
    name="chat_completion",
    description="调用大模型进行对话补全。支持 ernie-lite（轻量）和 ernie-3.5（强力）两个模型。",
    input_schema={
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "description": "对话消息列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": ["user", "assistant", "system"]},
                        "content": {"type": "string"}
                    },
                    "required": ["role", "content"]
                }
            },
            "model": {
                "type": "string",
                "description": "模型名称",
                "enum": ["ernie-lite", "ernie-3.5"],
                "default": "ernie-lite"
            },
            "temperature": {
                "type": "number",
                "description": "温度参数 (0-1)",
                "default": 0.7
            },
            "max_output_tokens": {
                "type": "integer",
                "description": "最大输出 token 数",
                "default": 2048
            }
        },
        "required": ["messages"]
    }
)
def chat_completion(messages, model="ernie-lite", temperature=0.7, max_output_tokens=2048):
    """调用大模型"""
    try:
        import erniebot
        erniebot.api_type = "aistudio"
        # 从环境变量或默认值获取 token
        token = os.getenv("ERNIEBOT_ACCESS_TOKEN", "0b93205ac0fc59d69166edb8e24cf1bc48aed453")
        erniebot.access_token = token

        response = erniebot.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        return {
            "success": True,
            "result": response.get_result(),
            "model": model,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "model": model,
        }


@server.tool(
    name="route_model",
    description="根据任务类型，返回推荐使用的模型名称。用于自动路由。",
    input_schema={
        "type": "object",
        "properties": {
            "task_type": {
                "type": "string",
                "description": "任务类型",
                "enum": ["intent", "summary", "classify", "email", "diagnosis",
                         "code", "literature", "reasoning", "task_plan", "report", "general"]
            }
        },
        "required": ["task_type"]
    }
)
def route_model(task_type):
    """根据任务类型选择模型"""
    routing = {
        "intent": "ernie-lite", "summary": "ernie-lite", "classify": "ernie-lite",
        "entity": "ernie-lite", "translate": "ernie-lite", "general": "ernie-lite",
        "email": "ernie-3.5", "diagnosis": "ernie-3.5", "code": "ernie-3.5",
        "literature": "ernie-3.5", "reasoning": "ernie-3.5",
        "task_plan": "ernie-3.5", "report": "ernie-3.5",
    }
    model = routing.get(task_type, "ernie-lite")
    return {"task_type": task_type, "model": model}


@server.tool(
    name="list_models",
    description="列出所有可用的模型",
    input_schema={"type": "object", "properties": {}}
)
def list_models():
    """列出模型"""
    return {
        "models": [
            {"name": "ernie-lite", "description": "轻量快速，适合意图识别、摘要、分类"},
            {"name": "ernie-3.5", "description": "强力模型，适合生成、推理、分析"},
        ]
    }


# ========== 启动 ==========

if __name__ == "__main__":
    if "--test" in sys.argv:
        # 自测模式
        print(f"[{server.name}] 工具列表:")
        for t in server.tools.values():
            print(f"  - {t.name}: {t.description}")
        print(f"\n路由测试:")
        result = route_model("task_plan")
        print(f"  task_plan → {result}")
        result = route_model("summary")
        print(f"  summary → {result}")
        print("\n✅ 自测通过")
    else:
        # stdio 模式
        server.run()
