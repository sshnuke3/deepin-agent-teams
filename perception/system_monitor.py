"""
系统监控模块
检查服务状态、音频、网络、磁盘等系统状态
"""
import subprocess
import re
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ServiceStatus:
    """服务状态"""
    name: str
    active: bool
    running: bool
    description: str


def run_command(cmd: List[str], timeout: int = 5) -> tuple:
    """执行命令并返回 (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timeout"
    except FileNotFoundError:
        return -2, "", "Command not found"


def check_service(systemd_name: str) -> ServiceStatus:
    """
    检查 systemd 服务状态

    Args:
        systemd_name: 服务名（如 "cups" 而非 "cups.service"）

    Returns:
        ServiceStatus
    """
    full_name = systemd_name if ".service" in systemd_name else f"{systemd_name}.service"

    returncode, stdout, _ = run_command(["systemctl", "is-active", full_name])
    active = returncode == 0

    returncode, stdout, _ = run_command(["systemctl", "is-enabled", full_name])
    enabled = returncode == 0

    return ServiceStatus(
        name=systemd_name,
        active=active,
        running=enabled,
        description=f"{'active' if active else 'inactive'}"
    )


def get_service_details(systemd_name: str) -> Dict:
    """获取服务详细信息"""
    full_name = systemd_name if ".service" in systemd_name else f"{systemd_name}.service"

    status = {}

    # 服务状态
    rc, out, _ = run_command(["systemctl", "status", full_name])
    status["status_raw"] = out[:500] if out else ""

    # 提取关键信息
    if "Active: active (running)" in out:
        status["state"] = "running"
    elif "Active: inactive" in out:
        status["state"] = "inactive"
    elif "Active: failed" in out:
        status["state"] = "failed"
    else:
        status["state"] = "unknown"

    return status


def diagnose_printer() -> Dict:
    """
    诊断打印机问题

    Returns:
        诊断结果字典
    """
    result = {
        "component": "printer",
        "issues": [],
        "suggestions": [],
        "checks": {}
    }

    # 检查 CUPS 服务
    cups_status = check_service("cups")
    result["checks"]["cups_service"] = cups_status.active

    if not cups_status.active:
        result["issues"].append("CUPS 打印服务未运行")
        result["suggestions"].append("运行: sudo systemctl start cups")

    # 检查打印机列表
    rc, out, _ = run_command(["lpstat", "-a"])
    result["checks"]["printers_configured"] = rc == 0
    result["checks"]["printers_list"] = out[:200] if out else "无可用打印机"

    if rc != 0:
        result["issues"].append("未配置任何打印机")
        result["suggestions"].append("检查打印机连接，运行: sudo lpstat -a")

    # 检查权限
    rc, _, _ = run_command(["lpstat", "-r"])
    if rc != 0:
        result["issues"].append("CUPS 调度器未运行")
        result["suggestions"].append("运行: sudo systemctl restart cups")

    return result


def diagnose_audio() -> Dict:
    """
    诊断音频问题

    Returns:
        诊断结果字典
    """
    result = {
        "component": "audio",
        "issues": [],
        "suggestions": [],
        "checks": {}
    }

    # 检查 PulseAudio/PipeWire
    rc, out, _ = run_command(["pactl", "info"])
    result["checks"]["pulseaudio"] = rc == 0

    if rc != 0:
        result["issues"].append("音频服务未运行")
        result["suggestions"].append("运行: systemctl --user start pulseaudio 或 pipewire")
    else:
        # 解析音频服务器信息
        for line in out.split("\n"):
            if "Default Sink:" in line:
                result["checks"]["default_sink"] = line.split(":", 1)[1].strip()
            elif "Default Source:" in line:
                result["checks"]["default_source"] = line.split(":", 1)[1].strip()

    # 检查音量
    rc, out, _ = run_command(["amixer", "get", "Master"])
    if rc == 0:
        # 解析音量
        match = re.search(r"\[(\d+)%\]", out)
        if match:
            result["checks"]["volume_percent"] = int(match.group(1))

        if "off" in out.lower():
            result["issues"].append("主音量被静音")
            result["suggestions"].append("运行: amixer set Master unmute")

    # 检查无声模块
    rc, _, _ = run_command(["aplay", "-l"])
    result["checks"]["alsa_cards"] = rc == 0

    if rc != 0:
        result["issues"].append("未检测到音频设备")
        result["suggestions"].append("检查音频设备连接，确认驱动已安装")

    return result


def diagnose_network() -> Dict:
    """
    诊断网络问题

    Returns:
        诊断结果字典
    """
    result = {
        "component": "network",
        "issues": [],
        "suggestions": [],
        "checks": {}
    }

    # 检查 NetworkManager
    nm_status = check_service("NetworkManager")
    result["checks"]["networkmanager"] = nm_status.active

    if not nm_status.active:
        result["issues"].append("NetworkManager 未运行")
        result["suggestions"].append("运行: sudo systemctl start NetworkManager")

    # 检查网络连接状态
    rc, out, _ = run_command(["nmcli", "device", "status"])
    result["checks"]["nmcli_works"] = rc == 0

    if rc == 0:
        # 解析连接状态
        lines = out.split("\n")
        for line in lines[1:]:  # 跳过标题行
            if "connected" in line.lower():
                result["checks"]["connected"] = True
                break
        else:
            result["issues"].append("未连接到任何网络")
            result["suggestions"].append("检查 WiFi 或网线连接")
            result["checks"]["connected"] = False

    # ping 测试
    rc, _, _ = run_command(["ping", "-c", "1", "-W", "2", "8.8.8.8"])
    result["checks"]["internet_reachable"] = rc == 0

    if rc != 0:
        result["issues"].append("无法访问互联网")
        result["suggestions"].append("检查网络配置或 DNS 设置")

    return result


def diagnose_bluetooth() -> Dict:
    """诊断蓝牙问题"""
    result = {
        "component": "bluetooth",
        "issues": [],
        "suggestions": [],
        "checks": {}
    }

    bt_status = check_service("bluetooth")
    result["checks"]["bluetooth_service"] = bt_status.active

    if not bt_status.active:
        result["issues"].append("蓝牙服务未运行")
        result["suggestions"].append("运行: sudo systemctl start bluetooth")

    rc, out, _ = run_command(["rfkill", "list", "bluetooth"])
    if rc == 0 and "blocked" in out.lower():
        result["issues"].append("蓝牙被 rfkill 阻止")
        result["suggestions"].append("运行: sudo rfkill unblock bluetooth")

    return result


def install_package(package_name: str) -> Dict:
    """
    安装软件包

    Returns:
        安装结果
    """
    result = {"package": package_name, "success": False, "message": ""}

    # 检测包管理器
    package_managers = [
        ("apt", ["sudo", "apt", "install", "-y", package_name]),
        ("dnf", ["sudo", "dnf", "install", "-y", package_name]),
        ("yum", ["sudo", "yum", "install", "-y", package_name]),
        ("pacman", ["sudo", "pacman", "-S", "--noconfirm", package_name]),
    ]

    for name, cmd in package_managers:
        rc, _, _ = run_command(["which", cmd[1]], timeout=2)
        if rc == 0:
            result["package_manager"] = name
            rc, out, err = run_command(cmd, timeout=60)
            result["success"] = rc == 0
            result["message"] = out if rc == 0 else err[:200]
            return result

    result["message"] = "未找到支持的包管理器 (apt/dnf/yum/pacman)"
    return result


def get_system_summary() -> Dict:
    """
    获取系统状态摘要

    Returns:
        系统状态字典
    """
    summary = {
        "timestamp": datetime.now().isoformat(),
        "services": {},
        "cpu_percent": 0,
        "memory_percent": 0,
        "disk_percent": 0
    }

    # 关键服务状态
    for svc in ["cups", "NetworkManager", "bluetooth", "ssh"]:
        status = check_service(svc)
        summary["services"][svc] = status.active

    # CPU 使用率
    try:
        with open("/proc/loadavg") as f:
            load = f.read().split()[:3]
            summary["load_average"] = [float(x) for x in load]
    except:
        pass

    # 内存使用率
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
            total_match = re.search(r"MemTotal:\s+(\d+)", meminfo)
            avail_match = re.search(r"MemAvailable:\s+(\d+)", meminfo)
            if total_match and avail_match:
                total = int(total_match.group(1))
                avail = int(avail_match.group(1))
                summary["memory_percent"] = round((1 - avail / total) * 100, 1)
    except:
        pass

    return summary


def diagnose_issue(user_description: str) -> Dict:
    """
    根据用户描述智能诊断问题

    Args:
        user_description: 用户的问题描述

    Returns:
        诊断结果和建议
    """
    user_lower = user_description.lower()

    # 关键词匹配
    if any(kw in user_lower for kw in ["打印", "打印机", "print", "printer"]):
        return diagnose_printer()

    elif any(kw in user_lower for kw in ["声音", "音频", "声卡", "audio", "sound", "没声"]):
        return diagnose_audio()

    elif any(kw in user_lower for kw in ["网络", "wifi", "网", "network", "上不了"]):
        return diagnose_network()

    elif any(kw in user_lower for kw in ["蓝牙", "bluetooth", "蓝牙耳机"]):
        return diagnose_bluetooth()

    elif any(kw in user_lower for kw in ["安装", "install", "软件", "app"]):
        # 提取软件名
        package = re.search(r"(?:安装|装)(.+?)(?:软件|包|$)", user_lower)
        if package:
            return {
                "action": "install",
                "package": package.group(1).strip(),
                "steps": [
                    f"sudo apt update",
                    f"sudo apt install {package.group(1).strip()}"
                ]
            }

    # 默认：返回系统摘要
    return {
        "action": "info",
        "message": "无法根据描述确定问题类型",
        "system_summary": get_system_summary()
    }


def test():
    """测试系统监控功能"""
    print("=== 系统状态摘要 ===")
    summary = get_system_summary()
    print(f"时间: {summary['timestamp']}")
    print(f"内存: {summary['memory_percent']}%")
    print(f"服务: {summary['services']}")

    print("\n=== 诊断测试 ===")

    # 诊断音频
    print("\n音频诊断:")
    audio = diagnose_audio()
    print(f"  问题: {audio['issues']}")
    print(f"  建议: {audio['suggestions']}")

    # 诊断网络
    print("\n网络诊断:")
    network = diagnose_network()
    print(f"  问题: {network['issues']}")
    print(f"  建议: {network['suggestions']}")

    # 智能诊断
    print("\n智能诊断 '打印机连不上':")
    result = diagnose_issue("打印机连不上")
    print(f"  组件: {result.get('component', 'unknown')}")
    print(f"  问题: {result.get('issues', [])}")


if __name__ == "__main__":
    test()
