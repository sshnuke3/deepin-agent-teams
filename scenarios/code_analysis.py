"""
智能代码分析助手场景
识别代码分析意图 → 收集项目信息 → 分析代码 → 生成报告
"""
import logging
import os
import sys
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.system_operator import SystemOperator
from agents.information_collector import InformationCollector
from agents.content_creator import ContentCreator


class CodeAnalysisAssistant:
    """
    智能代码分析助手 - 场景三

    工作流程：
    1. 意图识别 → 2. 项目扫描 → 3. 核心代码分析 → 4. 报告生成
    """

    def __init__(self):
        self.collector = InformationCollector()
        self.creator = ContentCreator()
        self.operator = SystemOperator()

        self.code_keywords = [
            "分析代码", "代码分析", "看看代码", "代码审查",
            "代码解读", "项目分析", "代码结构", "看看项目",
            "分析项目", "review", "code analysis", "code review",
            "生成文档", "项目文档",
        ]

        # 上一次分析结果（用于后续命令）
        self.last_analysis: Optional[Dict] = None
        self.last_project_path: Optional[str] = None

    def detect_intent(self, user_input: str) -> Dict:
        """检测用户意图"""
        text_lower = user_input.lower()
        intent = {
            "is_code_intent": False,
            "action": None,
            "project_path": None,
            "language": None,
            "confidence": 0.0,
        }

        keyword_count = sum(1 for kw in self.code_keywords if kw in text_lower)
        if keyword_count > 0:
            intent["is_code_intent"] = True
            intent["confidence"] = min(keyword_count * 0.3, 0.95)

        # 提取项目路径
        path_patterns = [
            r"[/(~][\w./\-]+",           # 绝对路径或相对路径
            r"(?:在|到|路径|path)[:\s]*(.+?)(?:\s|$)",
            r"(?:分析|看看|审查)(.+?)(?:的代码|项目|代码|$)",
            r"(?:分析代码文件)\s+(.+?)(?:\s|$)",  # 匹配 "分析代码文件 xxx.py"
        ]
        for pattern in path_patterns:
            match = re.search(pattern, user_input)
            if match:
                candidate = match.group(0).strip().rstrip("的代码项目")
                # 去掉前缀 "分析代码文件 "
                candidate = re.sub(r'^分析代码文件\s*', '', candidate).strip()
                if not candidate:
                    continue
                # 验证路径是否存在
                expanded = os.path.expanduser(candidate)
                if os.path.isdir(expanded):
                    intent["project_path"] = expanded
                    break
                elif os.path.isfile(expanded):
                    # 单文件分析：转为所在目录
                    intent["project_path"] = os.path.dirname(expanded)
                    intent["target_file"] = expanded
                    break
                elif os.path.isdir(candidate):
                    intent["project_path"] = candidate
                    break
                elif os.path.isfile(candidate):
                    intent["project_path"] = os.path.dirname(candidate)
                    intent["target_file"] = candidate
                    break

        # 未指定路径时，默认使用当前工作目录（项目自身）
        if not intent["project_path"]:
            default_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if os.path.isdir(default_path):
                intent["project_path"] = default_path

        # 提取编程语言
        lang_keywords = {
            "python": ["python", "py", "python3"],
            "javascript": ["javascript", "js", "node", "nodejs"],
            "go": ["golang", "go"],
            "java": ["java"],
            "c++": ["c++", "cpp"],
            "rust": ["rust"],
        }
        for lang, keywords in lang_keywords.items():
            if any(kw in text_lower for kw in keywords):
                intent["language"] = lang
                break

        # 判断动作
        if any(k in text_lower for k in ["审查", "review", "检查"]):
            intent["action"] = "review"
        elif any(k in text_lower for k in ["文档", "生成文档", "readme"]):
            intent["action"] = "document"
        else:
            intent["action"] = "analyze"

        return intent

    def scan_project(self, project_path: str) -> Dict:
        """扫描项目结构"""
        return self.collector.collect_context_for_code(project_path)

    def analyze_core_files(self, project_path: str, max_files: int = 5) -> List[Dict]:
        """分析核心代码文件"""
        py_files = []
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if not d.startswith(('.', '__pycache__', 'node_modules', '.git', 'venv'))]
            for f in files:
                if f.endswith(('.py', '.js', '.go', '.java', '.rs')) and not f.startswith('.'):
                    fp = os.path.join(root, f)
                    try:
                        size = os.path.getsize(fp)
                        py_files.append((fp, size))
                    except Exception as e:
                        logger.warning("Failed to stat file %s: %s", fp, e)

        py_files.sort(key=lambda x: x[1], reverse=True)
        top_files = py_files[:max_files]

        analyses = []
        for fp, size in top_files:
            rel_path = os.path.relpath(fp, project_path)
            print(f"  📄 分析: {rel_path} ({size / 1024:.1f} KB)")

            content = ""
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(8000)
            except Exception as e:
                logger.warning("Failed to read file %s: %s", fp, e)
                content = "(无法读取)"

            analysis = self.creator.analyze_code(rel_path, content)
            analyses.append({
                "file": rel_path,
                "size": size,
                "analysis": analysis,
            })

        return analyses

    def analyze_single_file(self, file_path: str) -> Dict:
        """分析单个代码文件"""
        rel_path = os.path.basename(file_path)
        size = os.path.getsize(file_path)
        print(f"  📄 分析: {rel_path} ({size / 1024:.1f} KB)")
        
        content = ""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(8000)
        except Exception as e:
            logger.warning("Failed to read file %s: %s", file_path, e)
            content = "(无法读取)"
        
        analysis = self.creator.analyze_code(rel_path, content)
        return {
            "file": rel_path,
            "size": size,
            "analysis": analysis,
        }

    def generate_report(self, project_path: str, context: Dict, analyses: List[Dict]) -> str:
        """生成项目分析报告"""
        project_name = os.path.basename(project_path.rstrip('/'))

        structure = context.get("structure", {})
        tree = structure.get("tree", "(无法获取)")
        file_count = structure.get("file_count", 0)

        code_sections = []
        for a in analyses:
            code_sections.append(f"## {a['file']}\n{a['analysis']}")

        code_text = "\n\n".join(code_sections) if code_sections else "(未找到可分析的代码文件)"

        return self.creator.generate_code_report(
            project_name=project_name,
            tree=tree,
            file_count=file_count,
            code_sections=code_text,
        )

    def run(self, user_input: str) -> Dict:
        """
        执行代码分析场景

        Args:
            user_input: 用户指令（如"分析 /path/to/project 的代码"）

        Returns:
            执行结果
        """
        print(f"\n🔍 智能代码分析助手")
        print(f"输入: {user_input}")
        print("=" * 50)

        result = {
            "success": False,
            "intent": None,
            "project_path": None,
            "context": None,
            "analyses": None,
            "report": None,
            "steps": [],
        }

        # Step 1: 意图识别
        print("\n[Step 1] 意图识别...")
        intent = self.detect_intent(user_input)
        result["intent"] = intent
        result["steps"].append({"step": "intent_detection", "done": True})

        if not intent["is_code_intent"]:
            print("❌ 未识别到代码分析意图")
            result["error"] = "Non-code intent"
            return result

        project_path = intent.get("project_path")
        if not project_path:
            print("❌ 未找到项目路径，请在指令中指定路径")
            result["error"] = "No project path"
            return result

        if not os.path.isdir(project_path):
            print(f"❌ 路径不存在或不是目录: {project_path}")
            result["error"] = f"Path not found: {project_path}"
            return result

        result["project_path"] = project_path
        target_file = intent.get("target_file")
        print(f"✅ 代码分析意图 (置信度: {intent['confidence']:.0%})")
        print(f"   动作: {intent['action']}")
        print(f"   项目: {project_path}")
        if target_file:
            print(f"   目标文件: {target_file}")
        if intent.get("language"):
            print(f"   语言: {intent['language']}")

        # Step 2: 项目扫描
        print("\n[Step 2] 扫描项目结构...")
        try:
            context = self.scan_project(project_path)
            result["context"] = context
            result["steps"].append({"step": "project_scan", "done": True})

            structure = context.get("structure", {})
            print(f"✅ 项目结构: {structure.get('file_count', 0)} 个文件")
            print(f"   语言分布: {structure.get('languages', '未知')}")
        except Exception as e:
            print(f"⚠️ 项目扫描异常: {e}")
            context = {"structure": {"tree": "", "file_count": 0}}
            result["context"] = context
            result["steps"].append({"step": "project_scan", "done": False, "error": str(e)})

        # Step 3: 核心代码分析
        print("\n[Step 3] 分析核心代码文件...")
        try:
            if target_file and os.path.isfile(target_file):
                # 分析单个文件
                analyses = [self.analyze_single_file(target_file)]
            else:
                analyses = self.analyze_core_files(project_path)
            result["analyses"] = analyses
            result["steps"].append({"step": "code_analysis", "done": True})
            print(f"✅ 分析了 {len(analyses)} 个核心文件")
        except Exception as e:
            print(f"⚠️ 代码分析异常: {e}")
            analyses = []
            result["analyses"] = []
            result["steps"].append({"step": "code_analysis", "done": False, "error": str(e)})

        # Step 4: 生成报告
        print("\n[Step 4] 生成分析报告...")
        try:
            report = self.generate_report(project_path, context, analyses)
            result["report"] = report
            result["steps"].append({"step": "report_generation", "done": True})

            self.last_analysis = result
            self.last_project_path = project_path

            print(f"\n{'=' * 50}")
            print(report[:2000])  # 预览前2000字符
            if len(report) > 2000:
                print(f"\n... (报告共 {len(report)} 字符)")
            print(f"{'=' * 50}")
            print("\n💡 回复'保存'导出为文件，或'重新分析'重新扫描")

        except Exception as e:
            print(f"❌ 报告生成失败: {e}")
            result["steps"].append({"step": "report_generation", "done": False, "error": str(e)})

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
            if not self.last_analysis:
                return {"success": False, "error": "没有分析结果，请先执行分析"}

            try:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                project_name = os.path.basename(self.last_project_path.rstrip('/'))
                report_file = f"/tmp/deepin_agent_code_report_{project_name}_{timestamp}.md"

                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(self.last_analysis.get("report", ""))

                print(f"✅ 报告已保存到: {report_file}")
                return {"success": True, "action": "save", "file": report_file}
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif cmd_lower in ["重新分析", "重新", "refresh", "reload"]:
            if not self.last_project_path:
                return {"success": False, "error": "没有之前的分析记录"}
            self.run(f"分析 {self.last_project_path} 的代码")
            return {"success": True, "action": "refresh"}

        elif cmd_lower in ["取消", "cancel", "quit"]:
            self.last_analysis = None
            self.last_project_path = None
            return {"success": True, "action": "cancel", "message": "已清除分析记录"}

        else:
            return {
                "success": False,
                "error": f"未知命令: {command}，请回复'保存'、'重新分析'或'取消'"
            }


