"""
Skills 技能库 - 带执行能力的技能模块

预定义技能模块：邮件撰写、系统诊断、代码分析、文件搜索、文献综述、系统信息

增强功能：
- SkillExecutor：端到端技能执行（匹配→工具收集→LLM生成→结构化结果）
- 多轮澄清：缺少信息时自动向用户提问
- 工具集成：自动调用 MCP 工具获取上下文
- LLM 路由：通过 model_router / erniebot 调用大模型
- 反馈学习：记录执行历史，支持后续优化
"""
import os
import sys
import time
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.mcp_adapter import get_adapter, ToolResult


# ==================== 数据结构 ====================

@dataclass
class SkillDef:
    """技能定义（保持向后兼容）"""
    name: str
    description: str
    category: str  # email, system, code, search, custom
    tools_used: List[str]  # 依赖的工具列表
    trigger_keywords: List[str]  # 触发关键词
    prompt_template: str = ""  # 提示模板
    required_fields: List[str] = field(default_factory=list)  # 必填字段
    task_type: str = "general"  # LLM 路由任务类型


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    skill_name: str
    output: Any = None
    text_response: str = ""
    missing_fields: List[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    tool_results: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SkillExecutionLog:
    """技能执行日志（用于反馈学习）"""
    skill_name: str
    user_input: str
    timestamp: float
    result: SkillResult
    user_feedback: Optional[str] = None


# ==================== 技能注册中心 ====================

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
            "required_fields": s.required_fields,
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
            required_fields=["recipient", "topic"],
            task_type="email",
            prompt_template="""根据以下信息撰写一封专业邮件：
收件人: {recipient}
主题: {topic}
背景信息: {context}

要求：
1. 开头称呼得体
2. 正文结构清晰（背景→要点→行动项）
3. 结尾礼貌
4. 语言简洁专业

请直接输出邮件全文。""",
        ))

        # === 系统诊断技能 ===
        self.register(SkillDef(
            name="system_diagnosis",
            description="系统问题诊断：问题分类→多维检查→修复方案→自动修复",
            category="system",
            tools_used=["exec_command", "manage_service"],
            trigger_keywords=["连不上", "没声音", "坏了", "不行", "错误", "故障", "卡", "慢"],
            required_fields=["problem"],
            task_type="diagnosis",
            prompt_template="""系统问题诊断报告：
问题描述: {problem}
诊断结果: {diagnosis}

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
            required_fields=["path"],
            task_type="code",
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
            required_fields=["keyword"],
            task_type="general",
            prompt_template="""文件搜索结果：
关键词: {keyword}
搜索路径: {path}
搜索结果: {search_results}

请整理并总结搜索结果，突出最相关的文件。""",
        ))

        # === 文献阅读技能 ===
        self.register(SkillDef(
            name="literature_review",
            description="文献阅读：文件读取→关键信息提取→摘要生成→综述",
            category="search",
            tools_used=["read_file"],
            trigger_keywords=["论文", "文献", "报告", "总结", "摘要", "综述"],
            required_fields=["files"],
            task_type="literature",
            prompt_template="""文献综述任务：
文件列表: {files}
文件内容: {file_contents}
研究问题: {question}

请生成文献综述，包括：
1. 各文献核心观点
2. 共同主题和差异
3. 研究趋势和空白""",
        ))

        # === 系统信息技能 ===
        self.register(SkillDef(
            name="system_info",
            description="系统信息查询：CPU/内存/磁盘/网络状态",
            category="system",
            tools_used=["exec_command"],
            trigger_keywords=["系统信息", "CPU", "内存", "磁盘", "运行状态"],
            required_fields=[],
            task_type="general",
            prompt_template="""系统信息汇总：
{system_data}

请用简洁的中文总结系统当前状态，指出需要注意的问题。""",
        ))


# ==================== 技能执行器 ====================

class SkillExecutor:
    """
    技能执行器

    端到端执行技能：匹配→工具收集→LLM生成→结构化结果
    支持多轮澄清和反馈学习
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._execution_log: List[SkillExecutionLog] = []
        self._llm_caller: Optional[Callable] = None  # 可注入的 LLM 调用器

    def set_llm_caller(self, caller: Callable):
        """注入 LLM 调用函数（签名: caller(prompt, task_type) -> str）"""
        self._llm_caller = caller

    def execute(
        self,
        skill: SkillDef,
        user_input: str,
        context: Dict[str, Any] = None,
        interactive: bool = False,
    ) -> SkillResult:
        """
        执行一个技能

        Args:
            skill: 技能定义
            user_input: 用户原始输入
            context: 预置上下文（可跳过工具收集）
            interactive: 是否交互式（支持多轮澄清）

        Returns:
            SkillResult 结构化执行结果
        """
        start_time = time.time()
        context = context or {}

        if self.verbose:
            print(f"[SKILL] 🚀 执行技能: {skill.name} ({skill.description})")

        # Step 1: 从用户输入提取字段
        extracted = self._extract_fields(skill, user_input)

        # Step 2: 合并上下文
        for key, value in context.items():
            if key not in extracted or not extracted[key]:
                extracted[key] = value

        # Step 3: 检查必填字段
        missing = [
            f for f in skill.required_fields
            if f not in extracted or not extracted[f]
        ]

        if missing and not interactive:
            # 非交互模式：尝试用工具自动填充
            auto_filled = self._auto_fill_fields(skill, missing, user_input, extracted)
            extracted.update(auto_filled)
            missing = [
                f for f in skill.required_fields
                if f not in extracted or not extracted[f]
            ]

        if missing and interactive:
            # 交互模式：向用户提问
            question = self._generate_clarification_question(skill, missing, extracted)
            duration = int((time.time() - start_time) * 1000)
            result = SkillResult(
                success=False,
                skill_name=skill.name,
                needs_clarification=True,
                missing_fields=missing,
                clarification_question=question,
                duration_ms=duration,
            )
            self._log_execution(skill, user_input, result)
            return result

        # Step 4: 收集工具上下文
        tool_results = self._gather_tool_context(skill, extracted)
        extracted["context"] = self._format_tool_results(tool_results)

        # Step 5: 格式化提示词
        prompt = self._format_prompt(skill, extracted)

        # Step 6: 调用 LLM
        response = self._call_llm(prompt, skill.task_type)

        # Step 7: 构建结果
        duration = int((time.time() - start_time) * 1000)

        if response:
            result = SkillResult(
                success=True,
                skill_name=skill.name,
                output=extracted,
                text_response=response,
                tool_results=tool_results,
                duration_ms=duration,
            )
            if self.verbose:
                preview = response[:200] + ("..." if len(response) > 200 else "")
                print(f"[SKILL] ✅ 完成 ({duration}ms): {preview}")
        else:
            result = SkillResult(
                success=False,
                skill_name=skill.name,
                error="LLM 调用失败，所有通道均不可用",
                tool_results=tool_results,
                duration_ms=duration,
            )
            if self.verbose:
                print(f"[SKILL] ❌ 失败 ({duration}ms): LLM 不可用")

        self._log_execution(skill, user_input, result)
        return result

    def continue_execution(
        self,
        skill: SkillDef,
        user_input: str,
        previous_result: SkillResult,
        clarification_answers: Dict[str, str],
    ) -> SkillResult:
        """
        多轮澄清后续执行

        Args:
            skill: 技能定义
            user_input: 用户原始输入
            previous_result: 之前的执行结果（含提取的字段）
            clarification_answers: 用户对澄清问题的回答

        Returns:
            SkillResult
        """
        # 合并之前的提取结果和用户的回答
        context = previous_result.output or {}
        context.update(clarification_answers)

        return self.execute(
            skill=skill,
            user_input=user_input,
            context=context,
            interactive=False,
        )

    def record_feedback(self, skill_name: str, feedback: str):
        """记录用户反馈（用于后续优化）"""
        for log in reversed(self._execution_log):
            if log.skill_name == skill_name and log.user_feedback is None:
                log.user_feedback = feedback
                if self.verbose:
                    print(f"[SKILL] 📝 记录反馈: {skill_name} → {feedback}")
                return
        if self.verbose:
            print(f"[SKILL] ⚠️ 未找到可记录反馈的执行记录: {skill_name}")

    # ==================== 内部方法 ====================

    def _extract_fields(self, skill: SkillDef, user_input: str) -> Dict[str, Any]:
        """从用户输入中提取字段（基于关键词启发式）"""
        extracted = {"user_input": user_input}

        # 收件人提取
        for prefix in ["发给", "发邮件给", "告知", "通知"]:
            if prefix in user_input:
                after = user_input.split(prefix, 1)[1].strip()
                # 取第一个空格前或"说"/"关于"前的内容
                for sep in ["说", "关于", "，", ",", " "]:
                    if sep in after:
                        extracted["recipient"] = after.split(sep, 1)[0].strip()
                        break
                if "recipient" not in extracted and after:
                    extracted["recipient"] = after.split()[0] if after.split() else after

        # 主题/话题提取
        for prefix in ["说", "关于", "告知", "通知"]:
            if prefix in user_input:
                after = user_input.split(prefix, 1)[1].strip()
                if after:
                    extracted["topic"] = after
                    break

        # 路径提取
        import re
        paths = re.findall(r'[/~][\w./\-]+', user_input)
        if paths:
            extracted["path"] = paths[0]
            extracted["files"] = paths

        # 关键词提取（搜索类）
        for prefix in ["找", "搜索", "查找", "搜"]:
            if prefix in user_input:
                after = user_input.split(prefix, 1)[1].strip()
                if after:
                    extracted["keyword"] = after.split()[0] if after.split() else after
                    break

        # 问题描述提取（诊断类）
        extracted["problem"] = user_input

        # 问题提取（文献类）
        for prefix in ["研究问题", "问题"]:
            if prefix in user_input:
                extracted["question"] = user_input.split(prefix, 1)[1].strip()

        return extracted

    def _auto_fill_fields(
        self,
        skill: SkillDef,
        missing_fields: List[str],
        user_input: str,
        current: Dict[str, Any],
    ) -> Dict[str, Any]:
        """尝试自动填充缺失字段"""
        filled = {}

        for field_name in missing_fields:
            if field_name == "path":
                # 默认使用当前目录
                filled["path"] = os.getcwd()
            elif field_name == "keyword":
                # 用用户输入作为关键词
                filled["keyword"] = user_input
            elif field_name == "problem":
                filled["problem"] = user_input
            elif field_name == "question":
                filled["question"] = "请分析这些文献的核心观点"
            # 其他字段无法自动填充

        return filled

    def _generate_clarification_question(
        self,
        skill: SkillDef,
        missing_fields: List[str],
        current: Dict[str, Any],
    ) -> str:
        """生成澄清问题"""
        field_prompts = {
            "recipient": "请告诉我收件人是谁？",
            "topic": "邮件的主题是什么？",
            "path": "请提供项目/文件路径",
            "keyword": "你想搜索什么关键词？",
            "problem": "请描述遇到的问题",
            "files": "请提供文件路径列表",
            "question": "你的研究问题是什么？",
        }

        questions = []
        for f in missing_fields:
            questions.append(field_prompts.get(f, f"请提供 {f} 的值"))

        return "我需要更多信息：" + " ".join(questions)

    def _gather_tool_context(
        self, skill: SkillDef, extracted: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用工具收集上下文"""
        adapter = get_adapter()
        results = {}

        for tool_name in skill.tools_used:
            try:
                if tool_name == "get_clipboard":
                    result = adapter.call("get_clipboard")
                    if result.success:
                        results["clipboard"] = result.output

                elif tool_name == "get_active_window":
                    result = adapter.call("get_active_window")
                    if result.success:
                        results["active_window"] = result.output

                elif tool_name == "exec_command":
                    # 根据技能类型执行不同的诊断命令
                    if skill.name == "system_diagnosis":
                        for cmd_name, cmd in [
                            ("disk", "df -h | head -10"),
                            ("memory", "free -h"),
                            ("cpu", "uptime"),
                            ("processes", "ps aux --sort=-%mem | head -10"),
                        ]:
                            r = adapter.call("exec_command", {"command": cmd})
                            if r.success:
                                results[cmd_name] = r.output
                    elif skill.name == "system_info":
                        for cmd_name, cmd in [
                            ("uname", "uname -a"),
                            ("disk", "df -h"),
                            ("memory", "free -h"),
                            ("cpu_info", "lscpu | head -15"),
                            ("uptime", "uptime"),
                            ("network", "ip addr show | head -30"),
                        ]:
                            r = adapter.call("exec_command", {"command": cmd})
                            if r.success:
                                results[cmd_name] = r.output

                elif tool_name == "list_directory":
                    path = extracted.get("path", os.getcwd())
                    result = adapter.call("list_directory", {"path": path})
                    if result.success:
                        results["directory_listing"] = result.output

                elif tool_name == "read_file":
                    files = extracted.get("files", [])
                    if files:
                        file_contents = {}
                        for fpath in files[:5]:  # 最多读 5 个文件
                            r = adapter.call("read_file", {"path": fpath, "max_lines": 200})
                            if r.success:
                                file_contents[fpath] = r.output
                        results["file_contents"] = file_contents

                elif tool_name == "search_files":
                    keyword = extracted.get("keyword", "")
                    path = extracted.get("path", ".")
                    if keyword:
                        result = adapter.call("search_files", {
                            "keyword": keyword, "path": path,
                        })
                        if result.success:
                            results["search_results"] = result.output

            except Exception as e:
                results[f"{tool_name}_error"] = str(e)

        return results

    def _format_tool_results(self, tool_results: Dict[str, Any]) -> str:
        """格式化工具结果为文本"""
        if not tool_results:
            return "（无工具上下文）"

        parts = []
        for key, value in tool_results.items():
            if isinstance(value, dict):
                formatted = json.dumps(value, ensure_ascii=False, indent=2)
                parts.append(f"[{key}]\n{formatted[:1000]}")
            else:
                parts.append(f"[{key}]\n{str(value)[:1000]}")

        return "\n\n".join(parts)

    def _format_prompt(self, skill: SkillDef, extracted: Dict[str, Any]) -> str:
        """格式化提示词模板"""
        template = skill.prompt_template

        # 用已提取的字段填充模板
        try:
            # 先尝试直接格式化
            prompt = template.format(**{k: v for k, v in extracted.items() if isinstance(v, (str, int, float))})
        except KeyError:
            # 降级：逐个替换已知字段
            prompt = template
            for key, value in extracted.items():
                placeholder = "{" + key + "}"
                if placeholder in prompt:
                    prompt = prompt.replace(placeholder, str(value))

        # 补充未在模板中出现的上下文
        context = extracted.get("context", "")
        if context and "{context}" not in template:
            prompt += f"\n\n补充上下文：\n{context}"

        # 补充原始用户输入
        user_input = extracted.get("user_input", "")
        if user_input:
            prompt += f"\n\n用户原始输入：{user_input}"

        return prompt

    def _call_llm(self, prompt: str, task_type: str = "general") -> Optional[str]:
        """调用 LLM（优先使用注入的调用器）"""
        # 使用注入的 LLM 调用器（来自 Orchestrator）
        if self._llm_caller:
            try:
                return self._llm_caller(prompt, task_type)
            except Exception as e:
                if self.verbose:
                    print(f"[SKILL] ⚠️ 注入的 LLM 调用失败: {e}")

        # 独立调用：model_router → erniebot
        # 方式 1: model_router
        try:
            from model_router import get_router
            router = get_router(verbose=self.verbose)
            resp = router.chat(prompt, task_type=task_type)
            if resp.get("success"):
                return resp["result"]
        except Exception as e:
            if self.verbose:
                print(f"[SKILL] ⚠️ model_router 调用失败: {e}")

        # 方式 2: erniebot 直接调用
        try:
            import erniebot
            from config import ERNIEBOT_ACCESS_TOKEN, DEFAULT_ACCESS_TOKEN
            token = ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN
            if token:
                erniebot.api_type = "aistudio"
                erniebot.access_token = token
                response = erniebot.ChatCompletion.create(
                    model="ernie-lite",
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.get_result() if hasattr(response, 'get_result') else str(response)
        except Exception as e:
            if self.verbose:
                print(f"[SKILL] ⚠️ erniebot 调用失败: {e}")

        return None

    def _log_execution(self, skill: SkillDef, user_input: str, result: SkillResult):
        """记录执行日志"""
        self._execution_log.append(SkillExecutionLog(
            skill_name=skill.name,
            user_input=user_input,
            timestamp=time.time(),
            result=result,
        ))

    def get_execution_history(self, skill_name: str = None) -> List[Dict]:
        """获取执行历史"""
        logs = self._execution_log
        if skill_name:
            logs = [l for l in logs if l.skill_name == skill_name]
        return [{
            "skill_name": l.skill_name,
            "user_input": l.user_input[:100],
            "success": l.result.success,
            "duration_ms": l.result.duration_ms,
            "feedback": l.user_feedback,
            "timestamp": l.timestamp,
        } for l in logs]


# ==================== 技能注册中心（保持向后兼容）====================


# ==================== 全局单例 ====================

_registry: Optional[SkillRegistry] = None
_executor: Optional[SkillExecutor] = None


def get_registry() -> SkillRegistry:
    """获取技能注册中心单例"""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


def get_executor() -> SkillExecutor:
    """获取技能执行器单例"""
    global _executor
    if _executor is None:
        _executor = SkillExecutor()
    return _executor


def find_skill(user_input: str) -> Optional[SkillDef]:
    """快捷方法：根据输入匹配技能"""
    return get_registry().find_skill(user_input)


def execute_skill(
    user_input: str,
    context: Dict[str, Any] = None,
    interactive: bool = False,
    verbose: bool = True,
) -> SkillResult:
    """
    便捷函数：自动匹配并执行技能

    Args:
        user_input: 用户输入
        context: 预置上下文
        interactive: 是否交互式
        verbose: 是否详细输出

    Returns:
        SkillResult（如果未匹配到技能，success=False 且 error 包含提示）
    """
    registry = get_registry()
    skill = registry.find_skill(user_input)

    if skill is None:
        return SkillResult(
            success=False,
            skill_name="",
            error="未匹配到任何技能",
        )

    executor = get_executor()
    executor.verbose = verbose
    return executor.execute(skill, user_input, context=context, interactive=interactive)


def list_skills_formatted() -> str:
    """格式化列出所有技能（用于 CLI 输出）"""
    registry = get_registry()
    skills = registry.list_skills()

    if not skills:
        return "暂无注册技能"

    lines = ["\n📋 可用技能列表：", "=" * 50]
    categories: Dict[str, List] = {}
    for s in skills:
        cat = s["category"]
        categories.setdefault(cat, []).append(s)

    category_icons = {
        "email": "📧",
        "system": "🩺",
        "code": "🔍",
        "search": "📚",
        "custom": "🔧",
    }

    for cat, cat_skills in categories.items():
        icon = category_icons.get(cat, "📌")
        lines.append(f"\n{icon} [{cat}]")
        for s in cat_skills:
            lines.append(f"  • {s['name']}: {s['description']}")
            lines.append(f"    触发词: {', '.join(s['trigger_keywords'][:5])}")
            if s["required_fields"]:
                lines.append(f"    必填字段: {', '.join(s['required_fields'])}")

    lines.append(f"\n共 {len(skills)} 个技能")
    return "\n".join(lines)
