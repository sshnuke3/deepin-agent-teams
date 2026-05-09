"""
双模型路由器
根据任务类型自动选择合适的文心大模型：
- ernie-lite：轻量快速（意图识别、上下文摘要、简单分类）
- ernie-3.5/ernie-4.0：强力模型（邮件生成、诊断报告、代码分析、复杂推理）
"""
import os
from typing import Optional, Dict, Any
from config import (
    ERNIEBOT_ACCESS_TOKEN, DEFAULT_ACCESS_TOKEN,
    MODEL_LITE, MODEL_STRONG, MODEL_ROUTING
)

try:
    import erniebot
except ImportError:
    erniebot = None


class ModelRouter:
    """模型路由器 - 根据任务类型选择最优模型"""

    def __init__(self, lite_token: str = None, strong_token: str = None):
        """
        Args:
            lite_token: ernie-lite 的 access_token（默认用 config 中的）
            strong_token: ernie-3.5/4.0 的 access_token（默认用 config 中的）
        """
        self.lite_token = lite_token or ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN
        self.strong_token = strong_token or self.lite_token  # 无强模型token时降级到lite

        # 模型配置
        self.models = {
            "lite": {
                "model": MODEL_LITE,
                "token": self.lite_token,
                "description": "轻量快速，适合意图识别、摘要、分类",
            },
            "strong": {
                "model": MODEL_STRONG,
                "token": self.strong_token,
                "description": "强力模型，适合生成、推理、分析",
            },
        }

        # 路由表：任务类型 → 模型级别
        self.routing = MODEL_ROUTING

    def get_model_for_task(self, task_type: str) -> str:
        """根据任务类型返回模型名称"""
        level = self.routing.get(task_type, "lite")
        return self.models[level]["model"]

    def get_token_for_task(self, task_type: str) -> str:
        """根据任务类型返回对应的 token"""
        level = self.routing.get(task_type, "lite")
        return self.models[level]["token"]

    def get_level_for_task(self, task_type: str) -> str:
        """返回任务对应的模型级别"""
        return self.routing.get(task_type, "lite")

    def chat(self, task_type: str, messages: list, temperature: float = 0.7,
             max_output_tokens: int = 2048, **kwargs) -> Dict[str, Any]:
        """
        使用对应模型进行对话

        Args:
            task_type: 任务类型（intent/summary/email/diagnosis/code/literature/general）
            messages: 对话消息列表
            temperature: 温度参数
            max_output_tokens: 最大输出 token 数

        Returns:
            {"success": bool, "result": str, "model": str, "level": str}
        """
        if erniebot is None:
            return {"success": False, "error": "erniebot 未安装", "model": "none", "level": "none"}

        model = self.get_model_for_task(task_type)
        token = self.get_token_for_task(task_type)
        level = self.get_level_for_task(task_type)

        try:
            erniebot.api_type = "aistudio"
            erniebot.access_token = token

            response = erniebot.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                **kwargs
            )

            result = response.get_result()
            return {
                "success": True,
                "result": result,
                "model": model,
                "level": level,
                "task_type": task_type,
            }

        except Exception as e:
            # 强模型失败时降级到 lite
            if level == "strong" and model != MODEL_LITE:
                try:
                    erniebot.access_token = self.lite_token
                    response = erniebot.ChatCompletion.create(
                        model=MODEL_LITE,
                        messages=messages,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        **kwargs
                    )
                    result = response.get_result()
                    return {
                        "success": True,
                        "result": result,
                        "model": MODEL_LITE,
                        "level": "lite (降级)",
                        "task_type": task_type,
                        "warning": f"强模型 {model} 失败，已降级到 lite: {str(e)}",
                    }
                except Exception as e2:
                    return {"success": False, "error": f"降级也失败: {str(e2)}", "model": MODEL_LITE, "level": "lite"}
            return {"success": False, "error": str(e), "model": model, "level": level}

    def get_status(self) -> Dict[str, Any]:
        """获取路由器状态"""
        return {
            "lite_model": MODEL_LITE,
            "strong_model": MODEL_STRONG,
            "lite_token_set": bool(self.lite_token),
            "strong_token_set": bool(self.strong_token),
            "tokens_same": self.lite_token == self.strong_token,
            "routing_table": self.routing,
        }


# 全局单例
_router: Optional[ModelRouter] = None


def get_router() -> ModelRouter:
    """获取全局模型路由器单例"""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def chat(task_type: str, messages: list, **kwargs) -> Dict[str, Any]:
    """快捷方法：使用全局路由器进行对话"""
    return get_router().chat(task_type, messages, **kwargs)


def get_model(task_type: str) -> str:
    """快捷方法：获取任务对应的模型名"""
    return get_router().get_model_for_task(task_type)
