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
    1. 问题分类 → 2. 系统诊断 → 3. 修复方案 → 4. 执行修复
    """

    def __init__(self):
        self.operator = SystemOperator()
        self.collector = InformationCollector()
        # 多轮对话状态
        self._clarification_pending: Optional[Dict] = None
        # 最近一次修复结果（用于效果验证）
        self._last_fix_result: Optional[Dict] = None

        self.issue_keywords = {
            "audio": ["声音", "音频", "声卡", "没声", "audio", "sound", "sound card"],
            "network": ["网络", "wifi", "网", "上不了", "network", "internet"],
            "printer": ["打印", "打印机", "print", "printer"],
            "bluetooth": ["蓝牙", "bluetooth", "蓝牙耳机"],
            "install": ["安装", "装", "install", "app"],
        }

    def classify_issue(self, user_input: str) -> Dict:
        """分类问题类型"""
        text_lower = user_input.lower()
        scores = {}

        for issue_type, keywords in self.issue_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[issue_type] = score

        if not scores:
            return {"type": "unknown", "confidence": 0, "scores": {}, "original": user_input}

        max_type = max(scores.items(), key=lambda x: x[1])
        confidence = min(max_type[1] * 0.4, 0.95)

        return {
            "type": max_type[0],
            "confidence": confidence,
            "scores": scores,
            "original": user_input
        }

    def diagnose(self, issue_type: str) -> Dict:
        """执行诊断"""
        from perception.system_monitor import (
            diagnose_audio, diagnose_network, diagnose_printer, diagnose_bluetooth
        )

        diag_funcs = {
            "audio": diagnose_audio,
            "network": diagnose_network,
            "printer": diagnose_printer,
            "bluetooth": diagnose_bluetooth,
        }

        diag_func = diag_funcs.get(issue_type)
        if diag_func:
            return diag_func()
        return {"error": f"Unknown issue type: {issue_type}"}

    def generate_fix_plan(self, issue_type: str, diagnosis: Dict) -> Dict:
        """生成修复方案"""
        issues = diagnosis.get("issues", [])

        fix_plan = {
            "issue_type": issue_type,
            "problems": issues,
            "steps": [],
            "auto_steps": [],
            "confirm_steps": [],
        }

        commands = {
            "audio": {
                "auto": [
                    ("检查音量状态", "amixer get Master"),
                    ("检查静音状态", "amixer get Master | grep -i mute"),
                ],
                "confirm": [
                    ("取消静音", "amixer set Master unmute", "取消系统静音"),
                    ("重启音频服务", "systemctl restart pulseaudio", "重启音频服务（需要sudo）"),
                ]
            },
            "network": {
                "auto": [
                    ("检查网络设备", "nmcli device status"),
                    ("检查连接状态", "ip addr show"),
                    ("测试网络连通性", "ping -c 1 -W 2 8.8.8.8"),
                ],
                "confirm": [
                    ("重启网络管理器", "systemctl restart NetworkManager", "重启网络服务（需要sudo）"),
                    ("启用网络", "nmcli networking on", "启用网络连接（需要sudo）"),
                ]
            },
            "printer": {
                "auto": [
                    ("检查CUPS服务", "systemctl status cups"),
                    ("列出打印机", "lpstat -a"),
                ],
                "confirm": [
                    ("重启CUPS服务", "systemctl restart cups", "重启打印服务（需要sudo）"),
                    ("启用所有打印机", "cupsenable all", "启用所有打印机（需要sudo）"),
                ]
            },
            "bluetooth": {
                "auto": [
                    ("检查蓝牙状态", "rfkill list bluetooth"),
                    ("检查蓝牙服务", "systemctl status bluetooth"),
                ],
                "confirm": [
                    ("启动蓝牙服务", "systemctl start bluetooth", "启动蓝牙（需要sudo）"),
                    ("解锁蓝牙", "rfkill unblock bluetooth", "解锁蓝牙射频（需要sudo）"),
                ]
            }
        }

        cmd_set = commands.get(issue_type, {})
        for desc, cmd in cmd_set.get("auto", []):
            fix_plan["auto_steps"].append({"description": desc, "command": cmd})

        for desc, cmd, reason in cmd_set.get("confirm", []):
            fix_plan["confirm_steps"].append({
                "description": desc,
                "command": cmd,
                "reason": reason,
                "sudo": True
            })

        return fix_plan

    def execute_fix(self, fix_plan: Dict) -> Dict:
        """执行修复方案"""
        results = {
            "auto_results": [],
            "confirm_results": [],
            "all_success": True,
        }

        # 执行自动步骤
        print("\n" + "=" * 50)
        print("🔧 执行自动修复步骤...")
        print("=" * 50)

        for step in fix_plan.get("auto_steps", []):
            print(f"\n▶ {step['description']}...")
            print(f"  命令: {step['command']}")

            result = self.operator.execute_command(step["command"], timeout=15)
            success = result.success

            output = result.stdout[:300] if result.stdout else result.stderr[:300]
            print(f"  {'✅ 成功' if success else '❌ 失败'}: {output}")

            results["auto_results"].append({
                "step": step["description"],
                "success": success,
                "output": output
            })
            if not success:
                results["all_success"] = False

        # 执行确认步骤
        if fix_plan.get("confirm_steps"):
            print("\n" + "=" * 50)
            print("⚠️  需要确认的修复步骤（需要管理员权限）")
            print("=" * 50)

            for i, step in enumerate(fix_plan["confirm_steps"], 1):
                print(f"\n{i}. {step['description']}")
                print(f"   命令: {step['command']}")
                print(f"   原因: {step['reason']}")

                # 自动执行确认步骤（实际场景中应询问用户）
                response = input("   执行? [Y/n]: ").strip().lower()
                if response in ["", "y", "yes"]:
                    print(f"   正在执行...")
                    result = self.operator.execute_command(step["command"], timeout=15, sudo=True)
                    success = result.success
                    output = result.stdout[:300] if result.stdout else result.stderr[:300]
                    print(f"   {'✅ 成功' if success else '❌ 失败'}: {output}")
                    results["confirm_results"].append({
                        "step": step["description"],
                        "success": success,
                        "output": output
                    })
                    if not success:
                        results["all_success"] = False
                else:
                    print(f"   ⏭️  已跳过")
                    results["confirm_results"].append({
                        "step": step["description"],
                        "success": False,
                        "skipped": True
                    })

        return results

    def run(self, user_input: str, auto_fix: bool = False) -> Dict:
        """
        执行系统诊断修复（支持多轮对话/意图澄清）

        Args:
            user_input: 用户问题描述
            auto_fix: 是否自动执行修复

        Returns:
            执行结果
        """
        print(f"\n🔧 系统医生")
        print(f"问题: {user_input}")
        print("=" * 50)

        result = {
            "success": False,
            "issue_type": None,
            "diagnosis": None,
            "fix_plan": None,
            "execution": None,
            "steps": [],
            "needs_clarification": False,
        }

        # 处理多轮对话：有待回答的澄清问题
        if self._clarification_pending:
            return self._continue_clarification(user_input, auto_fix)

        # Step 1: 问题分类
        print("\n[Step 1] 问题分类...")
        classification = self.classify_issue(user_input)
        result["issue_type"] = classification["type"]
        result["steps"].append({"step": "classification", "done": True})

        if classification["type"] == "unknown":
            # 多轮澄清：问题描述不清时主动追问
            question = self._build_clarification_question(user_input)
            print(f"\n🤔 {question}")
            self._clarification_pending = {
                "original_input": user_input,
                "question": question,
            }
            result["needs_clarification"] = True
            result["question"] = question
            result["success"] = True
            return result

        type_names = {
            "audio": "音频/声音",
            "network": "网络",
            "printer": "打印机",
            "bluetooth": "蓝牙",
            "install": "软件安装"
        }
        print(f"✅ 识别为: {type_names.get(classification['type'], classification['type'])}")
        print(f"   置信度: {classification['confidence']:.0%}")

        # Step 2: 系统诊断
        print("\n[Step 2] 系统诊断...")
        diagnosis = self.diagnose(classification["type"])
        result["diagnosis"] = diagnosis
        result["steps"].append({"step": "diagnosis", "done": True})

        issues = diagnosis.get("issues", [])
        if issues:
            print(f"\n⚠️  发现 {len(issues)} 个问题:")
            for issue in issues:
                print(f"   • {issue}")
        else:
            print("✅ 未发现明显问题")

        # 打印诊断详情
        checks = diagnosis.get("checks", {})
        if checks:
            print("\n诊断详情:")
            for key, value in checks.items():
                if isinstance(value, bool):
                    status = "✅" if value else "❌"
                    print(f"   {status} {key}: {value}")
                else:
                    print(f"   • {key}: {str(value)[:50]}")

        # Step 3: 生成修复方案
        print("\n[Step 3] 修复方案...")
        fix_plan = self.generate_fix_plan(classification["type"], diagnosis)
        result["fix_plan"] = fix_plan
        result["steps"].append({"step": "fix_plan", "done": True})

        print(f"\n📋 修复方案:")
        if fix_plan["auto_steps"]:
            print(f"\n  自动步骤 ({len(fix_plan['auto_steps'])} 项):")
            for i, step in enumerate(fix_plan["auto_steps"], 1):
                print(f"    {i}. {step['description']}")

        if fix_plan["confirm_steps"]:
            print(f"\n  需确认步骤 ({len(fix_plan['confirm_steps'])} 项):")
            for i, step in enumerate(fix_plan["confirm_steps"], 1):
                print(f"    {i}. {step['description']} ({step['reason']})")

        # Step 4: 执行修复
        if auto_fix or (not issues and not fix_plan["confirm_steps"]):
            print("\n[Step 4] 执行修复...")
            execution = self.execute_fix(fix_plan)
            result["execution"] = execution
            self._last_fix_result = execution
            result["steps"].append({"step": "execution", "done": True})

            # Step 5: 验证修复（赛题明确要求）
            print("\n[Step 5] 验证修复效果...")
            verification = self.verify_fix(classification["type"])
            result["verification"] = verification
            result["steps"].append({"step": "verification", "done": True, "resolved": verification["resolved"]})

            if not verification["resolved"] and verification["remaining_issues"]:
                # 未解决时给出替代方案
                print("\n💡 替代方案建议:")
                print("  1. 检查硬件连接是否正常")
                print("  2. 尝试重启系统")
                print("  3. 查看系统日志获取更多信息")

        result["success"] = True
        return result

    def _build_clarification_question(self, user_input: str) -> str:
        """生成澄清追问：问题描述不清时主动询问具体是什么问题"""
        return (
            "🤔 我不太确定你遇到了什么问题，能具体描述一下吗？\n"
            "\n比如：\n"
            "  • 打印机连不上 / 打印没反应\n"
            "  • 没声音了 / 音频播放异常\n"
            "  • 网络连不上 / WiFi断了\n"
            "  • 蓝牙连不上\n"
            "  • 想安装某个软件"
        )

    def _continue_clarification(self, user_input: str, auto_fix: bool) -> Dict:
        """处理用户对澄清问题的回答，继续诊断流程"""
        self._clarification_pending = None

        # 重新分类（用用户的补充描述）
        classification = self.classify_issue(user_input)

        if classification["type"] == "unknown":
            # 仍然无法识别，尝试全系统扫描
            print("❌ 仍然无法识别问题类型，进行系统全面扫描...")
            result = {"success": True, "steps": [], "needs_clarification": False}
            summary = self.operator.execute_command(
                "echo '=== 系统信息 ===' && uname -a && uptime && "
                "echo '=== 磁盘 ===' && df -h | head -5 && "
                "echo '=== 内存 ===' && free -h && "
                "echo '=== 网络 ===' && ip addr show | grep inet && "
                "echo '=== 最近错误 ===' && journalctl -p err -n 10 --no-pager",
                timeout=15
            )
            result["system_info"] = summary.stdout if summary.success else summary.stderr
            print("\n📋 系统全面信息:")
            print(result["system_info"][:500])
            return result

        # 识别成功，用新的输入重新走诊断流程
        print(f"✅ 已识别为: {classification['type']}，开始诊断...")
        return self.run(user_input, auto_fix=auto_fix)

    def verify_fix(self, issue_type: str, wait_seconds: int = 3) -> Dict:
        """
        修复效果验证：修复后重新检查系统状态

        Returns:
            {resolved: bool, remaining_issues: list}
        """
        import time
        print(f"\n🔍 验证修复效果（等待{wait_seconds}秒）...")
        time.sleep(wait_seconds)

        verification = self.diagnose(issue_type)
        remaining = verification.get("issues", [])

        result = {
            "resolved": len(remaining) == 0,
            "remaining_issues": remaining,
            "checks": verification.get("checks", {}),
        }

        if result["resolved"]:
            print("✅ 验证通过：所有问题已解决！")
        else:
            print(f"⚠️ 验证未通过：仍有 {len(remaining)} 个问题:")
            for issue in remaining:
                print(f"   • {issue}")
            print("\n💡 建议尝试其他方案或联系系统管理员")

        return result

    def handle_command(self, command: str) -> Dict:
        """处理用户回复"""
        cmd_lower = command.lower().strip()

        if cmd_lower in ["执行", "fix", "repair", "修复"]:
            return {"action": "execute", "message": "开始执行修复"}
        elif cmd_lower in ["取消", "cancel"]:
            return {"action": "cancel", "message": "已取消"}
        else:
            return {"action": "unknown", "message": f"未知命令: {command}"}


def demo():
    """演示系统医生"""
    doctor = SystemDoctor()

    test_cases = [
        ("打印机连不上", True),
        ("没有声音了", True),
        ("网络连不上", True),
    ]

    print("=" * 60)
    print("🔧 系统医生 - 场景演示")
    print("=" * 60)

    for test_input, auto in test_cases:
        print(f"\n{'#'*60}")
        print(f"# 问题: {test_input}")
        print(f"#" * 60)
        result = doctor.run(test_input, auto_fix=auto)
        print(f"\n结果: {'✅' if result['success'] else '❌'}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        print("🔧 系统医生 - 交互模式")
        print("输入系统问题描述，或'退出'结束\n")
        doctor = SystemDoctor()
        while True:
            try:
                user_input = input("\n👤 你: ").strip()
                if not user_input:
                    continue
                if user_input in ["退出", "exit"]:
                    break
                doctor.run(user_input, auto_fix=False)
            except KeyboardInterrupt:
                break
        print("再见!")
    else:
        demo()
