#!/usr/bin/env python3
"""
agents/sessions_orchestrator.py - v4 Sessions-Spawn 多 Agent 编排器

使用方式（两种）：

方式 A（推荐）：在 OpenClaw 对话中运行此脚本，它会输出 sessions_spawn 指令，
              然后直接把指令 COPY-PASTE 到 OpenClaw 对话里执行。

方式 B：直接运行 --auto 模式，由 erniebot 生成子 Agent 任务内容，
        但 sessions_spawn 本身仍需在 OpenClaw 上下文中调用。

本模块是真正的 v4 架构：基于 OpenClaw sessions_spawn 的原生多 Agent 协作。
"""
import json
import os
import sys
import erniebot


ERNIE_TOKEN = "0b93205ac0fc59d69166edb8e24cf1bc48aed453"


def init_ernie():
    erniebot.api_type = "aistudio"
    erniebot.access_token = ERNIE_TOKEN


# ========== 子 Agent System Prompts ==========

RESEARCHER_SYSTEM = """你是一个 Researcher Agent，在 deepin-agent-teams 多智能体系统中工作。

角色职责：
- 负责信息检索、文献分析、文件研究
- 使用 OpenClaw 内置工具（read, web_fetch, search, exec）完成任务

工作流程：
1. 收到 Lead Agent 发来的研究任务
2. 使用合适的工具收集信息（读文件、搜网页、抓取URL等）
3. 对信息进行分析和结构化
4. 用 Markdown 格式输出结构化研究报告
5. 以「[任务完成]」结尾

重要：
- 专注研究和信息收集，不要越界做代码分析
- 用工具完成任务，不要只输出文字"""

CODER_SYSTEM = """你是一个 Coder Agent，在 deepin-agent-teams 多智能体系统中工作。

角色职责：
- 负责代码分析、语法检查、文档生成
- 使用 OpenClaw 内置工具（read, exec, write）完成任务

工作流程：
1. 收到 Lead Agent 发来的编码分析任务
2. 使用合适的工具分析代码（读文件、执行检查命令、生成文档等）
3. 提取函数、类、import 等关键信息
4. 用 Markdown 格式输出结构化分析报告
5. 以「[任务完成]」结尾

重要：
- 专注代码分析和文档生成
- 用工具完成任务，不要只输出文字"""

GENERAL_SYSTEM = """你是一个 General Agent，在 deepin-agent-teams 多智能体系统中工作。

角色职责：
- 执行通用任务（Shell 命令、文件操作等）
- 使用 OpenClaw 内置工具（read, exec, write, search）完成任务

工作流程：
1. 收到 Lead Agent 发来的任务
2. 分析任务类型，选择合适的工具执行
3. 返回执行结果
4. 以「[任务完成]」结尾

重要：
- 执行通用任务，不专属于研究或编码
- 用工具完成任务，不要只输出文字"""


# ========== Capability 映射 ==========

CAPABILITY_TO_AGENT = {
    "web_search": "researcher",
    "web_fetcher": "researcher",
    "file_reader": "general",
    "dir_scanner": "general",
    "file_writer": "general",
    "shell_executor": "general",
    "code_analyzer": "coder",
    "ast_parser": "coder",
    "syntax_checker": "coder",
    "dependency_analyzer": "coder",
    "git_analyzer": "coder",
    "doc_generator": "coder",
    "markdown_writer": "general",
}


def get_agent_system(agent_type: str) -> str:
    mapping = {
        "researcher": RESEARCHER_SYSTEM,
        "coder": CODER_SYSTEM,
        "general": GENERAL_SYSTEM,
    }
    return mapping.get(agent_type, GENERAL_SYSTEM)


def get_agent_label(base_type: str, counter: dict) -> str:
    counter[base_type] = counter.get(base_type, 0) + 1
    return f"{base_type}-{counter[base_type]}"


# ========== 任务分解 ==========

def decompose(user_request: str) -> dict:
    """用 erniebot 将任务分解为 capabilities"""
    prompt = f"""用户需求：{user_request}

请将上述需求分解为具体的子任务。

输出格式为纯 JSON：
{{
  "tasks": [
    {{
      "id": "task-1",
      "description": "详细的任务描述",
      "capabilities_needed": ["cap1", "cap2"]
    }}
  ],
  "spawn_plan": [
    {{
      "agent_type": "researcher | coder | general",
      "agent_label": "如 researcher-1",
      "tasks": ["task-id-1"]
    }}
  ],
  "summary": "一句话总结"
}}

可用能力：file_reader, dir_scanner, file_writer, code_analyzer, ast_parser,
syntax_checker, dependency_analyzer, shell_executor, git_analyzer,
web_search, web_fetcher, doc_generator, markdown_writer

capability → agent_type 映射：
- web_search/web_fetcher → researcher
- code_analyzer/ast_parser/syntax_checker/dependency_analyzer/git_analyzer → coder
- 其余 → general

规则：
- spawn_plan 中每个 agent_label 必须唯一
- capabilities_needed 列出任务所需能力
- 只输出 JSON"""

    response = erniebot.ChatCompletion.create(
        model="ernie-lite",
        messages=[{"role": "user", "content": prompt}],
    )
    result = response.get_result() if hasattr(response, 'get_result') else str(response)

    try:
        return json.loads(result)
    except:
        return {
            "tasks": [{"id": "task-1", "description": user_request,
                      "capabilities_needed": ["shell_executor"]}],
            "spawn_plan": [{"agent_type": "general", "agent_label": "general-1",
                           "tasks": ["task-1"]}],
            "summary": user_request,
        }


