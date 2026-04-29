"""
智能文献阅读助手场景
识别文献阅读意图 → 读取文献 → 提取关键信息 → 生成综述
"""
import os
import sys
import re
import subprocess
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.system_operator import SystemOperator
from agents.information_collector import InformationCollector
from agents.content_creator import ContentCreator


class LiteratureAssistant:
    """
    智能文献阅读助手 - 场景四

    工作流程：
    1. 意图识别 → 2. 文献读取 → 3. 关键信息提取 → 4. 综述生成
    """

    def __init__(self):
        self.collector = InformationCollector()
        self.creator = ContentCreator()
        self.operator = SystemOperator()

        self.literature_keywords = [
            "文献", "论文", "综述", "摘要", "pdf",
            "papers", "literature", "review", "abstract",
            "读文献", "读论文", "文献分析", "论文分析",
            "研究问题", "研究报告", "学术",
        ]

        # 上一次分析结果
        self.last_review: Optional[Dict] = None
        self.last_question: Optional[str] = None

    def detect_intent(self, user_input: str) -> Dict:
        """检测用户意图"""
        text_lower = user_input.lower()
        intent = {
            "is_literature_intent": False,
            "action": None,
            "file_paths": [],
            "question": None,
            "confidence": 0.0,
        }

        keyword_count = sum(1 for kw in self.literature_keywords if kw in text_lower)
        if keyword_count > 0:
            intent["is_literature_intent"] = True
            intent["confidence"] = min(keyword_count * 0.3, 0.95)

        # 提取文件路径（支持多个）
        path_patterns = [
            r"[/~][\w./\-]+\.(?:pdf|txt|md|docx|doc)",
            r"(?:文件|文献|论文|路径|path)[:\s]*([^\s,，]+)",
        ]
        for pattern in path_patterns:
            matches = re.findall(pattern, user_input)
            for m in matches:
                expanded = os.path.expanduser(m.strip())
                if os.path.isfile(expanded):
                    intent["file_paths"].append(expanded)
                elif os.path.isfile(m.strip()):
                    intent["file_paths"].append(m.strip())

        # 提取研究问题
        question_patterns = [
            r"(?:关于|围绕|针对|研究问题[:\s]*)(.+?)(?:的文献|的论文|的综述|$)",
            r"(?:分析|综述|总结)(.+?)(?:方面|领域|主题|方向|$)",
            r"(?:问题[:\s]*)(.+)",
        ]
        for pattern in question_patterns:
            match = re.search(pattern, user_input)
            if match:
                intent["question"] = match.group(1).strip()
                break

        # 如果没有提取到问题，用整个输入作为问题
        if not intent["question"]:
            # 去掉路径部分，剩下的作为问题
            cleaned = user_input
            for p in intent["file_paths"]:
                cleaned = cleaned.replace(p, "")
            for kw in self.literature_keywords:
                cleaned = cleaned.replace(kw, "")
            cleaned = re.sub(r"[/~][\w./\-]+", "", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned:
                intent["question"] = cleaned

        # 判断动作
        if any(k in text_lower for k in ["综述", "总结", "overview", "summary"]):
            intent["action"] = "review"
        elif any(k in text_lower for k in ["摘要", "abstract", "提取"]):
            intent["action"] = "extract"
        else:
            intent["action"] = "analyze"

        return intent

    def read_literature(self, file_paths: List[str]) -> Dict[str, str]:
        """读取文献内容"""
        contents = {}
        for fp in file_paths:
            if not os.path.exists(fp):
                contents[fp] = f"❌ 文件不存在: {fp}"
                continue

            try:
                if fp.lower().endswith('.pdf'):
                    contents[fp] = self._extract_pdf(fp)
                elif fp.lower().endswith(('.docx', '.doc')):
                    contents[fp] = self._extract_docx(fp)
                else:
                    with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                        contents[fp] = f.read(100000)
            except Exception as e:
                contents[fp] = f"❌ 读取失败: {e}"

        return contents

    def extract_key_info(self, file_path: str, content: str, question: str) -> str:
        """从单篇文献中提取关键信息"""
        if content.startswith("❌"):
            return content

        filename = os.path.basename(file_path)
        return self.creator.extract_literature_key_info(
            filename=filename,
            content=content[:30000],
            question=question,
        )

    def generate_review(self, question: str, summaries: Dict[str, str]) -> str:
        """生成文献综述报告"""
        return self.creator.generate_literature_review(
            question=question,
            summaries=summaries,
        )

    def _extract_pdf(self, pdf_path: str) -> str:
        """提取 PDF 文本"""
        try:
            result = subprocess.run(
                ['pdftotext', pdf_path, '-'],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout[:100000]
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # 尝试用 Python 库
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                text_parts = []
                for page in pdf.pages[:50]:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                return "\n\n".join(text_parts)[:100000]
        except ImportError:
            pass
        except Exception:
            pass

        return "(PDF 文件，需安装 pdftotext 或 pdfplumber 提取)"

    def _extract_docx(self, docx_path: str) -> str:
        """提取 DOCX 文本"""
        try:
            import docx
            doc = docx.Document(docx_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)[:100000]
        except ImportError:
            pass
        except Exception:
            pass
        return "(DOCX 文件，需安装 python-docx 提取)"

    def run(self, user_input: str) -> Dict:
        """
        执行文献阅读场景

        Args:
            user_input: 用户指令（如"分析这几篇关于AI Agent的文献 /path/1.pdf /path/2.pdf"）

        Returns:
            执行结果
        """
        print(f"\n📚 智能文献阅读助手")
        print(f"输入: {user_input}")
        print("=" * 50)

        result = {
            "success": False,
            "intent": None,
            "file_paths": [],
            "question": None,
            "contents": None,
            "summaries": None,
            "review": None,
            "steps": [],
        }

        # Step 1: 意图识别
        print("\n[Step 1] 意图识别...")
        intent = self.detect_intent(user_input)
        result["intent"] = intent
        result["steps"].append({"step": "intent_detection", "done": True})

        if not intent["is_literature_intent"]:
            print("❌ 未识别到文献阅读意图")
            result["error"] = "Non-literature intent"
            return result

        file_paths = intent.get("file_paths", [])
        question = intent.get("question", "请分析这些文献的核心观点")

        if not file_paths:
            print("❌ 未找到文献文件路径，请在指令中指定 PDF/TXT 文件")
            result["error"] = "No file paths"
            return result

        result["file_paths"] = file_paths
        result["question"] = question

        print(f"✅ 文献阅读意图 (置信度: {intent['confidence']:.0%})")
        print(f"   动作: {intent['action']}")
        print(f"   文件数: {len(file_paths)}")
        print(f"   研究问题: {question}")

        # Step 2: 文献读取
        print(f"\n[Step 2] 读取 {len(file_paths)} 篇文献...")
        try:
            contents = self.read_literature(file_paths)
            result["contents"] = contents
            result["steps"].append({"step": "literature_reading", "done": True})

            for fp, content in contents.items():
                status = "✅" if not content.startswith("❌") else "❌"
                print(f"   {status} {os.path.basename(fp)}: {len(content)} 字符")
        except Exception as e:
            print(f"⚠️ 文献读取异常: {e}")
            contents = {}
            result["contents"] = {}
            result["steps"].append({"step": "literature_reading", "done": False, "error": str(e)})

        # Step 3: 关键信息提取
        print("\n[Step 3] 提取各文献关键信息...")
        summaries = {}
        try:
            for fp, content in contents.items():
                filename = os.path.basename(fp)
                print(f"   📄 {filename}...")
                key_info = self.extract_key_info(fp, content, question)
                summaries[filename] = key_info
            result["summaries"] = summaries
            result["steps"].append({"step": "key_info_extraction", "done": True})
            print(f"✅ 提取了 {len(summaries)} 篇文献的关键信息")
        except Exception as e:
            print(f"⚠️ 关键信息提取异常: {e}")
            result["summaries"] = summaries
            result["steps"].append({"step": "key_info_extraction", "done": False, "error": str(e)})

        # Step 4: 生成综述
        print("\n[Step 4] 生成文献综述报告...")
        try:
            review = self.generate_review(question, summaries)
            result["review"] = review
            result["steps"].append({"step": "review_generation", "done": True})

            self.last_review = result
            self.last_question = question

            print(f"\n{'=' * 50}")
            print(review[:2000])
            if len(review) > 2000:
                print(f"\n... (综述共 {len(review)} 字符)")
            print(f"{'=' * 50}")
            print("\n💡 回复'保存'导出为文件，或'重新分析'重新生成")
        except Exception as e:
            print(f"❌ 综述生成失败: {e}")
            result["steps"].append({"step": "review_generation", "done": False, "error": str(e)})

        result["success"] = True
        return result

    def handle_command(self, command: str) -> Dict:
        """
        处理用户命令

        Args:
            command: 用户回复命令

        Returns:
            处理结果
        """
        cmd_lower = command.lower().strip()

        if cmd_lower in ["保存", "save", "导出", "export"]:
            if not self.last_review:
                return {"success": False, "error": "没有综述结果，请先执行文献分析"}

            try:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                question_slug = re.sub(r'[^\w]', '_', self.last_question or "review")[:30]
                report_file = f"/tmp/deepin_agent_literature_{question_slug}_{timestamp}.md"

                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(f"# 文献综述报告\n\n")
                    f.write(f"**研究问题**: {self.last_question}\n\n")
                    f.write(f"**生成时间**: {datetime.now().isoformat()}\n\n")
                    f.write("---\n\n")
                    f.write(self.last_review.get("review", ""))

                print(f"✅ 综述已保存到: {report_file}")
                return {"success": True, "action": "save", "file": report_file}
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif cmd_lower in ["重新分析", "重新", "refresh", "reload"]:
            if not self.last_review or not self.last_review.get("file_paths"):
                return {"success": False, "error": "没有之前的分析记录"}

            file_paths = self.last_review["file_paths"]
            question = self.last_question or "请分析这些文献的核心观点"
            self.run(f"分析 {question} {' '.join(file_paths)}")
            return {"success": True, "action": "refresh"}

        elif cmd_lower in ["取消", "cancel", "quit"]:
            self.last_review = None
            self.last_question = None
            return {"success": True, "action": "cancel", "message": "已清除分析记录"}

        else:
            return {
                "success": False,
                "error": f"未知命令: {command}，请回复'保存'、'重新分析'或'取消'"
            }


def interactive_demo():
    """交互式演示"""
    print("=" * 60)
    print("📚 智能文献阅读助手 - 交互演示")
    print("=" * 60)
    print("输入文献分析指令，如：'分析这几篇关于AI的文献 /path/1.pdf /path/2.pdf'")
    print("输入'退出'结束\n")

    assistant = LiteratureAssistant()

    while True:
        try:
            user_input = input("\n👤 你: ").strip()
            if not user_input:
                continue
            if user_input in ["退出", "exit", "quit"]:
                print("再见！👋")
                break

            # 检查是否是命令
            if assistant.last_review:
                cmd_result = assistant.handle_command(user_input)
                if cmd_result.get("action") in ["save", "refresh", "cancel"]:
                    continue
                if cmd_result.get("error") and "未知命令" not in cmd_result.get("error", ""):
                    print(f"❌ {cmd_result['error']}")
                    continue

            # 执行文献分析
            assistant.run(user_input)

        except KeyboardInterrupt:
            print("\n\n再见！👋")
            break


def batch_demo():
    """批量演示"""
    assistant = LiteratureAssistant()

    test_cases = [
        "分析这几篇关于AI Agent的文献 /tmp/paper1.pdf /tmp/paper2.pdf",
        "综述 deepin 桌面环境的技术论文 /tmp/deepin_paper.txt",
        "读一下这篇论文 /tmp/research.pdf 研究问题：大模型如何提升代码质量",
    ]

    print("=" * 60)
    print("📚 智能文献阅读助手 - 批量演示")
    print("=" * 60)

    for i, test_input in enumerate(test_cases, 1):
        print(f"\n\n{'#' * 60}")
        print(f"# 测试 {i}: {test_input}")
        print("#" * 60)
        result = assistant.run(test_input)
        print(f"\n结果: {'✅' if result['success'] else '❌'}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_demo()
    else:
        batch_demo()
