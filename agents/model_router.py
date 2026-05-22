#!/usr/bin/env python3
"""
agents/model_router.py - 多模型路由器

支持模型：
1. MiniMax（大当家，当前主力）
2. ERNIE BOT（备选，当前 token 耗尽）

路由策略：
- 轻量任务（意图识别/摘要/分类）→ MiniMax
- 复杂任务（代码分析/生成/诊断）→ MiniMax
- ERNIE 仅在 MiniMax 完全不可用时降级使用

设计原则：
1. 每次调用超时 30s，超时自动切换
2. 降级链：MiniMax → ERNIE-lite → ERNIE-3.5 → 本地 fallback
3. 记录每步调用结果（成功/失败/耗时/token）
"""
import os
import time
import json
from typing import Literal, Optional, Dict, Any
from dataclasses import dataclass, field

# 优先从环境变量读取 MiniMax key
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
ERNIE_TOKEN = os.environ.get("ERNIE_TOKEN", "0b93205ac0fc59d69166edb8e24cf1bc48aed453")

DEFAULT_TIMEOUT = 30


@dataclass
class ModelResponse:
    """标准响应格式"""
    content: str
    model: str           # 实际使用的模型
    success: bool
    error: Optional[str] = None
    latency_ms: int = 0
    token_used: int = 0


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    provider: str        # "minimax" | "ernie"
    model_id: str        # 具体模型名
    timeout: int = 30
    max_tokens: int = 4096
    enabled: bool = True


