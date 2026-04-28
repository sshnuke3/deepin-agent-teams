#!/usr/bin/env python3
"""
deepin-agent-teams CLI
智能邮件助手 + 系统医生 统一入口

用法:
    python deepin_agent.py --email "给张三发邮件说项目进度"
    python deepin_agent.py --doctor "打印机连不上"
    python deepin_agent.py --interactive
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scenarios.email_assistant import EmailAssistant
from scenarios.system_doctor import SystemDoctor


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="deepin-agent-teams 智能助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python deepin_agent.py --email "给张三发邮件说项目进度"
  python deepin_agent.py --doctor "打印机连不上"
  python deepin_agent.py --interactive
        """
    )

    parser.add_argument(
        "--email", "-e",
        metavar="TEXT",
        help="执行邮件助手，输入邮件内容描述"
    )

    parser.add_argument(
        "--doctor", "-d",
        metavar="TEXT",
        help="执行系统医生，输入系统问题描述"
    )

    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="交互模式"
    )

    parser.add_argument(
        "--auto",
        action="store_true",
        help="自动执行修复（不询问确认）"
    )

    args = parser.parse_args()

    if args.email:
        assistant = EmailAssistant()
        assistant.run(args.email, auto_send=args.auto)

    elif args.doctor:
        doctor = SystemDoctor()
        doctor.run(args.doctor, auto_fix=args.auto)

    elif args.interactive:
        interactive_mode()

    else:
        parser.print_help()
        print("\n" + "=" * 50)
        print("🧪 快速测试")
        print("=" * 50)

        # 自动测试两个场景
        print("\n📧 场景一: 智能邮件助手")
        assistant = EmailAssistant()
        assistant.run("给张三发邮件说项目进度")

        print("\n\n🔧 场景二: 系统医生")
        doctor = SystemDoctor()
        doctor.run("打印机连不上", auto_fix=True)


def interactive_mode():
    """交互式对话"""
    print("=" * 60)
    print("🦞 deepin-agent-teams 智能助手")
    print("=" * 60)
    print("我可以帮你:")
    print("  📧 智能邮件 - 输入邮件内容，如'给张三发邮件说项目进度'")
    print("  🔧 系统医生 - 输入系统问题，如'打印机连不上'")
    print("  退出 - 结束对话")
    print("=" * 60)

    assistant = EmailAssistant()
    doctor = SystemDoctor()

    while True:
        try:
            user_input = input("\n👤 你: ").strip()

            if not user_input:
                continue

            if user_input in ["退出", "exit", "quit"]:
                print("再见! 👋")
                break

            # 简单判断走哪个场景
            email_keywords = ["邮件", "发给", "email", "发给", "发邮件"]
            is_email = any(kw in user_input.lower() for kw in email_keywords)

            if is_email:
                assistant.run(user_input)
            else:
                doctor.run(user_input)

        except KeyboardInterrupt:
            print("\n\n再见! 👋")
            break


if __name__ == "__main__":
    main()
