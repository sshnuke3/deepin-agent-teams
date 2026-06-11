#!/usr/bin/env python3
"""
deepin-agent-teams GUI 入口
悬浮球 + 对话窗口 + 系统托盘
"""
import sys
import os

# 将项目根目录加入路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from gui.floating_ball import FloatingBall
from gui.chat_window import ChatWindow
from gui.tray_icon import TrayIcon
from gui.perception_bridge import PerceptionBridge


def load_scenarios():
    """加载所有场景"""
    from scenarios import EmailAssistant, SystemDoctor, CodeAnalysisAssistant, LiteratureAssistant
    return {
        "email": EmailAssistant(),
        "doctor": SystemDoctor(),
        "code": CodeAnalysisAssistant(),
        "literature": LiteratureAssistant(),
    }


def main():
    # 高 DPI 支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，靠托盘驻留

    # 加载场景
    scenarios = load_scenarios()

    # 创建组件
    ball = FloatingBall()
    chat_window = ChatWindow(scenarios)
    tray = TrayIcon()

    # ---- 信号连接 ----
    # 悬浮球点击 → 展开对话窗口
    def toggle_chat():
        if chat_window.isVisible():
            chat_window.hide()
        else:
            chat_window.show()
            chat_window.raise_()
            chat_window.activateWindow()

    ball.clicked.connect(toggle_chat)
    tray.show_window.connect(toggle_chat)
    tray.quit_app.connect(lambda: (chat_window.close(), app.quit()))

    # ---- 感知桥接 ----
    bridge = PerceptionBridge()

    # 剪贴板变化 → 悬浮球变色
    bridge.clipboard_changed.connect(
        lambda text: ball.show_perception_hint("clipboard", "📋")
    )

    # 窗口变化 → 悬浮球变色
    bridge.window_changed.connect(
        lambda title, cls: ball.show_perception_hint("window", "🪟")
    )

    # 系统告警 → 悬浮球变色
    bridge.system_alert.connect(
        lambda svc, desc: ball.show_perception_hint("alert", "⚠️")
    )

    # 主动建议 → 对话窗口弹出
    bridge.proactive_suggestion.connect(chat_window.show_proactive_suggestion)

    # 主动建议 → 托盘通知
    def on_perception_notify(text):
        tray.show_message_notification("deepin Agent Teams", text[:50] + "...")
    bridge.proactive_suggestion.connect(on_perception_notify)

    # 显示
    ball.show()
    tray.show()
    tray.show_message_notification(
        "deepin Agent Teams",
        "🦞 已启动！点击右下角悬浮球或托盘图标开始对话"
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
