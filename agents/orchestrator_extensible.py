#!/usr/bin/env python3
"""
agents/orchestrator_extensible.py - 可扩展的多 Agent 编排器
使用 Registry 能力注册 + 任务队列实现真正的自主分工
"""
import json
import os
import sys
import time
import subprocess
import threading
import erniebot
from typing import Dict, List, Any

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registry import AgentRegistry


ERNIE_TOKEN = "0b93205ac0fc59d69166edb8e24cf1bc48aed453"


def init_ernie():
    erniebot.api_type = "aistudio"
    erniebot.access_token = ERNIE_TOKEN


class ExtensibleOrchestrator:
    """
    可扩展编排器 - 能力驱动架构

    流程：
    1. spawn_workers() → 各 Worker 启动并注册到 Registry
    2. erniebot 分解任务为 capabilities
    3. registry.submit_task() → 任务入队
    4. Worker 自主从 Registry 认领（基于能力匹配）
    5. Worker 自主执行（自己决定用哪个能力）
    6. registry.complete_task() → 结果入栈
    7. erniebot 整合
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.registry = AgentRegistry()
        self.workers = []
        self.init_ernie()

    def init_ernie(self):
        init_ernie()

    def spawn_workers(self):
        """启动 Worker 池，每个 Worker 独立注册"""
        if self.verbose:
            print("\n[Step 0] 启动 Worker 池（Registry 模式）...")

        base = os.path.dirname(os.path.abspath(__file__))
        worker_script = os.path.join(base, "worker_v2.py")

        worker_configs = [
            ("researcher", ["file_reader", "dir_scanner", "code_analyzer", "dependency_analyzer", "web_search", "web_fetcher", "markdown_writer"]),
            ("coder", ["file_reader", "code_analyzer", "ast_parser", "syntax_checker", "shell_executor", "git_analyzer", "markdown_writer"]),
            ("general", ["file_reader", "dir_scanner", "code_analyzer", "ast_parser", "syntax_checker", "shell_executor", "markdown_writer"]),
        ]

        for role, caps in worker_configs:
            proc = subprocess.Popen(
                ["python3", worker_script, "--role", role, "--caps"] + caps,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self.workers.append((role, caps, proc))
            print(f"[Orchestrator] 启动 {role} Worker (PID={proc.pid})...", flush=True)

        # 等待所有 Worker 注册完成
        if self.verbose:
            print("[Orchestrator] 等待 Worker 注册...", flush=True)

        deadline = time.time() + 15
        registered = set()

        while time.time() < deadline and len(registered) < len(self.workers):
            for role, _, proc in self.workers:
                if role in registered:
                    continue
                # 非阻塞检查 stdout
                import select
                if select.select([proc.stdout], [], [], 0.1)[0]:
                    line = proc.stdout.readline()
                    if "REGISTERED:" in line:
                        agent_id = line.strip().split("REGISTERED:")[1]
                        registered.add(role)
                        if self.verbose:
                            print(f"[Orchestrator] ✓ {role} 注册完成: {agent_id[:40]}...", flush=True)

        # 额外等待确保 Registry 写入完成
        time.sleep(0.5)

        agents = self.registry.list_agents()
        if self.verbose:
            print(f"[Orchestrator] 当前注册 Worker 数: {len(agents)}")

    def decompose_with_erniebot(self, user_request: str) -> dict:
        """
        erniebot 将任务分解为 capabilities（不指定谁来执行）
        """
        prompt = f"""用户需求：{user_request}

请将上述需求分解为具体的能力任务。

输出格式为纯 JSON：
{{
  "tasks": [
    {{
      "id": "task-1",
      "description": "详细描述这个子任务",
      "capabilities_needed": ["cap1", "cap2"],
      "params": {{"path": "/项目路径", ...}}
    }}
  ],
  "summary": "一句话总结"
}}

可用能力（选择最合适的）：
- file_reader: 读取文件
- dir_scanner: 扫描目录
- code_analyzer: 分析代码（函数/类/import）
- ast_parser: AST 解析
- syntax_checker: Python 语法检查
- dependency_analyzer: 依赖分析
- shell_executor: 执行 Shell 命令
- git_analyzer: Git 信息分析
- web_search: 网络搜索
- web_fetcher: 获取网页
- markdown_writer: 写 Markdown

