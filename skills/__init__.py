"""
Skills 技能库
预定义技能模块：邮件撰写、系统诊断、代码分析、文件搜索
"""
import os
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.mcp_adapter import get_adapter, ToolResult


@dataclass
class SkillDef:
    """技能定义"""
    name: str
    description: str
    category: str  # email, system, code, search, custom
    tools_used: List[str]  # 依赖的工具列表
    trigger_keywords: List[str]  # 触发关键词
    prompt_template: str = ""  # 提示模板


class SkillRegistry:
    """
    技能注册中心

    管理预定义技能，支持动态注册和发现
    """

    def __init__(self):
        self.skills: Dict[str, SkillDef] = {}
        self._register_builtin_skills()

    def register(self, skill: SkillDef):
        """注册技能"""
        self.skills[skill.name] = skill

    def unregister(self, name: str):
        """注销技能"""
        self.skills.pop(name, None)

    def list_skills(self, category: str = None) -> List[Dict]:
        """列出所有技能"""
        skills = list(self.skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return [{
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "tools_used": s.tools_used,
            "trigger_keywords": s.trigger_keywords,
        } for s in skills]

    def find_skill(self, user_input: str) -> Optional[SkillDef]:
        """根据用户输入匹配最佳技能"""
        text_lower = user_input.lower()
        best_skill = None
        best_score = 0

        for skill in self.skills.values():
            score = sum(1 for kw in skill.trigger_keywords if kw.lower() in text_lower)
            if score > best_score:
                best_score = score
                best_skill = skill

        return best_skill if best_score > 0 else None

    def get_skill(self, name: str) -> Optional[SkillDef]:
        """获取技能定义"""
        return self.skills.get(name)

    def _register_builtin_skills(self):
        """注册内置技能"""

        # === 邮件撰写技能 ===
        self.register(SkillDef(
            name="compose_email",
            description="智能邮件撰写：意图识别→信息收集→邮件生成→发送确认",
            category="email",
            tools_used=["get_clipboard", "search_files", "get_active_window"],
            trigger_keywords=["发邮件", "写邮件", "邮件", "发给", "告知", "通知"],
            prompt_template="""根据以下信息撰写一封专业邮件：
收件人: {recipient}
主题: {topic}
背景信息: {context}

要求：
1. 开头称呼得体
2. 正文结构清晰（背景→要点→行动项）
3. 结尾礼貌
4. 语言简洁专业""",
        ))

        # === 系统诊断技能 ===
        self.register(SkillDef(
            name="system_diagnosis",
            description="系统问题诊断：问题分类→多维检查→修复方案→自动修复",
            category="system",
            tools_used=["exec_command", "manage_service"],
            trigger_keywords=["连不上", "没声音", "坏了", "不行", "错误", "故障", "卡", "慢"],
            prompt_template="""系统问题诊断报告：
问题描述: {problem}
诊断结果: {diagnosis}
发现问题: {issues}

请生成修复方案，包括：
1. 问题根因分析
2. 推荐修复步骤（标注风险等级）
3. 替代方案""",
        ))

        # === 代码分析技能 ===
        self.register(SkillDef(
            name="code_analysis",
            description="代码项目分析：结构扫描→核心模块→质量评估→改进建议",
            category="code",
            tools_used=["list_directory", "read_file", "search_files", "exec_command"],
            trigger_keywords=["代码", "分析", "项目", "review", "bug", "重构"],
            prompt_template="""代码分析报告：
项目路径: {path}
项目结构: {structure}
核心文件: {key_files}

请提供：
1. 项目架构评估
2. 代码质量分析
3. 潜在问题和改进建议""",
        ))

        # === 文件搜索技能 ===
        self.register(SkillDef(
            name="file_search",
            description="智能文件搜索：关键词→文件系统扫描→内容匹配→结果排序",
            category="search",
            tools_used=["search_files", "read_file"],
            trigger_keywords=["找", "搜索", "查找", "哪个文件", "在哪"],
        ))

        # === 文献阅读技能 ===
        self.register(SkillDef(
            name="literature_review",
            description="文献阅读：文件读取→关键信息提取→摘要生成→综述",
            category="search",
            tools_used=["read_file"],
            trigger_keywords=["论文", "文献", "报告", "总结", "摘要", "综述"],
        ))

        # === 系统信息技能 ===
        self.register(SkillDef(
            name="system_info",
            description="系统信息查询：CPU/内存/磁盘/网络状态",
            category="system",
            tools_used=["exec_command"],
            trigger_keywords=["系统信息", "CPU", "内存", "磁盘", "运行状态"],
        ))


# 全局单例
_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


def find_skill(user_input: str) -> Optional[SkillDef]:
    """快捷方法：根据输入匹配技能"""
    return get_registry().find_skill(user_input)
