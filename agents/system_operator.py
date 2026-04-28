"""
系统操作员 Agent
执行 bash 命令、系统配置、服务管理等
"""
import subprocess
import os
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool
    stdout: str
    stderr: str
    return_code: int


class SystemOperator:
    """
    系统操作员 - 负责执行系统级操作

    能力：
    - Bash 命令执行
    - systemd 服务管理
    - 软件包安装
    - 系统配置修改
    - 文件操作
    """

    def __init__(self, config: Dict = None):
        self.name = "SystemOperator"
        self.config = config or {}
        self.capabilities = [
            "bash_execution",
            "service_management",
            "package_installation",
            "system_configuration",
            "file_operations",
        ]

    def execute_command(self, cmd: str, timeout: int = 30, sudo: bool = False) -> CommandResult:
        """
        执行 bash 命令

        Args:
            cmd: 命令字符串
            timeout: 超时秒数
            sudo: 是否需要 sudo

        Returns:
            CommandResult
        """
        if sudo:
            cmd = f"sudo {cmd}"

        shell = isinstance(cmd, str) and not cmd.startswith("[")
        try:
            result = subprocess.run(
                cmd,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return CommandResult(
                success=result.returncode == 0,
                stdout=result.stdout[:5000],
                stderr=result.stderr[:2000],
                return_code=result.returncode
            )
        except subprocess.TimeoutExpired:
            return CommandResult(False, "", "Command timeout", -1)
        except Exception as e:
            return CommandResult(False, "", str(e), -1)

    def run_diagnosis(self, issue_type: str) -> Dict:
        """
        运行系统诊断

        Args:
            issue_type: 问题类型 (audio|network|printer|bluetooth)

        Returns:
            诊断结果
        """
        from perception.system_monitor import (
            diagnose_audio, diagnose_network, diagnose_printer, diagnose_bluetooth
        )

        diag_map = {
            "audio": diagnose_audio,
            "network": diagnose_network,
            "printer": diagnose_printer,
            "bluetooth": diagnose_bluetooth,
        }

        diag_func = diag_map.get(issue_type)
        if diag_func:
            return diag_func()
        return {"error": f"Unknown issue type: {issue_type}"}

    def repair_action(self, issue_type: str, dry_run: bool = True) -> Dict:
        """
        生成修复操作

        Args:
            issue_type: 问题类型
            dry_run: True 则只返回命令，不执行

        Returns:
            修复计划
        """
        plans = {
            "audio": {
                "commands": [
                    "pactl info",
                    "amixer set Master unmute",
                    "pulseaudio --start",
                ],
                "description": "音频修复：检查音量、解静音、启动服务"
            },
            "network": {
                "commands": [
                    "nmcli device list",
                    "systemctl restart NetworkManager",
                    "nmcli networking on",
                ],
                "description": "网络修复：检查设备、重启NetworkManager"
            },
            "printer": {
                "commands": [
                    "systemctl restart cups",
                    "lpstat -a",
                    "cupsenable $(lpstat -a | head -1 | cut -d' ' -f1)",
                ],
                "description": "打印机修复：重启CUPS、启用打印机"
            },
        }

        plan = plans.get(issue_type, {"error": "Unknown issue type"})

        if not dry_run:
            results = []
            for cmd in plan.get("commands", []):
                result = self.execute_command(cmd)
                results.append({
                    "cmd": cmd,
                    "success": result.success,
                    "output": result.stdout[:200]
                })
            plan["execution_results"] = results

        return plan

    def install_software(self, package_name: str) -> Dict:
        """
        安装软件

        Args:
            package_name: 包名

        Returns:
            安装结果
        """
        from perception.system_monitor import install_package

        result = install_package(package_name)

        return {
            "package": package_name,
            "success": result["success"],
            "message": result["message"],
            "package_manager": result.get("package_manager", "unknown")
        }

    def check_permission(self, cmd: str) -> bool:
        """检查命令是否需要 sudo"""
        privileged_prefixes = [
            "systemctl", "service", "apt", "dpkg", "yum", "dnf",
            "pacman", "mount", "umount", "shutdown", "reboot",
            "useradd", "userdel", "usermod", "passwd",
            "ip", "iptables", "modprobe", "insmod"
        ]
        first_word = cmd.strip().split()[0] if cmd.strip() else ""
        return first_word in privileged_prefixes

    def process_task(self, task: str) -> Dict:
        """
        处理系统操作任务

        Args:
            task: 任务描述

        Returns:
            处理结果
        """
        task_lower = task.lower()
        result = {"task": task, "actions": [], "success": True}

        # 诊断类任务
        if any(k in task_lower for k in ["检查", "诊断", "看看", "有没有问题"]):
            for issue in ["audio", "network", "printer"]:
                if issue in task_lower or "系统" in task_lower:
                    diag = self.run_diagnosis(issue)
                    result["actions"].append({
                        "type": "diagnosis",
                        "issue": issue,
                        "result": diag
                    })

        # 修复类任务
        if any(k in task_lower for k in ["修复", "解决", "修一下"]):
            for issue in ["audio", "network", "printer"]:
                if issue in task_lower:
                    plan = self.repair_action(issue, dry_run=False)
                    result["actions"].append({
                        "type": "repair",
                        "issue": issue,
                        "plan": plan
                    })

        # 安装类任务
        if any(k in task_lower for k in ["安装", "install", "装"]):
            import re
            match = re.search(r"(?:安装|装)(.+?)(?:软件|吗|$)", task_lower)
            if match:
                package = match.group(1).strip()
                install_result = self.install_software(package)
                result["actions"].append({
                    "type": "install",
                    "package": package,
                    "result": install_result
                })

        return result


def test():
    """测试 SystemOperator"""
    op = SystemOperator()

    print("=== SystemOperator 测试 ===\n")

    # 测试命令执行
    print("1. 执行命令: uname -a")
    r = op.execute_command("uname -a")
    print(f"   成功: {r.success}")
    print(f"   输出: {r.stdout[:100]}")

    # 测试权限检查
    print("\n2. 权限检查:")
    print(f"   'ls': {op.check_permission('ls')}")  # False
    print(f"   'systemctl restart nginx': {op.check_permission('systemctl restart nginx')}")  # True

    # 测试诊断
    print("\n3. 系统诊断:")
    diag = op.run_diagnosis("network")
    print(f"   组件: {diag.get('component')}")
    print(f"   问题: {diag.get('issues', [])}")

    # 测试安装（dry run）
    print("\n4. 安装计划 (微信):")
    plan = op.repair_action("audio", dry_run=True)
    print(f"   描述: {plan.get('description')}")
    print(f"   命令: {plan.get('commands', [])}")


if __name__ == "__main__":
    test()
