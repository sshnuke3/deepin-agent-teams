"""
智能邮件助手场景
识别用户发邮件意图 → 收集上下文 → 生成邮件 → 发送
"""
import os
import sys
import re
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.system_operator import SystemOperator
from agents.information_collector import InformationCollector
from agents.content_creator import ContentCreator


class EmailAssistant:
    """
    智能邮件助手 - 场景一

    工作流程：
    1. 意图识别 → 2. 上下文收集 → 3. 邮件生成 → 4. 发送确认
    """

    def __init__(self):
        self.collector = InformationCollector()
        self.creator = ContentCreator()
        self.operator = SystemOperator()

        self.email_keywords = [
            "发邮件", "发个邮件", "写邮件", "邮件",
            "给", "发给", "email", "mail",
            "告知", "通知",
        ]

        # 已识别的邮件草稿（用于发送阶段）
        self.pending_draft: Optional[Dict] = None
        # 多轮对话状态
        self._clarification_pending: Optional[Dict] = None

    def detect_intent(self, user_input: str) -> Dict:
        """检测用户意图"""
        text_lower = user_input.lower()
        intent = {
            "is_email_intent": False,
            "action": None,
            "recipient": None,
            "topic": None,
            "confidence": 0.0
        }

        keyword_count = sum(1 for kw in self.email_keywords if kw in text_lower)
        if keyword_count > 0:
            intent["is_email_intent"] = True
            intent["confidence"] = min(keyword_count * 0.3, 0.95)

        # 提取收件人
        recipient_patterns = [
            r"给([^\s,，:：]+)发",
            r"发给([^\s,，:：]+)",
            r"to[:\s]*([^\s,，]+)",
            r"发给([^\s,，]+)的",
        ]
        for pattern in recipient_patterns:
            match = re.search(pattern, user_input)
            if match:
                intent["recipient"] = match.group(1).strip()
                break

        # 提取主题
        topic_patterns = [
            r"关于(.+)的",
            r"说(.+)的",
            r"关于(.+)",
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
        elif any(k in text_lower for k in ["回复", "回", "re"]):
            intent["action"] = "reply"

        return intent

    def collect_context(self, topic: str = None) -> Dict:
        """收集邮件上下文"""
        return self.collector.collect_context_for_email(topic)

    def generate_draft(self, context: Dict, recipient: str = None, topic: str = None) -> Dict:
        """生成邮件草稿"""
        email_draft = self.creator.generate_email(context, recipient, topic)
        return {
            "to": email_draft.to,
            "subject": email_draft.subject,
            "body": email_draft.body,
            "cc": email_draft.cc or "",
        }

    def send_email(self, draft: Dict) -> Dict:
        """
        发送邮件

        Args:
            draft: 邮件草稿 {to, subject, body, cc}

        Returns:
            发送结果
        """
        if not draft.get("to") or draft["to"] == "待定":
            return {"success": False, "error": "收件人为空，请先指定收件人"}

        if not draft.get("subject"):
            return {"success": False, "error": "邮件主题为空"}

        # 方法1: 使用 thunderbird (如果可用)
        try:
            result = self.operator.execute_command("which thunderbird", timeout=5)
            if result.success:
                # 构建 thunderbird 命令行
                import subprocess
                cmd = [
                    "thunderbird",
                    "-compose",
                    f"to={draft['to']}",
                    f"subject={draft['subject']}",
                ]
                if draft.get("cc"):
                    cmd.append(f"cc={draft['cc']}")
                if draft.get("body"):
                    # body 需要通过文件传递
                    body_file = "/tmp/deepin_agent_email_body.txt"
                    with open(body_file, "w") as f:
                        f.write(draft["body"])
                    cmd.append(f"bodyurl=file://{body_file}")

                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {"success": True, "method": "thunderbird", "message": "已打开 Thunderbird，请确认发送"}

        except Exception as e:
            pass

        # 方法2: 使用 mailx / sendmail
        try:
            import subprocess
            import tempfile

            # 构建邮件内容
            email_content = f"To: {draft['to']}\n"
            if draft.get("cc"):
                email_content += f"Cc: {draft['cc']}\n"
            email_content += f"Subject: {draft['subject']}\n\n"
            email_content += draft.get("body", "")

            # 尝试使用 mailx 发送
            result = subprocess.run(
                ["which", "mailx"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                proc = subprocess.Popen(
                    ["mailx", "-v", draft["to"]],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                stdout, stderr = proc.communicate(input=email_content, timeout=10)
                if proc.returncode == 0:
                    return {"success": True, "method": "mailx", "message": "邮件发送成功"}

        except Exception as e:
            pass

        # 方法3: 输出为文件，用户手动发送
        try:
            import tempfile
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            draft_file = f"/tmp/deepin_agent_email_draft_{timestamp}.txt"

            with open(draft_file, "w") as f:
                f.write(f"收件人: {draft['to']}\n")
                if draft.get("cc"):
                    f.write(f"抄送: {draft['cc']}\n")
                f.write(f"主题: {draft['subject']}\n")
                f.write("=" * 50 + "\n")
                f.write(draft.get("body", ""))

            return {
                "success": True,
                "method": "file",
                "file": draft_file,
                "message": f"邮件已保存到 {draft_file}，请手动发送"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def run(self, user_input: str, auto_send: bool = False) -> Dict:
        """
        执行邮件助手场景（支持多轮对话/意图澄清）

        Args:
            user_input: 用户指令
            auto_send: 是否自动发送（跳过确认）

        Returns:
            执行结果
        """
        print(f"\n📧 智能邮件助手")
        print(f"输入: {user_input}")
        print("=" * 50)

        result = {
            "success": False,
            "intent": None,
            "context": None,
            "draft": None,
            "send_result": None,
            "steps": [],
            "needs_clarification": False,
        }

        # 处理多轮对话：如果有待回答的澄清问题
        if self._clarification_pending:
            result = self._continue_clarification(user_input)
            return result

        # Step 1: 意图识别
        print("\n[Step 1] 意图识别...")
        intent = self.detect_intent(user_input)
        result["intent"] = intent
        result["steps"].append({"step": "intent_detection", "done": True})

        if not intent["is_email_intent"]:
            print("❌ 未识别到邮件意图")
            result["error"] = "Non-email intent"
            return result

        print(f"✅ 邮件意图 (置信度: {intent['confidence']:.0%})")
        print(f"   动作: {intent['action']}")
        print(f"   收件人: {intent['recipient'] or '待提取'}")
        print(f"   主题: {intent['topic'] or '待提取'}")

        # Step 1.5: 多轮意图澄清 — 信息不全时主动追问
        missing = []
        if not intent["recipient"]:
            missing.append("recipient")
        if not intent["topic"]:
            missing.append("topic")

        if missing:
            question = self._build_clarification_question(missing, intent)
            print(f"\n🤔 {question}")
            self._clarification_pending = {
                "intent": intent,
                "missing": missing,
                "original_input": user_input,
                "question": question,
            }
            result["needs_clarification"] = True
            result["question"] = question
            result["missing"] = missing
            result["success"] = True
            return result

        # Step 2: 上下文收集
        print("\n[Step 2] 上下文收集...")
        topic = intent.get("topic") or intent.get("recipient") or user_input
        context = self.collect_context(topic)
        result["context"] = context
        result["steps"].append({"step": "context_collection", "done": True})

        print(f"✅ 收集到 {len(context['sources'])} 个信息源:")
        for src in context["sources"][:3]:
            print(f"   [{src['type']}] 相关性: {src.get('relevance', 0):.0%}")
            if src["type"] == "clipboard":
                print(f"      内容: {src.get('preview', '')[:80]}...")
            elif src["type"] == "file":
                print(f"      文件: {src.get('path', '')}")

        # Step 3: 邮件生成
        print("\n[Step 3] 生成邮件...")
        try:
            draft = self.generate_draft(context, intent.get("recipient"), intent.get("topic"))
            result["draft"] = draft
            self.pending_draft = draft
            result["steps"].append({"step": "email_generation", "done": True})

            print(f"\n{'='*50}")
            print(f"📧 收件人: {draft['to']}")
            print(f"📌 主题: {draft['subject']}")
            print(f"{'='*50}")
            print(draft.get("body", "(空)"))
            print(f"{'='*50}")

            if auto_send:
                print("\n[Step 4] 自动发送...")
                send_result = self.send_email(draft)
                result["send_result"] = send_result
                result["steps"].append({"step": "send", "done": True})

                if send_result["success"]:
                    print(f"✅ {send_result.get('message', '发送成功')}")
                else:
                    print(f"❌ 发送失败: {send_result.get('error')}")

            else:
                print("\n💡 回复'发送'开始发送，或'修改'调整内容")

            result["success"] = True

        except Exception as e:
            print(f"❌ 邮件生成失败: {str(e)}")
            result["error"] = str(e)
            result["steps"].append({"step": "email_generation", "done": False, "error": str(e)})

        return result

    def _build_clarification_question(self, missing: List[str], intent: Dict) -> str:
        """生成澄清追问"""
        questions = []
        if "recipient" in missing:
            questions.append("📧 你要发给谁？（请提供收件人姓名或邮箱）")
        if "topic" in missing:
            questions.append("📌 邮件主题是什么？（比如：项目进度、会议通知）")
        if intent.get("recipient") and "topic" in missing:
            return f"你要给 {intent['recipient']} 发邮件，具体说什么内容呢？"
        return "\n".join(questions)

    def _continue_clarification(self, user_input: str) -> Dict:
        """处理用户对澄清问题的回答，继续邮件流程"""
        pending = self._clarification_pending
        self._clarification_pending = None

        intent = pending["intent"]
        missing = pending["missing"]

        # 尝试从回答中提取信息
        if "recipient" in missing:
            # 用户回答了收件人
            recipient = user_input.strip()
            # 去除可能的多余词汇
            for prefix in ["发给", "给", "是", "叫"]:
                if recipient.startswith(prefix):
                    recipient = recipient[len(prefix):].strip()
            intent["recipient"] = recipient

        if "topic" in missing:
            # 用户回答了主题
            intent["topic"] = user_input.strip()

        print(f"✅ 已补充信息:")
        print(f"   收件人: {intent.get('recipient', '未知')}")
        print(f"   主题: {intent.get('topic', '未知')}")

        # 检查是否还有缺失
        still_missing = []
        if not intent.get("recipient"):
            still_missing.append("recipient")
        if not intent.get("topic"):
            still_missing.append("topic")

        if still_missing:
            # 继续追问
            question = self._build_clarification_question(still_missing, intent)
            print(f"\n🤔 {question}")
            self._clarification_pending = {
                "intent": intent,
                "missing": still_missing,
                "original_input": pending["original_input"],
                "question": question,
            }
            return {
                "success": True,
                "needs_clarification": True,
                "question": question,
                "missing": still_missing,
            }

        # 信息齐全，继续正常流程
        print("\n[继续] 信息已齐全，开始收集上下文...")
        topic = intent.get("topic") or intent.get("recipient")
        context = self.collect_context(topic)

        try:
            draft = self.generate_draft(context, intent.get("recipient"), intent.get("topic"))
            self.pending_draft = draft

            print(f"\n{'='*50}")
            print(f"📧 收件人: {draft['to']}")
            print(f"📌 主题: {draft['subject']}")
            print(f"{'='*50}")
            print(draft.get("body", "(空)"))
            print(f"{'='*50}")
            print("\n💡 回复'发送'开始发送，或'修改'调整内容")

            return {
                "success": True,
                "draft": draft,
                "context": context,
                "intent": intent,
                "needs_clarification": False,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def handle_command(self, command: str) -> Dict:
        """
        处理用户命令

        Args:
            command: 用户回复命令 (发送/修改/取消)

        Returns:
            处理结果
        """
        cmd_lower = command.lower().strip()

        if cmd_lower in ["发送", "发", "send", "go"]:
            if not self.pending_draft:
                return {"success": False, "error": "没有待发送的邮件"}

            print("\n[发送] 开始发送邮件...")
            result = self.send_email(self.pending_draft)
            if result["success"]:
                self.pending_draft = None
                print(f"✅ {result.get('message', '发送成功')}")
            else:
                print(f"❌ {result.get('error', '发送失败')}")
            return result

        elif cmd_lower in ["修改", "edit", "change"]:
            return {
                "success": True,
                "action": "edit",
                "message": "请告诉我需要修改什么（例如：收件人、主题、正文）"
            }

        elif cmd_lower in ["取消", "cancel", "quit"]:
            self.pending_draft = None
            return {"success": True, "action": "cancel", "message": "已取消"}

        else:
            return {
                "success": False,
                "error": f"未知命令: {command}，请回复'发送'、'修改'或'取消'"
            }


def interactive_demo():
    """交互式演示"""
    print("=" * 60)
    print("📧 智能邮件助手 - 交互演示")
    print("=" * 60)
    print("输入邮件指令，如：'给张三发邮件说项目进度'")
    print("输入'退出'结束\n")

    assistant = EmailAssistant()

    while True:
        try:
            user_input = input("\n👤 你: ").strip()
            if not user_input:
                continue
            if user_input in ["退出", "exit", "quit"]:
                print("再见！👋")
                break

            # 检查是否是命令
            if assistant.pending_draft:
                result = assistant.handle_command(user_input)
                if result.get("action") == "edit":
                    print(f"📝 {result['message']}")
                    # 重新生成
                    topic = input("新的主题: ").strip() or assistant.pending_draft["subject"]
                    assistant.pending_draft["subject"] = topic
                    print(f"已修改主题为: {topic}")
                continue

            # 执行邮件助手
            assistant.run(user_input)

        except KeyboardInterrupt:
            print("\n\n再见！👋")
            break


def batch_demo():
    """批量演示"""
    assistant = EmailAssistant()

    test_cases = [
        "给张三发邮件说项目进度",
        "写封邮件通知大家明天开会",
        "帮我给李四发邮件告诉他bug已修复",
    ]

    print("=" * 60)
    print("📧 智能邮件助手 - 批量演示")
    print("=" * 60)

    for i, test_input in enumerate(test_cases, 1):
        print(f"\n\n{'#'*60}")
        print(f"# 测试 {i}: {test_input}")
        print("#" * 60)
        result = assistant.run(test_input)
        print(f"\n结果: {'✅' if result['success'] else '❌'}")

        if result.get("draft"):
            d = result["draft"]
            print(f"收件人: {d.get('to', 'N/A')}")
            print(f"主题: {d.get('subject', 'N/A')}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_demo()
    else:
        batch_demo()