规则：
- 每个 task 至少需要 1 个 capability
- params 包含执行参数
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
                "tasks": [{"id": f"task-{int(time.time())}", "description": user_request,
                          "capabilities_needed": ["shell_executor"], "params": {}}],
                "summary": user_request,
            }

    def submit_tasks(self, tasks: List[Dict]) -> List[str]:
        """提交任务到 Registry"""
        task_ids = []
        for task in tasks:
            if "params" not in task:
                task["params"] = {}
            task_id = self.registry.submit_task(task)
            task_ids.append(task_id)
            if self.verbose:
                caps = task.get("capabilities_needed", [])
                print(f"[Orchestrator] 任务入队: {task_id} [需要的 capabilities: {', '.join(caps)}]")
        return task_ids

    def wait_for_results(self, task_ids: List[str], timeout: float = 60) -> Dict[str, Dict]:
        """等待所有任务完成"""
        results = {}
        deadline = time.time() + timeout

        while time.time() < deadline:
            pending = [tid for tid in task_ids if tid not in results]
            if not pending:
                break

            for task_id in pending:
                result = self.registry.get_result(task_id)
                if result:
                    results[task_id] = result
                    if self.verbose:
                        print(f"[Orchestrator] ✓ 任务完成: {task_id}")
            time.sleep(0.5)

        for tid in task_ids:
            if tid not in results:
                results[tid] = {"error": "任务超时"}

        return results

    def integrate_with_erniebot(self, user_request: str, plan: dict, results: Dict) -> str:
        """整合结果"""
        result_parts = []
        for task_id, data in results.items():
            if isinstance(data, dict):
                role = data.get("role", "unknown")
                result_val = data.get("result", {})
                if isinstance(result_val, dict):
                    summary = result_val.get("summary", result_val.get("description", ""))[:200]
                else:
                    summary = str(result_val)[:200]
                result_parts.append(f"## 任务 {task_id} ({role})\n{summary}")

        integration_prompt = f"""用户需求：{user_request}

需求分解：
{json.dumps(plan, ensure_ascii=False, indent=2)}

Worker 执行结果：
{chr(10).join(result_parts)}

请生成 Markdown 格式报告，包含：
1. 执行概述
2. 各子任务执行情况
3. 关键发现
4. 最终结论和建议

只用 Markdown 输出。"""

        response = erniebot.ChatCompletion.create(
            model="ernie-lite",
            messages=[{"role": "user", "content": integration_prompt}],
        )
        return response.get_result() if hasattr(response, 'get_result') else str(response)

    def stop_workers(self):
        """停止所有 Worker"""
        for role, caps, proc in self.workers:
            try:
                proc.terminate()
                proc.wait(timeout=3)
                print(f"[Orchestrator] {role} Worker 已停止")
            except:
                pass

    def run(self, user_request: str, project_path: str = "") -> dict:
        """执行可扩展多 Agent 协作"""
        print(f"\n{'='*60}")
        print(f"[ExtensibleOrchestrator] 启动（能力驱动模式）")
        print(f"请求: {user_request[:50]}...")
        print(f"{'='*60}")

        # Step 0: 启动 Worker 池
        self.spawn_workers()

        # Step 1: erniebot 分解
        print("\n[Step 1] erniebot 分解任务为 capabilities...")
        plan = self.decompose_with_erniebot(user_request)
        tasks = plan.get("tasks", [])
        print(f"  → {len(tasks)} 个子任务")
        for t in tasks:
            caps = t.get("capabilities_needed", [])
            print(f"    [{', '.join(caps)}] {t.get('description', '')[:35]}...")

        # 补充 project_path
        if project_path:
            for t in tasks:
                if "params" not in t:
                    t["params"] = {}
                if "path" not in t["params"]:
                    t["params"]["path"] = project_path
                if "project_path" not in t["params"]:
                    t["params"]["project_path"] = project_path

        # Step 2: 提交任务
        print("\n[Step 2] 任务入 Registry（自主路由）...")
        task_ids = self.submit_tasks(tasks)

        # Step 3: 等待 Worker 执行
        print("\n[Step 3] Worker 自主认领和执行...")
        results = self.wait_for_results(task_ids, timeout=60)

        # Step 4: 整合
        print("\n[Step 4] erniebot 整合结果...")
        final_report = self.integrate_with_erniebot(user_request, plan, results)

        self.stop_workers()

        print(f"\n{'='*60}")
        print("[ExtensibleOrchestrator] 完成")
        print(f"{'='*60}")

        return {
            "request": user_request,
            "plan": plan,
            "results": results,
            "final_report": final_report,
        }


if __name__ == "__main__":
    init_ernie()
    orch = ExtensibleOrchestrator(verbose=True)
    result = orch.run(
        "分析 deepin-agent-teams 项目的代码结构，生成文档",
        project_path="/root/.openclaw/workspace/deepin-agent-teams"
    )
    print("\n最终报告：\n")
    print(result["final_report"])
