"""
agents/base.py - Agent 基础类
使用 model_router 实现双模型路由
"""
from typing import Optional, List, Dict, Any
from config import ERNIEBOT_ACCESS_TOKEN, DEFAULT_ACCESS_TOKEN, AGENTS_CONFIG

try:
    import erniebot
except ImportError:
    erniebot = None


class BaseAgent:
    """
    所有 Agent 的基类
    封装 erniebot 调用，支持双模型路由（model_router）
    """

    def __init__(self, role: str, verbose: bool = True) -> None:
        self.role = role
        self.verbose = verbose
        self.config = AGENTS_CONFIG.get(role, {})
        self.messages: List[Dict[str, str]] = []

        # 模型路由
        self.task_type = self.config.get("task_type", "general")
        self._init_model_router()

        # 系统提示词
        self._setup_system_prompt()

    def _init_model_router(self):
        """初始化模型路由器"""
        try:
            from model_router import get_router
            self.router = get_router()
        except ImportError:
            self.router = None
            # 降级：直接用 erniebot
            token = ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN
            if token and erniebot:
                erniebot.api_type = "aistudio"
                erniebot.access_token = token

    def _setup_system_prompt(self):
        """设置系统提示词（使用 user role，erniebot aistudio 不支持 system）"""
        system_prompt = self.config.get("system_prompt", f"你是一个 {self.role} 智能体。")
        self.messages.append({
            "role": "user",
            "content": system_prompt
        })

    def chat(self, message: str, stream: bool = False, task_type: str = None) -> str:
        """
        发送消息并获取回复（自动路由模型）

        Args:
            message: 用户消息
            stream: 是否流式输出
            task_type: 覆盖默认任务类型（用于动态选择模型）

        Returns:
            Agent 的回复文本
        """
        self.messages.append({"role": "user", "content": message})

        # 使用模型路由器
        effective_task_type = task_type or self.task_type

        if self.router:
            result = self.router.chat(
                task_type=effective_task_type,
                messages=self.messages,
                temperature=self.config.get("temperature", 0.7),
            )
            if result["success"]:
                reply = result["result"]
                if self.verbose:
                    model_info = f"[{result['model']}/{result['level']}]"
                    print(f"[{self.role.upper()}] {model_info} {reply[:200]}{'...' if len(reply) > 200 else ''}")
            else:
                reply = f"[模型调用失败] {result.get('error', '未知错误')}"
                if self.verbose:
                    print(f"[{self.role.upper()}] ❌ {reply}")
        else:
            # 降级：直接调用 erniebot
            if erniebot is None:
                reply = "[错误] erniebot 未安装"
            else:
                try:
                    model = self.config.get("model", "ernie-lite")
                    response = erniebot.ChatCompletion.create(
                        model=model,
                        messages=self.messages,
                        temperature=self.config.get("temperature", 0.7),
                        stream=stream,
                    )
                    reply = response.get_result() if hasattr(response, 'get_result') else str(response)
                except Exception as e:
                    reply = f"[模型调用异常] {str(e)}"

        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        """重置对话历史（保留 system prompt）"""
        sys_msg = self.messages[0]
        self.messages = [sys_msg]

    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self.messages[1:]  # 排除 system prompt

    def get_model_info(self) -> Dict[str, str]:
        """获取当前 Agent 的模型信息"""
        return {
            "role": self.role,
            "task_type": self.task_type,
            "model": self.config.get("model", "unknown"),
        }
