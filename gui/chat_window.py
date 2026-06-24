"""
deepin-agent-teams 对话窗口
单输入框 + 自动意图路由（无需手动切 tab）
"""
import sys
import traceback
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QTextEdit, QPushButton, QScrollArea, QApplication,
    QGraphicsDropShadowEffect, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import (
    Qt, pyqtSignal, QThread, QTimer, QSize, QPropertyAnimation, QEasingCurve,
    QCoreApplication
)
from PyQt5.QtGui import QColor, QFont, QTextCursor, QKeyEvent

from .styles import CHAT_WINDOW_STYLE, COLORS


# 场景类型 → 显示名称映射
SCENARIO_DISPLAY = {
    "email": ("📧", "邮件助手"),
    "system_fix": ("🩺", "系统诊断"),
    "doctor": ("🩺", "系统诊断"),
    "code": ("🔍", "代码分析"),
    "literature": ("📚", "文献阅读"),
    "search": ("🔍", "信息检索"),
    "content": ("📝", "内容创作"),
    "chat": ("💬", "通用对话"),
    "file_op": ("📁", "文件操作"),
    "unknown": ("💬", "通用对话"),
}

# 场景 ID 映射（ScenarioClassifier 的类型 → 本地 scenario key）
SCENARIO_ID_MAP = {
    "email": "email",
    "system_fix": "doctor",
    "code": "code",
    "literature": "literature",
    "search": "literature",
    "content": "literature",
    "file_op": "code",
    "chat": None,
    "unknown": None,
}


class AgentWorker(QThread):
    """后台 Agent 执行线程"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, scenario, user_input):
        super().__init__()
        self.scenario = scenario
        self.user_input = user_input

    def run(self):
        try:
            self.status_update.emit("⏳ 正在思考...")
            result = self.scenario.run(self.user_input)
            if result.get("needs_clarification"):
                question = result.get("clarification_question",
                             result.get("output", result.get("draft", "请补充信息")))
                self.finished.emit(str(question))
            elif result.get("success"):
                output = result.get("output", result.get("report", "执行完成"))
                self.finished.emit(str(output))
            else:
                error_msg = result.get("error", "未知错误")
                self.error.emit(f"执行失败: {error_msg}")
        except Exception as e:
            self.error.emit(f"异常: {str(e)}\n{traceback.format_exc()}")


class LLMWorker(QThread):
    """通用 LLM 对话线程（闲聊/无场景时用）"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, model_router, user_input):
        super().__init__()
        self.model_router = model_router
        self.user_input = user_input

    def run(self):
        try:
            import erniebot
            erniebot.api_type = 'aistudio'

            import os
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv("ERNIEBOT_ACCESS_TOKEN", "")
            erniebot.access_token = token

            resp = erniebot.ChatCompletion.create(
                model='ernie-lite',
                messages=[{"role": "user", "content": self.user_input}],
            )
            self.finished.emit(resp.result)
        except Exception as e:
            self.error.emit(f"对话异常: {str(e)}")


class MessageBubble(QFrame):
    """消息气泡"""

    def __init__(self, text, is_user=True, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self._init_ui(text)

    def _init_ui(self, text):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        bubble = QFrame()
        bubble.setObjectName("userMsgBubble" if self.is_user else "agentMsgBubble")

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)

        label = QLabel(text)
        label.setObjectName("userMsgText" if self.is_user else "agentMsgText")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMaximumWidth(480)
        bubble_layout.addWidget(label)

        if self.is_user:
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            layout.addWidget(bubble)
            layout.addStretch()


class ChatInputBox(QTextEdit):
    """自定义输入框，支持 Enter 发送，兼容中文输入法"""
    submit_pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self._is_composing = False

    def inputMethodEvent(self, event):
        """跟踪输入法组合状态"""
        # 多种方式检测组合状态
        has_preedit = len(event.preeditString()) > 0
        has_commit = len(event.commitString()) > 0
        # 有预编辑文本说明正在组合
        if has_preedit:
            self._is_composing = True
        # 有提交文本说明组合完成
        elif has_commit:
            self._is_composing = False
        super().inputMethodEvent(event)

    def focusOutEvent(self, event):
        """失焦时重置组合状态"""
        self._is_composing = False
        super().focusOutEvent(event)

    def focusInEvent(self, event):
        """获焦时显式激活输入法"""
        super().focusInEvent(event)
        # FramelessWindowHint 下 fcitx 可能检测不到焦点，手动激活
        im = QApplication.inputMethod()
        if im:
            im.setFocusObject(self)

    def keyPressEvent(self, event: QKeyEvent):
        # 输入法正在组合中文时，不拦截按键
        if self._is_composing:
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self._is_composing = False
            self.submit_pressed.emit()
        else:
            super().keyPressEvent(event)


