"""
agents/coder.py - Coder Agent（编码智能体）
"""
from .base import BaseAgent
import subprocess
import os


class CoderAgent(BaseAgent):
    """
    Coder Agent 负责代码分析和文档生成
    支持：代码分析、Shell 执行、文档生成
    """

    def __init__(self, verbose: bool = True):
        super().__init__("coder", verbose=verbose)

    def run_command(self, cmd: str) -> str:
        """执行 Shell 命令"""
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60
            )
            output = f"[EXIT {result.returncode}]\n"
            if result.stdout:
                output += f"STDOUT:\n{result.stdout[:10000]}"
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr[:5000]}"
            return output
        except subprocess.TimeoutExpired:
            return "命令执行超时（60秒）"
        except Exception as e:
            return f"执行失败: {e}"

    def analyze_code(self, code: str) -> str:
        """分析代码片段"""
        prompt = f"""请分析以下代码，输出结构化的分析报告（包含：功能说明、关键函数、依赖关系、潜在问题）：

```{code}
```"""
        return self.chat(prompt)

    def analyze_file(self, file_path: str) -> str:
        """分析代码文件"""
        if not os.path.exists(file_path):
            return f"文件不存在: {file_path}"
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read(50000)
            return self.analyze_code(code)
        except Exception as e:
            return f"读取失败: {e}"

    def generate_docs(self, source_dir: str, output_format: str = "markdown") -> str:
        """生成项目文档"""
        prompt = f"""请为以下项目目录生成{output_format}格式的文档，包含：
1. 项目结构树
2. 各模块功能说明
3. 关键文件说明
4. 依赖关系

项目路径：{source_dir}"""
        return self.chat(prompt)

    def chat(self, message: str, stream: bool = False) -> str:
        """重写 chat，支持特殊指令"""
        if message.startswith("run:"):
            cmd = message[4:].strip()
            result = self.run_command(cmd)
            return self.chat(f"命令执行结果：\n{result}")
        
        if message.startswith("analyze:"):
            file_path = message[8:].strip()
            return self.analyze_file(file_path)
        
        if message.startswith("docs:"):
            dir_path = message[5:].strip()
            return self.generate_docs(dir_path)
        
        return super().chat(message, stream)
