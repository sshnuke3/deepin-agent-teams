#!/usr/bin/env python3
"""
agents/worker_v2.py - 基于 Registry 的可扩展 Worker
启动时注册能力，从 Registry 自主认领任务并执行
"""
import json
import os
import sys
import time
import subprocess
import glob
import re
import hashlib

# 添加路径以便导入 registry
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registry import AgentRegistry


# ========== 能力实现 ==========

class CapabilityExecutor:
    """能力执行器 - 每个方法对应一个能力"""

    def __init__(self):
        self.results = []

    # --- 文件能力 ---
    def file_reader(self, params: dict) -> dict:
        path = params.get("path", "")
        max_chars = params.get("max_chars", 50000)
        if not os.path.exists(path):
            return {"error": f"文件不存在: {path}"}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read(max_chars)
            size = os.path.getsize(path)
            return {
                "path": path, "size": size, "truncated": size > max_chars,
                "lines": len(content.splitlines()),
                "preview": content[:300],
            }
        except Exception as e:
            return {"error": str(e)}

    def dir_scanner(self, params: dict) -> dict:
        path = params.get("path", ".")
        max_depth = params.get("max_depth", 3)
        current_depth = params.get("_depth", 0)
        
        if current_depth >= max_depth:
            return {"path": path, "status": "max_depth"}
        
        if not os.path.exists(path):
            return {"error": f"目录不存在: {path}"}
        
        entries = []
        try:
            for entry in os.scandir(path):
                if entry.name.startswith('.') or entry.name == '__pycache__':
                    continue
                info = {"name": entry.name, "type": "dir" if entry.is_dir() else "file"}
                if entry.is_file():
                    info["size"] = entry.stat().st_size
                if entry.is_dir() and current_depth + 1 < max_depth:
                    info["children"] = self.dir_scanner({**params, "_depth": current_depth + 1})
                entries.append(info)
        except PermissionError:
            return {"error": "权限不足"}
        
        return {"path": path, "entries": entries, "count": len(entries)}

    def file_writer(self, params: dict) -> dict:
        path = params.get("path", "")
        content = params.get("content", "")
        if not path:
            return {"error": "缺少 path 参数"}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"success": True, "path": path, "size": len(content)}
        except Exception as e:
            return {"error": str(e)}

    # --- 代码能力 ---
    def code_analyzer(self, params: dict) -> dict:
        path = params.get("path", "")
        if not os.path.exists(path):
            return {"error": f"文件不存在: {path}"}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            funcs = re.findall(r'def (\w+)', content)
            classes = re.findall(r'class (\w+)', content)
            imports = re.findall(r'^(?:from|import) .+', content, re.MULTILINE)
            return {
                "path": path, "functions": funcs, "classes": classes,
                "imports": imports[:10], "lines": len(content.splitlines()),
            }
        except Exception as e:
            return {"error": str(e)}

    def ast_parser(self, params: dict) -> dict:
        path = params.get("path", "")
        try:
            import ast
            with open(path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            nodes = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    nodes.append({"type": type(node).__name__, "name": node.name})
            return {"path": path, "ast_nodes": nodes[:50], "total": len(nodes)}
        except Exception as e:
            return {"error": f"AST 解析失败: {e}"}

    def syntax_checker(self, params: dict) -> dict:
        path = params.get("path", "")
        result = subprocess.run(
            ["python3", "-m", "py_compile", path],
            capture_output=True, text=True, timeout=30
        )
        return {"path": path, "ok": result.returncode == 0, "error": result.stderr[:500] if result.stderr else None}

    def dependency_analyzer(self, params: dict) -> dict:
        path = params.get("path", ".")
        deps = {}
        for req_file in ["requirements.txt", "setup.py", "pyproject.toml"]:
            fp = os.path.join(path, req_file)
            if os.path.exists(fp):
                with open(fp, 'r') as f:
                    deps[req_file] = f.read()[:2000]
        return {"path": path, "dependencies": deps}

    # --- Shell 能力 ---
    def shell_executor(self, params: dict) -> dict:
        command = params.get("command", "")
        timeout = params.get("timeout", 30)
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return {
                "command": command, "exit_code": result.returncode,
                "stdout": result.stdout[:5000], "stderr": result.stderr[:2000],
            }
        except subprocess.TimeoutExpired:
            return {"error": "命令执行超时", "command": command}
        except Exception as e:
            return {"error": str(e)}

    def git_analyzer(self, params: dict) -> dict:
        path = params.get("path", ".")
        if not os.path.exists(os.path.join(path, '.git')):
            return {"error": "不是 Git 仓库"}
        try:
            commits = subprocess.run(
                ["git", "-C", path, "log", "--oneline", "-10"],
                capture_output=True, text=True, timeout=10
            ).stdout
            branch = subprocess.run(
                ["git", "-C", path, "branch", "--show-current"],
                capture_output=True, text=True, timeout=10
            ).stdout.strip()
            status = subprocess.run(
                ["git", "-C", path, "status", "--short"],
                capture_output=True, text=True, timeout=10
            ).stdout
            return {"path": path, "branch": branch, "recent_commits": commits, "status": status[:500]}
        except Exception as e:
            return {"error": str(e)}

    # --- 文档能力 ---
    def doc_generator(self, params: dict) -> dict:
        content = params.get("content", "")
        return {"generated": True, "length": len(content), "format": "markdown"}

    def markdown_writer(self, params: dict) -> dict:
        return self.file_writer(params)

    # --- 网络能力 ---
    def web_search(self, params: dict) -> dict:
        query = params.get("query", "")
        return {"query": query, "note": "需要配置 web search API"}

    def web_fetcher(self, params: dict) -> dict:
        url = params.get("url", "")
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "10", "-L", url],
                capture_output=True, text=True, timeout=15
            )
            return {"url": url, "length": len(result.stdout), "preview": result.stdout[:500]}
        except Exception as e:
            return {"error": str(e)}

    # --- 能力路由表 ---
    CAPABILITY_MAP = {
        "file_reader": file_reader,
        "dir_scanner": dir_scanner,
        "file_writer": file_writer,
        "code_analyzer": code_analyzer,
        "ast_parser": ast_parser,
        "syntax_checker": syntax_checker,
        "dependency_analyzer": dependency_analyzer,
        "shell_executor": shell_executor,
        "git_analyzer": git_analyzer,
        "doc_generator": doc_generator,
        "markdown_writer": markdown_writer,
        "web_search": web_search,
        "web_fetcher": web_fetcher,
    }

    def execute(self, capability: str, params: dict) -> dict:
        """执行指定能力"""
        handler = self.CAPABILITY_MAP.get(capability)
        if handler:
            return handler(self, params)
        return {"error": f"未知能力: {capability}"}


