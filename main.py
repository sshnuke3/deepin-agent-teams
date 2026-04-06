#!/usr/bin/env python3
"""
deepin-agent-teams - 多智能体协作系统
主入口
"""
import argparse
import os
from agents import LeadAgent, ResearcherAgent, CoderAgent
from scenarios import CodeAnalysisScenario, LiteratureReviewScenario
from config import ERNIEBOT_ACCESS_TOKEN, DEFAULT_ACCESS_TOKEN


def parse_args():
    parser = argparse.ArgumentParser(description="deepin Agent Teams - 多智能体协作系统")
    parser.add_argument("task", nargs="?", help="要执行的任务描述")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--demo", "-d", choices=["code-analysis", "literature", "all"],
                        help="运行预设演示场景")
    parser.add_argument("--multi", "-m", action="store_true",
                        help="使用真正多进程多 Agent 模式（推荐）")
    parser.add_argument("--path", "-p", help="项目路径（用于代码分析场景）")
    parser.add_argument("--files", "-f", nargs="+", help="文件路径列表（用于文献综述场景）")
    parser.add_argument("--question", "-q", help="研究问题（用于文献综述场景）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出模式")
    return parser.parse_args()


def init_agents(verbose: bool = True):
    """初始化 Agent 系统"""
    researcher = ResearcherAgent(verbose=verbose)
    coder = CoderAgent(verbose=verbose)
    lead = LeadAgent(researcher, coder, verbose=verbose)
    return lead, researcher, coder


def run_demo_all(lead: LeadAgent, researcher: ResearcherAgent, coder: CoderAgent):
    """运行所有演示场景"""
    print("\n" + "="*60)
    print("🧪 deepin-agent-teams 演示模式")
    print("="*60)

    # 场景一：代码分析
    print("\n\n" + "🔷"*25)
    scenario1 = CodeAnalysisScenario(researcher, coder, lead)
    project_path = os.path.dirname(os.path.abspath(__file__))  # 分析自己
    result1 = scenario1.run(project_path)
    print("\n📄 生成的文档预览：")
    print("-"*40)
    print(result1[:1500] + "..." if len(result1) > 1500 else result1)

    # 场景二：文献综述
    print("\n\n" + "🔷"*25)
    print("📚 场景二演示（需要提供 PDF/文本文件）")
    print("   使用方式: python main.py --demo literature --files <file1> <file2> --question <问题>")
    print("-"*40)

    print("\n\n" + "="*60)
    print("✅ 所有演示场景完成")
    print("="*60)


def main():
    args = parse_args()
    verbose = args.verbose

    # 检查 API 凭证
    if not (ERNIEBOT_ACCESS_TOKEN or DEFAULT_ACCESS_TOKEN):
        print("⚠️  警告: 未设置 ERNIEBOT_ACCESS_TOKEN")
        print("   设置方式: cp .env.example .env && 编辑 .env 填入 token\n")

    # 初始化 Agent
    print("🚀 初始化 Agent 系统...")
    lead, researcher, coder = init_agents(verbose)

    # 演示模式
    if args.demo:
        if args.demo == "code-analysis":
            scenario = CodeAnalysisScenario(researcher, coder, lead)
            path = args.path or os.path.dirname(os.path.abspath(__file__))
            result = scenario.run(path)
            print("\n📄 生成的文档：")
            print("-"*40)
            print(result)

        elif args.demo == "literature":
            if not args.files or not args.question:
                print("❌ 文献综述场景需要: --files <文件列表> --question <研究问题>")
                return
            scenario = LiteratureReviewScenario(researcher, coder, lead)
            result = scenario.run(args.files, args.question)
            print("\n📄 生成的综述：")
            print("-"*40)
            print(result)

        elif args.demo == "all":
            run_demo_all(lead, researcher, coder)
        return

    # 多进程多 Agent 模式（真正并行）
    if args.multi:
        from agents.orchestrator import Orchestrator
        print("🚀 启动真正多进程多 Agent 模式...")
        orch = Orchestrator(verbose=True)
        result = orch.run(
            args.task or "分析当前项目",
            project_path=args.path or os.path.dirname(os.path.abspath(__file__))
        )
        print("\n" + "="*60)
        print("最终报告：")
        print("="*60)
        print(result["final_report"])
        return

    # 交互模式
    if args.interactive:
        print("\n" + "="*50)
        print("deepin-agent-teams 交互模式")
        print("输入你的需求，Ctrl+C 退出")
        print("="*50)
        print("可用命令：")
        print("  分析代码  /path/to/project  - 分析项目代码")
        print("  文献综述  <问题> [文件列表] - 生成文献综述")
        print("  exit/quit - 退出\n")

        while True:
            try:
                user_input = input("\n[你] ")
                if user_input.strip().lower() in ("exit", "quit", "退出"):
                    break
                response = lead.handle(user_input)
                print(f"\n[Lead] {response}\n")
            except KeyboardInterrupt:
                print("\n\n退出。")
                break
        return

    # 单任务模式
    if args.task:
        print(f"[任务] {args.task}\n")
        result = lead.handle(args.task)
        print("\n" + "="*50)
        print("最终输出：")
        print("="*50)
        print(result)
        return

    # 默认：显示帮助
    print(__doc__)
    print("\n使用示例：")
    print("  python main.py --demo code-analysis                    # 代码分析演示（单进程）")
    print("  python main.py -m '分析项目'                          # 多进程多 Agent（推荐）")
    print("  python main.py -m '分析项目' -p /path/to/project       # 多 Agent + 指定路径")
    print("  python main.py -i                                    # 交互模式")


if __name__ == "__main__":
    main()
