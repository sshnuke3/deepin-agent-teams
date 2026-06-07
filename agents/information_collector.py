"""
信息收集员 Agent
从文件、邮件、日志、网络等渠道收集信息
"""
import os
import subprocess
import re
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class InfoSource:
    """信息源"""
    source_type: str
    path: str
    content: str
    relevance: float


class InformationCollector:
    """
    信息收集员 - 负责从多渠道收集信息

    能力：
    - 文件系统搜索
    - 剪贴板读取
    - 网络信息获取
    - 日志文件分析
    - 邮件内容收集
    """

    def __init__(self, config: Dict = None):
        self.name = "InformationCollector"
        self.config = config or {}
        self.capabilities = [
            "file_search",
            "clipboard_access",
            "web_fetch",
            "log_analysis",
            "email_collection",
        ]

    def search_files(self, keyword: str, path: str = None, extensions: List[str] = None) -> List[Dict]:
        """
        在文件系统中搜索关键词

        Args:
            keyword: 搜索关键词
            path: 搜索路径，默认当前目录
            extensions: 文件扩展名过滤

        Returns:
            匹配文件列表
        """
        if path is None:
            path = os.environ.get("HOME", "/root")
        if extensions is None:
            extensions = []

        results = []
        try:
            if extensions:
                ext_args = []
                for ext in extensions:
                    ext_args.extend(["-name", f"*{ext}"])
                cmd = ["find", path, "-type", "f"] + ext_args + ["-print"]
            else:
                cmd = ["find", path, "-type", "f", "-print"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            for file_path in result.stdout.split("\n")[:100]:
                if not file_path.strip():
                    continue
                try:
                    with open(file_path, "r", errors="ignore") as f:
                        content = f.read(10000)
                        if keyword.lower() in content.lower():
                            count = content.lower().count(keyword.lower())
                            results.append({
                                "path": file_path,
                                "relevance": min(count / 10, 1.0),
                                "preview": content[:300],
                                "size": os.path.getsize(file_path)
                            })
                except (IOError, OSError, UnicodeDecodeError):
                    continue

        except Exception:
            pass  # 搜索失败返回空结果

        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:20]

    def get_clipboard_content(self) -> Dict:
        """获取剪贴板内容"""
        from perception import get_clipboard_text, ClipboardMonitor

        monitor = ClipboardMonitor()
        text = monitor.get_text()
        info = monitor.get_clipboard_info()

        return {
            "has_text": info["has_text"],
            "text": text,
            "text_length": info["text_length"],
            "preview": text[:500] if text else "",
            "has_image": info["has_image"]
        }

    def get_recent_files(self, directory: str = None, days: int = 7, limit: int = 20) -> List[Dict]:
        """获取最近修改的文件"""
        if directory is None:
            directory = os.environ.get("HOME", "/root")

        results = []
        try:
            cmd = ["find", directory, "-type", "f", "-mtime", f"-{days}", "-print"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            from datetime import datetime
            files = []
            for path in result.stdout.split("\n")[:100]:
                if path.strip():
                    try:
                        stat = os.stat(path)
                        files.append({
                            "path": path,
                            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "size": stat.st_size
                        })
                    except:
                        continue

            files.sort(key=lambda x: x["mtime"], reverse=True)
            results = files[:limit]

        except Exception as e:
            pass

        return results

    def analyze_log(self, log_path: str, pattern: str = None, lines: int = 100) -> Dict:
        """分析日志文件"""
        from datetime import datetime

        result = {
            "path": log_path,
            "exists": os.path.exists(log_path),
            "lines": [],
            "errors": [],
            "warnings": []
        }

        if not result["exists"]:
            return result

        try:
            with open(log_path, "r", errors="ignore") as f:
                all_lines = f.readlines()
                result["total_lines"] = len(all_lines)
                tail_lines = all_lines[-lines:]
                result["lines"] = [l.strip() for l in tail_lines if l.strip()]

                for line in tail_lines:
                    line_lower = line.lower()
                    if any(e in line_lower for e in ["error", "exception", "failed", "fatal"]):
                        result["errors"].append(line.strip())
                    elif any(w in line_lower for w in ["warning", "warn"]):
                        result["warnings"].append(line.strip())

                if pattern:
                    try:
                        regex = re.compile(pattern, re.IGNORECASE)
                        result["matched"] = [l.strip() for l in all_lines if regex.search(l)][:50]
                    except re.error:
                        result["pattern_error"] = "Invalid regex"

        except Exception as e:
            result["error"] = str(e)

        return result

    def collect_context_for_email(self, topic: str = None) -> Dict:
        """为邮件助手收集上下文信息"""
        from datetime import datetime

        context = {
            "timestamp": datetime.now().isoformat(),
            "sources": [],
            "information": []
        }

        # 1. 剪贴板内容
        clipboard = self.get_clipboard_content()
        if clipboard["has_text"]:
            relevance = 0.8 if topic and topic in clipboard["text"].lower() else 0.5
            context["sources"].append({
                "type": "clipboard",
                "relevance": relevance,
                "preview": clipboard["preview"]
            })
            context["information"].append({
                "category": "clipboard",
                "content": clipboard["text"]
            })

        # 2. 最近相关文件
        home = os.environ.get("HOME", "/root")
        if topic:
            files = self.search_files(topic, path=home, extensions=[".txt", ".md", ".docx", ".pdf"])
            for f in files[:5]:
                context["sources"].append({
                    "type": "file",
                    "path": f["path"],
                    "relevance": f["relevance"],
                    "preview": f["preview"][:200]
                })
                context["information"].append({
                    "category": "file",
                    "path": f["path"],
                    "content": f["preview"]
                })

        # 3. 当前活动窗口
        try:
            from perception import get_active_app_context
            window_ctx = get_active_app_context()
            if window_ctx.get("available"):
                context["sources"].append({
                    "type": "window",
                    "app_type": window_ctx.get("app_type"),
                    "title": window_ctx.get("title"),
                    "relevance": 0.6
                })
        except:
            pass

        context["sources"].sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return context

    def summarize_content(self, content: str, max_length: int = 500) -> str:
        """使用 ERNIE 总结内容"""
        if len(content) <= max_length:
            return content

        prompt = f"""请简要总结以下内容，保留关键信息，不超过{max_length}字：

{content[:2000]}

摘要："""

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
            summary = response.get("result", "")
            return summary if summary else content[:max_length]
        except Exception as e:
            return content[:max_length] + "..."

    def process_task(self, task: str) -> Dict:
        """处理信息收集任务"""
        task_lower = task.lower()
        result = {"task": task, "collected": [], "summary": ""}

        # 邮件相关收集
        if any(k in task_lower for k in ["邮件", "email", "发给", "给谁"]):
            topic = task
            context = self.collect_context_for_email(topic)
            result["context"] = context
            result["collected"].append("email_context")

        # 剪贴板
        if any(k in task_lower for k in ["剪贴板", "复制", "clipboard"]):
            clipboard = self.get_clipboard_content()
            result["clipboard"] = clipboard
            result["collected"].append("clipboard")

        # 搜索文件
        if any(k in task_lower for k in ["找", "搜索", "查找", "相关"]):
            import re
            match = re.search(r"(?:找|搜索|查找)(.+?)(?:的|相关|文件|$)", task)
            if match:
                keyword = match.group(1).strip()
                files = self.search_files(keyword)
                result["files"] = files
                result["collected"].append("files")

        # 日志分析
        if any(k in task_lower for k in ["日志", "log", "错误"]):
            log_paths = [
                "/var/log/syslog",
                "/var/log/dmesg",
            ]
            for log_path in log_paths:
                if os.path.exists(log_path):
                    analysis = self.analyze_log(log_path, lines=50)
                    if analysis["errors"]:
                        result["log_errors"] = analysis["errors"][:10]
                        result["collected"].append("log")
                        break

        return result


def test():
    """测试 InformationCollector"""
    collector = InformationCollector()

    print("=== InformationCollector 测试 ===\n")

    # 测试剪贴板
    print("1. 剪贴板内容:")
    cb = collector.get_clipboard_content()
    print(f"   有文本: {cb['has_text']}")
    print(f"   预览: {cb['preview'][:100]}...")

    # 测试文件搜索
    print("\n2. 文件搜索 (python):")
    files = collector.search_files("import", extensions=[".py"])
    print(f"   找到 {len(files)} 个文件")
    if files:
        print(f"   最相关: {files[0]['path']}")


if __name__ == "__main__":
    test()
