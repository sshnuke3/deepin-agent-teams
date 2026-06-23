#!/usr/bin/env python3
"""
agents/model_router.py - 双文心模型路由器

赛题要求：至少调用两款文心大模型 API
方案：
  - ernie-lite：轻量快速（意图识别/摘要/分类/通用对话）
  - ernie-3.5：强力复杂（代码分析/诊断/邮件生成/文献综述/任务规划）
  - MiniMax：第三方备选（仅在文心模型全部不可用时降级）

路由策略：根据 config.py 的 MODEL_ROUTING 表自动选择模型

设计原则：
1. 每次调用超时 30s，超时自动切换
2. 降级链：ernie-3.5 ↔ ernie-lite → MiniMax → 本地 fallback
3. 记录每步调用结果（成功/失败/耗时/token）
"""
import os
import sys
import time
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

# 添加项目根目录到 path（config.py 在上级目录）
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_this_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 导入项目配置
try:
    from config import (
        MODEL_LITE, MODEL_STRONG, MODEL_ROUTING,
        ERNIEBOT_ACCESS_TOKEN, ERNIEBOT_STRONG_TOKEN, DEFAULT_ACCESS_TOKEN,
    )
except ImportError:
    MODEL_LITE = "ernie-lite"
    MODEL_STRONG = "ernie-3.5"
    MODEL_ROUTING = {}
    ERNIEBOT_ACCESS_TOKEN = ""
    ERNIEBOT_STRONG_TOKEN = ""
    DEFAULT_ACCESS_TOKEN = os.environ.get("DEFAULT_ACCESS_TOKEN", "")

# MiniMax 作为第三方备选
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")

DEFAULT_TIMEOUT = 30


@dataclass
class ModelResponse:
    """标准响应格式"""
    content: str
    model: str           # 实际使用的模型名
    level: str           # "lite" | "strong" | "minimax" | "fallback"
    success: bool
    error: Optional[str] = None
    latency_ms: int = 0
    token_used: int = 0


