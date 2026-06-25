"""
内容创作员 Agent
生成邮件、报告、摘要等结构化内容
"""
import os
from typing import Dict, List, Optional
from dataclasses import dataclass

# Prompt 模板加载
try:
    from prompt_loader import get_loader
except ImportError:
    get_loader = None


@dataclass
class EmailDraft:
    """邮件草稿"""
    to: str
    subject: str
    body: str
    cc: str = ""
    attachments: List[str] = None


class ContentCreator:
    """
    内容创作员 - 负责生成结构化内容

    能力：
    - 邮件撰写
    - 报告生成
    - 内容摘要
    - 回复草稿
    - 格式化输出
    """

    def __init__(self, config: Dict = None) -> None:
        self.name = "ContentCreator"
        self.config = config or {}

    def generate_email(self, context: Dict, recipient: str = None, topic: str = None) -> EmailDraft:
        """
        根据收集到的上下文生成邮件

        Args:
            context: 信息收集员聚合的上下文
            recipient: 收件人
            topic: 邮件主题

        Returns:
            EmailDraft
        """
        # 提取关键信息
        info_items = []
        for info in context.get("information", []):
            if info["category"] == "clipboard":
                info_items.append(f"【剪贴板内容】\n{info['content'][:500]}")
            elif info["category"] == "file":
                info_items.append(f"【相关文档 - {info['path']}】\n{info['content'][:300]}")

        context_text = "\n\n".join(info_items) if info_items else "无额外上下文"

        # 使用 PromptLoader 加载模板
        if get_loader is not None:
            loader = get_loader()
            prompt = loader.render("content_creator/email", context_text=context_text)
        else:
            prompt = f"""你是一个专业的商务邮件助手。请根据以下信息撰写一封邮件。

## 上下文信息
{context_text}

## 要求
1. 邮件主题简洁明确
2. 正文结构清晰，分段合理
3. 语言专业得体
4. 如果上下文中有具体数据或事实，务必包含
5. 不要编造任何不存在的具体信息

请直接输出邮件内容，格式如下：
---
收件人: <邮箱地址>
主题: <邮件主题>
正文:
<邮件正文>
---"""

        try:
            import erniebot
            from config import ERNIEBOT_ACCESS_TOKEN, DEFAULT_ACCESS_TOKEN
            token = ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN
            erniebot.api_type = "aistudio"
            erniebot.access_token = token

            response = erniebot.ChatCompletion.create(
                model="ernie-lite",
                messages=[{"role": "user", "content": prompt}]
            )
            email_text = response.get("result", "")
            draft = self._parse_email_response(email_text)
            if recipient:
                draft.to = recipient
            if topic:
                draft.subject = topic
            return draft

        except Exception as e:
            return EmailDraft(
                to=recipient or "待定",
                subject=topic or "无主题",
                body=f"邮件生成失败: {str(e)}\n\n请手动撰写"
            )

    def _parse_email_response(self, text: str) -> EmailDraft:
        """解析 LLM 返回的邮件文本"""
        draft = EmailDraft(to="", subject="", body="")

        lines = text.split("\n")
        current_section = "body"
        body_lines = []

        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("收件人:") or line_stripped.startswith("To:"):
                draft.to = line.split(":", 1)[1].strip()
            elif line_stripped.startswith("主题:") or line_stripped.startswith("Subject:"):
                draft.subject = line.split(":", 1)[1].strip()
            elif line_stripped.startswith("正文:") or line_stripped.startswith("Body:"):
                current_section = "body"
            elif line_stripped.startswith("---") and draft.body:
                current_section = "done"
            else:
                if current_section == "body":
                    body_lines.append(line)

        draft.body = "\n".join(body_lines).strip()
        return draft

    def generate_report(self, title: str, sections: Dict[str, str]) -> str:
        """生成格式化报告"""
        from datetime import datetime

        report = f"# {title}\n\n"
        report += f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        report += "---\n\n"

        for section_title, content in sections.items():
            report += f"## {section_title}\n\n"
            if isinstance(content, list):
                for item in content:
                    report += f"- {item}\n"
            else:
                report += f"{content}\n"
            report += "\n"

        report += "---\n\n"
        report += "*由 deepin-agent-teams 自动生成*"

        return report

    def summarize_text(self, text: str, style: str = "简洁") -> str:
        """总结文本内容"""
        length_map = {"简洁": 100, "详细": 300, "专业": 200}
        max_len = length_map.get(style, 150)

        if len(text) <= max_len:
            return text

        prompt = f"""请将以下内容总结为不超过{max_len}字的{style}摘要：

{text[:3000]}

摘要："""

        # 尝试使用 PromptLoader
        if get_loader is not None:
            loader = get_loader()
            loaded_prompt = loader.render(
                "content_creator/summary",
                max_len=max_len,
                style=style,
                content=text[:3000],
            )
            if loaded_prompt and "不存在" not in loaded_prompt:
                prompt = loaded_prompt

        try:
            import erniebot
            from config import ERNIEBOT_ACCESS_TOKEN, DEFAULT_ACCESS_TOKEN
            token = ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN
            erniebot.api_type = "aistudio"
            erniebot.access_token = token

            response = erniebot.ChatCompletion.create(
                model="ernie-lite",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.get("result", text[:max_len])
        except Exception:
            return text[:max_len] + "..."

    def process_task(self, task: str, context: Dict = None) -> Dict:
        """处理内容创作任务"""
        task_lower = task.lower()
        result = {"task": task, "content": "", "type": "unknown"}

        # 邮件撰写
        if any(k in task_lower for k in ["邮件", "email", "写信", "发邮件"]):
            if context:
                draft = self.generate_email(context)
                result["type"] = "email"
                result["content"] = self._format_email(draft)
            else:
                result["content"] = "需要先收集邮件上下文信息"

        # 内容总结
        elif any(k in task_lower for k in ["总结", "摘要", "概括"]):
            if context and context.get("information"):
                source_text = "\n".join([
                    f"{i['category']}: {i['content'][:500]}"
                    for i in context["information"][:3]
                ])
                summary = self.summarize_text(source_text)
                result["type"] = "summary"
                result["content"] = summary
            else:
                result["content"] = "没有足够的内容可供总结"

        # 报告生成
        elif any(k in task_lower for k in ["报告", "汇报"]):
            sections = {
                "概述": "本次汇报主要内容...",
                "进展": "当前项目进展...",
                "问题": "遇到的主要问题...",
                "计划": "下一步计划..."
            }
            result["type"] = "report"
            result["content"] = self.generate_report("项目汇报", sections)

        return result

    def analyze_code(self, file_path: str, content: str = None) -> Dict:
        """分析单个代码文件"""
        result = {
            "file": file_path,
            "lines": 0,
            "functions": [],
            "classes": [],
            "imports": [],
            "complexity": "unknown",
            "summary": "",
        }
        
        if content is None:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception as e:
                result["summary"] = f"无法读取文件: {e}"
                return result
        
        lines = content.split('\n')
        result["lines"] = len(lines)
        
        # 提取 import
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                result["imports"].append(stripped[:80])
        
        # 提取函数和类
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('def '):
                func_name = stripped.split('(')[0].replace('def ', '').strip()
                result["functions"].append(func_name)
            elif stripped.startswith('class '):
                class_name = stripped.split('(')[0].split(':')[0].replace('class ', '').strip()
                result["classes"].append(class_name)
        
        # 简单复杂度评估
        if len(lines) > 500:
            result["complexity"] = "high"
        elif len(lines) > 200:
            result["complexity"] = "medium"
        else:
            result["complexity"] = "low"
        
        # 生成摘要
        parts = []
        if result["classes"]:
            parts.append(f"类: {', '.join(result['classes'][:3])}")
        if result["functions"]:
            parts.append(f"函数: {len(result['functions'])}个")
        parts.append(f"{result['lines']}行")
        result["summary"] = " | ".join(parts)
        
        return result

    def generate_code_report(self, project_name: str = None, project_path: str = None, 
                              structure: Dict = None, analyses: List[Dict] = None,
                              tree: str = None, file_count: int = 0, code_sections: str = None) -> str:
        """生成代码分析报告"""
        report = []
        
        name = project_name or os.path.basename((project_path or "").rstrip('/')) or "未知项目"
        
        report.append(f"# {name} 代码分析报告\n")
        if project_path:
            report.append(f"📁 项目路径: {project_path}\n")
        
        # 项目结构
        report.append("## 项目结构\n")
        if structure:
            report.append(f"- 文件总数: {structure.get('file_count', file_count)}")
            report.append(f"- 语言分布: {structure.get('languages', '未知')}\n")
        elif file_count:
            report.append(f"- 文件总数: {file_count}\n")
        
        # 项目树
        if tree:
            report.append("## 目录树\n")
            report.append(f"```\n{tree}\n```\n")
        
        # 核心文件分析
        if analyses:
            report.append("## 核心文件分析\n")
            for analysis in analyses:
                report.append(f"### {analysis.get('file', '未知')}\n")
                report.append(f"- 行数: {analysis.get('lines', 0)}")
                if analysis.get('classes'):
                    report.append(f"- 类: {', '.join(analysis['classes'][:5])}")
                if analysis.get('functions'):
                    report.append(f"- 函数: {', '.join(analysis['functions'][:10])}")
                report.append(f"- 复杂度: {analysis.get('complexity', '未知')}")
                report.append(f"- 摘要: {analysis.get('summary', '')}\n")
        
        # 代码片段
        if code_sections:
            report.append("## 代码片段\n")
            report.append(code_sections)
        
        return "\n".join(report)

    def _format_email(self, draft: EmailDraft) -> str:
        """格式化邮件为可读字符串"""
        email = []
        email.append(f"📧 收件人: {draft.to}")
        email.append(f"📌 主题: {draft.subject}")
        email.append(f"\n{'─' * 40}\n")
        email.append(draft.body)
        return "\n".join(email)


def test():
    """测试 ContentCreator"""
    creator = ContentCreator()

    print("=== ContentCreator 测试 ===\n")

    # 测试报告生成
    print("1. 报告生成:")
    report = creator.generate_report("周报", {
        "本周工作": ["完成用户模块", "修复登录bug"],
        "下周计划": ["完成订单模块", "性能优化"]
    })
    print(report[:300])


if __name__ == "__main__":
    test()
