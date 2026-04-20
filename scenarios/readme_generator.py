#!/usr/bin/env python3
"""
scenarios/readme_generator.py - 自动生成 README 场景

工作流程：
1. sessions_spawn 并行创建两个子 Agent：
   - StructureAgent：扫描项目目录结构
   - CoreAgent：分析核心代码文件
2. sessions_send 向两个 Agent 发送任务
3. 汇总两份报告，erniebot 生成 README
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_instructions(project_path: str, project_name: str = "") -> str:
    """生成 sessions_spawn + sessions_send 指令序列"""
    pname = project_name or os.path.basename(project_path.rstrip("/"))

    lines = []
    lines.append("# README 自动生成场景 - sessions_spawn 并行执行\n")
    lines.append(f"**项目**：`{pname}`\n")
    lines.append(f"**路径**：`{project_path}`\n\n")
    lines.append("---\n\n")

    # Step 1: Spawn 两个并行子 Agent
    lines.append("## Step 1: 同时创建两个子 Agent\n")
    lines.append("```python\n")
    lines.append("sessions_spawn(\n")
    lines.append("    task='''你是一个项目结构分析 Agent。\n\n你的职责：\n1. 递归扫描项目目录 " + project_path + "，列出所有文件（忽略 __pycache__、.git、node_modules 等）\n2. 识别项目类型（Python/JS/Go/C++ 等）\n3. 列出目录树结构（深度 3 层）\n4. 识别关键文件：入口文件、配置文件、依赖文件\n5. 分析完毕后以「[任务完成]」结尾\n\n使用 exec 工具执行 find/ls 等命令收集信息。'''")
    lines.append("    ,\n")
    lines.append("    label='structure-agent',\n")
    lines.append("    mode='run',\n")
    lines.append("    runTimeoutSeconds=90,\n")
    lines.append(")\n")
    lines.append("```\n\n")

    lines.append("```python\n")
    lines.append("sessions_spawn(\n")
    lines.append("    task='''你是一个核心代码分析 Agent。\n\n你的职责：\n1. 进入项目 " + project_path + "\n2. 找到核心代码文件（主入口、最重要的模块）\n3. 使用 read 工具读取这些文件的内容\n4. 分析每个文件的作用、关键函数/类、依赖关系\n5. 总结项目的主要功能和技术栈\n6. 分析完毕后以「[任务完成]」结尾\n\n使用 read 工具读取代码文件，使用 exec 执行 find/grep 等命令定位文件。'''")
    lines.append("    ,\n")
    lines.append("    label='core-agent',\n")
    lines.append("    mode='run',\n")
    lines.append("    runTimeoutSeconds=90,\n")
    lines.append(")\n")
    lines.append("```\n\n")

    # Step 2: 分发任务
    lines.append("## Step 2: 获取 childSessionKey 并分发任务\n")
    lines.append("运行上述两个 spawn 后，记录返回的 `childSessionKey`：\n")
    lines.append("- structure-agent 的 childSessionKey\n")
    lines.append("- core-agent 的 childSessionKey\n\n")
    lines.append("然后分别发送任务：\n\n")
    lines.append("```python\n")
    lines.append("sessions_send(\n")
    lines.append("    sessionKey='<structure-agent 的 childSessionKey>',\n")
    lines.append("    message='开始分析项目结构。',\n")
    lines.append("    timeoutSeconds=90,\n")
    lines.append(")\n")
    lines.append("```\n\n")
    lines.append("```python\n")
    lines.append("sessions_send(\n")
    lines.append("    sessionKey='<core-agent 的 childSessionKey>',\n")
    lines.append("    message='开始分析核心代码。',\n")
    lines.append("    timeoutSeconds=90,\n")
    lines.append(")\n")
    lines.append("```\n\n")

    # Step 3: 汇总
    lines.append("## Step 3: 汇总结果\n")
    lines.append("收集两个 Agent 的输出后，用 erniebot 生成最终 README。\n\n")
    lines.append("将以下代码中的 `<structure-agent 输出>` 和 `<core-agent 输出>` 替换为实际返回内容，\n")
    lines.append("然后在本地运行（需要配置 erniebot API）：\n\n")
    lines.append("```python\n")
    lines.append("import erniebot\n")
    lines.append("erniebot.api_type = 'aistudio'\n")
    lines.append("erniebot.access_token = '0b93205ac0fc59d69166edb8e24cf1bc48aed453'\n\n")
    lines.append("prompt = \"\"\"项目：" + pname + "\n\n")
    lines.append("结构分析结果：\n<structure-agent 的输出>\n\n")
    lines.append("核心代码分析结果：\n<core-agent 的输出>\n\n")
    lines.append("请生成一份完整的 README.md，包含：\n")
    lines.append("1. 项目简介（一句话描述）\n")
    lines.append("2. 功能特性（3-5个亮点）\n")
    lines.append("3. 目录结构\n")
    lines.append("4. 技术栈\n")
    lines.append("5. 快速开始（安装+运行）\n")
    lines.append("6. 使用示例\n\n")
    lines.append("只输出 Markdown，不要其他内容。\"\"\"\n\n")
    lines.append("response = erniebot.ChatCompletion.create(\n")
    lines.append("    model='ernie-lite',\n")
    lines.append("    messages=[{'role': 'user', 'content': prompt}],\n")
    lines.append(")\n")
    lines.append("print(response.get_result())\n")
    lines.append("```\n")

    return "".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="README 自动生成场景")
    parser.add_argument("path", nargs="?", default=".", help="项目路径")
    parser.add_argument("--name", "-n", help="项目名称（用于 README）")
    parser.add_argument("--output", "-o", help="输出到文件")
    args = parser.parse_args()

    project_path = os.path.abspath(args.path)
    project_name = args.name or os.path.basename(project_path.rstrip("/"))

    print(f"项目：{project_name}")
    print(f"路径：{project_path}\n")

    instructions = get_instructions(project_path, project_name)

    if args.output:
        with open(args.output, "w") as f:
            f.write(instructions)
        print(f"已保存到 {args.output}")
    else:
        print(instructions)


if __name__ == "__main__":
    main()
