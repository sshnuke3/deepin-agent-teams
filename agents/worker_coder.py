#!/usr/bin/env python3
"""
agents/worker_coder.py - Coder 子 Agent 工作进程
真正的独立进程，通过文件与 Lead 通信
"""
import json
import os
import time
import subprocess
import re
from typing import Optional


TASK_FILE = "/tmp/agent_task_coder.json"
RESULT_FILE = "/tmp/agent_result_coder.json"


def read_task() -> Optional[dict]:
    if os.path.exists(TASK_FILE):
        with open(TASK_FILE, 'r') as f:
            data = f.read()
        os.remove(TASK_FILE)
        return json.loads(data)
    return None


def write_result(result: dict) -> None:
    with open(RESULT_FILE, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def run_command(cmd: str, timeout: int = 30) -> str:
    """执行 Shell 命令"""
    import shlex
    try:
        cmd_parts = shlex.split(cmd)
        result = subprocess.run(
            cmd_parts, capture_output=True, text=True, timeout=timeout
        )
        output = f"[EXIT {result.returncode}]\n"
        if result.stdout:
            output += result.stdout[:5000]
        if result.stderr:
            output += f"\nSTDERR: {result.stderr[:2000]}"
        return output
    except subprocess.TimeoutExpired:
        return "命令执行超时"
    except Exception as e:
        return f"执行失败: {e}"


def extract_code_elements(content: str) -> dict:
    """从代码中提取函数、类、import"""
    funcs = re.findall(r'def (\w+)', content)
    classes = re.findall(r'class (\w+)', content)
    imports = re.findall(r'^(?:from|import) .+', content, re.MULTILINE)
    return {
        "functions": funcs[:10],
        "classes": classes[:10],
        "imports": imports[:10]
    }


def analyze_python_file(fp: str, project_path: str) -> dict:
    """分析单个 Python 文件"""
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        
        elements = extract_code_elements(content)
        rel_path = os.path.relpath(fp, project_path)
        
        # 行数统计
        lines = content.split('\n')
        
        # 尝试执行语法检查
        import shlex
        syntax_check = run_command(f"python3 -m py_compile {shlex.quote(fp)}")
        
        return {
            "file": rel_path,
            "lines": len(lines),
            "functions": elements['functions'],
            "classes": elements['classes'],
            "top_imports": elements['imports'][:5],
            "syntax_ok": "EXIT 0" in syntax_check,
            "docstring": (content[:200] if content.startswith('"""') or content.startswith("'''") else ""),
        }
    except Exception as e:
        return {"file": fp, "error": str(e)}


def run_coder(task: dict) -> dict:
    """执行编码分析任务"""
    analysis = []
    
    project_path = task.get('project_path', '')
    description = task.get('description', '')
    
    print(f"[Coder] 开始: {description}", flush=True)
    
    if project_path and os.path.exists(project_path):
        # 1. 找出所有 Python 文件
        py_files = []
        for root, _, files in os.walk(project_path):
            if '__pycache__' in root or '.git' in root:
                continue
            for f in files:
                if f.endswith('.py') and not f.startswith('.'):
                    py_files.append(os.path.join(root, f))
        
        analysis.append(f"## Python 文件统计\n共找到 {len(py_files)} 个 .py 文件\n")
        
        # 2. 分析前 5 个最大的文件
        py_files.sort(key=lambda x: os.path.getsize(x), reverse=True)
        for fp in py_files[:5]:
            result = analyze_python_file(fp, project_path)
            rel = os.path.relpath(fp, project_path)
            
            line_str = f"{result.get('lines', '?')} 行"
            funcs = ', '.join(result.get('functions', [])[:5]) or '无'
            classes = ', '.join(result.get('classes', [])[:5]) or '无'
            
            analysis.append(f"""## {rel} ({line_str})

- **函数**: {funcs}
- **类**: {classes}
- **语法检查**: {'✅ 通过' if result.get('syntax_ok') else '❌ 失败'}
""")
        
        # 3. 执行环境验证
        env_check = run_command("python3 --version && pip3 list 2>/dev/null | head -10")
        analysis.append(f"## 环境验证\n```\n{env_check}\n```\n")
        
        # 4. 生成文档建议
        doc_suggestions = []
        for fp in py_files[:3]:
            rel = os.path.relpath(fp, project_path)
            doc_suggestions.append(f"- {rel}")
        
        analysis.append(f"""## 文档生成建议

建议为以下文件生成文档：
{chr(10).join(doc_suggestions)}""")
    
    summary = f"完成编码分析：{description}\n分析了 {len(analysis)} 个维度"
    
    return {
        "agent": "Coder",
        "type": "code",
        "task": description,
        "status": "completed",
        "analysis": analysis,
        "summary": summary
    }


def main() -> None:
    print(f"[Coder] 子进程启动 PID={os.getpid()}", flush=True)
    print("READY", flush=True)
    
    while True:
        task = read_task()
        if task:
            print(f"[Coder] 收到任务: {task.get('type')}", flush=True)
            result = run_coder(task)
            write_result(result)
            print(f"[Coder] 任务完成: {result['summary']}", flush=True)
            print("TASK_DONE", flush=True)
        
        time.sleep(0.5)


if __name__ == "__main__":
    main()
