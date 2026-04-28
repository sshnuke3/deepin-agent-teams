"""
Deepin D-Bus 接口模块
对接 deepin 操作系统的控制中心 API
"""
import subprocess
import json
from typing import Dict, Optional, List
from dataclasses import dataclass


def is_deepin() -> bool:
    """检测是否为 deepin 系统"""
    try:
        with open("/etc/deepin-version") as f:
            return "deepin" in f.read().lower()
    except FileNotFoundError:
        pass

    # 检查桌面环境
    try:
        result = subprocess.run(
            ["echo", "$XDG_CURRENT_DESKTOP"],
            capture_output=True, text=True, shell=True
        )
        return "deepin" in result.stdout.lower()
    except:
        pass

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
    except:
        pass
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
    except:
        pass

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
    except:
        pass

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
    except:
        pass

    # 尝试 deepin D-Bus
    try:
        success, output = run_dbus_method(
            "org.deepin.dde.Display1",
            "/org/deepin/dde/Display1",
            "GetBrightness"
        )
        if success:
            return float(output.split(":")[-1].strip())
    except:
        pass

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
    except:
        pass

    # 尝试 deepin D-Bus
    try:
        success, _ = run_dbus_method(
            "org.deepin.dde.Display1",
            "/org/deepin/dde/Display1",
            "SetBrightness",
            args={"value": str(brightness)}
        )
        return success
    except:
        pass

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
    except:
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
    except:
        pass

    # 桌面会话
    try:
        result = subprocess.run(
            ["echo", "$XDG_CURRENT_DESKTOP"],
            capture_output=True, text=True, shell=True
        )
        info["desktop_session"] = result.stdout.strip()
    except:
        pass

    # D-Bus 服务
    info["dbus_services"] = list_dbus_services()[:20]  # 限制数量

    return info


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


if __name__ == "__main__":
    test()
