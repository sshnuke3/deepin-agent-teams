"""
deepin-agent-teams 悬浮球
常驻桌面右下角，可拖拽，点击展开对话窗口
"""
import sys
from PyQt5.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QApplication, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import (
    Qt, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal, QTimer
)
from PyQt5.QtGui import QColor, QFont, QCursor

from .styles import FLOATING_BALL_STYLE, COLORS


class FloatingBall(QFrame):
    """悬浮球主控件"""

    # 信号：点击展开对话窗口
    clicked = pyqtSignal()
    # 信号：右键菜单
    right_clicked = pyqtSignal(QPoint)
    # 信号：感知到变化，请求展示建议
    perception_triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("floatingBall")
        self._drag_pos = QPoint()
        self._dragging = False
        self._click_threshold = 10  # 拖拽超过此距离视为拖拽而非点击

        self._init_ui()
        self._init_shadow()
        self._init_animation()

    def _init_ui(self):
        """初始化 UI"""
        # 窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool  # 不在任务栏显示
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(56, 56)

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        # 图标
        self.icon_label = QLabel("🦞")
        self.icon_label.setObjectName("ballIcon")
        self.icon_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(22)
        self.icon_label.setFont(font)
        layout.addWidget(self.icon_label)

        # 应用样式
        self.setStyleSheet(FLOATING_BALL_STYLE)

        # 初始位置：右下角
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 80, screen.height() - 200)

    def _init_shadow(self):
        """添加阴影效果"""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    def _init_animation(self):
        """初始化动画"""
        self._pos_animation = QPropertyAnimation(self, b"pos")
        self._pos_animation.setDuration(200)
        self._pos_animation.setEasingCurve(QEasingCurve.OutCubic)

    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.pos()
            self._dragging = False
            event.accept()
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(event.globalPos())
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖拽"""
        if event.buttons() & Qt.LeftButton:
            new_pos = event.globalPos() - self._drag_pos
            self.move(new_pos)
            self._dragging = True
            event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        if event.button() == Qt.LeftButton:
            if not self._dragging:
                # 点击 → 展开对话窗口
                self.clicked.emit()
            else:
                # 拖拽结束 → 吸附到屏幕边缘
                self._snap_to_edge()
            event.accept()

    def _snap_to_edge(self):
        """吸附到屏幕边缘"""
        screen = QApplication.primaryScreen().geometry()
        ball_pos = self.pos()
        center_x = ball_pos.x() + self.width() // 2

        # 决定吸附到左边还是右边
        if center_x < screen.width() // 2:
            target_x = screen.left() + 10
        else:
            target_x = screen.right() - self.width() - 10

        # Y 轴限制在屏幕范围内
        target_y = max(screen.top() + 10,
                       min(ball_pos.y(), screen.bottom() - self.height() - 10))

        # 动画吸附
        self._pos_animation.setStartValue(ball_pos)
        self._pos_animation.setEndValue(QPoint(target_x, target_y))
        self._pos_animation.start()

    def enterEvent(self, event):
        """鼠标进入 - 微微放大"""
        self.setFixedSize(60, 60)

    def leaveEvent(self, event):
        """鼠标离开 - 恢复大小"""
        self.setFixedSize(56, 56)

    def set_status(self, status: str):
        """设置状态（改变图标颜色提示）"""
        status_icons = {
            "idle": "🦞",
            "working": "⏳",
            "success": "✅",
            "error": "❌",
        }
        self.icon_label.setText(status_icons.get(status, "🦞"))

    # ---- 感知状态指示 ----

    def show_perception_hint(self, hint_type: str = "default", icon: str = "🦞"):
        """
        显示感知提示：悬浮球变色 + 闪烁动画

        hint_type: clipboard / window / system / default
        """
        color_map = {
            "clipboard": "#4FC3F7",   # 蓝色 - 剪贴板
            "window":    "#81C784",   # 绿色 - 窗口
            "system":    "#FFB74D",   # 橙色 - 系统
            "alert":     "#EF5350",   # 红色 - 告警
            "default":   COLORS.get("primary", "#5B7FFF"),
        }
        color = color_map.get(hint_type, color_map["default"])
        self.icon_label.setText(icon)

        # 更新悬浮球背景色
        self.setStyleSheet(f"""
            QFrame#floatingBall {{
                background-color: {color};
                border-radius: 28px;
                border: 2px solid rgba(255, 255, 255, 0.3);
            }}
        """)

        # 启动呼吸动画（3 秒后自动恢复）
        self._start_pulse()
        QTimer.singleShot(3000, self._reset_style)

    def _start_pulse(self):
        """呼吸灯动画"""
        if not hasattr(self, '_pulse_timer'):
            self._pulse_timer = QTimer(self)
            self._pulse_count = 0
        self._pulse_count = 0
        self._pulse_timer.timeout.connect(self._pulse_step)
        self._pulse_timer.start(400)

    def _pulse_step(self):
        """呼吸灯单步：交替大小"""
        self._pulse_count += 1
        if self._pulse_count > 6:
            self._pulse_timer.stop()
            self.setFixedSize(56, 56)
            return
        size = 62 if self._pulse_count % 2 == 0 else 54
        self.setFixedSize(size, size)

    def _reset_style(self):
        """恢复默认样式"""
        self.setStyleSheet(FLOATING_BALL_STYLE)
        self.icon_label.setText("🦞")
