"""
deepin-agent-teams 系统托盘图标
"""
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, pyqtSignal

from .styles import TRAY_MENU_STYLE, COLORS


class TrayIcon(QSystemTrayIcon):
    """系统托盘图标"""

    show_window = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_icon()
        self._init_menu()
        self.activated.connect(self._on_activated)

    def _init_icon(self):
        """创建托盘图标"""
        # 绘制一个简单的龙虾图标（像素风格）
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景圆
        painter.setBrush(QColor(COLORS["primary"]))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 56, 56)

        # 文字
        font = QFont()
        font.setPointSize(28)
        painter.setFont(font)
        painter.setPen(QColor("white"))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "🦞")
        painter.end()

        self.setIcon(QIcon(pixmap))
        self.setToolTip("deepin Agent Teams")

    def _init_menu(self):
        """创建右键菜单"""
        menu = QMenu()
        menu.setStyleSheet(TRAY_MENU_STYLE)

        show_action = menu.addAction("📋 打开对话")
        show_action.triggered.connect(self.show_window.emit)

        menu.addSeparator()

        status_action = menu.addAction("🟢 系统运行中")
        status_action.setEnabled(False)

        menu.addSeparator()

        quit_action = menu.addAction("❌ 退出")
        quit_action.triggered.connect(self.quit_app.emit)

        self.setContextMenu(menu)

    def _on_activated(self, reason):
        """托盘图标被点击"""
        if reason == QSystemTrayIcon.Trigger:
            self.show_window.emit()

    def show_message_notification(self, title, message):
        """显示系统通知"""
        self.showMessage(title, message, QSystemTrayIcon.Information, 3000)