class ChatWindow(QMainWindow):
    """对话窗口 — 单输入框 + 自动意图路由"""
    closed = pyqtSignal()

    def __init__(self, scenarios: dict, classifier=None, parent=None):
        super().__init__(parent)
        self.setObjectName("chatWindow")
        self.scenarios = scenarios
        self._worker = None

        # 初始化场景分类器
        if classifier is not None:
            self.classifier = classifier
        else:
            try:
                from agents.scenario_classifier import ScenarioClassifier
                self.classifier = ScenarioClassifier()
            except ImportError:
                self.classifier = None

        self._init_window()
        self._init_ui()
        self._apply_style()

    def _init_window(self):
        """窗口属性"""
        self.setWindowTitle("deepin Agent Teams")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(520, 680)

        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

    def _init_ui(self):
        """初始化界面"""
        container = QFrame()
        container.setObjectName("chatWindow")
        container.setStyleSheet(f"""
            QFrame#chatWindow {{
                background-color: {COLORS['bg_main']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 标题栏 ----
        title_bar = self._create_title_bar()
        main_layout.addWidget(title_bar)

        # ---- 当前场景指示器 ----
        self.scene_indicator = self._create_scene_indicator()
        main_layout.addWidget(self.scene_indicator)

        # ---- 聊天消息区域 ----
        self.chat_area = self._create_chat_area()
        main_layout.addWidget(self.chat_area, 1)

        # ---- 输入区域 ----
        input_bar = self._create_input_bar()
        main_layout.addWidget(input_bar)

        # ---- 状态栏 ----
        status_bar = self._create_status_bar()
        main_layout.addWidget(status_bar)

        self.setCentralWidget(container)

    def _create_title_bar(self):
        """标题栏"""
        bar = QFrame()
        bar.setObjectName("titleBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 12, 0)

        title = QLabel("🦞 deepin Agent Teams")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        layout.addStretch()

        min_btn = QPushButton("−")
        min_btn.setObjectName("closeBtn")
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)

        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        return bar

    def _create_scene_indicator(self):
        """场景指示器（自动识别后显示）"""
        bar = QFrame()
        bar.setObjectName("sceneBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self.scene_icon_label = QLabel("💬")
        self.scene_icon_label.setStyleSheet("font-size: 16px; background: transparent;")
        layout.addWidget(self.scene_icon_label)

        self.scene_name_label = QLabel("输入需求，自动识别场景")
        self.scene_name_label.setObjectName("statusLabel")
        self.scene_name_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 13px; background: transparent;"
        )
        layout.addWidget(self.scene_name_label, 1)

        return bar

    def _create_chat_area(self):
        """聊天消息区域"""
        scroll = QScrollArea()
        scroll.setObjectName("chatArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        content.setObjectName("chatContent")
        self.chat_layout = QVBoxLayout(content)
        self.chat_layout.setContentsMargins(16, 12, 16, 12)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()

        scroll.setWidget(content)

        # 欢迎消息
        self._add_agent_message(
            "你好！我是 deepin Agent Teams 🦞\n\n"
            "直接输入你的需求，我会自动识别场景：\n"
            "• 📧 邮件：给张三发一封会议通知\n"
            "• 🩺 诊断：打印机连不上了\n"
            "• 🔍 代码：分析这个项目的代码结构\n"
            "• 📚 文献：总结这篇论文的核心观点\n"
            "• 💬 对话：你好，今天天气怎么样"
        )

        return scroll

    def _create_input_bar(self):
        """输入区域"""
        bar = QFrame()
        bar.setObjectName("inputBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.input_box = ChatInputBox()
        self.input_box.setObjectName("inputBox")
        self.input_box.setPlaceholderText("输入消息... (Enter 发送，Shift+Enter 换行)")
        self.input_box.setMinimumHeight(40)
        self.input_box.setMaximumHeight(80)
        self.input_box.submit_pressed.connect(self._on_send)
        layout.addWidget(self.input_box, 1)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        layout.addWidget(self.send_btn)

        return bar

    def _create_status_bar(self):
        """状态栏"""
        bar = QFrame()
        bar.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 2, 16, 6)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        layout.addStretch()

        return bar

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet(CHAT_WINDOW_STYLE)

    def _update_scene_indicator(self, scenario_type: str):
        """更新场景指示器"""
        icon, name = SCENARIO_DISPLAY.get(scenario_type, ("💬", "通用对话"))
        self.scene_icon_label.setText(icon)
        self.scene_name_label.setText(f"已识别：{name}")

    def _add_user_message(self, text):
        """添加用户消息"""
        bubble = MessageBubble(text, is_user=True)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def _add_agent_message(self, text):
        """添加 Agent 消息"""
        bubble = MessageBubble(text, is_user=False)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def _add_status_message(self, text):
        """添加状态提示（小字灰色）"""
        label = QLabel(text)
        label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; background: transparent;")
        label.setAlignment(Qt.AlignCenter)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, label)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """滚动到底部"""
        QTimer.singleShot(50, lambda: self.chat_area.verticalScrollBar().setValue(
            self.chat_area.verticalScrollBar().maximum()
        ))

    def _on_send(self):
        """发送消息 — 自动识别场景并路由"""
        text = self.input_box.toPlainText().strip()
        if not text:
            return

        if self._worker and self._worker.isRunning():
            return

        # 显示用户消息
        self._add_user_message(text)
        self.input_box.clear()

        # 自动识别场景
        scenario_type = "unknown"
        scenario_key = None
        if self.classifier:
            try:
                result = self.classifier.classify(text)
                scenario_type = result.scenario_type.value
                scenario_key = SCENARIO_ID_MAP.get(scenario_type)
            except Exception as e:
                print(f"[ChatWindow] classifier error: {e}")

        # 更新场景指示器
        self._update_scene_indicator(scenario_type)

        # 禁用输入
        self.send_btn.setEnabled(False)
        self.input_box.setEnabled(False)
        self.status_label.setText("⏳ Agent 正在工作...")

        # 路由到对应场景
        scenario = self.scenarios.get(scenario_key) if scenario_key else None

        if scenario:
            # 有匹配场景 → 走场景 Agent
            self._worker = AgentWorker(scenario, text)
            self._worker.finished.connect(self._on_agent_finished)
            self._worker.error.connect(self._on_agent_error)
            self._worker.status_update.connect(lambda msg: self.status_label.setText(msg))
            self._worker.start()
        else:
            # 无匹配场景 → 走通用 LLM 对话
            self._worker = LLMWorker(None, text)
            self._worker.finished.connect(self._on_agent_finished)
            self._worker.error.connect(self._on_agent_error)
            self._worker.start()

    def _on_agent_finished(self, result):
        """Agent 执行完成"""
        self._add_agent_message(result)
        self.send_btn.setEnabled(True)
        self.input_box.setEnabled(True)
        self.input_box.setFocus()
        self.status_label.setText("就绪")

    def _on_agent_error(self, error):
        """Agent 执行失败"""
        self._add_agent_message(f"❌ {error}")
        self.send_btn.setEnabled(True)
        self.input_box.setEnabled(True)
        self.input_box.setFocus()
        self.status_label.setText("就绪")

    def closeEvent(self, event):
        """关闭事件：隐藏而非退出"""
        self.hide()
        self.closed.emit()
        event.ignore()

    def keyPressEvent(self, event):
        """ESC 隐藏窗口"""
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    # ---- 感知主动推荐 ----

    def show_proactive_suggestion(self, text: str):
        """显示感知层推送的主动建议"""
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()

        self._add_perception_message(text)
        self.status_label.setText("🔍 感知触发")

        QTimer.singleShot(3000, lambda: self.status_label.setText("就绪"))

    def _add_perception_message(self, text):
        """添加感知推荐消息"""
        bubble = MessageBubble(text, is_user=False)
        for child in bubble.findChildren(QFrame):
            if child.objectName() == "agentMsgBubble":
                child.setStyleSheet(child.styleSheet() + """
                    QFrame {
                        border-left: 3px solid #4FC3F7;
                    }
                """)
                break
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def show_auto_result(self, text: str):
        """显示自动执行的结果"""
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()

        bubble = MessageBubble(text, is_user=False)
        for child in bubble.findChildren(QFrame):
            if child.objectName() == "agentMsgBubble":
                child.setStyleSheet(child.styleSheet() + """
                    QFrame {
                        border-left: 3px solid #81C784;
                    }
                """)
                break
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        self.status_label.setText("✅ 自动执行完成")
        QTimer.singleShot(3000, lambda: self.status_label.setText("就绪"))
