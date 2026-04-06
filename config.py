"""
deepin-agent-teams 配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 文心大模型 API 配置（AI Studio token）
ERNIEBOT_ACCESS_TOKEN = os.getenv("ERNIEBOT_ACCESS_TOKEN", "")
# 默认 token（来自 MEMORY.md）
DEFAULT_ACCESS_TOKEN = "0b93205ac0fc59d69166edb8e24cf1bc48aed453"

# Agent 配置
AGENTS_CONFIG = {
    "lead": {
        "model": "ernie-lite",
        "temperature": 0.7,
        "system_prompt": """你是一个多智能体系统的 Lead Agent（主智能体）。
你的职责：
1. 接收用户的高层需求
2. 将任务拆解为多个子任务
3. 调用 Researcher Agent 和 Coder Agent 执行子任务
4. 整合各 Agent 的结果，返回最终答案给用户

协作原则：
- 合理拆分任务粒度
- 需要信息检索 → 调用 Researcher
- 需要代码分析/文档生成 → 调用 Coder
- 保持上下文连贯""",
    },
    "researcher": {
        "model": "ernie-lite", 
        "temperature": 0.5,
        "system_prompt": """你是一个 Researcher Agent（研究智能体）。
你的职责：
1. 负责信息检索和文献分析
2. 输出结构化的研究发现
3. 支持多轮问答

工作方式：
- 读取用户提供的文件、URL 或问题
- 提取关键信息，生成结构化摘要
- 如需调用工具，使用 available_tools""",
    },
    "coder": {
        "model": "ernie-lite",
        "temperature": 0.3,
        "system_prompt": """你是一个 Coder Agent（编码智能体）。
你的职责：
1. 负责代码分析和文档生成
2. 执行 Python/Shell 命令
3. 输出结构化的分析报告

工作方式：
- 分析给定的代码文件或项目
- 生成清晰的文档和摘要
- 遇到错误时提供修复建议""",
    },
}

# OpenClaw 配置
OPENCLAW_CONFIG = {
    "workspace": "/root/.openclaw/workspace/deepin-agent-teams",
    "log_level": "INFO",
}
