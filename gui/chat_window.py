"""
deepin-agent-teams 对话窗口
场景切换 + 对话流 + 消息输入
"""
import sys
import traceback
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QTextEdit, QPushButton, QScrollArea, QApplication,
    QGraphicsDropShadowEffect, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import (
    Qt, pyqtSignal, QThread, QTimer, QSize, QPropertyAnimation, QEasingCurve
)
from PyQt5.QtGui import QColor, QFont, QTextCursor, QKeyEvent

from .styles import CHAT_WINDOW_STYLE, COLORS


class AgentWorker(QThread):
    """后台 Agent 执行线程"""
    finished = pyqtSignal(str)  # 成功：返回结果文本
    error = pyqtSignal(str)     # 失败：返回错误信息
    status_update = pyqtSignal(str)  # 状态更新

    def __init__(self, scenario, user_input):
        super().__init__()
        self.scenario = scenario
        self.user_input = user_input

    def run(self):
        try:
            self.status_update.emit("⏳ 正在思考...")
            result = self.scenario.run(self.user_input)
            if result.get("success"):
                output = result.get("output", result.get("report", "执行完成"))
                self.finished.emit(str(output))
            else:
                error_msg = result.get("error", "未知错误")
                self.error.emit(f"执行失败: {error_msg}")
        except Exception as e:
            self.error.emit(f"异常: {str(e)}\n{traceback.format_exc()}")


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
    """自定义输入框，支持 Enter 发送"""
    submit_pressed = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.submit_pressed.emit()
        else:
            super().keyPressEvent(event)


class ChatWindow(QMainWindow):
    """对话窗口"""
    closed = pyqtSignal()

    SCENES = [
        {"id": "email", "name": "📧 邮件助手", "color": COLORS["scene_email"]},
        {"id": "doctor", "name": "🩺 系统诊断", "color": COLORS["scene_doctor"]},
        {"id": "code", "name": "🔍 代码分析", "color": COLORS["scene_code"]},
        {"id": "literature", "name": "📚 文献阅读", "color": COLORS["scene_literature"]},
    ]

    def __init__(self, scenarios: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("chatWindow")
        self.scenarios = scenarios  # {"email": EmailAssistant, "doctor": SystemDoctor, ...}
        self.current_scene = "email"
        self._worker = None

        self._init_window()
        self._init_ui()
        self._apply_style()

    def _init_window(self):
        """窗口属性"""
        self.setWindowTitle("deepin Agent Teams")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(520, 680)

        # 居中显示
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

    def _init_ui(self):
        """初始化界面"""
        # 外层容器（带圆角 + 阴影）
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

        # ---- 场景选择栏 ----
        scene_bar = self._create_scene_bar()
        main_layout.addWidget(scene_bar)

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

        # 标题
        title = QLabel("🦞 deepin Agent Teams")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        layout.addStretch()

        # 最小化按钮
        min_btn = QPushButton("−")
        min_btn.setObjectName("closeBtn")
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)

        # 关闭按钮
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        return bar

    def _create_scene_bar(self):
        """场景选择栏"""
        bar = QFrame()
        bar.setObjectName("sceneBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self.scene_buttons = {}
        for scene in self.SCENES:
            btn = QPushButton(scene["name"])
            btn.setObjectName("sceneBtn")
            btn.setProperty("scene_id", scene["id"])
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, sid=scene["id"]: self._switch_scene(sid))
            layout.addWidget(btn)
            self.scene_buttons[scene["id"]] = btn

        # 高亮默认场景
        self._highlight_scene("email")

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
        self._add_agent_message("你好！我是 deepin Agent Teams 🦞\n\n请选择场景，然后输入你的需求：\n• 📧 邮件助手：自动撰写邮件\n• 🩺 系统诊断：排查系统问题\n• 🔍 代码分析：分析项目代码\n• 📚 文献阅读：提取文献要点")

        return scroll

    def _create_input_bar(self):
        """输入区域"""
        bar = QFrame()
        bar.setObjectName("inputBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # 输入框
        self.input_box = ChatInputBox()
        self.input_box.setObjectName("inputBox")
        self.input_box.setPlaceholderText("输入消息... (Enter 发送，Shift+Enter 换行)")
        self.input_box.setMinimumHeight(40)
        self.input_box.setMaximumHeight(80)
        self.input_box.submit_pressed.connect(self._on_send)
        layout.addWidget(self.input_box, 1)

        # 发送按钮
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

        self.scene_label = QLabel("📧 邮件助手")
        self.scene_label.setObjectName("statusLabel")
        layout.addWidget(self.scene_label)

        return bar

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet(CHAT_WINDOW_STYLE)

    def _switch_scene(self, scene_id):
        """切换场景"""
        self.current_scene = scene_id
        self._highlight_scene(scene_id)

        scene_info = next(s for s in self.SCENES if s["id"] == scene_id)
        self.scene_label.setText(scene_info["name"])

        scene_hints = {
            "email": "邮件助手已就绪，请描述邮件内容，如「给张三发一封项目进度汇报邮件」",
            "doctor": "系统诊断已就绪，请描述问题，如「打印机连不上了」或「系统很卡」",
            "code": "代码分析已就绪，请输入项目路径，如「分析 /home/user/project 的代码」",
            "literature": "文献阅读已就绪，请描述研究问题，如「总结这篇论文的核心观点」",
        }
        self._add_agent_message(scene_hints.get(scene_id, "场景已切换"))

    def _highlight_scene(self, scene_id):
        """高亮当前场景按钮"""
        for sid, btn in self.scene_buttons.items():
            btn.setProperty("active", sid == scene_id)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

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
        """发送消息"""
        text = self.input_box.toPlainText().strip()
        if not text:
            return

        if self._worker and self._worker.isRunning():
            return  # 上一个任务还在执行

        # 显示用户消息
        self._add_user_message(text)
        self.input_box.clear()

        # 获取当前场景的 Agent
        scenario = self.scenarios.get(self.current_scene)
        if not scenario:
            self._add_agent_message("❌ 当前场景不可用")
            return

        # 禁用输入
        self.send_btn.setEnabled(False)
        self.input_box.setEnabled(False)
        self.status_label.setText("⏳ Agent 正在工作...")

        # 后台执行
        self._worker = AgentWorker(scenario, text)
        self._worker.finished.connect(self._on_agent_finished)
        self._worker.error.connect(self._on_agent_error)
        self._worker.status_update.connect(lambda msg: self.status_label.setText(msg))
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
