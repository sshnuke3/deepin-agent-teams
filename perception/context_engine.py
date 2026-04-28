"""
环境感知与意图识别引擎
整合屏幕感知、剪贴板、窗口上下文
"""
import os
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class UserContext:
    """用户当前上下文"""
    window_title: str = ""
    window_type: str = ""
    clipboard_text: str = ""
    screen_text: str = ""
    active_app: str = ""
    timestamp: str = ""


@dataclass
class IntentResult:
    """意图识别结果"""
    intent_type: str  # email / system_fix / search / code_help / other
    confidence: float
    key_entities: Dict  # {recipient, topic, component, ...}
    reasoning: str
    trigger_context: str  # 触发意图的具体上下文


class ContextEngine:
    """
    上下文感知引擎

    整合多源感知数据，辅助意图识别
    """

    def __init__(self):
        self.last_context: Optional[UserContext] = None

        # 意图触发规则
        self.intent_rules = {
            "email": {
                "keywords": ["发邮件", "发给", "写邮件", "email", "告知", "通知"],
                "context_triggers": {
                    "mail": 0.9,  # 邮件客户端打开时
                    "clipboard_has_at": 0.3,  # 剪贴板有@符号
                }
            },
            "system_fix": {
                "keywords": ["连不上", "没声音", "坏了", "不行", "错误", "故障",
                           "can't", "not working", "error", "broken"],
                "context_triggers": {
                    "error_content": 0.5,  # 屏幕有错误信息
                }
            },
            "code_help": {
                "keywords": ["代码", "报错", "debug", "怎么写", "帮我改",
                           "error", "exception", "bug"],
                "context_triggers": {
                    "editor": 0.4,  # 编辑器打开
                    "terminal": 0.3,  # 终端打开
                }
            },
            "search": {
                "keywords": ["搜", "找", "查", "search", "find", "look up"],
                "context_triggers": {}
            }
        }

    def gather_context(self) -> UserContext:
        """收集当前所有感知数据"""
        from datetime import datetime

        ctx = UserContext()
        ctx.timestamp = datetime.now().isoformat()

        # 窗口上下文
        try:
            from perception.window_manager import get_active_window, get_window_classification
            window = get_active_window()
            if window:
                ctx.window_title = window.title
                ctx.window_type = get_window_classification(window.title, window.class_name)
                ctx.active_app = window.class_name or window.title
        except:
            pass

        # 剪贴板
        try:
            from perception.clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor()
            ctx.clipboard_text = monitor.get_text()[:500]  # 限制长度
        except:
            pass

        # 屏幕 OCR
        try:
            from perception.screen_ocr import ocr_screen, understand_screen_context
            screen_result = ocr_screen()
            if screen_result.get("success"):
                ctx.screen_text = screen_result.get("full_text", "")[:1000]
        except:
            pass

        self.last_context = ctx
        return ctx

    def recognize_intent(self, user_input: str = None, context: UserContext = None) -> IntentResult:
        """
        识别用户意图

        Args:
            user_input: 用户输入文本
            context: 上下文（None 则自动收集）

        Returns:
            IntentResult
        """
        if context is None:
            context = self.last_context or self.gather_context()

        # 基础评分
        scores = {}
        for intent_type, rules in self.intent_rules.items():
            score = 0.0

            # 关键词匹配
            if user_input:
                text_lower = user_input.lower()
                for kw in rules["keywords"]:
                    if kw.lower() in text_lower:
                        score += 0.4

            # 上下文触发
            for trigger, boost in rules.get("context_triggers", {}).items():
                if trigger == "mail" and context.window_type == "mail":
                    score += boost
                elif trigger == "editor" and context.window_type in ["editor", "ide"]:
                    score += boost
                elif trigger == "terminal" and context.window_type == "terminal":
                    score += boost
                elif trigger == "error_content":
                    error_kws = ["error", "exception", "failed", "错误", "异常"]
                    if any(kw in context.screen_text.lower() for kw in error_kws):
                        score += boost
                elif trigger == "clipboard_has_at":
                    if "@" in context.clipboard_text:
                        score += boost

            scores[intent_type] = min(score, 1.0)

        # 选择最高分
        if not scores or max(scores.values()) < 0.1:
            best_intent = "other"
            confidence = 0.1
        else:
            best_intent = max(scores.items(), key=lambda x: x[1])
            best_intent, confidence = best_intent

        # 提取实体
        entities = self._extract_entities(user_input or "", context)

        # 生成推理
        reasoning = self._generate_reasoning(best_intent, confidence, user_input, context)

        return IntentResult(
            intent_type=best_intent,
            confidence=confidence,
            key_entities=entities,
            reasoning=reasoning,
            trigger_context=self._summarize_context(context)
        )

    def _extract_entities(self, text: str, context: UserContext) -> Dict:
        """提取关键实体"""
        import re

        entities = {}

        # 邮件实体
        if any(kw in text.lower() for kw in ["邮件", "发给", "email"]):
            # 收件人
            patterns = [r"给([^\s,，]+)发", r"发给([^\s,，]+)"]
            for p in patterns:
                m = re.search(p, text)
                if m:
                    entities["recipient"] = m.group(1)
                    break

        # 系统问题实体
        system_keywords = {
            "audio": ["声音", "音频", "声卡"],
            "network": ["网络", "wifi", "网"],
            "printer": ["打印", "打印机"],
            "bluetooth": ["蓝牙"],
        }
        for comp, kws in system_keywords.items():
            if any(kw in text for kw in kws):
                entities["component"] = comp
                break

        return entities

    def _generate_reasoning(self, intent: str, confidence: float,
                           text: str, context: UserContext) -> str:
        """生成意图推理说明"""
        parts = []

        if confidence > 0.7:
            parts.append("高置信度识别")
        elif confidence > 0.4:
            parts.append("中等置信度")
        else:
            parts.append("低置信度，需要更多信息")

        if text:
            parts.append(f"用户输入包含意图关键词")

        if context.window_type and context.window_type != "other":
            parts.append(f"当前窗口为{context.window_type}类型")

        if context.clipboard_text:
            parts.append(f"剪贴板有内容（{len(context.clipboard_text)}字）")

        return "，".join(parts)

    def _summarize_context(self, context: UserContext) -> str:
        """总结上下文"""
        parts = []

        if context.window_title:
            parts.append(f"窗口: {context.window_title[:30]}")

        if context.window_type and context.window_type != "other":
            parts.append(f"类型: {context.window_type}")

        if context.clipboard_text:
            parts.append(f"剪贴板: {context.clipboard_text[:50]}...")

        if context.screen_text:
            parts.append(f"屏幕: {context.screen_text[:50]}...")

        return " | ".join(parts) if parts else "无上下文"

    def get_full_context(self) -> Dict:
        """获取完整上下文字典"""
        ctx = self.gather_context()

        return {
            "window": {
                "title": ctx.window_title,
                "type": ctx.window_type,
                "app": ctx.active_app,
            },
            "clipboard": {
                "text": ctx.clipboard_text,
                "length": len(ctx.clipboard_text),
            },
            "screen": {
                "text": ctx.screen_text[:500] if ctx.screen_text else "",
                "length": len(ctx.screen_text) if ctx.screen_text else 0,
            },
            "timestamp": ctx.timestamp,
        }


def test():
    """测试上下文引擎"""
    engine = ContextEngine()

    print("=== ContextEngine 测试 ===\n")

    # 收集上下文
    print("[1] 收集上下文...")
    ctx = engine.gather_context()
    print(f"   窗口: {ctx.window_title[:40] if ctx.window_title else '(无)'}")
    print(f"   类型: {ctx.window_type or '(无)'}")
    print(f"   剪贴板: {ctx.clipboard_text[:50] if ctx.clipboard_text else '(空)'}...")
    print(f"   屏幕OCR: {'成功' if ctx.screen_text else '无'}")

    # 意图识别
    print("\n[2] 意图识别测试...")

    test_inputs = [
        "给张三发邮件说项目进度",
        "打印机连不上了",
        "帮我查一下这个代码哪里有bug",
        "看看系统有没有问题",
    ]

    for inp in test_inputs:
        result = engine.recognize_intent(inp)
        print(f"\n   输入: {inp}")
        print(f"   → 意图: {result.intent_type} (置信度: {result.confidence:.0%})")
        print(f"   → 实体: {result.key_entities}")
        print(f"   → 推理: {result.reasoning}")


if __name__ == "__main__":
    test()
