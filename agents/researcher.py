"""
agents/researcher.py - Researcher Agent（研究智能体）
"""
from .base import BaseAgent
import os
import glob


class ResearcherAgent(BaseAgent):
    """
    Researcher Agent 负责信息检索和文献分析
    支持：文件读取、URL 内容抓取、文本分析
    """

    def __init__(self, verbose: bool = True):
        super().__init__("researcher", verbose=verbose)

    def read_file(self, file_path: str) -> str:
        """读取单个文件内容"""
        if not os.path.exists(file_path):
            return f"文件不存在: {file_path}"
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read(50000)  # 限制 50K 字符
            return f"--- {file_path} ---\n{content}"
        except Exception as e:
            return f"读取失败: {e}"

    def read_files(self, path_pattern: str) -> str:
        """批量读取文件（支持 glob 模式）"""
        files = glob.glob(path_pattern, recursive=True)
        if not files:
            return f"未找到匹配文件: {path_pattern}"
        
        results = []
        for f in files[:10]:  # 最多 10 个文件
            results.append(self.read_file(f))
        return "\n\n".join(results)

    def analyze(self, topic: str) -> str:
        """研究分析入口"""
        return self.chat(f"请研究分析以下主题，输出结构化的研究结果：\n{topic}")

    def chat(self, message: str, stream: bool = False) -> str:
        """重写 chat，支持文件路径参数"""
        # 如果消息以 "read:" 开头，先读取文件
        if message.startswith("read:"):
            file_path = message[5:].strip()
            content = self.read_file(file_path)
            return self._analyze_content(content)
        
        if message.startswith("glob:"):
            pattern = message[5:].strip()
            content = self.read_files(pattern)
            return self._analyze_content(content)
        
        return super().chat(message, stream)

    def _analyze_content(self, content: str) -> str:
        """分析已读取的内容"""
        prompt = f"""请分析以下内容，提取关键信息，输出结构化摘要：

{content[:40000]}"""
        return self.chat(prompt)
