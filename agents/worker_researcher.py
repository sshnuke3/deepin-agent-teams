#!/usr/bin/env python3
"""
agents/worker_researcher.py - Researcher 子 Agent 工作进程
真正的独立进程，通过文件与 Lead 通信
"""
import json
import os
import time
import subprocess
import glob


TASK_FILE = "/tmp/agent_task_researcher.json"
RESULT_FILE = "/tmp/agent_result_researcher.json"


def read_task():
    """读取任务文件（读取后删除）"""
    if os.path.exists(TASK_FILE):
        with open(TASK_FILE, 'r') as f:
            data = f.read()
        os.remove(TASK_FILE)
        return json.loads(data)
    return None


def write_result(result):
    """写入结果文件"""
    with open(RESULT_FILE, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def analyze_structure(project_path: str) -> str:
    """分析项目结构"""
    output = []
    
    # 文件树
    try:
        files = []
        for root, dirs, fnames in os.walk(project_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for f in fnames:
                if not f.startswith('.') and not f.endswith('.pyc'):
                    rel = os.path.relpath(os.path.join(root, f), project_path)
                    files.append(rel)
        
        output.append("## 项目文件列表\n")
        for f in sorted(files)[:30]:
            output.append(f"  - {f}")
        if len(files) > 30:
            output.append(f"  ... 还有 {len(files)-30} 个文件")
    except Exception as e:
        output.append(f"结构分析失败: {e}")
    
    return '\n'.join(output)


def read_key_files(project_path: str, max_files: int = 5, max_chars: int = 3000) -> str:
    """读取关键文件内容"""
    output = []
    
    py_files = []
    for root, _, files in os.walk(project_path):
        if '__pycache__' in root:
            continue
        for f in files:
            if f.endswith('.py') and not f.startswith('.'):
                fp = os.path.join(root, f)
                try:
                    size = os.path.getsize(fp)
                    py_files.append((fp, size))
                except:
                    pass
    
    # 取最大的几个
    py_files.sort(key=lambda x: x[1], reverse=True)
    
    for fp, size in py_files[:max_files]:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read(max_chars)
            rel = os.path.relpath(fp, project_path)
            output.append(f"\n## {rel}\n\n```python\n{content}\n```\n")
        except Exception as e:
            output.append(f"\n## {fp} 读取失败: {e}\n")
    
    return '\n'.join(output)


def analyze_dependencies(project_path: str) -> str:
    """分析项目依赖"""
    output = []
    
    for req_file in ['requirements.txt', 'setup.py', 'pyproject.toml']:
        fp = os.path.join(project_path, req_file)
        if os.path.exists(fp):
            with open(fp, 'r') as f:
                content = f.read()
            output.append(f"## {req_file}\n```\n{content}\n```\n")
    
    return '\n'.join(output) if output else "## 依赖\n未找到依赖文件"


def run_researcher(task: dict) -> dict:
    """执行研究任务"""
    findings = []
    
    project_path = task.get('project_path', '')
    description = task.get('description', '')
    
    print(f"[Researcher] 开始: {description}", flush=True)
    
    if project_path and os.path.exists(project_path):
        # 1. 结构分析
        structure = analyze_structure(project_path)
        findings.append(structure)
        
        # 2. 关键文件
        files_content = read_key_files(project_path)
        findings.append(files_content)
        
        # 3. 依赖
        deps = analyze_dependencies(project_path)
        findings.append(deps)
    
    summary = f"完成研究任务：{description}\n发现 {len(findings)} 个分析模块"
    
    return {
        "agent": "Researcher",
        "type": "research",
        "task": description,
        "status": "completed",
        "findings": findings,
        "summary": summary
    }


def main():
    print(f"[Researcher] 子进程启动 PID={os.getpid()}", flush=True)
    
    # 通知 Lead 已就绪
    print("READY", flush=True)
    
    while True:
        task = read_task()
        if task:
            print(f"[Researcher] 收到任务: {task.get('type')}", flush=True)
            result = run_researcher(task)
            write_result(result)
            print(f"[Researcher] 任务完成: {result['summary']}", flush=True)
            print("TASK_DONE", flush=True)
        
        time.sleep(0.5)


if __name__ == "__main__":
    main()
