"""
系统问题诊断修复场景
识别系统问题 → 多Agent协同诊断 → 自动修复
"""
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.system_operator import SystemOperator
from agents.information_collector import InformationCollector


class SystemDoctor:
    """
    系统问题诊断修复 - 场景二

    工作流程：
    1. 问题分类（Lead Agent）
    2. 多Agent协同诊断（SystemOperator + InformationCollector）
    3. 生成修复方案
    4. 用户确认后执行
    """

    def __init__(self):
        self.operator = SystemOperator()
        self.collector = InformationCollector()

        # 问题类型关键词
        self.issue_keywords = {
            "audio": ["声音", "音频", "声卡", "没声", "audio", "sound"],
            "network": ["网络", "wifi", "网", "上不了", "network", "连不上"],
            "printer": ["打印", "打印机", "print", "printer"],
            "bluetooth": ["蓝牙", "bluetooth"],
            "install": ["安装", "装", "install"],
        }

    def classify_issue(self, user_input: str) -> Dict:
        """
        分类问题类型

        Args:
            user_input: 用户描述

        Returns:
            问题分类结果
        """
        text_lower = user_input.lower()
        scores = {}

        for issue_type, keywords in self.issue_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[issue_type] = score

        if not scores:
            return {"type": "unknown", "confidence": 0, "original": user_input}

        # 选择得分最高的
        max_type = max(scores.items(), key=lambda x: x[1])
        confidence = min(max_type[1] * 0.4, 0.95)

        return {
            "type": max_type[0],
            "confidence": confidence,
            "scores": scores,
            "original": user_input
        }

    def diagnose(self, issue_type: str) -> Dict:
        """
        执行诊断

        Args:
            issue_type: 问题类型

        Returns:
            诊断结果
        """
        print(f"\n[诊断] 执行 {issue_type} 系统诊断...")

        # 调用系统监控模块
        from perception.system_monitor import (
            diagnose_audio, diagnose_network,
            diagnose_printer, diagnose_bluetooth
        )

        diag_funcs = {
            "audio": diagnose_audio,
            "network": diagnose_network,
            "printer": diagnose_printer,
            "bluetooth": diagnose_bluetooth,
        }

        diag_func = diag_funcs.get(issue_type)
        if diag_func:
            result = diag_func()
            return result

        return {"error": f"Unknown issue type: {issue_type}"}

    def generate_fix_plan(self, issue_type: str, diagnosis: Dict) -> Dict:
        """
        生成修复方案

        Args:
            issue_type: 问题类型
            diagnosis: 诊断结果

        Returns:
            修复方案
        """
        # 根据诊断结果生成方案
        issues = diagnosis.get("issues", [])
        suggestions = diagnosis.get("suggestions", [])

        fix_plan = {
            "issue_type": issue_type,
            "problems": issues,
            "steps": [],
            "risky_steps": [],  # 需要用户确认的步骤
            "auto_steps": [],   # 可自动执行的步骤
        }

        # 根据问题类型生成具体命令
        commands = {
            "audio": {
                "auto": [
                    ("检查音量", "amixer get Master"),
                    ("取消静音", "amixer set Master unmute"),
                ],
                "risky": [
                    ("重启音频服务", "systemctl restart pulseaudio"),
                ]
            },
            "network": {
                "auto": [
                    ("检查网络设备", "nmcli device status"),
                    ("检查连接状态", "ip addr"),
                ],
                "risky": [
                    ("重启网络管理器", "systemctl restart NetworkManager"),
                ]
            },
            "printer": {
                "auto": [
                    ("检查CUPS服务", "systemctl status cups"),
                    ("列出打印机", "lpstat -a"),
                ],
                "risky": [
                    ("重启CUPS", "systemctl restart cups"),
                ]
            },
            "bluetooth": {
                "auto": [
                    ("检查蓝牙状态", "rfkill list bluetooth"),
                ],
                "risky": [
                    ("重启蓝牙服务", "systemctl restart bluetooth"),
                ]
            }
        }

        cmd_set = commands.get(issue_type, {})
        for desc, cmd in cmd_set.get("auto", []):
            fix_plan["auto_steps"].append({"description": desc, "command": cmd})

        for desc, cmd in cmd_set.get("risky", []):
            fix_plan["risky_steps"].append({"description": desc, "command": cmd})

        return fix_plan

    def run(self, user_input: str, auto_execute: bool = False) -> Dict:
        """
        执行系统诊断修复场景

        Args:
            user_input: 用户问题描述
            auto_execute: 是否自动执行修复（默认False，需用户确认）

        Returns:
            执行结果
        """
        print(f"\n🔧 系统医生启动")
        print(f"用户问题: {user_input}")
        print("=" * 50)

        result = {
            "success": False,
            "issue_type": None,
            "diagnosis": None,
            "fix_plan": None,
            "execution": None,
            "steps": []
        }

        # Step 1: 问题分类
        print("\n[Step 1] 问题分类...")
        classification = self.classify_issue(user_input)
        result["issue_type"] = classification["type"]
        result["steps"].append({"step": "classification", "done": True})

        if classification["type"] == "unknown":
            print("❌ 无法识别问题类型")
            result["error"] = "Unknown issue type"
            return result

        print(f"✅ 识别为: {classification['type']} (置信度: {classification['confidence']:.0%})")

        # Step 2: 系统诊断
        print("\n[Step 2] 执行系统诊断...")
        diagnosis = self.diagnose(classification["type"])
        result["diagnosis"] = diagnosis
        result["steps"].append({"step": "diagnosis", "done": True})

        issues = diagnosis.get("issues", [])
        if issues:
            print(f"⚠️  发现 {len(issues)} 个问题:")
            for issue in issues:
                print(f"   - {issue}")
        else:
            print("✅ 未发现明显问题")

        # Step 3: 生成修复方案
        print("\n[Step 3] 生成修复方案...")
        fix_plan = self.generate_fix_plan(classification["type"], diagnosis)
        result["fix_plan"] = fix_plan
        result["steps"].append({"step": "fix_plan", "done": True})

        print("\n📋 修复步骤:")
        for i, step in enumerate(fix_plan.get("auto_steps", []), 1):
            print(f"   {i}. [自动] {step['description']}")
            print(f"      命令: {step['command']}")

        for i, step in enumerate(fix_plan.get("risky_steps", []), len(fix_plan.get("auto_steps", [])) + 1):
            print(f"   {i}. [⚠️ 需确认] {step['description']}")
            print(f"      命令: {step['command']}")

        # Step 4: 询问用户或自动执行
        if not auto_execute:
            print("\n💡 提示: 回复'执行'开始修复，或'取消'退出")
            result["requires_confirmation"] = True
            return result

        # Step 5: 执行修复
        print("\n[Step 4] 执行修复...")
        execution_results = []

        # 先执行自动步骤
        for step in fix_plan.get("auto_steps", []):
            print(f"   执行: {step['description']}...")
            cmd_result = self.operator.execute_command(step["command"])
            execution_results.append({
                "step": step["description"],
                "command": step["command"],
                "success": cmd_result.success,
                "output": cmd_result.stdout[:200] if cmd_result.success else cmd_result.stderr[:200]
            })
            print(f"   {'✅' if cmd_result.success else '❌'} {cmd_result.stdout[:100] if cmd_result.success else cmd_result.stderr[:100]}")

        # 执行需要确认的步骤
        for step in fix_plan.get("risky_steps", []):
            print(f"\n   ⚠️  {step['description']} (需要管理员权限)")
            print(f"   命令: {step['command']}")
            cmd_result = self.operator.execute_command(step["command"], sudo=True)
            execution_results.append({
                "step": step["description"],
                "command": step["command"],
                "success": cmd_result.success,
                "output": cmd_result.stdout[:200] if cmd_result.success else cmd_result.stderr[:200]
            })
            print(f"   {'✅' if cmd_result.success else '❌'} {cmd_result.stdout[:100] if cmd_result.success else cmd_result.stderr[:100]}")

        result["execution"] = execution_results
        result["success"] = all(r["success"] for r in execution_results)
        result["steps"].append({"step": "execution", "done": True})

        # Step 6: 验证修复
        print("\n[Step 5] 验证修复...")
        verification = self.diagnose(classification["type"])
        remaining_issues = verification.get("issues", [])

        if remaining_issues:
            print(f"⚠️  仍有 {len(remaining_issues)} 个问题未解决:")
            for issue in remaining_issues:
                print(f"   - {issue}")
        else:
            print("✅ 所有问题已解决!")

        return result


def demo():
    """演示系统医生"""
    doctor = SystemDoctor()

    test_cases = [
        ("打印机连不上", False),
        ("没有声音了", False),
        ("网络连不上", False),
    ]

    print("=" * 60)
    print("🧪 系统医生 - 场景演示")
    print("=" * 60)

    for test_input, auto_exec in test_cases:
        print(f"\n\n{'#' * 60}")
        print(f"# 用户问题: {test_input}")
        print(f"#" * 60)
        result = doctor.run(test_input, auto_execute=auto_exec)


if __name__ == "__main__":
    demo()
