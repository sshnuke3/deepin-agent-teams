"""
窗口管理器模块
获取当前活动窗口、窗口列表、窗口属性
"""
import subprocess
import re
import os
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WindowInfo:
    """窗口信息"""
    id: str
    title: str
    class_name: str
    pid: int
    is_focused: bool


def is_wayland() -> bool:
    """检测是否使用 Wayland"""
    return os.environ.get("XDG_SESSION_TYPE", "") == "wayland"


def get_active_window() -> Optional[WindowInfo]:
    """
    获取当前活动窗口

    Returns:
        WindowInfo 或 None
    """
    if is_wayland():
        return _get_active_window_wayland()
    else:
        return _get_active_window_x11()


def _get_active_window_x11() -> Optional[WindowInfo]:
    """X11: 获取活动窗口"""
    try:
        # 使用 xprop 获取当前焦点窗口
        output = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            capture_output=True, text=True, check=True
        ).stdout

        # 解析窗口 ID
        match = re.search(r"window id # (0x[0-9a-f]+)", output)
        if not match:
            return None

        window_id = match.group(1)

        # 获取窗口属性
        props = subprocess.run(
            ["xprop", "-id", window_id, "WM_NAME", "WM_CLASS", "_NET_WM_PID"],
            capture_output=True, text=True, check=True
        ).stdout

        title = ""
        class_name = ""
        pid = 0

        for line in props.split("\n"):
            if "WM_NAME" in line:
                match = re.search(r'"([^"]*)"', line)
                if match:
                    title = match.group(1)
            elif "WM_CLASS" in line:
                match = re.search(r'"([^"]*)"', line)
                if match:
                    class_name = match.group(1)
            elif "_NET_WM_PID" in line:
                match = re.search(r"= (\d+)", line)
                if match:
                    pid = int(match.group(1))

        return WindowInfo(
            id=window_id,
            title=title,
            class_name=class_name,
            pid=pid,
            is_focused=True
        )

    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _get_active_window_wayland() -> Optional[WindowInfo]:
    """Wayland: 获取活动窗口"""
    try:
        # swaymsg 获取焦点窗口
        output = subprocess.run(
            ["swaymsg", "-t", "get_focused_window"],
            capture_output=True, text=True, check=True
        ).stdout

        import json
        data = json.loads(output)

        if "id" in data:
            return WindowInfo(
                id=str(data.get("id", "")),
                title=data.get("name", ""),
                class_name=data.get("app_id", ""),
                pid=data.get("pid", 0),
                is_focused=True
            )

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        pass

    # 降级：使用 wmctrl
    try:
        output = subprocess.run(
            ["wmctrl", "-a"],
            capture_output=True, text=True
        )
        # 解析输出
        match = re.search(r"0x([0-9a-f]+).*\s+(.+)$", output.stdout)
        if match:
            return WindowInfo(
                id=f"0x{match.group(1)}",
                title=match.group(2).strip(),
                class_name="",
                pid=0,
                is_focused=True
            )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return None


def get_window_list() -> List[WindowInfo]:
    """
    获取所有窗口列表

    Returns:
        窗口信息列表
    """
    if is_wayland():
        return _get_window_list_wayland()
    else:
        return _get_window_list_x11()


def _get_window_list_x11() -> List[WindowInfo]:
    """X11: 获取窗口列表"""
    windows = []

    try:
        # wmctrl -l 获取窗口列表
        output = subprocess.run(
            ["wmctrl", "-l"],
            capture_output=True, text=True, check=True
        ).stdout

        for line in output.split("\n"):
            if not line.strip():
                continue

            # 解析: window_id class_name host title
            parts = line.split(None, 3)
            if len(parts) >= 4:
                windows.append(WindowInfo(
                    id=parts[0],
                    title=parts[3],
                    class_name=parts[1],
                    pid=0,
                    is_focused=False
                ))

    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return windows


def _get_window_list_wayland() -> List[WindowInfo]:
    """Wayland: 获取窗口列表"""
    windows = []

    try:
        output = subprocess.run(
            ["swaymsg", "-t", "get_tree"],
            capture_output=True, text=True, check=True
        )

        import json
        data = json.loads(output.stdout)

        def extract_windows(node, windows_list):
            if node.get("type") == "window":
                windows_list.append(WindowInfo(
                    id=str(node.get("id", "")),
                    title=node.get("name", ""),
                    class_name=node.get("app_id", ""),
                    pid=node.get("pid", 0),
                    is_focused=node.get("focused", False)
                ))
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                extract_windows(child, windows_list)

        extract_windows(data, windows)

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        pass

    return windows


def get_window_classification(title: str, class_name: str) -> str:
    """
    根据窗口信息分类应用类型

    Returns:
        应用类型: browser, editor, terminal, mail, file_manager, etc.
    """
    title_lower = (title + class_name).lower()

    classifications = {
        "browser": ["firefox", "chrome", "chromium", "brave", "edge", "opera", "browser"],
        "terminal": ["terminal", "konsole", "gnome-terminal", "xterm", "alacritty", " kitty"],
        "editor": ["code", "vim", "emacs", "sublime", "atom", "gedit", "kate", "editor"],
        "file_manager": ["dde-file-manager", "nautilus", "thunar", "pcmanfm", "dolphin", "files"],
        "mail": ["thunderbird", "evolution", "geary", "mail", "outlook"],
        "document": ["libreoffice", "wps", "document", "pdf", "okular", "evince"],
        "chat": ["wechat", "dingtalk", " qq", "tencent", "feishu", "lark", "slack", "discord"],
        "music": ["music", "spotify", "player"],
        "video": ["video", "vlc", "mpv", " totem"],
        "settings": ["settings", "control", "system", "preference", "dde-control-center"],
        "ide": ["idea", "pycharm", "webstorm", "android studio", "clion"],
    }

    for app_type, keywords in classifications.items():
        for keyword in keywords:
            if keyword in title_lower:
                return app_type

    return "other"


def get_active_app_context() -> dict:
    """
    获取当前应用上下文

    Returns:
        上下文信息字典
    """
    window = get_active_window()

    if window is None:
        return {
            "available": False,
            "error": "无法获取活动窗口"
        }

    app_type = get_window_classification(window.title, window.class_name)

    return {
        "available": True,
        "window_id": window.id,
        "title": window.title,
        "class_name": window.class_name,
        "app_type": app_type,
        "pid": window.pid,
        "timestamp": datetime.now().isoformat(),
    }


def focus_window(window_id: str) -> bool:
    """聚焦指定窗口"""
    try:
        subprocess.run(["wmctrl", "-i", "-a", window_id], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def minimize_window(window_id: str) -> bool:
    """最小化指定窗口"""
    try:
        subprocess.run(["xdotool", "windowminimize", window_id], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def test():
    """测试窗口管理功能"""
    print(f"会话类型: {'Wayland' if is_wayland() else 'X11'}")

    # 测试获取活动窗口
    window = get_active_window()
    if window:
        print(f"\n当前活动窗口:")
        print(f"  ID: {window.id}")
        print(f"  标题: {window.title}")
        print(f"  类名: {window.class_name}")
        print(f"  类型: {get_window_classification(window.title, window.class_name)}")
    else:
        print("\n❌ 无法获取活动窗口")

    # 测试获取窗口列表
    windows = get_window_list()
    print(f"\n窗口列表 ({len(windows)} 个):")
    for w in windows[:5]:
        print(f"  [{w.class_name}] {w.title}")


if __name__ == "__main__":
    test()
