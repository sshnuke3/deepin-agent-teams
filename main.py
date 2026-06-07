#!/usr/bin/env python3
"""
deepin-agent-teams - 多智能体协作系统
主入口

使用方式：
  python main.py '分析项目代码'              # 直接执行任务（技能优先 → 编排器）
  python main.py -i                          # 交互模式
  python main.py --skills                    # 列出可用技能
  python main.py -d all                      # 运行所有演示
  python main.py -d code-analysis -p /path   # 代码分析演示
  python main.py -d email                    # 邮件助手演示
  python main.py -d doctor                   # 系统诊断演示
  python main.py --gui                       # GUI 模式（悬浮球+对话窗口）
  python main.py '分析项目' --mode workers    # 使用 Worker 池模式
"""
import argparse
import os
import sys

from config import ERNIEBOT_ACCESS_TOKEN, DEFAULT_ACCESS_TOKEN


def parse_args():
    parser = argparse.ArgumentParser(
        description="deepin Agent Teams - 多智能体协作系统（技能+编排器统一入口）"
    )
    parser.add_argument("task", nargs="?", help="要执行的任务描述")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument(
        "--demo", "-d",
        choices=["code-analysis", "literature", "email", "doctor", "all"],
        help="运行预设演示场景",
    )
    parser.add_argument("--gui", "-g", action="store_true", help="启动 GUI 模式")
    parser.add_argument("--skills", "-s", action="store_true", help="列出可用技能")
    parser.add_argument("--path", "-p", help="项目路径（用于代码分析）")
    parser.add_argument("--files", "-f", nargs="+", help="文件路径列表（用于文献综述）")
    parser.add_argument("--question", "-q", help="研究问题（用于文献综述）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出模式")
    parser.add_argument(
        "--mode", choices=["tools", "workers"], default="tools",
        help="编排器执行模式（默认 tools/MCP 工具驱动）",
    )
    parser.add_argument("--timeout", "-t", type=int, default=120, help="单任务超时秒数")
    parser.add_argument("--no-verifier", action="store_true", help="禁用 Verifier 验收")
    return parser.parse_args()


def _run_with_skill_or_orchestrator(task: str, args):
    """
    统一执行入口：先尝试技能匹配，失败则回退到编排器
    """
    from skills import find_skill, get_executor, SkillResult
    from agents.orchestrator import Orchestrator

    verbose = args.verbose

    # Step 1: 尝试技能匹配
    skill = find_skill(task)
    if skill:
        if verbose:
            print(f"🎯 匹配到技能: {skill.name} ({skill.description})")

        executor = get_executor()
        executor.verbose = verbose

        # 注入 LLM 调用器（使用 Orchestrator 的 LLM 通道）
        orch = Orchestrator(execution_mode="tools", verbose=False)
        executor.set_llm_caller(orch._call_llm)

        result = executor.execute(skill, task, interactive=False)

        if result.success:
            print("\n" + "=" * 60)
            print(f"📋 技能 [{skill.name}] 执行结果：")
            print("=" * 60)
            print(result.text_response)
            return

        if result.needs_clarification:
            print(f"\n❓ {result.clarification_question}")
            return

        if verbose:
            print(f"⚠️ 技能执行失败: {result.error}，回退到编排器...")

    # Step 2: 回退到编排器
    if verbose:
        print("🤖 使用 Orchestrator 执行任务...")

    orch = Orchestrator(
        execution_mode=args.mode,
        verbose=verbose,
        task_timeout=args.timeout,
        enable_verifier=not args.no_verifier,
    )
    project_path = args.path or os.path.dirname(os.path.abspath(__file__))

    if args.mode == "tools":
        orch.auto_connect_mcp_servers()

    result = orch.run(task, project_path=project_path)

    print("\n" + "=" * 60)
    print("📋 编排器执行报告：")
    print("=" * 60)
    print(result.final_report)


