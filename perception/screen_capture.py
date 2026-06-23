"""
屏幕截图模块
支持 deepin/Ubuntu 等 Linux 桌面环境
"""
import subprocess
import os
import tempfile
from pathlib import Path
from datetime import datetime


def is_wayland() -> bool:
    """检测是否使用 Wayland 会话"""
    return os.environ.get("XDG_SESSION_TYPE", "") == "wayland"


def is_x11() -> bool:
    """检测是否使用 X11 会话"""
    return os.environ.get("XDG_SESSION_TYPE", "") == "x11" or os.environ.get("DISPLAY", "") != ""


def capture_screen(output_path: str = None, region: tuple = None) -> str:
    """
    截取屏幕截图

    Args:
        output_path: 保存路径，默认 temp 文件
        region: 截图区域 (x, y, width, height)，仅 X11 支持

    Returns:
        str: 截图文件路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_path is None:
        output_path = f"/tmp/deepin_agent_screenshot_{timestamp}.png"

    if is_wayland():
        # Wayland: 使用 grim
        cmd = ["grim"]
        if region:
            x, y, w, h = region
            # grim 支持 -g 指定区域
            cmd.extend(["-g", f"{x},{y} {w}x{h}"])
        cmd.append(output_path)
    else:
        # X11: 使用 scrot 或 gnome-screenshot
        cmd = ["scrot", output_path]
        if region:
            # scrot 支持 -a 指定区域
            x, y, w, h = region
            cmd = ["scrot", "-a", f"{x},{y},{w},{h}", output_path]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except subprocess.CalledProcessError as e:
        # 降级：尝试 ImageMagick
        try:
            fallback_cmd = ["import", "-window", "root", output_path]
            subprocess.run(fallback_cmd, check=True, capture_output=True)
            return output_path
        except subprocess.CalledProcessError:
            raise RuntimeError(f"截图失败，请安装 grim (wayland) 或 scrot (x11): {e}")


def capture_active_window() -> str:
    """
    截取当前活动窗口

    Returns:
        str: 窗口截图路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"/tmp/deepin_agent_window_{timestamp}.png"

    if is_wayland():
        # Wayland: 使用 grim + slurp 获取当前窗口
        try:
            # 获取当前焦点窗口 ID
            window_id = subprocess.run(
                ["swaymsg", "-t", "get_focused_window"],
                capture_output=True, text=True, check=True
            ).stdout.strip()
            # grim 截取指定窗口
            subprocess.run(
                ["grim", "-w", window_id, output_path],
                check=True, capture_output=True
            )
        except subprocess.CalledProcessError:
            # 降级：截取全屏
            return capture_screen(output_path)
    else:
        # X11: 使用 scrot -u 截取当前窗口
        try:
            subprocess.run(["scrot", "-u", output_path], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # 降级：ImageMagick
            cmd = ["import", "-window", "focused", output_path]
            subprocess.run(cmd, check=True, capture_output=True)

    return output_path


def get_screen_info() -> dict:
    """获取屏幕信息"""
    info = {"session_type": os.environ.get("XDG_SESSION_TYPE", "unknown")}

    try:
        if is_wayland():
            # 获取屏幕尺寸
            output = subprocess.run(
                ["wlr-randr"],
                capture_output=True, text=True
            )
            info["wayland_output"] = output.stdout[:500]
        else:
            # 获取屏幕尺寸
            output = subprocess.run(
                ["xrandr"],
                capture_output=True, text=True, check=True
            )
            # 解析主屏幕分辨率
            lines = output.stdout.split("\n")
            for line in lines:
                if "*" in line and not line.strip().startswith("Screen"):
                    parts = line.split()
                    if parts:
                        info["resolution"] = parts[0]
                        break
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return info


def test():
    """测试截图功能"""
    print(f"会话类型: {os.environ.get('XDG_SESSION_TYPE', 'unknown')}")
    print(f"DISPLAY: {os.environ.get('DISPLAY', '(none)')}")

    try:
        path = capture_screen()
        size = os.path.getsize(path)
        print(f"✅ 截图成功: {path} ({size} bytes)")

        # 清理
        os.remove(path)
        print("✅ 清理完成")
    except Exception as e:
        print(f"❌ 截图失败: {e}")


if __name__ == "__main__":
    test()
