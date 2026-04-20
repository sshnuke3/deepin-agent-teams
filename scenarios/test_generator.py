#!/usr/bin/env python3
"""
scenarios/test_generator.py - 自动生成测试用例场景

工作流程：
1. erniebot 分析项目结构，确定要测试的模块
2. sessions_spawn 创建多个并行子 Agent，每个负责一个模块
3. 各 Agent 分析代码后生成对应的测试文件
4. 汇总所有测试文件

优势：多个模块同时被分析，并行节省时间
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_instructions(project_path: str, project_name: str = "", test_framework: str = "pytest") -> str:
    """生成多 Agent 并行生成测试用例的指令"""
    pname = project_name or os.path.basename(project_path.rstrip("/"))

    instructions = []
    instructions.append("# 自动生成测试用例场景 - 多 Agent 并行执行\n\n")
    instructions.append(f"**项目**：`{pname}`\n")
    instructions.append(f"**路径**：`{project_path}`\n")
    instructions.append(f"**测试框架**：`{test_framework}`\n\n")
    instructions.append("---\n\n")

    # Step 1: 分析项目，确定要测试的模块
    instructions.append("## Step 1: 先了解项目结构\n")
    instructions.append("建议先用 StructureAgent 扫描项目，识别要测试的模块数量。\n\n")
    instructions.append("```python\n")
    instructions.append("sessions_spawn(\n")
    instructions.append("    task='''你是一个项目分析 Agent。\n\n你的职责：\n1. 扫描 `{project_path}` 项目目录\n2. 识别所有源代码文件（.py / .js / .go 等）\n3. 列出所有模块/文件，标注哪个是核心模块\n4. 判断项目使用的测试框架（pytest / unittest / jest / testing 等）\n5. 输出一个模块列表，包含：文件名、文件路径、是否是核心模块\n\n注意：只分析，不修改任何文件。分析完毕后以「[任务完成]」结尾。'''".replace("{project_path}", project_path))
    instructions.append("    ,\n")
    instructions.append("    label='project-scanner',\n")
    instructions.append("    mode='run',\n")
    instructions.append("    runTimeoutSeconds=60,\n")
    instructions.append(")\n")
    instructions.append("```\n\n")

    # Step 2: 根据扫描结果创建测试 Agent
    instructions.append("## Step 2: 为每个核心模块创建测试 Agent\n")
    instructions.append("假设项目有 3 个核心模块：`module_a.py`、`module_b.py`、`module_c.py`，\n")
    instructions.append("可以并行创建 3 个 TestAgent，每个负责一个模块：\n\n")

    for i, module in enumerate(["module_a", "module_b", "module_c"], 1):
        instructions.append(f"### TestAgent-{i}：{module}\n")
        instructions.append("```python\n")
        instructions.append("sessions_spawn(\n")
        instructions.append(f"    task='''你是一个测试工程师 Agent，负责为 `{module}` 模块编写测试用例。\n\n你的职责：\n1. 使用 read 工具读取 `{project_path}/{module}.py` 源码\n2. 分析模块中的函数和类\n3. 使用 exec 工具为每个公开函数生成测试用例\n4. 测试用例要求：\n   - 覆盖正常输入和边界条件\n   - 包含至少 2 个异常输入测试\n   - 使用 `assert` 语句，不要只写 print\n5. 输出格式：直接输出完整的测试文件内容（Python 代码）\n6. 使用 {test_framework} 框架\n\n完成后以「[任务完成]」结尾。'''".replace("{project_path}", project_path).replace("{test_framework}", test_framework))
        instructions.append("    ,\n")
        instructions.append(f"    label='test-agent-{i}',\n")
        instructions.append("    mode='run',\n")
        instructions.append("    runTimeoutSeconds=90,\n")
        instructions.append(")\n")
        instructions.append("```\n\n")

    # Step 3: 收集
    instructions.append("## Step 3: 收集并合并测试文件\n")
    instructions.append("所有 TestAgent 返回后，收集每个 Agent 的测试代码片段，\n")
    instructions.append("合并到一个 `test_all.py` 文件中（或按模块拆分到不同文件）。\n\n")
    instructions.append("```bash\n")
    instructions.append(f"# 创建 tests 目录\n")
    instructions.append(f"mkdir -p {project_path}/tests\n")
    instructions.append(f"# 每个 Agent 的输出保存为：\n")
    instructions.append(f"# tests/test_module_a.py\n")
    instructions.append(f"# tests/test_module_b.py\n")
    instructions.append(f"# tests/test_module_c.py\n")
    instructions.append(f"# tests/conftest.py（共享 fixture）\n\n")
    instructions.append(f"# 运行测试\n")
    instructions.append(f"cd {project_path} && {test_framework} tests/ -v\n")
    instructions.append("```\n")

    return "".join(instructions)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="自动生成测试用例场景")
    parser.add_argument("path", nargs="?", default=".", help="项目路径")
    parser.add_argument("--name", "-n", help="项目名称")
    parser.add_argument("--framework", "-f", default="pytest", help="测试框架（默认 pytest）")
    parser.add_argument("--output", "-o", help="输出到文件")
    args = parser.parse_args()

    project_path = os.path.abspath(args.path)
    project_name = args.name or os.path.basename(project_path.rstrip("/"))

    print(f"项目：{project_name}")
    print(f"路径：{project_path}")
    print(f"框架：{args.framework}\n")

    instructions = get_instructions(project_path, project_name, args.framework)

    if args.output:
        with open(args.output, "w") as f:
            f.write(instructions)
        print(f"已保存到 {args.output}")
    else:
        print(instructions)


if __name__ == "__main__":
    main()
