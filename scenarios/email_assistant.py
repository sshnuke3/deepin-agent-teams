"""
智能邮件助手场景
识别用户发邮件意图 → 收集上下文 → 生成邮件
"""
import os
import sys
from typing import Dict, List, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.system_operator import SystemOperator
from agents.information_collector import InformationCollector
from agents.content_creator import ContentCreator


class EmailAssistant:
    """
    智能邮件助手 - 场景一

    工作流程：
    1. 意图识别（Lead Agent）
    2. 信息收集（InformationCollector）
    3. 邮件生成（ContentCreator）
    4. 发送确认（SystemOperator）
    """

    def __init__(self):
        self.collector = InformationCollector()
        self.creator = ContentCreator()
        self.operator = SystemOperator()

        # 邮件相关的意图关键词
        self.email_keywords = [
            "发邮件", "发个邮件", "写邮件", "邮件",
            "给", "发给", "email", "mail",
            "告知", "通知", "回复",
        ]

    def detect_intent(self, user_input: str) -> Dict:
        """
        检测用户意图

        Args:
            user_input: 用户输入

        Returns:
            意图分析结果
        """
        text_lower = user_input.lower()
        intent = {
            "is_email_intent": False,
            "action": None,
            "recipient": None,
            "topic": None,
            "confidence": 0.0
        }

        # 检查是否包含邮件关键词
        keyword_count = sum(1 for kw in self.email_keywords if kw in text_lower)
        if keyword_count > 0:
            intent["is_email_intent"] = True
            intent["confidence"] = min(keyword_count * 0.3, 0.95)

        # 提取收件人
        import re
        recipient_patterns = [
            r"给([^\s,，]+)发",
            r"发给([^\s,，]+)",
            r"to[:\s]*([^\s,，]+)",
        ]
        for pattern in recipient_patterns:
            match = re.search(pattern, user_input)
            if match:
                intent["recipient"] = match.group(1)
                break

        # 提取主题
        topic_patterns = [
            r"关于(.+)的",
            r"说(.+)的",
            r"主题[:\s]*(.+)",
        ]
        for pattern in topic_patterns:
            match = re.search(pattern, user_input)
            if match:
                intent["topic"] = match.group(1).strip()
                break

        # 判断动作
        if any(k in text_lower for k in ["发", "写", "给"]):
            intent["action"] = "compose"
        elif any(k in text_lower for k in ["回复", "回"]):
            intent["action"] = "reply"

        return intent

    def run(self, user_input: str) -> Dict:
        """
        执行邮件助手场景

        Args:
            user_input: 用户指令，如 "给张三发邮件说项目进度"

        Returns:
            执行结果
        """
        print(f"\n📧 智能邮件助手启动")
        print(f"用户输入: {user_input}")
        print("=" * 50)

        result = {
            "success": False,
            "intent": None,
            "context": None,
            "email_draft": None,
            "steps": []
        }

        # Step 1: 意图识别
        print("\n[Step 1] 意图识别...")
        intent = self.detect_intent(user_input)
        result["intent"] = intent
        result["steps"].append({"step": "intent_detection", "done": True})

        if not intent["is_email_intent"]:
            print("❌ 未识别到邮件意图")
            result["error"] = "Non-email intent"
            return result

        print(f"✅ 识别为邮件意图 (置信度: {intent['confidence']:.0%})")
        print(f"   动作: {intent['action']}")
        print(f"   收件人: {intent['recipient'] or '待提取'}")
        print(f"   主题: {intent['topic'] or '待提取'}")

        # Step 2: 上下文收集
        print("\n[Step 2] 收集上下文...")
        topic = intent.get("topic") or intent.get("recipient") or user_input
        context = self.collector.collect_context_for_email(topic)
        result["context"] = context
        result["steps"].append({"step": "context_collection", "done": True})

        print(f"✅ 收集到 {len(context['sources'])} 个信息源:")
        for src in context["sources"][:3]:
            print(f"   - [{src['type']}] 相关性: {src.get('relevance', 0):.0%}")

        # Step 3: 邮件生成
        print("\n[Step 3] 生成邮件...")
        try:
            email_draft = self.creator.generate_email(
                context=context,
                recipient=intent.get("recipient"),
                topic=intent.get("topic")
            )
            result["email_draft"] = {
                "to": email_draft.to,
                "subject": email_draft.subject,
                "body": email_draft.body
            }
            result["steps"].append({"step": "email_generation", "done": True})

            print(f"✅ 邮件已生成:")
            print(f"\n{self._format_email_display(email_draft)}")

            result["success"] = True

        except Exception as e:
            print(f"❌ 邮件生成失败: {str(e)}")
            result["error"] = str(e)
            result["steps"].append({"step": "email_generation", "done": False, "error": str(e)})

        return result

    def _format_email_display(self, draft) -> str:
        """格式化邮件显示"""
        lines = [
            "─" * 50,
            f"📧 收件人: {draft.to or '待定'}",
            f"📌 主题: {draft.subject or '无主题'}",
            "─" * 50,
            draft.body or '(空)',
            "─" * 50,
            "💡 提示: 请确认邮件内容后，回复'发送'我将调用邮件客户端"
        ]
        return "\n".join(lines)


def demo():
    """演示邮件助手"""
    assistant = EmailAssistant()

    # 测试用例
    test_cases = [
        "给张三发邮件说项目进度",
        "写封邮件通知大家明天开会",
        "帮我给李四发个邮件告诉他bug已修复",
    ]

    print("=" * 60)
    print("🧪 智能邮件助手 - 场景演示")
    print("=" * 60)

    for i, test_input in enumerate(test_cases, 1):
        print(f"\n\n{'#' * 60}")
        print(f"# 测试 {i}: {test_input}")
        print("#" * 60)
        result = assistant.run(test_input)
        print(f"\n结果: {'✅ 成功' if result['success'] else '❌ 失败'}")


if __name__ == "__main__":
    demo()
