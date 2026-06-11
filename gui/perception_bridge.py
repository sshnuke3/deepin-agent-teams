#!/usr/bin/env python3
"""
感知桥接层
将 perception 模块的事件接入 GUI（悬浮球 + 对话窗口）
"""
import os
import sys
import hashlib
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

# 项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from perception.clipboard_monitor import get_clipboard_text
from perception.window_manager import get_active_window, get_window_classification
from perception.system_monitor import get_system_summary
from perception.context_engine import ContextEngine


class PerceptionBridge(QObject):
    """
    感知桥接器

    定时轮询各感知模块，检测变化后发射信号给 GUI
    """

    # ---- 信号 ----
    clipboard_changed = pyqtSignal(str)        # 剪贴板内容变化
    window_changed = pyqtSignal(str, str)      # (窗口标题, 应用分类)
    system_alert = pyqtSignal(str, str)        # (异常类型, 描述)
    proactive_suggestion = pyqtSignal(str)     # 主动推荐文本

    def __init__(self, parent=None):
        super().__init__(parent)
        self.context_engine = ContextEngine()
        self._last_clipboard_hash = ""
        self._last_window_title = ""
        self._last_system_ok = True
        self._enabled = True

        # 剪贴板轮询：每 2 秒
        self._clip_timer = QTimer(self)
        self._clip_timer.timeout.connect(self._check_clipboard)
        self._clip_timer.start(2000)

        # 窗口轮询：每 3 秒
        self._win_timer = QTimer(self)
        self._win_timer.timeout.connect(self._check_window)
        self._win_timer.start(3000)

        # 系统监控轮询：每 10 秒
        self._sys_timer = QTimer(self)
        self._sys_timer.timeout.connect(self._check_system)
        self._sys_timer.start(10000)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    # ---- 剪贴板感知 ----
    def _check_clipboard(self):
        if not self._enabled:
            return
        try:
            text = get_clipboard_text()
            if not text or len(text.strip()) < 10:
                return
            h = hashlib.md5(text.encode()).hexdigest()
            if h != self._last_clipboard_hash:
                self._last_clipboard_hash = h
                self.clipboard_changed.emit(text)
                self._suggest_for_clipboard(text)
        except Exception:
            pass

    def _suggest_for_clipboard(self, text: str):
        """根据剪贴板内容生成主动建议"""
        text_lower = text.lower().strip()

        # 英文内容 → 翻译/总结
        ascii_count = sum(1 for c in text if ord(c) < 128)
        if ascii_count > len(text) * 0.7 and len(text) > 50:
            self.proactive_suggestion.emit(
                "🔍 检测到您复制了一段英文内容，需要翻译还是总结？"
            )
            return

        # URL → 打开/下载/摘要
        if text_lower.startswith("http://") or text_lower.startswith("https://"):
            self.proactive_suggestion.emit(
                "🔗 检测到您复制了一个链接，需要打开还是下载？"
            )
            return

        # 代码片段 → 分析
        code_keywords = ["def ", "class ", "import ", "function ", "var ", "const ",
                         "SELECT ", "FROM ", "WHERE ", "<div", "console.log"]
        if any(kw in text for kw in code_keywords):
            self.proactive_suggestion.emit(
                "💻 检测到您复制了代码片段，需要分析还是优化？"
            )
            return

        # 长文本 → 总结
        if len(text) > 200:
            self.proactive_suggestion.emit(
                "📝 检测到您复制了一段较长的文本，需要总结要点吗？"
            )

    # ---- 窗口感知 ----
    def _check_window(self):
        if not self._enabled:
            return
        try:
            win = get_active_window()
            title = win.get("title", "") if isinstance(win, dict) else getattr(win, "title", "")
            if not title or title == self._last_window_title:
                return
            self._last_window_title = title
            app_class = win.get("app_class", "") if isinstance(win, dict) else getattr(win, "app_class", "")
            classification = get_window_classification(title)
            self.window_changed.emit(title, classification)
            self._suggest_for_window(title, classification, app_class)
        except Exception:
            pass

    def _suggest_for_window(self, title: str, classification: str, app_class: str = ""):
        """根据当前窗口生成主动建议"""
        title_lower = title.lower()
        app_lower = app_class.lower()

        # Python 文件
        if title_lower.endswith(".py") or "python" in app_lower:
            self.proactive_suggestion.emit(
                f"🐍 检测到您正在查看 Python 代码，需要代码分析还是优化建议？"
            )
            return

        # 其他代码文件
        code_exts = [".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".sh", ".html", ".css"]
        if any(title_lower.endswith(ext) for ext in code_exts):
            self.proactive_suggestion.emit(
                f"💻 检测到您正在查看代码文件，需要分析还是优化建议？"
            )
            return

        # 邮件客户端
        if classification == "email" or "mail" in title_lower or "邮件" in title_lower:
            self.proactive_suggestion.emit(
                "📧 检测到您正在处理邮件，需要帮忙起草回复吗？"
            )
            return

        # 终端
        if classification == "terminal" or "terminal" in app_lower:
            # 不要太频繁打扰终端用户
            pass

        # 文档
        doc_exts = [".doc", ".docx", ".pdf", ".md", ".txt"]
        if any(title_lower.endswith(ext) for ext in doc_exts):
            self.proactive_suggestion.emit(
                "📄 检测到您正在阅读文档，需要总结要点吗？"
            )

    # ---- 系统感知 ----
    def _check_system(self):
        if not self._enabled:
            return
        try:
            summary = get_system_summary()
            if not summary:
                return

            # 检查关键服务
            services = summary.get("services", {})
            for svc_name, svc_info in services.items():
                if isinstance(svc_info, dict):
                    status = svc_info.get("status", "")
                    if status not in ("active", "running", "loaded"):
                        if self._last_system_ok:
                            self._last_system_ok = False
                            desc = svc_info.get("description", svc_name)
                            self.system_alert.emit(svc_name, f"服务异常：{desc}")
                            self.proactive_suggestion.emit(
                                f"⚠️ 检测到系统服务异常（{svc_name}），需要自动诊断吗？"
                            )
                            return

            self._last_system_ok = True
        except Exception:
            pass

    # ---- 感知状态查询 ----
    def get_status(self) -> dict:
        return {
            "clipboard_monitoring": self._clip_timer.isActive(),
            "window_monitoring": self._win_timer.isActive(),
            "system_monitoring": self._sys_timer.isActive(),
            "enabled": self._enabled,
        }
