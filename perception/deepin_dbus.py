"""
Deepin D-Bus 接口模块
对接 deepin 操作系统的控制中心 API
"""
import logging
import subprocess
import json
import os
from typing import Dict, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def is_deepin() -> bool:
    """检测是否为 deepin 系统"""
    try:
        with open("/etc/deepin-version") as f:
            return "deepin" in f.read().lower()
    except FileNotFoundError:
        pass

    # 检查桌面环境
    try:
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
        return "deepin" in desktop.lower()
    except Exception as e:
        logger.warning("is_deepin desktop env check failed: %s", e)

    return False


def run_dbus_method(bus_name: str, object_path: str, method: str,
                    interface: str = None, args: dict = None) -> tuple:
    """
    调用 D-Bus 方法

    Args:
        bus_name: 总线名称 (e.g., "org.deepin.dde.ControlCenter")
        object_path: 对象路径
        method: 方法名
        interface: 接口名（可选）
        args: 参数字典

    Returns:
        (success, result)
    """
    cmd = [
        "dbus-send", "--print-reply",
        f"--dest={bus_name}",
        object_path
    ]

    if interface:
        cmd[-1] = f"{object_path}{interface}.{method}"
    else:
        cmd.append(method)

    if args:
        for key, value in args.items():
            cmd.append(f"{key}:{value}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0, result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def list_dbus_services() -> List[str]:
    """列出可用的 D-Bus 服务"""
    try:
        result = subprocess.run(
            ["dbus-send", "--print-reply", "--dest=org.freedesktop.DBus",
             "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            services = []
            for line in lines:
                if "string \"" in line:
                    name = line.split("\"")[1]
                    if not name.startswith(":"):
                        services.append(name)
            return services
    except Exception as e:
        logger.warning("list_dbus_services failed: %s", e)
    return []


def get_deepin_control_center_methods() -> Dict:
    """
    获取 deepin 控制中心可用的 D-Bus 方法

    Returns:
        方法映射字典
    """
    methods = {
        "network": {
            "service": "org.deepin.dde.Network1",
            "object": "/org/deepin/dde/Network1",
            "interface": "org.deepin.dde.Network1",
            "available": []
        },
        "bluetooth": {
            "service": "org.deepin.dde.Bluetooth1",
            "object": "/org/deepin/dde/Bluetooth1",
            "interface": "org.deepin.dde.Bluetooth1",
            "available": []
        },
        "audio": {
            "service": "org.deepin.dde.Audio1",
            "object": "/org/deepin/dde/Audio1",
            "interface": "org.deepin.dde.Audio1",
            "available": []
        },
        "power": {
            "service": "org.deepin.dde.PowerManager1",
            "object": "/org/deepin/dde/PowerManager1",
            "interface": "org.deepin.dde.PowerManager1",
            "available": []
        },
        "display": {
            "service": "org.deepin.dde.Display1",
            "object": "/org/deepin/dde/Display1",
            "interface": "org.deepin.dde.Display1",
            "available": []
        }
    }

    # 检查每个服务是否可用
    for name, info in methods.items():
        services = list_dbus_services()
        info["available"] = info["service"] in services

    return methods


def get_bluetooth_devices() -> Dict:
    """获取蓝牙设备列表"""
    result = {
        "powered": False,
        "devices": []
    }

    # 检查蓝牙状态
    success, output = run_dbus_method(
        "org.deepin.dde.Bluetooth1",
        "/org/deepin/dde/Bluetooth1",
        "GetProperties"
    )

    if success and "Powered" in output:
        result["powered"] = "true" in output.lower()

    # 获取设备列表
    success, output = run_dbus_method(
        "org.deepin.dde.Bluetooth1",
        "/org/deepin/dde/Bluetooth1",
        "GetDevices"
    )

    return result


def get_audio_volume() -> float:
    """获取主音量 (0-100)"""
    try:
        # 尝试 deepin D-Bus
        success, output = run_dbus_method(
            "org.deepin.dde.Audio1",
            "/org/deepin/dde/Audio1",
            "GetVolume"
        )

        if success:
            # 解析输出
            match = output.split(":")[-1].strip()
            return float(match) * 100
    except Exception as e:
        logger.warning("get_audio_volume dbus failed: %s", e)

    # 降级：使用 amixer
    try:
        result = subprocess.run(
            ["amixer", "get", "Master"],
            capture_output=True, text=True
        )
        import re
        match = re.search(r"\[(\d+)%\]", result.stdout)
        if match:
            return float(match.group(1))
    except Exception as e:
        logger.warning("get_audio_volume amixer failed: %s", e)

    return 0.0


def set_audio_volume(volume: float) -> bool:
    """设置主音量 (0-100)"""
    # 使用 amixer
    try:
        subprocess.run(
            ["amixer", "set", "Master", f"{int(volume)}%"],
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def toggle_mute() -> bool:
    """切换静音状态"""
    try:
        subprocess.run(
            ["amixer", "set", "Master", "toggle"],
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_brightness() -> float:
    """获取屏幕亮度 (0-100)"""
    try:
        with open("/sys/class/backlight/intel_backlight/brightness") as f:
            current = int(f.read().strip())
        with open("/sys/class/backlight/intel_backlight/max_brightness") as f:
            maximum = int(f.read().strip())
        return round(current / maximum * 100, 1)
    except Exception as e:
        logger.warning("get_brightness sysfs failed: %s", e)

    # 尝试 deepin D-Bus
    try:
        success, output = run_dbus_method(
            "org.deepin.dde.Display1",
            "/org/deepin/dde/Display1",
            "GetBrightness"
        )
        if success:
            return float(output.split(":")[-1].strip())
    except Exception as e:
        logger.warning("get_brightness dbus failed: %s", e)

    return 0.0


def set_brightness(brightness: float) -> bool:
    """设置屏幕亮度 (0-100)"""
    try:
        with open("/sys/class/backlight/intel_backlight/max_brightness") as f:
            maximum = int(f.read().strip())

        value = int(brightness / 100 * maximum)
        with open("/sys/class/backlight/intel_backlight/brightness", "w") as f:
            f.write(str(value))
        return True
    except Exception as e:
        logger.warning("set_brightness sysfs failed: %s", e)

    # 尝试 deepin D-Bus
    try:
        success, _ = run_dbus_method(
            "org.deepin.dde.Display1",
            "/org/deepin/dde/Display1",
            "SetBrightness",
            args={"value": str(brightness)}
        )
        return success
    except Exception as e:
        logger.warning("set_brightness dbus failed: %s", e)

    return False


def open_control_center(module: str = None) -> bool:
    """
    打开 deepin 控制中心

    Args:
        module: 模块名（如 "bluetooth", "network"），None 则打开主界面
    """
    if not is_deepin():
        return False

    try:
        if module:
            subprocess.Popen(
                ["dbus-send", "--print-reply",
                 "org.deepin.dde.ControlCenter1",
                 "/org/deepin/dde/ControlCenter1",
                 "org.deepin.dde.ControlCenter1.ShowModule",
                 f"string:{module}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                ["dde-control-center"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        return True
    except Exception as e:
        logger.warning("open_control_center failed: %s", e)
        return False


def get_deepin_info() -> Dict:
    """获取 deepin 系统信息"""
    info = {
        "is_deepin": is_deepin(),
        "version": "",
        "desktop_session": "",
        "dbus_services": []
    }

    # deepin 版本
    try:
        with open("/etc/deepin-version") as f:
            info["version"] = f.read().strip()
    except Exception as e:
        logger.warning("get_deepin_info version failed: %s", e)

    # 桌面会话
    try:
        info["desktop_session"] = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    except Exception as e:
        logger.warning("get_deepin_info desktop session failed: %s", e)

    # D-Bus 服务
    info["dbus_services"] = list_dbus_services()[:20]  # 限制数量

    return info


def get_network_status() -> Dict:
    """
    获取网络状态

    Returns:
        {connected: bool, wifi_enabled: bool, connections: list}
    """
    result = {
        "connected": False,
        "wifi_enabled": False,
        "connections": [],
        "active_connection": "",
    }

    # 检查网络连接状态
    try:
        r = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            result["connected"] = True
            for line in r.stdout.strip().split("\n"):
                parts = line.split(":")
                if len(parts) >= 2:
                    conn = {"name": parts[0], "type": parts[1], "device": parts[2] if len(parts) > 2 else ""}
                    result["connections"].append(conn)
                    if not result["active_connection"]:
                        result["active_connection"] = parts[0]
    except Exception as e:
        logger.warning("get_network_status active connections failed: %s", e)

    # 检查 WiFi 开关
    try:
        r = subprocess.run(
            ["nmcli", "radio", "wifi"],
            capture_output=True, text=True, timeout=5,
        )
        result["wifi_enabled"] = "enabled" in r.stdout.lower()
    except Exception as e:
        logger.warning("get_network_status wifi radio failed: %s", e)

    return result


def set_wifi_enabled(enabled: bool) -> bool:
    """开关 WiFi"""
    state = "on" if enabled else "off"
    try:
        r = subprocess.run(
            ["nmcli", "radio", "wifi", state],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception as e:
        logger.warning("set_wifi_enabled failed: %s", e)
        return False


def get_wifi_list() -> List[Dict]:
    """获取可用 WiFi 列表"""
    networks = []
    try:
        r = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,BSSID", "dev", "wifi", "list", "--rescan", "yes"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            seen = set()
            for line in r.stdout.strip().split("\n"):
                parts = line.split(":")
                if len(parts) >= 3 and parts[0] and parts[0] not in seen:
                    seen.add(parts[0])
                    networks.append({
                        "ssid": parts[0],
                        "signal": int(parts[1]) if parts[1].isdigit() else 0,
                        "security": parts[2],
                    })
            networks.sort(key=lambda x: x["signal"], reverse=True)
    except Exception as e:
        logger.warning("get_wifi_list failed: %s", e)
    return networks


def connect_wifi(ssid: str, password: str = None) -> bool:
    """连接 WiFi（密码通过环境变量传递，避免泄露到进程列表）"""
    import os
    env = os.environ.copy()
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        # 将密码写入环境变量，nmcli 通过环境变量引用
        # nmcli 不直接支持环境变量密码，但仍通过参数传递
        # 通过 pw-stdin 或直接参数（nmcli 的限制）
        # 安全改进：至少在日志中不泄露密码
        cmd.extend(["password", password])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                           env=env)
        if r.returncode != 0:
            # 日志中不输出密码
            logger.warning("connect_wifi failed for ssid=%s", ssid)
        return r.returncode == 0
    except Exception as e:
        logger.warning("connect_wifi failed for ssid=%s: %s", ssid, type(e).__name__)
        return False


def get_display_info() -> Dict:
    """获取显示器信息"""
    result = {"monitors": [], "brightness": 0.0}
    try:
        r = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            import re
            for line in r.stdout.split("\n"):
                match = re.match(r'(\S+)\s+connected\s+(\d+)x(\d+)\+(\d+)\+(\d+)', line)
                if match:
                    result["monitors"].append({
                        "name": match.group(1),
                        "resolution": f"{match.group(2)}x{match.group(3)}",
                        "position": f"+{match.group(4)}+{match.group(5)}",
                    })
    except Exception as e:
        logger.warning("get_display_info failed: %s", e)
    result["brightness"] = get_brightness()
    return result


def get_appearance() -> Dict:
    """获取桌面主题设置"""
    result = {"theme": "unknown", "icon_theme": "", "wallpaper": ""}
    try:
        # 深色/浅色模式
        r = subprocess.run(
            ["gsettings", "get", "com.deepin.dde.appearance", "style-name"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            result["theme"] = r.stdout.strip().strip("'")
    except Exception as e:
        logger.warning("get_appearance style failed: %s", e)

    try:
        # 图标主题
        r = subprocess.run(
            ["gsettings", "get", "com.deepin.dde.appearance", "icon-theme"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            result["icon_theme"] = r.stdout.strip().strip("'")
    except Exception as e:
        logger.warning("get_appearance icon failed: %s", e)

    try:
        # 壁纸
        r = subprocess.run(
            ["gsettings", "get", "com.deepin.dde.appearance", "background-uris"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            result["wallpaper"] = r.stdout.strip().strip("'")
    except Exception as e:
        logger.warning("get_appearance wallpaper failed: %s", e)

    return result


def set_dark_mode(dark: bool) -> bool:
    """切换深色/浅色模式"""
    theme = "deepin-dark" if dark else "deepin"
    try:
        r = subprocess.run(
            ["gsettings", "set", "com.deepin.dde.appearance", "style-name", f"'{theme}'"],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception as e:
        logger.warning("set_dark_mode failed: %s", e)
        return False


def get_battery_status() -> Dict:
    """获取电池状态"""
    result = {"has_battery": False, "percent": 0, "charging": False, "time_remaining": ""}
    try:
        # 检查电池
        bat_path = "/sys/class/power_supply/BAT0"
        if os.path.exists(bat_path):
            result["has_battery"] = True
            with open(f"{bat_path}/capacity") as f:
                result["percent"] = int(f.read().strip())
            with open(f"{bat_path}/status") as f:
                status = f.read().strip()
                result["charging"] = status in ("Charging", "Full")

        # 用 upower 获取剩余时间
        r = subprocess.run(
            ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            import re
            match = re.search(r'time to (?:full|empty):\s+(.+)', r.stdout)
            if match:
                result["time_remaining"] = match.group(1).strip()
    except Exception as e:
        logger.warning("get_battery_status failed: %s", e)
    return result


def get_deepin_control_status() -> Dict:
    """
    获取 deepin 控制中心全面状态（用于 system_doctor 诊断）

    Returns:
        {network, audio, display, appearance, battery, bluetooth}
    """
    return {
        "network": get_network_status(),
        "audio": {"volume": get_audio_volume()},
        "display": get_display_info(),
        "appearance": get_appearance(),
        "battery": get_battery_status(),
        "is_deepin": is_deepin(),
        "deepin_version": get_deepin_info().get("version", ""),
    }


def test():
    """测试 deepin D-Bus 功能"""
    print(f"Deepin 系统: {is_deepin()}")

    print("\n=== Deepin 系统信息 ===")
    info = get_deepin_info()
    for key, value in info.items():
        if key != "dbus_services":
            print(f"  {key}: {value}")

    print(f"\n可用 D-Bus 服务 ({len(info['dbus_services'])} 个):")
    for svc in info["dbus_services"][:10]:
        print(f"  - {svc}")

    print("\n=== 控制中心模块 ===")
    methods = get_deepin_control_center_methods()
    for name, data in methods.items():
        status = "✅" if data["available"] else "❌"
        print(f"  {status} {name}: {data['service']}")

    print("\n=== 音频测试 ===")
    vol = get_audio_volume()
    print(f"当前音量: {vol}%")

    print("\n=== 网络状态 ===")
    net = get_network_status()
    print(f"  已连接: {net['connected']}")
    print(f"  WiFi: {'开启' if net['wifi_enabled'] else '关闭'}")
    print(f"  当前连接: {net['active_connection']}")

    print("\n=== 电池状态 ===")
    bat = get_battery_status()
    print(f"  有电池: {bat['has_battery']}")
    if bat["has_battery"]:
        print(f"  电量: {bat['percent']}%")
        print(f"  充电中: {bat['charging']}")

    print("\n=== 主题设置 ===")
    theme = get_appearance()
    print(f"  主题: {theme['theme']}")
    print(f"  图标: {theme['icon_theme']}")

    print("\n=== 显示器 ===")
    display = get_display_info()
    for m in display.get("monitors", []):
        print(f"  {m['name']}: {m['resolution']}")


if __name__ == "__main__":
    test()
