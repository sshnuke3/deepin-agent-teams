#!/usr/bin/env python3
"""
agents/worker_base.py - 可扩展的通用 Worker Agent
根据任务自主决定执行策略，支持任意任务类型
"""
import json
import os
import sys
import time
import subprocess
import glob
import hashlib
from typing import Dict, List, Any, Optional
from registry import AgentRegistry, RESULT_DIR


class BaseWorker:
    """
    可扩展 Worker 基类

    设计原则：
    1. 能力驱动：Worker 声明自己的能力，任务基于能力路由
    2. 自主执行：收到任务后自主决定执行策略，不依赖预定义分工
    3. 可扩展：新增 Worker 类型只需继承并注册新能力
    4. 结果导向：所有结果统一格式，可被 Lead 整合
    """

    def __init__(self, role: str, capabilities: List[str]):
        self.role = role
        self.capabilities = capabilities
        self.agent_id = None
        self.registry = AgentRegistry()
        self.current_task = None

    def register(self) -> str:
        """注册到中心"""
        self.agent_id = self.registry.register(
            capabilities=self.capabilities,
            metadata={"role": self.role, "pid": os.getpid()}
        )
        print(f"[{self.role}] Worker 注册完成: {self.agent_id}", flush=True)
        return self.agent_id

    def unregister(self):
        """注销"""
        self.registry.unregister()

    def heartbeat(self):
        """发送心跳"""
        self.registry.heartbeat()

    def capabilities_match(self, task: Dict) -> bool:
        """检查自己是否能处理这个任务"""
        needed = task.get("capabilities_needed", [])
        # 至少满足一个核心能力就算匹配
        return bool(set(needed) & set(self.capabilities))

    def execute_task(self, task: Dict) -> Dict:
        """
        执行任务 - 子类重写具体逻辑
        返回结果字典
        """
        raise NotImplementedError("子类必须实现 execute_task()")

    def execute_capability(self, capability: str, params: Dict) -> Any:
        """
        根据能力自主选择执行模块
        这就是"自主分工"的核心 - 不是被分配，而是自己判断用哪个能力
        """
        capability_map = {
            # 文件能力
            "file_reader": lambda p: self._read_file(p.get("path")),
            "dir_scanner": lambda p: self._scan_dir(p.get("path")),
            "file_writer": lambda p: self._write_file(p.get("path"), p.get("content", "")),

            # 代码能力
            "code_analyzer": lambda p: self._analyze_code(p.get("path")),
            "ast_parser": lambda p: self._parse_ast(p.get("path")),
            "syntax_checker": lambda p: self._syntax_check(p.get("path")),
            "dependency_analyzer": lambda p: self._analyze_deps(p.get("path")),

            # Shell 能力
            "shell_executor": lambda p: self._run_shell(p.get("command"), p.get("timeout", 30)),
            "git_analyzer": lambda p: self._analyze_git(p.get("path")),
            "process_manager": lambda p: self._manage_process(p.get("command")),

            # 研究能力
            "web_search": lambda p: self._web_search(p.get("query")),
            "web_fetcher": lambda p: self._fetch_url(p.get("url")),

            # 文档能力
            "doc_generator": lambda p: self._generate_doc(p.get("content")),
            "markdown_writer": lambda p: self._write_markdown(p.get("path"), p.get("content")),
        }

        handler = capability_map.get(capability)
        if handler:
            return handler(params)
        return {"error": f"未知能力: {capability}"}

    # ========== 能力实现 ==========

    def _read_file(self, path: str, max_chars: int = 50000) -> Dict:
        if not os.path.exists(path):
            return {"error": f"文件不存在: {path}"}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read(max_chars)
            size = os.path.getsize(path)
            return {
                "path": path,
                "size": size,
                "truncated": size > max_chars,
                "content_preview": content[:500],
                "lines": len(content.splitlines()),
            }
        except Exception as e:
            return {"error": str(e)}

    def _scan_dir(self, path: str, max_depth: int = 3, current_depth: int = 0) -> Dict:
        if current_depth >= max_depth:
            return {"path": path, "status": "max_depth_reached"}
        if not os.path.exists(path):
            return {"error": f"目录不存在: {path}"}

        entries = []
        try:
            for entry in os.scandir(path):
                if entry.name.startswith('.') or entry.name == '__pycache__':
                    continue
                info = {
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                }
                if entry.is_file():
                    info["size"] = entry.stat().st_size
                if entry.is_dir() and current_depth + 1 < max_depth:
                    info["children"] = self._scan_dir(entry.path, max_depth, current_depth + 1)
                entries.append(info)
        except PermissionError:
            return {"error": "权限不足"}

        return {"path": path, "entries": entries, "count": len(entries)}

    def _write_file(self, path: str, content: str) -> Dict:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"success": True, "path": path, "size": len(content)}
        except Exception as e:
            return {"error": str(e)}

    def _analyze_code(self, path: str) -> Dict:
        """分析代码文件"""
        import re
        if not os.path.exists(path):
            return {"error": f"文件不存在: {path}"}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            funcs = re.findall(r'def (\w+)', content)
            classes = re.findall(r'class (\w+)', content)
            imports = re.findall(r'^(?:from|import) .+', content, re.MULTILINE)
            return {
                "path": path,
                "functions": funcs,
                "classes": classes,
                "imports": imports[:10],
                "lines": len(content.splitlines()),
            }
        except Exception as e:
            return {"error": str(e)}

    def _parse_ast(self, path: str) -> Dict:
        """AST 解析"""
        try:
            import ast
            with open(path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            nodes = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    nodes.append({"type": type(node).__name__, "name": node.name})
            return {"path": path, "ast_nodes": nodes[:50]}
        except Exception as e:
            return {"error": f"AST 解析失败: {e}"}

    def _syntax_check(self, path: str) -> Dict:
        """语法检查"""
        result = subprocess.run(
            ["python3", "-m", "py_compile", path],
            capture_output=True, text=True
        )
        return {"path": path, "ok": result.returncode == 0, "error": result.stderr[:500] if result.stderr else None}

    def _analyze_deps(self, path: str) -> Dict:
        """分析依赖"""
        deps = {}
        for req_file in ["requirements.txt", "setup.py", "pyproject.toml"]:
            fp = os.path.join(path, req_file)
            if os.path.exists(fp):
                with open(fp, 'r') as f:
                    deps[req_file] = f.read()[:2000]
        return {"path": path, "dependencies": deps}

    def _run_shell(self, command: str, timeout: int = 30) -> Dict:
        """执行 Shell 命令"""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return {
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
            }
        except subprocess.TimeoutExpired:
            return {"error": "命令执行超时", "command": command, "timeout": timeout}
        except Exception as e:
            return {"error": str(e), "command": command}

    def _analyze_git(self, path: str) -> Dict:
        """Git 信息分析"""
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
            return {"path": path, "branch": branch, "recent_commits": commits}
        except Exception as e:
            return {"error": str(e)}

    def _web_search(self, query: str) -> Dict:
        """网页搜索（简单实现）"""
        return {"query": query, "note": "需要配置 web search API"}

    def _fetch_url(self, url: str) -> Dict:
        """获取网页内容"""
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "10", url],
                capture_output=True, text=True, timeout=15
            )
            return {"url": url, "length": len(result.stdout), "preview": result.stdout[:500]}
        except Exception as e:
            return {"error": str(e)}

    def _generate_doc(self, content: str) -> Dict:
        """生成文档"""
        return {"generated": True, "length": len(content), "format": "markdown"}

    def _write_markdown(self, path: str, content: str) -> Dict:
        """写 Markdown 文件"""
        return self._write_file(path, content)

    def _manage_process(self, command: str) -> Dict:
        """进程管理"""
        return self._run_shell(command)

    # ========== Worker 主循环 ==========

    def run(self):
        """Worker 主循环"""
        self.register()

        print(f"[{self.role}] Worker 主循环启动，等待任务...", flush=True)

        while True:
            self.heartbeat()

            # 尝试认领任务
            task = self.registry.claim_task(self.agent_id)

            if task:
                print(f"[{self.role}] 认领任务: {task['id']}", flush=True)
                self.current_task = task

                try:
                    result = self.execute_task(task)
                except Exception as e:
                    result = {"error": str(e), "status": "failed"}

                # 提交结果
                self.registry.complete_task(task["id"], {
                    "agent_id": self.agent_id,
                    "role": self.role,
                    "result": result,
                    "capabilities_used": self.capabilities,
                })
                print(f"[{self.role}] 任务完成: {task['id']}", flush=True)
                self.current_task = None
            else:
                # 没有任务，短暂休眠
                time.sleep(1)


