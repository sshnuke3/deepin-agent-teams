#!/usr/bin/env python3
"""
deepin-agent-teams - 多智能体协作系统
主入口
"""
import argparse
from agents import LeadAgent, ResearcherAgent, CoderAgent
from config import ERNIEBOT_API_KEY, ERNIEBOT_SECRET_KEY


def parse_args():
    parser = argparse.ArgumentParser(description="deepin Agent Teams - 多智能体协作系统")
    parser.add_argument("task", nargs="?", help="要执行的任务描述")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--agent", choices=["lead", "researcher", "coder"], 
                        help="单独运行某个 Agent")
    parser.add_argument("--demo", choices=["code-analysis", "literature"],
                        help="运行预设演示场景")
    return parser.parse_args()


def interactive_mode(lead: LeadAgent):
    """交互式对话"""
    print("=" * 50)
    print("deepin-agent-teams 交互模式")
    print("输入你的需求，Ctrl+C 退出")
    print("=" * 50)
    
    while True:
        try:
            user_input = input("\n[你] ")
            if user_input.strip().lower() in ("exit", "quit", "退出"):
                break
            response = lead.handle(user_input)
            print(f"\n[Lead] {response}")
        except KeyboardInterrupt:
            print("\n\n退出。")
            break


def demo_code_analysis(lead: LeadAgent):
    """演示场景一：项目代码分析 + 文档生成"""
    task = "分析当前项目目录 /root/.openclaw/workspace/deepin-agent-teams 的代码结构，并生成项目文档"
    print(f"[DEMO] 运行代码分析场景...\n")
    result = lead.handle(task)
    print("\n" + "=" * 50)
    print("最终输出：")
    print("=" * 50)
    print(result)


def main():
    args = parse_args()
    
    # 检查 API 凭证
    if not ERNIEBOT_API_KEY:
        print("⚠️  警告: 未设置 ERNIEBOT_API_KEY，部分功能可能受限")
        print("   设置方式: export ERNIEBOT_API_KEY=your_key")
    
    # 初始化 Agent
    print("🚀 初始化 Agent 系统...")
    researcher = ResearcherAgent(verbose=False)
    coder = CoderAgent(verbose=False)
    lead = LeadAgent(researcher, coder, verbose=True)
    
    if args.demo:
        if args.demo == "code-analysis":
            demo_code_analysis(lead)
        return
    
    if args.agent:
        # 单独运行某个 Agent
        agent_map = {"lead": lead, "researcher": researcher, "coder": coder}
        agent = agent_map[args.agent]
        print(f"运行 {args.agent} Agent（输入 exit 退出）...")
        while True:
            try:
                user_input = input(f"[{args.agent}] ")
                if user_input.strip().lower() in ("exit", "quit"):
                    break
                print(agent.chat(user_input))
            except KeyboardInterrupt:
                break
        return
    
    if args.task:
        # 执行指定任务
        print(f"[Task] {args.task}\n")
        result = lead.handle(args.task)
        print("\n" + "=" * 50)
        print("最终输出：")
        print("=" * 50)
        print(result)
        return
    
    if args.interactive:
        interactive_mode(lead)
        return
    
    # 默认：交互模式
    interactive_mode(lead)


if __name__ == "__main__":
    main()