# ========== 生成 sessions_spawn 指令 ==========

def generate_sessions_spawn(agent_type: str, label: str) -> str:
    """生成 sessions_spawn 调用代码"""
    system = get_agent_system(agent_type)
    return f"""sessions_spawn(
    task='''{system}

等待消息。收到任务后执行，完成后以「[任务完成]」结尾。''',
    label='{label}',
    mode='run',
    runTimeoutSeconds=120,
)"""


def generate_sessions_send(label: str, description: str) -> str:
    """生成 sessions_send 调用代码"""
    return f"""sessions_send(
    sessionKey='<{label}的childSessionKey>',
    message='''任务：{description}

请使用 OpenClaw 工具执行，完成后以「[任务完成]」结尾。''',
    timeoutSeconds=120,
)"""


def generate_instructions(plan: dict) -> str:
    """生成完整的可执行指令"""
    lines = []
    counter = {}

    lines.append("# v4 Sessions-Spawn 多 Agent 协作编排\n")
    lines.append(f"**需求**：`{plan.get('summary', '')}`\n")
    lines.append(f"**子任务数**：`{len(plan.get('tasks', []))}`\n")
    lines.append("---\n")

    # Step 1: Spawn
    lines.append("## Step 1: Spawn 子 Agent\n")
    for spawn in plan.get("spawn_plan", []):
        atype = spawn["agent_type"]
        label = spawn["agent_label"]
        lines.append(f"### {label}（{atype} Agent）\n")
        lines.append("```python")
        lines.append(generate_sessions_spawn(atype, label))
        lines.append("```\n")

    # Step 2: 获取 sessionKey
    lines.append("## Step 2: 获取 childSessionKey\n")
    lines.append("运行上述 `sessions_spawn` 后会返回 JSON：\n")
    lines.append("```json\n")
    lines.append('{"status": "accepted", "childSessionKey": "agent:main:subagent:<uuid>", ...}')
    lines.append("```\n")
    lines.append("记录每个 Agent 的 `<uuid>` 部分，填入下方的 `sessionKey`。\n")

    # Step 3: 发送任务
    lines.append("## Step 3: 分发任务\n")
    task_map = {t["id"]: t for t in plan.get("tasks", [])}
    for spawn in plan.get("spawn_plan", []):
        label = spawn["agent_label"]
        for tid in spawn.get("tasks", []):
            t = task_map.get(tid, {})
            if t:
                lines.append(f"### {label} ← 任务 [{tid}]\n")
                lines.append(f"**描述**：`{t.get('description', '')}`\n")
                lines.append(f"**能力**：`{', '.join(t.get('capabilities_needed', []))}`\n")
                lines.append("```python")
                lines.append(generate_sessions_send(label, t.get("description", "")))
                lines.append("```\n")

    # Step 4: 整合
    lines.append("## Step 4: 整合结果\n")
    lines.append("所有子 Agent 返回后，收集 Markdown 格式结果，整合为最终报告。\n")

    return "".join(lines)


# ========== Auto 模式（生成子 Agent 任务内容） ==========

def generate_subagent_task_content(plan: dict) -> dict:
    """生成每个子 Agent 的完整任务内容（用于 auto 模式）"""
    contents = {}
    for spawn in plan.get("spawn_plan", []):
        label = spawn["agent_label"]
        system = get_agent_system(spawn["agent_type"])
        task_ids = spawn.get("tasks", [])
        task_map = {t["id"]: t for t in plan.get("tasks", [])}

        task_descriptions = []
        for tid in task_ids:
            t = task_map.get(tid, {})
            if t:
                task_descriptions.append(f"- **{t.get('description', '')}**（能力：{', '.join(t.get('capabilities_needed', []))})")

        content = f"""{system}

你的任务：

{chr(10).join(task_descriptions)}

请执行上述任务，使用 OpenClaw 工具收集信息并分析，完成后以「[任务完成]」结尾。"""

        contents[label] = {
            "agent_type": spawn["agent_type"],
            "content": content,
            "tasks": task_descriptions,
        }

    return contents


# ========== 主函数 ==========

def main():
    import argparse
    parser = argparse.ArgumentParser(description="v4 Sessions-Spawn 多 Agent 编排器")
    parser.add_argument("task", nargs="?", help="要执行的任务描述")
    parser.add_argument("--auto", "-a", action="store_true",
                        help="生成完整的任务内容（不含 sessions_spawn 调用）")
    parser.add_argument("--output", "-o", help="输出到文件")
    args = parser.parse_args()

    if not args.task:
        print("用法: python sessions_orchestrator.py '<任务>'")
        print("   或: python sessions_orchestrator.py '<任务>' --auto")
        return

    init_ernie()
    print(f"分析任务：{args.task[:50]}...\n", file=sys.stderr)

    plan = decompose(args.task)
    print(f"分解完成：{len(plan.get('tasks', []))} 个子任务\n", file=sys.stderr)

    if args.auto:
        # 生成子 Agent 完整任务内容
        contents = generate_subagent_task_content(plan)
        print(json.dumps(contents, ensure_ascii=False, indent=2))
        return

    instructions = generate_instructions(plan)
    print(instructions)

    if args.output:
        with open(args.output, "w") as f:
            f.write(instructions)
        print(f"\n已保存到 {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