class GeneralWorker(BaseWorker):
    """
    通用 Worker - 自主分析任务并选择合适的能力执行
    """

    def __init__(self, role: str, capabilities: List[str]):
        super().__init__(role, capabilities)

    def execute_task(self, task: Dict) -> Dict:
        """
        自主执行：分析任务需求 → 选择能力 → 组合执行 → 输出结果
        这是"自主分工"的核心实现
        """
        task_id = task.get("id", "unknown")
        description = task.get("description", "")
        capabilities_needed = task.get("capabilities_needed", [])
        params = task.get("params", {})

        print(f"[{self.role}] 分析任务: {description[:50]}...", flush=True)
        print(f"[{self.role}] 可用能力: {self.capabilities}", flush=True)
        print(f"[{self.role}] 需求能力: {capabilities_needed}", flush=True)

        results = {}

        # 自主决定执行顺序和策略
        for capability in capabilities_needed:
            if capability in self.capabilities:
                print(f"[{self.role}] → 执行能力: {capability}", flush=True)
                try:
                    # 根据能力类型构建参数
                    cap_params = self._build_params_for_capability(capability, params, description)
                    results[capability] = self.execute_capability(capability, cap_params)
                except Exception as e:
                    results[capability] = {"error": str(e)}
            else:
                results[capability] = {"error": f"Worker 不具备能力: {capability}"}

        return {
            "task_id": task_id,
            "description": description,
            "capabilities_used": [c for c in capabilities_needed if c in self.capabilities],
            "capabilities_unavailable": [c for c in capabilities_needed if c not in self.capabilities],
            "results": results,
            "summary": self._summarize_results(results),
        }

    def _build_params_for_capability(self, capability: str, params: Dict, description: str) -> Dict:
        """根据能力类型从描述中提取或构建参数"""
        # 如果 params 里有，直接用
        if params.get(capability):
            return params[capability]

        # 从描述中推断
        if "project" in description.lower() or "项目" in description:
            if "path" not in params:
                params["path"] = params.get("project_path", "/root/.openclaw/workspace/deepin-agent-teams")

        return params

    def _summarize_results(self, results: Dict) -> str:
        """汇总执行结果"""
        summary_parts = []
        for cap, result in results.items():
            if isinstance(result, dict):
                if result.get("error"):
                    summary_parts.append(f"{cap}: ❌ {result['error']}")
                else:
                    keys = list(result.keys())[:3]
                    summary_parts.append(f"{cap}: ✅ {', '.join(keys)}")
        return " | ".join(summary_parts) if summary_parts else "无结果"


if __name__ == "__main__":
    # 默认启动一个通用 Worker
    worker = GeneralWorker(
        role="general",
        capabilities=[
            "file_reader", "dir_scanner", "code_analyzer",
            "ast_parser", "syntax_checker", "dependency_analyzer",
            "shell_executor", "markdown_writer",
        ]
    )
    try:
        worker.run()
    except KeyboardInterrupt:
        worker.unregister()
        print(f"\n[{worker.role}] Worker 已停止")
