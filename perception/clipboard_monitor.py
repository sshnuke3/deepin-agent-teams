"""
剪贴板监控模块
监听剪贴板变化，支持文本和图片
"""
import logging
import subprocess
import time
import threading
from datetime import datetime
from typing import Callable, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ClipboardMonitor:
    """剪贴板监控器"""

    def __init__(self, poll_interval: float = 0.5):
        """
        Args:
            poll_interval: 轮询间隔（秒）
        """
        self.poll_interval = poll_interval
        self._last_text = ""
        self._last_image_hash = ""
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks = []

    def get_text(self) -> str:
        """获取当前剪贴板文本内容"""
        try:
            # 优先使用 xclip (X11)
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o", "-t", "text/plain"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            # 降级：wl-paste (Wayland)
            result = subprocess.run(
                ["wl-paste", "-t", "text"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            # 再降级：pbpaste (macOS 兼容)
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return ""

    def get_image(self) -> Optional[bytes]:
        """获取当前剪贴板图片内容（PNG bytes）"""
        try:
            # X11: xclip 获取图片
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o", "-t", "image/png"],
                capture_output=True, timeout=2
            )
            if result.returncode == 0 and len(result.stdout) > 0:
                return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            # Wayland: wl-paste 获取图片
            result = subprocess.run(
                ["wl-paste", "-t", "image", "-n"],
                capture_output=True, timeout=2
            )
            if result.returncode == 0 and len(result.stdout) > 0:
                return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return None

    def save_image(self, output_path: str = None) -> Optional[str]:
        """保存剪贴板图片到文件"""
        image_bytes = self.get_image()
        if image_bytes is None:
            return None

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"/tmp/clipboard_image_{timestamp}.png"

        with open(output_path, "wb") as f:
            f.write(image_bytes)

        return output_path

    def has_changed(self) -> bool:
        """检测剪贴板是否发生变化"""
        current_text = self.get_text()
        if current_text != self._last_text:
            self._last_text = current_text
            return True
        return False

    def check_and_notify(self) -> Optional[str]:
        """
        检查剪贴板变化，如果有变化返回新内容
        Returns:
            新文本内容，或 None（无变化）
        """
        current = self.get_text()
        if current != self._last_text:
            self._last_text = current
            # 触发回调
            for callback in self._callbacks:
                try:
                    callback(current)
                except Exception as e:
                    logger.warning("Clipboard callback failed: %s", e)
            return current
        return None

    def add_callback(self, callback: Callable[[str], None]):
        """添加剪贴板变化回调"""
        self._callbacks.append(callback)

    def start_monitoring(self, callback: Callable[[str], None] = None):
        """
        开始监控剪贴板

        Args:
            callback: 变化时的回调函数
        """
        if callback:
            self.add_callback(callback)

        self._running = True
        self._last_text = self.get_text()  # 初始化

        def _monitor():
            while self._running:
                self.check_and_notify()
                time.sleep(self.poll_interval)

        self._thread = threading.Thread(target=_monitor, daemon=True)
        self._thread.start()

    def stop_monitoring(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_clipboard_info(self) -> dict:
        """获取剪贴板详细信息"""
        info = {"has_text": False, "has_image": False, "text_length": 0}

        text = self.get_text()
        if text:
            info["has_text"] = True
            info["text_length"] = len(text)
            info["text_preview"] = text[:200] + "..." if len(text) > 200 else text

        image = self.get_image()
        if image:
            info["has_image"] = True
            info["image_size"] = len(image)

        return info


def get_clipboard_text() -> str:
    """快捷函数：获取剪贴板文本"""
    monitor = ClipboardMonitor()
    return monitor.get_text()


def test():
    """测试剪贴板功能"""
    monitor = ClipboardMonitor()

    # 测试获取文本
    text = monitor.get_text()
    print(f"📋 剪贴板文本: {text[:100]}..." if len(text) > 100 else f"📋 剪贴板文本: {text or '(空)'}")

    # 测试获取图片
    image = monitor.get_image()
    print(f"🖼️  剪贴板图片: {'有' if image else '无'}")

    # 测试监控
    changes = []

    def on_change(new_text):
        changes.append(new_text)
        print(f"📝 变化检测: {new_text[:50]}...")

    print("\n监控剪贴板变化（5秒，按 Ctrl+C 退出）...")
    monitor.start_monitoring(on_change)

    try:
        time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop_monitoring()

    print(f"\n共检测 {len(changes)} 次变化")


if __name__ == "__main__":
    test()