# ========== Worker 主类 ==========

class ExtensibleWorker:
    """
    可扩展 Worker - 基于 Registry 的任务认领

    与旧 Worker 的区别：
    - 不再轮询固定的任务文件
    - 而是从 Registry 自主认领任务
    - 根据任务需求的 capabilities 选择执行
    """

    def __init__(self, role: str, capabilities: list):
        self.role = role
        self.capabilities = capabilities
        self.agent_id = None
        self.registry = AgentRegistry()
        self.executor = CapabilityExecutor()

    def register(self) -> str:
        """注册到 Registry"""
        self.agent_id = self.registry.register(
            capabilities=self.capabilities,
            metadata={"role": self.role, "pid": os.getpid()}
        )
        print(f"[{self.role}] Worker 注册完成: {self.agent_id}", flush=True)
        # 通知父进程已就绪
        sys.stdout.write(f"REGISTERED:{self.agent_id}\n")
        sys.stdout.flush()
        return self.agent_id

    def unregister(self):
        self.registry.unregister()

    def heartbeat_loop(self):
        """心跳线程"""
        while True:
            self.registry.heartbeat()
            time.sleep(10)

    def can_handle(self, task: dict) -> bool:
        """判断是否能处理这个任务"""
        needed = set(task.get("capabilities_needed", []))
        available = set(self.capabilities)
        # 至少满足一个能力
        return bool(needed & available)

    def execute_task(self, task: dict) -> dict:
        """执行任务 - 自主选择能力"""
        task_id = task.get("id", "unknown")
        description = task.get("description", "")
        needed_caps = task.get("capabilities_needed", [])
        params = task.get("params", {})

        print(f"[{self.role}] 执行任务: {description[:40]}...", flush=True)
        print(f"[{self.role}] 所需能力: {needed_caps}", flush=True)

        results = {}
        for cap in needed_caps:
            if cap in self.capabilities:
                print(f"[{self.role}] → 执行能力: {cap}", flush=True)
                try:
                    # 补充 path 参数
                    cap_params = {**params}
                    if "path" not in cap_params:
                        cap_params["path"] = params.get("project_path", "/root/.openclaw/workspace/deepin-agent-teams")
                    results[cap] = self.executor.execute(cap, cap_params)
                except Exception as e:
                    results[cap] = {"error": str(e)}
            else:
                results[cap] = {"error": f"不具备能力: {cap}"}

        # 汇总
        summary_parts = []
        for cap, res in results.items():
            if isinstance(res, dict) and res.get("error"):
                summary_parts.append(f"{cap}: ❌ {res['error'][:30]}")
            else:
                keys = list(res.keys())[:3] if isinstance(res, dict) else ["ok"]
                summary_parts.append(f"{cap}: ✅ {', '.join(keys)}")

        return {
            "task_id": task_id,
            "description": description,
            "capabilities_used": [c for c in needed_caps if c in self.capabilities],
            "results": results,
            "summary": " | ".join(summary_parts),
        }

    def run(self):
        """Worker 主循环"""
        self.register()

        print(f"[{self.role}] Worker 主循环启动，等待 Registry 任务...", flush=True)

        while True:
            # 认领任务
            task = self.registry.claim_task(self.agent_id, timeout=3)

            if task:
                print(f"[{self.role}] 认领任务: {task['id']}", flush=True)

                try:
                    result = self.execute_task(task)
                except Exception as e:
                    result = {"error": str(e)}

                self.registry.complete_task(task["id"], {
                    "agent_id": self.agent_id,
                    "role": self.role,
                    "capabilities_used": self.capabilities,
                    "result": result,
                })
                print(f"[{self.role}] 任务 {task['id']} 完成", flush=True)
            else:
                # 无任务休眠
                time.sleep(0.5)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", default="general", help="Worker 角色")
    parser.add_argument("--caps", nargs="+", default=[
        "file_reader", "dir_scanner", "code_analyzer",
        "ast_parser", "syntax_checker", "dependency_analyzer",
        "shell_executor", "markdown_writer",
    ], help="能力列表")
    args = parser.parse_args()

    worker = ExtensibleWorker(role=args.role, capabilities=args.caps)
    try:
        worker.run()
    except KeyboardInterrupt:
        worker.unregister()
        print(f"\n[{worker.role}] Worker 已停止")
