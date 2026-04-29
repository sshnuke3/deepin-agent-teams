#!/usr/bin/env python3
"""
deepin-agent-teams - 多智能体协作系统
主入口
"""
import argparse
import os
import sys
from scenarios import CodeAnalysisAssistant, LiteratureAssistant, EmailAssistant, SystemDoctor
from config import ERNIEBOT_ACCESS_TOKEN, DEFAULT_ACCESS_TOKEN


def parse_args():
    parser = argparse.ArgumentParser(description="deepin Agent Teams - 多智能体协作系统")
    parser.add_argument("task", nargs="?", help="要执行的任务描述")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--demo", "-d", choices=["code-analysis", "literature", "email", "doctor", "all"],
                        help="运行预设演示场景")
    parser.add_argument("--multi", "-m", action="store_true",
                        help="使用多进程多 Agent 模式")
    parser.add_argument("--extensible", "-e", action="store_true",
                        help="使用可扩展架构（能力驱动自主分工）")
    parser.add_argument("--v4", "-4", action="store_true",
                        help="使用 sessions_spawn v4 架构（OpenClaw 原生多 Agent）")
    parser.add_argument("--v41", "-41", action="store_true",
                        help="使用 v4.1 生产级架构（超时+重试+日志+降级）")
    parser.add_argument("--path", "-p", help="项目路径（用于代码分析场景）")
    parser.add_argument("--files", "-f", nargs="+", help="文件路径列表（用于文献综述场景）")
    parser.add_argument("--question", "-q", help="研究问题（用于文献综述场景）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出模式")
    return parser.parse_args()


def run_demo_all():
    """运行所有演示场景"""
    print("\n" + "=" * 60)
    print("🧪 deepin-agent-teams 演示模式")
    print("=" * 60)

    # 场景一：智能邮件助手
    print("\n\n" + "🔷" * 25)
    print("📧 场景一：智能邮件助手")
    print("-" * 40)
    assistant = EmailAssistant()
    result = assistant.run("给张三发邮件说项目进度")
    print(f"\n结果: {'✅' if result['success'] else '❌'}")

    # 场景二：系统问题诊断
    print("\n\n" + "🔷" * 25)
    print("🩺 场景二：系统问题诊断")
    print("-" * 40)
    doctor = SystemDoctor()
    result = doctor.run("打印机连不上了")
    print(f"\n结果: {'✅' if result['success'] else '❌'}")

    # 场景三：代码分析
    print("\n\n" + "🔷" * 25)
    print("🔍 场景三：代码分析助手")
    print("-" * 40)
    analyzer = CodeAnalysisAssistant()
    project_path = os.path.dirname(os.path.abspath(__file__))
    result = analyzer.run(f"分析 {project_path} 的代码")
    print(f"\n结果: {'✅' if result['success'] else '❌'}")

    print("\n\n" + "=" * 60)
    print("✅ 所有演示场景完成")
    print("=" * 60)