def interactive_demo():
    """交互式演示"""
    print("=" * 60)
    print("🔍 智能代码分析助手 - 交互演示")
    print("=" * 60)
    print("输入代码分析指令，如：'分析 /path/to/project 的代码'")
    print("输入'退出'结束\n")

    assistant = CodeAnalysisAssistant()

    while True:
        try:
            user_input = input("\n👤 你: ").strip()
            if not user_input:
                continue
            if user_input in ["退出", "exit", "quit"]:
                print("再见！👋")
                break

            # 检查是否是命令
            if assistant.last_analysis:
                cmd_result = assistant.handle_command(user_input)
                if cmd_result.get("action") in ["save", "refresh", "cancel"]:
                    continue
                if cmd_result.get("error") and "未知命令" not in cmd_result.get("error", ""):
                    print(f"❌ {cmd_result['error']}")
                    continue

            # 执行代码分析
            assistant.run(user_input)

        except KeyboardInterrupt:
            print("\n\n再见！👋")
            break


def batch_demo():
    """批量演示"""
    assistant = CodeAnalysisAssistant()

    test_cases = [
        "分析 /root/.openclaw/workspace/deepin-agent-teams 的代码",
        "看看 scenarios 目录的代码结构",
        "审查 agents 目录的核心文件",
    ]

    print("=" * 60)
    print("🔍 智能代码分析助手 - 批量演示")
    print("=" * 60)

    for i, test_input in enumerate(test_cases, 1):
        print(f"\n\n{'#' * 60}")
        print(f"# 测试 {i}: {test_input}")
        print("#" * 60)
        result = assistant.run(test_input)
        print(f"\n结果: {'✅' if result['success'] else '❌'}")

        if result.get("report"):
            print(f"报告长度: {len(result['report'])} 字符")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_demo()
    else:
        batch_demo()