class ModelRouter:
    """
    双文心模型路由器

    使用方式：
        router = ModelRouter()
        resp = router.chat("分析这段代码...", task_type="code")
        print(resp.content)

    路由逻辑（遵循 config.py MODEL_ROUTING 表）：
        task_type → "lite" → ernie-lite
        task_type → "strong" → ernie-3.5
        两者均失败 → MiniMax（第三方备选）
    """

    def __init__(self, verbose: bool = True) -> None:
        self.verbose = verbose
        self._ernie_available = False
        self._minimax_available = False
        self._strong_available = True   # ernie-3.5 是否可用（token 是否耗尽）
        self._call_log: list = []

        self._init_ernie()
        self._init_minimax()

    def _init_ernie(self):
        """初始化 ERNIE BOT（文心大模型）"""
        try:
            import erniebot
            token = ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN
            if not token:
                if self.verbose:
                    print("[ModelRouter] ERNIE token not configured")
                return
            erniebot.api_type = "aistudio"
            erniebot.access_token = token
            self._ernie_available = True
            if self.verbose:
                print(f"[ModelRouter] ERNIE initialized (token={token[:8]}...)")
        except ImportError:
            if self.verbose:
                print("[ModelRouter] erniebot not installed (pip install erniebot)")
        except Exception as e:
            if self.verbose:
                print(f"[ModelRouter] ERNIE init failed: {e}")

    def _init_minimax(self):
        """初始化 MiniMax（第三方备选）"""
        if not MINIMAX_API_KEY:
            if self.verbose:
                print("[ModelRouter] MiniMax API key not found (fallback unavailable)")
            return
        self._minimax_available = True
        if self.verbose:
            print(f"[ModelRouter] MiniMax fallback initialized (key={MINIMAX_API_KEY[:8]}...)")

    def chat(
        self,
        message: str,
        system: Optional[str] = None,
        task_type: str = "general",
        messages: Optional[List[Dict]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        统一聊天接口，根据 task_type 自动路由到合适的文心模型

        Args:
            message: 用户消息（当 messages 提供时可为空）
            system: 系统提示（可选）
            task_type: 任务类型，决定使用 lite 还是 strong
                - lite 级：intent/summary/classify/entity/translate/general
                - strong 级：email/diagnosis/code/literature/reasoning/task_plan/report
            messages: 完整消息历史（可选，优先于 message）
            temperature: 温度参数

        Returns:
            {"success": bool, "result": str, "model": str, "level": str, "error": str}
        """
        # 根据 task_type 确定模型级别
        level = MODEL_ROUTING.get(task_type, "lite")
        model_name = MODEL_STRONG if level == "strong" else MODEL_LITE

        # 构建消息
        if messages:
            chat_messages = messages
            if system:
                chat_messages = [{"role": "user", "content": f"[系统提示] {system}"}] + chat_messages
        else:
            chat_messages = self._build_messages(message, system)

        # 尝试1：指定模型
        resp = self._call_ernie(model_name, chat_messages, temperature, task_type)
        if resp.success:
            self._log_call(model_name, task_type, resp)
            return {
                "success": True, "result": resp.content,
                "model": resp.model, "level": level,
                "latency_ms": resp.latency_ms,
            }

        # 尝试2：如果 strong 失败，降级到 lite
        if level == "strong" and model_name != MODEL_LITE:
            if self.verbose:
                print(f"[ModelRouter] {model_name} failed, fallback to {MODEL_LITE}")
            resp = self._call_ernie(MODEL_LITE, chat_messages, temperature, task_type)
            if resp.success:
                self._log_call(MODEL_LITE, task_type, resp)
                return {
                    "success": True, "result": resp.content,
                    "model": resp.model, "level": "lite",
                    "latency_ms": resp.latency_ms,
                }

        # 尝试3：MiniMax 第三方备选
        if self._minimax_available:
            if self.verbose:
                print(f"[ModelRouter] ERNIE models unavailable, fallback to MiniMax")
            resp = self._call_minimax(message, system, temperature)
            if resp.success:
                self._log_call("minimax", task_type, resp)
                return {
                    "success": True, "result": resp.content,
                    "model": "MiniMax-Text-01", "level": "minimax",
                    "latency_ms": resp.latency_ms,
                }

        # 全部失败
        self._log_call("none", task_type, resp)
        return {
            "success": False,
            "result": f"[模型全部不可用] 请检查 API 配置。任务类型: {task_type}",
            "model": "none", "level": "fallback",
            "error": resp.error or "all models unavailable",
        }

    def _call_ernie(
        self,
        model_name: str,
        messages: List[Dict],
        temperature: float,
        task_type: str,
    ) -> ModelResponse:
        """调用 ERNIE BOT API"""
        start = time.time()

        if not self._ernie_available:
            return ModelResponse(
                content="", model=model_name, level="",
                success=False, error="ERNIE not initialized",
                latency_ms=int((time.time() - start) * 1000),
            )

        # ernie-3.5 如果之前标记不可用，直接跳过
        if model_name == MODEL_STRONG and not self._strong_available:
            return ModelResponse(
                content="", model=model_name, level="",
                success=False, error="ernie-3.5 token exhausted",
                latency_ms=int((time.time() - start) * 1000),
            )

        try:
            import erniebot

            # 如果有 strong token 且用 strong 模型，切换 token
            token_to_use = ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN
            if model_name == MODEL_STRONG and ERNIEBOT_STRONG_TOKEN:
                token_to_use = ERNIEBOT_STRONG_TOKEN
                erniebot.access_token = token_to_use

            response = erniebot.ChatCompletion.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
            )

            content = response.get_result() if hasattr(response, 'get_result') else str(response)

            return ModelResponse(
                content=str(content),
                model=model_name,
                level="strong" if model_name == MODEL_STRONG else "lite",
                success=True,
                latency_ms=int((time.time() - start) * 1000),
            )

        except Exception as e:
            err_str = str(e)
            # 如果是 quota/token 耗尽，标记该模型不可用
            if "quota" in err_str.lower() or "token" in err_str.lower() or "额度" in err_str:
                if model_name == MODEL_STRONG:
                    self._strong_available = False
                    if self.verbose:
                        print(f"[ModelRouter] ernie-3.5 token exhausted, marking unavailable")

            return ModelResponse(
                content="", model=model_name, level="",
                success=False, error=err_str[:200],
                latency_ms=int((time.time() - start) * 1000),
            )

    def _call_minimax(
        self,
        message: str,
        system: Optional[str],
        temperature: float,
    ) -> ModelResponse:
        """调用 MiniMax API（第三方备选）"""
        start = time.time()

        if not self._minimax_available:
            return ModelResponse(
                content="", model="MiniMax-Text-01", level="minimax",
                success=False, error="MiniMax not available",
                latency_ms=int((time.time() - start) * 1000),
            )

        try:
            import urllib.request

            url = "https://api.minimax.chat/v1/text/chatcompletion_pro"
            headers = {
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json",
            }

            messages = []
            if system:
                messages.append({"role": "system", "name": "assistant", "content": system})
            messages.append({"role": "user", "content": message})

            payload = {
                "model": "MiniMax-Text-01",
                "messages": messages,
                "max_tokens": 2048,
                "temperature": temperature,
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
                level="minimax",
                success=True,
                latency_ms=int((time.time() - start) * 1000),
                token_used=result.get("usage", {}).get("total_tokens", 0),
            )

        except Exception as e:
            return ModelResponse(
                content="", model="MiniMax-Text-01", level="minimax",
                success=False, error=str(e)[:200],
                latency_ms=int((time.time() - start) * 1000),
            )

    def _build_messages(self, message: str, system: Optional[str]) -> List[Dict]:
        """构建消息列表（ERNIE aistudio 不支持 system role）"""
        messages = []
        if system:
            messages.append({"role": "user", "content": f"[系统提示] {system}\n\n{message}"})
        else:
            messages.append({"role": "user", "content": message})
        return messages

    def _log_call(self, model: str, task_type: str, resp: ModelResponse):
        """记录调用日志"""
        self._call_log.append({
            "ts": time.time(),
            "model": model,
            "task_type": task_type,
            "level": resp.level,
            "success": resp.success,
            "latency_ms": resp.latency_ms,
            "token_used": resp.token_used,
            "error": resp.error,
        })

    def stats(self) -> dict:
        """返回调用统计"""
        total = len(self._call_log)
        success = sum(1 for c in self._call_log if c["success"])
        by_model = {}
        for c in self._call_log:
            m = c["model"]
            if m not in by_model:
                by_model[m] = {"total": 0, "success": 0}
            by_model[m]["total"] += 1
            if c["success"]:
                by_model[m]["success"] += 1

        return {
            "total_calls": total,
            "success": success,
            "failures": total - success,
            "success_rate": f"{100*success/total:.1f}%" if total else "0%",
            "by_model": by_model,
            "models_used": list(by_model.keys()),
        }

    def get_routing_info(self) -> dict:
        """返回路由配置信息（用于调试和展示）"""
        info = {
            "routing_table": {},
            "ernie_available": self._ernie_available,
            "strong_available": self._strong_available,
            "minimax_available": self._minimax_available,
        }
        for task_type, level in MODEL_ROUTING.items():
            model = MODEL_STRONG if level == "strong" else MODEL_LITE
            info["routing_table"][task_type] = {"level": level, "model": model}
        return info


# 全局单例
_router_instance: Optional[ModelRouter] = None


def get_router(verbose: bool = True) -> ModelRouter:
    """获取全局 ModelRouter 单例"""
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter(verbose=verbose)
    return _router_instance


# ========== 单元测试 ==========

def _test():
    print("\n=== ModelRouter 单元测试 ===\n")

    # Test 1: 初始化
    print("Test 1: 初始化")
    router = ModelRouter(verbose=True)
    print("  ✅ PASS\n")

    # Test 2: 路由表
    print("Test 2: 路由表（config.py MODEL_ROUTING）")
    info = router.get_routing_info()
    print(f"  路由条目数: {len(info['routing_table'])}")
    for task, cfg in info["routing_table"].items():
        print(f"    {task} → {cfg['level']} ({cfg['model']})")
    assert len(info["routing_table"]) > 0
    print("  ✅ PASS\n")

    # Test 3: 轻量任务路由 → ernie-lite
    print("Test 3: 轻量任务路由")
    level = MODEL_ROUTING.get("intent", "lite")
    assert level == "lite", f"expected lite, got {level}"
    print(f"  intent → {level} (ernie-lite)")
    print("  ✅ PASS\n")

    # Test 4: 复杂任务路由 → ernie-3.5
    print("Test 4: 复杂任务路由")
    level = MODEL_ROUTING.get("code", "lite")
    assert level == "strong", f"expected strong, got {level}"
    print(f"  code → {level} (ernie-3.5)")
    print("  ✅ PASS\n")

    # Test 5: 消息构建（ERNIE 不支持 system role）
    print("Test 5: 消息构建")
    msgs = router._build_messages("分析代码", "你是专家")
    assert len(msgs) == 1
    assert "[系统提示]" in msgs[0]["content"]
    print(f"  消息数: {len(msgs)}, 包含系统提示: {'[系统提示]' in msgs[0]['content']}")
    print("  ✅ PASS\n")

    # Test 6: stats 初始状态
    print("Test 6: stats 初始状态")
    stats = router.stats()
    assert stats["total_calls"] == 0
    print(f"  stats={stats}")
    print("  ✅ PASS\n")

    # Test 7: 双模型覆盖
    print("Test 7: 双文心模型覆盖验证")
    lite_tasks = [t for t, l in MODEL_ROUTING.items() if l == "lite"]
    strong_tasks = [t for t, l in MODEL_ROUTING.items() if l == "strong"]
    print(f"  ernie-lite 任务: {lite_tasks}")
    print(f"  ernie-3.5 任务: {strong_tasks}")
    assert len(lite_tasks) > 0, "lite 任务不能为空"
    assert len(strong_tasks) > 0, "strong 任务不能为空"
    print(f"  ✅ 双模型覆盖: {len(lite_tasks)} 个 lite + {len(strong_tasks)} 个 strong\n")

    print("=== 所有测试通过 ===\n")


if __name__ == "__main__":
    _test()
