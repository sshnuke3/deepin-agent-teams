#!/usr/bin/env python3
"""
感知桥接层
将 perception 模块的事件接入 GUI（悬浮球 + 对话窗口）
"""
import logging
import os
import sys
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

# 项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from perception.clipboard_monitor import get_clipboard_text
from perception.window_manager import get_active_window, get_window_classification
from perception.system_monitor import get_system_summary
from perception.context_engine import ContextEngine
from gui.decision_engine import DecisionEngine, Decision


class PerceptionBridge(QObject):
    """
    感知桥接器

    定时轮询各感知模块，检测变化后发射信号给 GUI
    """

    # ---- 信号 ----
    clipboard_changed = pyqtSignal(str)        # 剪贴板内容变化
    window_changed = pyqtSignal(str, str)      # (窗口标题, 应用分类)
    system_alert = pyqtSignal(str, str)        # (异常类型, 描述)
    proactive_suggestion = pyqtSignal(str, str)  # (主动推荐文本, 窗口标题/上下文)
    auto_action = pyqtSignal(object)           # 自动执行结果（Decision对象）

    def __init__(self, decision_engine=None, feedback_tracker=None, parent=None):
        super().__init__(parent)
        self.context_engine = ContextEngine()
        self.decision_engine = decision_engine or DecisionEngine(feedback_tracker)
        self.feedback_tracker = feedback_tracker
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
        except Exception as e:
            logger.warning("_check_clipboard failed: %s", e)

    def _suggest_for_clipboard(self, text: str):
        """通过决策引擎处理剪贴板内容"""
        decision = self.decision_engine.decide_clipboard(text)
        if decision.action == "ignore":
            return
        self._emit_decision(decision)

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
            classification = get_window_classification(title, app_class)
            self.window_changed.emit(title, classification)
            self._suggest_for_window(title, classification, app_class)
        except Exception as e:
            logger.warning("_check_window failed: %s", e)

    def _suggest_for_window(self, title: str, classification: str, app_class: str = ""):
        """通过决策引擎处理窗口变化"""
        decision = self.decision_engine.decide_window(title, classification, app_class)
        if decision.action == "ignore":
            return
        self._emit_decision(decision)

    def _emit_decision(self, decision):
        """根据决策结果发射对应信号"""
        # 检查是否被用户抑制
        if self.feedback_tracker and self.feedback_tracker.should_suppress(decision.action):
            return

        if decision.auto_execute:
            # 自动执行：通知 AutoExecutor
            self.auto_action.emit(decision)
        else:
            # 需要用户确认：生成建议文本
            hints = {
                "translate": "🔍 检测到英文内容，需要翻译吗？",
                "summarize": "📝 检测到长文本，需要总结要点吗？",
                "analyze_code": "💻 检测到代码，需要分析吗？",
                "open_url": "🔗 检测到链接，需要打开吗？",
                "suggest_reply": "📧 检测到邮件，需要帮忙回复吗？",
                "diagnose": f"⚠️ 检测到服务异常（{decision.context.get('service', '')}），需要诊断吗？",
            }
            hint = hints.get(decision.action, f"🔍 {decision.reasoning}")
            # 传递窗口标题作为上下文，用于确认时定位文件
            context = getattr(decision, 'context', {}).get('window_title', self._last_window_title)
            self.proactive_suggestion.emit(hint, context)

    # ---- 系统感知 ----
    def _check_system(self):
        if not self._enabled:
            return
        try:
            summary = get_system_summary()
            if not summary:
                return

            services = summary.get("services", {})
            for svc_name, svc_info in services.items():
                if isinstance(svc_info, dict):
                    status = svc_info.get("status", "")
                    if status not in ("active", "running", "loaded"):
                        if self._last_system_ok:
                            self._last_system_ok = False
                            desc = svc_info.get("description", svc_name)
                            self.system_alert.emit(svc_name, f"服务异常：{desc}")
                            # 通过决策引擎处理
                            decision = self.decision_engine.decide_system(svc_name, desc)
                            self._emit_decision(decision)
                            return

            self._last_system_ok = True
        except Exception as e:
            logger.warning("_check_system failed: %s", e)

    # ---- 感知状态查询 ----
    def get_status(self) -> dict:
        return {
            "clipboard_monitoring": self._clip_timer.isActive(),
            "window_monitoring": self._win_timer.isActive(),
            "system_monitoring": self._sys_timer.isActive(),
            "enabled": self._enabled,
        }
