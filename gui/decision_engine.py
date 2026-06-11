#!/usr/bin/env python3
"""
决策引擎
根据感知信号，判断是否需要干预、以什么方式干预

核心逻辑：
- confidence > 0.8 + risk=low  → 自动执行（不问用户）
- confidence 0.5~0.8 + risk=medium → 建议，等用户确认
- risk=high → 只告警，不执行
"""
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


@dataclass
class Decision:
    """决策结果"""
    action: str              # translate / summarize / analyze / diagnose / open / ignore
    confidence: float        # 0.0 ~ 1.0
    risk_level: str          # low / medium / high
    auto_execute: bool       # 是否自动执行
    reasoning: str           # 决策理由
    context: dict = field(default_factory=dict)  # 附加上下文


class DecisionEngine:
    """
    决策引擎

    输入：感知事件（类型 + 内容）
    输出：Decision（动作 + 置信度 + 风险 + 是否自动执行）
    """

    def __init__(self, feedback_tracker=None):
        self.feedback_tracker = feedback_tracker
        # 基础置信度（可被 feedback_tracker 动态调整）
        self._base_confidence = {
            "translate_en": 0.85,
            "translate_other": 0.75,
            "summarize_long": 0.80,
            "analyze_code": 0.70,
            "open_url": 0.60,
            "diagnose_service": 0.75,
            "suggest_fix": 0.50,
        }

    def decide_clipboard(self, text: str) -> Decision:
        """剪贴板内容变化 → 决策"""
        text_stripped = text.strip()
        text_lower = text_stripped.lower()

        # 1. 英文内容 → 翻译
        ascii_count = sum(1 for c in text_stripped if ord(c) < 128)
        if ascii_count > len(text_stripped) * 0.7 and len(text_stripped) > 50:
            conf = self._get_confidence("translate_en")
            return Decision(
                action="translate",
                confidence=conf,
                risk_level="low",
                auto_execute=conf > 0.8,
                reasoning=f"检测到英文内容（{len(text_stripped)}字符），置信度{conf:.0%}",
                context={"text": text_stripped, "source_lang": "en"}
            )

        # 2. URL → 打开/摘要
        if text_lower.startswith("http://") or text_lower.startswith("https://"):
            conf = self._get_confidence("open_url")
            return Decision(
                action="open_url",
                confidence=conf,
                risk_level="medium",
                auto_execute=False,  # URL 永远不自动打开（安全考虑）
                reasoning=f"检测到URL，需要用户确认是否打开",
                context={"url": text_stripped}
            )

        # 3. 代码片段 → 分析
        code_keywords = ["def ", "class ", "import ", "function ", "var ", "const ",
                         "SELECT ", "FROM ", "WHERE ", "<div", "console.log",
                         "public static", "int main", "#include"]
        if any(kw in text_stripped for kw in code_keywords):
            conf = self._get_confidence("analyze_code")
            return Decision(
                action="analyze_code",
                confidence=conf,
                risk_level="low",
                auto_execute=conf > 0.8,
                reasoning="检测到代码片段",
                context={"code": text_stripped}
            )

        # 4. 长文本 → 总结
        if len(text_stripped) > 200:
            conf = self._get_confidence("summarize_long")
            return Decision(
                action="summarize",
                confidence=conf,
                risk_level="low",
                auto_execute=conf > 0.8,
                reasoning=f"检测到长文本（{len(text_stripped)}字符）",
                context={"text": text_stripped}
            )

        # 5. 短文本 → 忽略
        return Decision(
            action="ignore",
            confidence=0.0,
            risk_level="low",
            auto_execute=False,
            reasoning="文本过短，无需处理"
        )

    def decide_window(self, title: str, classification: str, app_class: str = "") -> Decision:
        """窗口切换 → 决策"""
        title_lower = title.lower()
        app_lower = app_class.lower()

        # 1. Python 文件 → 代码分析
        if title_lower.endswith(".py") or "python" in app_lower:
            conf = self._get_confidence("analyze_code")
            return Decision(
                action="analyze_code",
                confidence=conf,
                risk_level="low",
                auto_execute=conf > 0.8,
                reasoning=f"检测到Python代码窗口：{title}",
                context={"file": title, "language": "python"}
            )

        # 2. 其他代码文件
        code_exts = {
            ".js": "javascript", ".ts": "typescript", ".java": "java",
            ".c": "c", ".cpp": "cpp", ".go": "go", ".rs": "rust",
            ".sh": "shell", ".html": "html", ".css": "css",
        }
        for ext, lang in code_exts.items():
            if title_lower.endswith(ext):
                conf = self._get_confidence("analyze_code")
                return Decision(
                    action="analyze_code",
                    confidence=conf * 0.9,  # 非 Python 置信度稍低
                    risk_level="low",
                    auto_execute=False,
                    reasoning=f"检测到{lang}代码窗口：{title}",
                    context={"file": title, "language": lang}
                )

        # 3. 邮件客户端
        if classification == "email" or "mail" in title_lower or "邮件" in title_lower:
            conf = self._get_confidence("analyze_code") * 0.8
            return Decision(
                action="suggest_reply",
                confidence=conf,
                risk_level="low",
                auto_execute=False,
                reasoning="检测到邮件客户端",
                context={"app": title}
            )

        # 4. 文档
        doc_exts = [".doc", ".docx", ".pdf", ".md", ".txt"]
        if any(title_lower.endswith(ext) for ext in doc_exts):
            conf = self._get_confidence("summarize_long")
            return Decision(
                action="summarize",
                confidence=conf * 0.8,
                risk_level="low",
                auto_execute=False,
                reasoning=f"检测到文档窗口：{title}",
                context={"file": title}
            )

        # 5. 其他 → 忽略
        return Decision(
            action="ignore",
            confidence=0.0,
            risk_level="low",
            auto_execute=False,
            reasoning="窗口类型无需处理"
        )

    def decide_system(self, service_name: str, description: str) -> Decision:
        """系统异常 → 决策"""
        # 系统异常永远是 medium/high 风险，不自动执行修复
        critical_services = ["network", "NetworkManager", "bluetooth", "audio", "display"]
        is_critical = any(s in service_name.lower() for s in critical_services)

        if is_critical:
            return Decision(
                action="diagnose",
                confidence=0.85,
                risk_level="high",
                auto_execute=False,  # 关键服务异常，只诊断不自动修复
                reasoning=f"关键服务异常：{service_name}",
                context={"service": service_name, "description": description}
            )
        else:
            return Decision(
                action="diagnose",
                confidence=0.75,
                risk_level="medium",
                auto_execute=False,
                reasoning=f"服务异常：{service_name}",
                context={"service": service_name, "description": description}
            )

    def _get_confidence(self, action_type: str) -> float:
        """获取置信度（含反馈调整）"""
        base = self._base_confidence.get(action_type, 0.5)
        if self.feedback_tracker:
            modifier = self.feedback_tracker.get_confidence_modifier(action_type)
            return max(0.0, min(1.0, base + modifier))
        return base
