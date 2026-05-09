"""
deepin-agent-teams 配置
双模型路由：ernie-lite（快）+ ernie-3.5（强）
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 文心大模型 API 配置（AI Studio token）
ERNIEBOT_ACCESS_TOKEN = os.getenv("ERNIEBOT_ACCESS_TOKEN", "")
# 强模型 token（可单独配置，为空则与 lite 共用）
ERNIEBOT_STRONG_TOKEN = os.getenv("ERNIEBOT_STRONG_TOKEN", "")
# 默认 token（来自 MEMORY.md）
DEFAULT_ACCESS_TOKEN = "0b93205ac0fc59d69166edb8e24cf1bc48aed453"

# 双模型配置
MODEL_LITE = os.getenv("MODEL_LITE", "ernie-lite")       # 轻量快速
MODEL_STRONG = os.getenv("MODEL_STRONG", "ernie-3.5")     # 强力模型

# 模型路由表：任务类型 → 模型级别
MODEL_ROUTING = {
    # lite 级别：快、便宜、简单任务
    "intent":       "lite",     # 意图识别
    "summary":      "lite",     # 上下文摘要
    "classify":     "lite",     # 分类/标签
    "entity":       "lite",     # 实体提取
    "translate":    "lite",     # 简单翻译

    # strong 级别：强、复杂、需要推理
    "email":        "strong",   # 邮件生成
    "diagnosis":    "strong",   # 系统诊断报告
    "code":         "strong",   # 代码分析
    "literature":   "strong",   # 文献综述
    "reasoning":    "strong",   # 复杂推理
    "task_plan":    "strong",   # 任务拆解/规划
    "report":       "strong",   # 报告生成

    # 默认
    "general":      "lite",     # 通用对话
}

# Agent 配置（双模型路由）
AGENTS_CONFIG = {
    "lead": {
        "model": MODEL_STRONG,  # 主Agent用强模型做任务拆解
        "task_type": "task_plan",
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
        "model": MODEL_LITE,    # 研究Agent用轻量模型做信息检索
        "task_type": "summary",
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
        "model": MODEL_LITE,    # 编码Agent用轻量模型做代码分析
        "task_type": "code",
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
    "email_writer": {
        "model": MODEL_STRONG,  # 邮件撰写用强模型
        "task_type": "email",
        "temperature": 0.7,
        "system_prompt": """你是一个邮件撰写智能体。
你的职责：
1. 根据用户意图和收集到的信息，撰写专业的邮件
2. 邮件结构清晰：开头、正文、结尾
3. 语言得体，符合商务邮件规范
4. 支持用户反馈后的迭代优化""",
    },
    "diagnosis_expert": {
        "model": MODEL_STRONG,  # 诊断用强模型
        "task_type": "diagnosis",
        "temperature": 0.5,
        "system_prompt": """你是一个系统诊断智能体。
你的职责：
1. 分析系统问题的根本原因
2. 生成修复方案并评估风险
3. 优先安全操作，高风险操作需用户确认
4. 修复后验证问题是否解决""",
    },
}

# OpenClaw 配置
OPENCLAW_CONFIG = {
    "workspace": "/root/.openclaw/workspace/deepin-agent-teams",
    "log_level": "INFO",
}