def main():
    args = parse_args()

    # 检查 API 凭证
    if not (ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN):
        print("⚠️  警告: 未设置 ERNIEBOT_ACCESS_TOKEN")
        print("   设置方式: cp .env.example .env && 编辑 .env 填入 token\n")

    # 演示模式
    if args.demo:
        if args.demo == "code-analysis":
            assistant = CodeAnalysisAssistant()
            path = args.path or os.path.dirname(os.path.abspath(__file__))
            assistant.run(f"分析 {path} 的代码")

        elif args.demo == "literature":
            if not args.files:
                print("❌ 文献综述场景需要: --files <文件列表> [--question <研究问题>]")
                return
            assistant = LiteratureAssistant()
            question = args.question or "请分析这些文献的核心观点"
            file_args = " ".join(args.files)
            assistant.run(f"分析 {question} {file_args}")

        elif args.demo == "email":
            assistant = EmailAssistant()
            assistant.run("给张三发邮件说项目进度", auto_send=False)

        elif args.demo == "doctor":
            doctor = SystemDoctor()
            doctor.run("打印机连不上了", auto_fix=False)

        elif args.demo == "all":
            run_demo_all()
        return

    # 多进程多 Agent 模式（真正并行）
    if args.multi:
        from agents.orchestrator import Orchestrator
        print("🚀 启动多进程多 Agent 模式...")
        orch = Orchestrator(verbose=True)
        result = orch.run(
            args.task or "分析当前项目",
            project_path=args.path or os.path.dirname(os.path.abspath(__file__))
        )
        print("\n" + "=" * 60)
        print("最终报告：")
        print("=" * 60)
        print(result["final_report"])
        return

    # 可扩展多 Agent 模式（能力驱动自主分工）
    if args.extensible:
        from agents.orchestrator_extensible import ExtensibleOrchestrator
        print("🚀 启动可扩展多 Agent 模式（能力驱动）...")
        orch = ExtensibleOrchestrator(verbose=True)
        result = orch.run(
            args.task or "分析当前项目",
            project_path=args.path or os.path.dirname(os.path.abspath(__file__))
        )
        print("\n" + "=" * 60)
        print("最终报告：")
        print("=" * 60)
        print(result["final_report"])
        return

    # v4 sessions_spawn 模式（OpenClaw 原生多 Agent）
    if args.v4:
        print("""🚀 v4 Sessions-Spawn 模式

此模式需要在 OpenClaw 对话中运行，输出 sessions_spawn 指令供直接执行。

使用方式：
python agents/sessions_orchestrator.py "你的任务"

将输出的 Python 指令复制到 OpenClaw 对话中执行，即可创建真正的 OpenClaw 子 Agent。
""")
        from agents.sessions_orchestrator import main as sessions_main
        sys.argv = ["sessions_orchestrator.py", args.task or "分析当前项目"]
        sessions_main()
        return

    # v4.1 生产级模式（超时+重试+日志+降级）
    if args.v41:
        print("""🚀 v4.1 生产级 Sessions-Spawn 模式

在 v4 基础上增加：
- 超时控制：单 Agent 超时 + 全局超时守护线程
- 重试机制：网络错误自动重试，指数退避
- 错误处理：子 Agent 失败不影响其他，优雅降级
- 结构化日志：彩色多级别日志 + 日志文件
- 状态跟踪：PENDING/RUNNING/DONE/FAILED/TIMEOUT
- 降级策略：任务分解失败时降级为单一 general 任务

使用方式（与 v4 相同）：
python agents/sessions_orchestrator_prod.py "你的任务"

将输出的 Python 指令复制到 OpenClaw 对话中执行。
""")
        from agents.sessions_orchestrator_prod import main as sessions_prod_main
        sys.argv = ["sessions_orchestrator_prod.py", args.task or "分析当前项目"]
        sessions_prod_main()
        return

    # 交互模式
    if args.interactive:
        print("\n" + "=" * 50)
        print("deepin-agent-teams 交互模式")
        print("=" * 50)
        print("可用场景：")
        print("  📧 邮件助手: '给张三发邮件说项目进度'")
        print("  🩺 系统诊断: '打印机连不上了'")
        print("  🔍 代码分析: '分析 /path/to/project 的代码'")
        print("  📚 文献阅读: '分析这些文献 /path/1.pdf 研究问题'")
        print("  输入 exit/quit 退出\n")

        scenarios = [
            EmailAssistant(),
            SystemDoctor(),
            CodeAnalysisAssistant(),
            LiteratureAssistant(),
        ]

        while True:
            try:
                user_input = input("\n👤 你: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "退出"):
                    print("再见！👋")
                    break

                # 尝试每个场景的意图识别
                handled = False
                for scenario in scenarios:
                    # 检查是否有待处理命令
                    if hasattr(scenario, 'pending_draft') and scenario.pending_draft:
                        result = scenario.handle_command(user_input)
                        if result.get("success"):
                            handled = True
                            break
                    if hasattr(scenario, 'last_analysis') and scenario.last_analysis:
                        result = scenario.handle_command(user_input)
                        if result.get("success"):
                            handled = True
                            break
                    if hasattr(scenario, 'last_review') and scenario.last_review:
                        result = scenario.handle_command(user_input)
                        if result.get("success"):
                            handled = True
                            break

                if not handled:
                    # 尝试各个场景
                    for scenario in scenarios:
                        result = scenario.run(user_input)
                        if result.get("success"):
                            handled = True
                            break

                    if not handled:
                        print("❌ 未识别到有效意图，请重试")

            except KeyboardInterrupt:
                print("\n\n再见！👋")
                break
        return

    # 默认：显示帮助
    print(__doc__)
    print("\n使用示例：")
    print("  python main.py -d all                              # 运行所有演示")
    print("  python main.py -d code-analysis -p /path/to/proj  # 代码分析演示")
    print("  python main.py -d literature -f a.pdf b.pdf -q 问题 # 文献综述演示")
    print("  python main.py -d email                            # 邮件助手演示")
    print("  python main.py -d doctor                           # 系统诊断演示")
    print("  python main.py -i                                  # 交互模式")
    print("  python main.py --v41 '分析项目'                    # v4.1 生产级模式")
    print("  python main.py -e '分析项目'                       # 可扩展架构")


if __name__ == "__main__":
    main()
