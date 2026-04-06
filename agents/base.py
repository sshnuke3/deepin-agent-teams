"""
agents/base.py - Agent 基础类
"""
import erniebot
from typing import Optional, List, Dict, Any
from config import ERNIEBOT_API_KEY, ERNIEBOT_SECRET_KEY, AGENTS_CONFIG


class BaseAgent:
    """所有 Agent 的基类，封装 erniebot 调用"""

    def __init__(self, role: str, verbose: bool = True):
        self.role = role
        self.verbose = verbose
        self.config = AGENTS_CONFIG[role]
        self.messages: List[Dict[str, str]] = []
        
        # 设置 erniebot 凭证
        if ERNIEBOT_API_KEY and ERNIEBOT_SECRET_KEY:
            erniebot.api_type = "aistudio"
            erniebot.aistudio_access_token = ERNIEBOT_API_KEY
        
        # 系统提示词
        self._setup_system_prompt()

    def _setup_system_prompt(self):
        """设置系统提示词"""
        self.messages.append({
            "role": "system",
            "content": self.config["system_prompt"]
        })

    def chat(self, message: str, stream: bool = False) -> str:
        """
        发送消息并获取回复
        
        Args:
            message: 用户消息
            stream: 是否流式输出
        
        Returns:
            Agent 的回复文本
        """
        self.messages.append({"role": "user", "content": message})
        
        response = erniebot.ChatCompletion.create(
            model=self.config["model"],
            messages=self.messages,
            temperature=self.config["temperature"],
            stream=stream,
        )
        
        reply = response.get_result() if hasattr(response, 'get_result') else str(response)
        
        self.messages.append({"role": "assistant", "content": reply})
        
        if self.verbose:
            print(f"[{self.role.upper()}] {reply[:200]}{'...' if len(reply) > 200 else ''}")
        
        return reply

    def reset(self):
        """重置对话历史（保留 system prompt）"""
        sys_msg = self.messages[0]
        self.messages = [sys_msg]

    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self.messages[1:]  # 排除 system prompt