def run_demo_all():
    """运行所有演示场景"""
    from scenarios import CodeAnalysisAssistant, EmailAssistant, SystemDoctor

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

    # --skills: 列出可用技能
    if args.skills:
        from skills import list_skills_formatted
        print(list_skills_formatted())
        return

    # --demo: 演示模式
    if args.demo:
        from scenarios import CodeAnalysisAssistant, LiteratureAssistant, EmailAssistant, SystemDoctor

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

    # --gui: GUI 模式
    if args.gui:
        from gui.main_gui import main as gui_main
        gui_main()
        return

    # --interactive: 交互模式
    if args.interactive:
        _run_interactive(args)
        return

    # 有任务：技能优先 → 编排器
    if args.task:
        _run_with_skill_or_orchestrator(args.task, args)
        return

    # 默认：显示帮助
    print(__doc__)


def _run_interactive(args):
    """交互模式"""
    from skills import find_skill, get_executor, get_registry, list_skills_formatted

    print("\n" + "=" * 50)
    print("deepin-agent-teams 交互模式（技能+编排器）")
    print("=" * 50)
    print("输入任务即可自动匹配技能或使用编排器。")
    print("特殊命令：")
    print("  /skills     - 列出可用技能")
    print("  /history    - 查看执行历史")
    print("  /feedback   - 对上次执行提供反馈")
    print("  exit/quit   - 退出")
    print()

    executor = get_executor()
    executor.verbose = args.verbose
    last_result = None
    last_skill = None

    while True:
        try:
            user_input = input("👤 你: ").strip()
            if not user_input:
                continue

            # 特殊命令
            if user_input.lower() in ("exit", "quit", "退出"):
                print("再见！👋")
                break

            if user_input == "/skills":
                print(list_skills_formatted())
                continue

            if user_input == "/history":
                history = executor.get_execution_history()
                if not history:
                    print("暂无执行历史")
                else:
                    for h in history[-10:]:
                        status = "✅" if h["success"] else "❌"
                        fb = f" (反馈: {h['feedback']})" if h["feedback"] else ""
                        print(f"  {status} [{h['skill_name']}] {h['user_input']}{fb}")
                continue

            if user_input.startswith("/feedback"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1 and last_skill:
                    executor.record_feedback(last_skill, parts[1])
                    print("✅ 反馈已记录")
                else:
                    print("用法: /feedback <反馈内容>")
                continue

            # 处理多轮澄清
            if last_result and last_result.needs_clarification and last_skill:
                # 用户的回答用于补充缺失字段
                skill = get_registry().get_skill(last_skill)
                if skill:
                    answers = {}
                    for field_name in last_result.missing_fields:
                        answers[field_name] = user_input
                    result = executor.continue_execution(
                        skill, user_input, last_result, answers
                    )
                    last_result = result
                    last_skill = skill.name if result.success else None
                    if result.success:
                        print(f"\n📋 结果：\n{result.text_response}")
                    else:
                        print(f"\n❌ {result.error}")
                    continue

            # 尝试技能匹配
            skill = find_skill(user_input)
            if skill:
                result = executor.execute(skill, user_input, interactive=True)
                last_result = result
                last_skill = skill.name

                if result.success:
                    print(f"\n📋 技能 [{skill.name}] 结果：\n{result.text_response}")
                elif result.needs_clarification:
                    print(f"\n❓ {result.clarification_question}")
                else:
                    print(f"\n⚠️ 技能执行失败: {result.error}，尝试编排器...")
                    _run_orchestrator_fallback(user_input, args)
            else:
                # 无匹配技能 → 编排器
                _run_orchestrator_fallback(user_input, args)

        except KeyboardInterrupt:
            print("\n\n再见！👋")
            break


def _run_orchestrator_fallback(task: str, args):
    """编排器回退执行"""
    from agents.orchestrator import Orchestrator

    orch = Orchestrator(
        execution_mode=args.mode,
        verbose=args.verbose,
        task_timeout=args.timeout,
        enable_verifier=not args.no_verifier,
    )
    project_path = args.path or os.path.dirname(os.path.abspath(__file__))

    if args.mode == "tools":
        orch.auto_connect_mcp_servers()

    result = orch.run(task, project_path=project_path)
    print(f"\n📋 编排器结果：\n{result.final_report}")


if __name__ == "__main__":
    main()