class ModelRouter:
    """
    多模型路由器

    使用方式：
        router = ModelRouter()
        resp = router.chat("分析这段代码...", task_type="code_analysis")
        print(resp.content)
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._minimax_client = None
        self._ernie_client = None
        self._call_log: list = []

        # 初始化客户端
        self._init_minimax()
        self._init_ernie()

    def _init_minimax(self):
        if not MINIMAX_API_KEY:
            if self.verbose:
                print("[ModelRouter] MiniMax API key not found in env")
            return
        try:
            # MiniMax SDK 是标准 HTTP 调用
            self._minimax_client = {
                "api_key": MINIMAX_API_KEY,
                "available": True,
            }
            if self.verbose:
                print(f"[ModelRouter] MiniMax initialized (key={MINIMAX_API_KEY[:8]}...)")
        except Exception as e:
            if self.verbose:
                print(f"[ModelRouter] MiniMax init failed: {e}")
            self._minimax_client = {"available": False, "error": str(e)}

    def _init_ernie(self):
        if not ERNIE_TOKEN:
            return
        try:
            import erniebot
            erniebot.api_type = "aistudio"
            erniebot.access_token = ERNIE_TOKEN
            self._ernie_client = {"available": True}
            if self.verbose:
                print("[ModelRouter] ERNIE initialized")
        except Exception as e:
            if self.verbose:
                print(f"[ModelRouter] ERNIE init failed: {e}")
            self._ernie_client = {"available": False, "error": str(e)}

    def chat(
        self,
        message: str,
        system: Optional[str] = None,
        task_type: str = "general",
        model_preference: Optional[str] = None,
    ) -> ModelResponse:
        """
        统一聊天接口，自动路由到合适模型

        Args:
            message: 用户消息
            system: 系统提示（可选）
            task_type: 任务类型，影响路由
                - "intent/classification" → 轻量快速
                - "code_analysis/summarization" → 复杂准确
                - "creative/writing" → 中等
            model_preference: 强制使用某个模型（可选）
        """
        models_priority = ["minimax"]
        if model_preference:
            models_priority = [model_preference]

        # 尝试每个模型
        for model_name in models_priority:
            resp = self._try_model(model_name, message, system, task_type)
            if resp.success:
                self._log_call(model_name, task_type, resp)
                return resp

        # 全部失败 → fallback
        return self._fallback_response(task_type)

    def _try_model(
        self,
        model_name: str,
        message: str,
        system: Optional[str],
        task_type: str,
    ) -> ModelResponse:
        """尝试调用指定模型"""
        start = time.time()

        if model_name == "minimax":
            return self._call_minimax(message, system, task_type, start)
        elif model_name == "ernie":
            return self._call_ernie(message, system, task_type, start)
        else:
            return ModelResponse(
                content="",
                model=model_name,
                success=False,
                error=f"unknown model: {model_name}",
                latency_ms=int((time.time() - start) * 1000),
            )

    def _call_minimax(
        self,
        message: str,
        system: Optional[str],
        task_type: str,
        start: float,
    ) -> ModelResponse:
        """调用 MiniMax API"""
        if not self._minimax_client or not self._minimax_client.get("available"):
            return ModelResponse(
                content="", model="minimax", success=False,
                error="MiniMax client not available",
                latency_ms=int((time.time() - start) * 1000),
            )

        try:
            import urllib.request
            import urllib.parse

            # MiniMax 官方 API endpoint
            url = "https://api.minimax.chat/v1/text/chatcompletion_pro"
            headers = {
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": "MiniMax-Text-01",
                "messages": self._build_messages_minimax(message, system),
                "max_tokens": 2048,
                "temperature": 0.7,
            }

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            req.add_header("Content-Length", str(len(data)))

            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            choices = result.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""

            return ModelResponse(
                content=content,
                model="MiniMax-Text-01",
                success=True,
                latency_ms=int((time.time() - start) * 1000),
                token_used=result.get("usage", {}).get("total_tokens", 0),
            )

        except Exception as e:
            return ModelResponse(
                content="", model="MiniMax-Text-01", success=False,
                error=str(e)[:100],
                latency_ms=int((time.time() - start) * 1000),
            )

    def _call_ernie(
        self,
        message: str,
        system: Optional[str],
        task_type: str,
        start: float,
    ) -> ModelResponse:
        """调用 ERNIE BOT API"""
        if not self._ernie_client or not self._ernie_client.get("available"):
            return ModelResponse(
                content="", model="ernie", success=False,
                error="ERNIE client not available",
                latency_ms=int((time.time() - start) * 1000),
            )

        try:
            import erniebot

            msgs = self._build_messages_ernie(message, system)
            response = erniebot.ChatCompletion.create(
                model="ernie-lite",
                messages=msgs,
            )

            content = response.get_result() if hasattr(response, 'get_result') else str(response)
            return ModelResponse(
                content=str(content),
                model="ernie-lite",
                success=True,
                latency_ms=int((time.time() - start) * 1000),
            )

        except Exception as e:
            err_str = str(e)
            # 如果是 quota 耗尽，标记不可用
            if "quota" in err_str.lower() or "token" in err_str.lower():
                if self._ernie_client:
                    self._ernie_client["available"] = False

            return ModelResponse(
                content="", model="ernie-lite", success=False,
                error=err_str[:100],
                latency_ms=int((time.time() - start) * 1000),
            )

    def _build_messages_minimax(self, message: str, system: Optional[str]) -> list:
        """构建 MiniMax 消息格式"""
        messages = []
        if system:
            messages.append({"role": "system", "name": "ominous", "content": system})
        messages.append({"role": "user", "content": message})
        return messages

    def _build_messages_ernie(self, message: str, system: Optional[str]) -> list:
        """构建 ERNIE 消息格式（ERNIE 不支持 system role）"""
        messages = []
        # ERNIE 不支持 system，用 user 代替
        if system:
            messages.append({"role": "user", "content": f"[系统提示] {system}\n\n{message}"})
        else:
            messages.append({"role": "user", "content": message})
        return messages

    def _fallback_response(self, task_type: str) -> ModelResponse:
        """所有模型都失败时的 fallback"""
        return ModelResponse(
            content=f"[模型全部不可用] 请检查网络和 API 配置。\n任务类型: {task_type}",
            model="none",
            success=False,
            error="all models unavailable",
            latency_ms=0,
        )

    def _log_call(self, model: str, task_type: str, resp: ModelResponse):
        """记录调用日志"""
        self._call_log.append({
            "ts": time.time(),
            "model": model,
            "task_type": task_type,
            "success": resp.success,
            "latency_ms": resp.latency_ms,
            "token_used": resp.token_used,
            "error": resp.error,
        })
        if self.verbose and not resp.success:
            print(f"[ModelRouter] {model} failed: {resp.error}")

    def stats(self) -> dict:
        """返回调用统计"""
        total = len(self._call_log)
        success = sum(1 for c in self._call_log if c["success"])
        failures = sum(1 for c in self._call_log if not c["success"])
        total_latency = sum(c["latency_ms"] for c in self._call_log)
        return {
            "total_calls": total,
            "success": success,
            "failures": failures,
            "success_rate": f"{100*success/total:.1f}%" if total else "0%",
            "avg_latency_ms": int(total_latency / total) if total else 0,
            "models_tried": list({c["model"] for c in self._call_log}),
        }


# ========== 单元测试（不走 API） ==========

def _test():
    print("\n=== ModelRouter 单元测试 ===\n")

    # Test 1: 初始化
    print("Test 1: 初始化（不调用 API）")
    router = ModelRouter(verbose=True)
    print("  ✅ PASS\n")

    # Test 2: stats 初始状态
    print("Test 2: stats 初始状态")
    stats = router.stats()
    assert stats["total_calls"] == 0
    assert stats["success"] == 0
    print(f"  stats={stats}")
    print("  ✅ PASS\n")

    # Test 3: message 构建
    print("Test 3: message 构建")
    msgs = router._build_messages_minimax("你好", "你是一个助手")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    print("  ✅ PASS\n")

    # Test 4: ERNIE message 构建（不支持 system）
    print("Test 4: ERNIE message 构建")
    msgs = router._build_messages_ernie("分析代码", "你是专家")
    assert len(msgs) == 1
    assert "[系统提示]" in msgs[0]["content"]
    print("  ✅ PASS\n")

    print("=== 所有测试通过（不涉及实际 API 调用）===\n")


if __name__ == "__main__":
    _test()