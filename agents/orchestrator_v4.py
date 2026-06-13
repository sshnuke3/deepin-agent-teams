#!/usr/bin/env python3
"""
agents/orchestrator_v4.py - MCP 驱动的多 Agent 编排器

核心改进（vs v3）：
1. 工具通过 MCP 协议连接，不硬编码
2. 加新工具 = 写 MCP Server + connect_server() 一行代码
3. 自动发现所有已连接 Server 的工具
4. 工具列表可直接用于 LLM Function Calling

架构：
  orchestrator_v4.py
    ├── MCP Client ──→ model-service (model_server.py)
    ├── MCP Client ──→ file-service   (file_server.py)
    ├── MCP Client ──→ system-service (system_server.py)
    └── ToolRegistry（统一工具调用接口）

使用方式：
    orch = OrchestratorV4()
    orch.auto_connect_servers()  # 自动启动所有内置 MCP Server
    result = orch.run("分析项目代码结构", project_path="/path/to/project")
"""
import json
import os
import sys
import time
import subprocess
from typing import Dict, List, Optional

# 路径
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
MCP_SERVERS_DIR = os.path.join(PROJECT_ROOT, "mcp_servers")
sys.path.insert(0, PROJECT_ROOT)

from tools.tool_registry import ToolRegistry, CallResult
from mcp_servers.mcp_protocol import MCPClient
from agents.task_state_machine import TaskStateMachine, TaskState, TransitionContext, MAX_RETRY
from agents.verifier import Verifier


class OrchestratorV4:
    """
    MCP 驱动的编排器

    核心变化（vs v3）：
    - 工具通过 MCP Client 连接，不硬编码
    - 自动发现工具，自动生成 LLM tools 参数
    - 加新工具零侵入
    """

    def __init__(self, verbose: bool = True):
        import warnings
        warnings.warn(
            "OrchestratorV4 已废弃，请使用 agents.orchestrator.Orchestrator",
            DeprecationWarning, stacklevel=2
        )
        self.verbose = verbose
        self.registry = ToolRegistry()
        self.verifier = Verifier()
        self.mcp_clients: Dict[str, MCPClient] = {}  # server_name → client
        self.task_state_machines: Dict[str, TaskStateMachine] = {}
        self.workers = []

    # ========== MCP Server 连接 ==========

    def connect_server(self, name: str, command: str, args: List[str]):
        """
        连接一个 MCP Server

        Args:
            name: Server 名称（如 "model-service"）
            command: 启动命令（如 "python3"）
            args: 启动参数（如 ["mcp_servers/model_server.py"]）
        """
        client = MCPClient()
        client.connect(command, args)

        self.mcp_clients[name] = client
        self.registry.connect_mcp_server(name, client)

        # 自动注册 Server 暴露的工具
        tools = client.list_tools()
        self.registry.register_from_mcp_server(name, tools)

        if self.verbose:
            tool_names = [t["name"] for t in tools]
            print(f"[OrchestratorV4] ✅ 连接 MCP Server: {name}")
            print(f"  工具: {tool_names}")

    def auto_connect_servers(self):
        """
        自动启动所有内置 MCP Server

        扫描 mcp_servers/ 目录下所有 *_server.py 文件并连接。
        """
        servers = [
            ("model-service", "model_server.py"),
            ("file-service", "file_server.py"),
            ("system-service", "system_server.py"),
        ]

        for name, filename in servers:
            server_path = os.path.join(MCP_SERVERS_DIR, filename)
            if os.path.exists(server_path):
                try:
                    self.connect_server(name, "python3", [server_path])
                except Exception as e:
                    if self.verbose:
                        print(f"[OrchestratorV4] ⚠️ 连接 {name} 失败: {e}")
            else:
                if self.verbose:
                    print(f"[OrchestratorV4] ⚠️ MCP Server 文件不存在: {server_path}")

    def disconnect_all(self):
        """断开所有 MCP 连接"""
        for name, client in self.mcp_clients.items():
            try:
                client.disconnect()
                if self.verbose:
                    print(f"[OrchestratorV4] 断开: {name}")
            except Exception:
                import logging
                logging.getLogger(__name__).warning("Failed to disconnect MCP: %s", name)
        self.mcp_clients.clear()

    # ========== Worker 管理（复用 v3 逻辑）==========

    def spawn_workers(self):
        """启动 Worker 池"""
        if self.verbose:
            print("\n[OrchestratorV4] 启动 Worker 池...")

        worker_script = os.path.join(AGENT_DIR, "worker_v2.py")
        if not os.path.exists(worker_script):
            if self.verbose:
                print("[OrchestratorV4] ⚠️ worker_v2.py 不存在，跳过 Worker 启动")
            return

        worker_configs = [
            ("researcher", ["file_reader", "dir_scanner", "code_analyzer",
                            "dependency_analyzer", "web_search", "web_fetcher", "markdown_writer"]),
            ("coder", ["file_reader", "code_analyzer", "ast_parser", "syntax_checker",
                       "shell_executor", "git_analyzer", "markdown_writer"]),
            ("general", ["file_reader", "dir_scanner", "code_analyzer", "ast_parser",
                         "syntax_checker", "shell_executor", "markdown_writer"]),
        ]

        for role, caps in worker_configs:
            proc = subprocess.Popen(
                ["python3", worker_script, "--role", role, "--caps"] + caps,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            self.workers.append((role, caps, proc))
            if self.verbose:
                print(f"[OrchestratorV4] 启动 {role} Worker (PID={proc.pid})")

        # 等待注册
        import select
        deadline = time.time() + 15
        registered = set()
        while time.time() < deadline and len(registered) < len(self.workers):
            for role, _, proc in self.workers:
                if role in registered:
                    continue
                if select.select([proc.stdout], [], [], 0.1)[0]:
                    line = proc.stdout.readline()
                    if "REGISTERED:" in line:
                        registered.add(role)
            time.sleep(0.1)

    def stop_workers(self):
        for role, caps, proc in self.workers:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                import logging
                logging.getLogger(__name__).warning("Failed to terminate worker %s", role)

    # ========== 任务分解（使用 MCP 工具）==========

    def decompose(self, user_request: str) -> dict:
        """使用 MCP model-service 分解任务"""
        # 获取可用工具列表（供 LLM 参考）
        tools_desc = json.dumps(self.registry.list_for_llm(), ensure_ascii=False, indent=2)

        prompt = f"""用户需求：{user_request}

可用工具（通过 MCP 协议连接）：
{tools_desc}

请将需求分解为具体任务。输出纯 JSON：
{{
  "tasks": [
    {{
      "id": "task-1",
      "description": "详细描述",
      "tool_name": "使用哪个工具",
      "params": {{}},
      "type": "任务类型"
    }}
  ],
  "summary": "一句话总结"
}}
只输出 JSON。"""

        # 通过 MCP 调用 model-service
        result = self.registry.call("chat_completion", {
            "messages": [
                {"role": "system", "content": "你是任务分解专家。只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "model": "ernie-3.5",
            "temperature": 0.3,
        })

        if result.success:
            try:
                resp = result.output
                if isinstance(resp, dict) and resp.get("success"):
                    text = resp["result"]
                    # 清理 markdown 代码块
                    text = text.strip()
                    if text.startswith("```"):
                        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                        text = text.rstrip("`").strip()
                    return json.loads(text)
            except (json.JSONDecodeError, KeyError) as e:
                if self.verbose:
                    print(f"[OrchestratorV4] JSON 解析失败: {e}")

        # 降级：单任务
        return {
            "tasks": [{
                "id": f"task-{int(time.time())}",
                "description": user_request,
                "tool_name": "exec_command",
                "params": {"command": f"echo '{user_request}'"},
                "type": "general",
            }],
            "summary": user_request,
        }

    # ========== 任务执行 ==========

    def execute_task(self, task: dict, task_id: str) -> dict:
        """
        执行单个任务

        状态机：PENDING → CLAIMED → RUNNING → VERIFIED → COMPLETED
        """
        sm = TaskStateMachine(task_id)
        self.task_state_machines[task_id] = sm

        tool_name = task.get("tool_name", "exec_command")
        params = task.get("params", {})
        retry_count = 0

        while True:
            # PENDING → CLAIMED
            sm.transition(TaskState.CLAIMED, TransitionContext(worker_id=tool_name))

            # CLAIMED → RUNNING
            sm.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))

            # 通过 ToolRegistry 调用（自动路由到 MCP Server 或本地 handler）
            result = self.registry.call(tool_name, params)

            if not result.success:
                # 工具调用失败
                if retry_count < MAX_RETRY:
                    retry_count += 1
                    if self.verbose:
                        print(f"[OrchestratorV4] {task_id}: 工具调用失败，重试 ({retry_count}/{MAX_RETRY})")
                    sm.transition(TaskState.RETRY, TransitionContext(
                        verdict="FAIL", retry_count=retry_count, error_msg=result.error,
                    ))
                    sm.retry_with_increment()
                    continue
                else:
                    sm.transition(TaskState.FAILED, TransitionContext(
                        error_msg=result.error, verdict="FAIL", retry_count=retry_count,
                    ))
                    return {"status": "failed", "error": result.error, "trace": sm.get_trace()}

            # Verifier 验收
            v = self.verifier.verify(task, {"result": result.output if isinstance(result.output, dict) else {"output": result.output}})

            if v.is_pass:
                sm.transition(TaskState.VERIFIED, TransitionContext(verdict="PASS"))
                sm.transition(TaskState.COMPLETED, TransitionContext())
                return {
                    "status": "completed",
                    "result": result.output,
                    "tool": tool_name,
                    "duration_ms": result.duration_ms,
                    "trace": sm.get_trace(),
                }
            else:
                if retry_count < MAX_RETRY:
                    retry_count += 1
                    if self.verbose:
                        print(f"[OrchestratorV4] {task_id}: Verifier 打回，重试 ({retry_count})")
                    sm.transition(TaskState.RETRY, TransitionContext(
                        verdict="FAIL", verdict_causes=v.causes, retry_count=retry_count,
                    ))
                    sm.retry_with_increment()
                    continue
                else:
                    sm.transition(TaskState.FAILED, TransitionContext(
                        verdict="FAIL", verdict_causes=v.causes, retry_count=retry_count,
                    ))
                    return {"status": "failed", "reason": v.causes, "trace": sm.get_trace()}

    # ========== 整合结果 ==========

    def integrate(self, user_request: str, plan: dict, results: dict) -> str:
        """整合所有任务结果，生成报告"""
        result_parts = []
        for task_id, data in results.items():
            sm = self.task_state_machines.get(task_id)
            state_str = sm.state.value if sm else "unknown"
            status = data.get("status", "unknown")
            result_val = data.get("result", {})
            if isinstance(result_val, dict):
                summary = json.dumps(result_val, ensure_ascii=False)[:300]
            else:
                summary = str(result_val)[:300]
            result_parts.append(f"## {task_id} [{state_str}]\n{summary}")

        prompt = f"""用户需求：{user_request}

任务分解：{json.dumps(plan, ensure_ascii=False, indent=2)}

执行结果：
{chr(10).join(result_parts)}

请生成 Markdown 报告，包含：执行概述、各子任务情况、关键发现、结论建议。"""

        result = self.registry.call("chat_completion", {
            "messages": [
                {"role": "system", "content": "你是报告撰写专家。"},
                {"role": "user", "content": prompt},
            ],
            "model": "ernie-3.5",
            "temperature": 0.5,
        })

        if result.success:
            resp = result.output
            if isinstance(resp, dict) and resp.get("success"):
                return resp["result"]

        return f"# 执行报告\n\n" + "\n".join(result_parts)

    # ========== 主流程 ==========

    def run(self, user_request: str, project_path: str = "") -> dict:
        """
        主流程

        1. 连接 MCP Server（自动发现工具）
        2. 分解任务
        3. 执行任务
        4. 整合结果
        5. 断开连接
        """
        print(f"\n{'='*60}")
        print(f"[OrchestratorV4] 启动（MCP 驱动模式）")
        print(f"请求: {user_request[:80]}...")
        print(f"{'='*60}")

        # Step 1: 连接 MCP Server
        print("\n[Step 1] 连接 MCP Server...")
        self.auto_connect_servers()
        tools = self.registry.list_tools()
        print(f"  → 已注册 {len(tools)} 个工具: {[t['name'] for t in tools]}")

        # Step 2: 分解任务
        print("\n[Step 2] 分解任务...")
        plan = self.decompose(user_request)
        tasks = plan.get("tasks", [])
        print(f"  → {len(tasks)} 个子任务")

        if project_path:
            for t in tasks:
                if "params" not in t:
                    t["params"] = {}
                t["params"].setdefault("path", project_path)

        # Step 3: 执行任务
        print("\n[Step 3] 执行任务...")
        task_results = {}
        for task in tasks:
            task_id = task.get("id", f"task-{int(time.time())}")
            if self.verbose:
                print(f"\n--- {task_id}: {task.get('description', '')[:60]} ---")
            task_results[task_id] = self.execute_task(task, task_id)

        # Step 4: 整合结果
        print("\n[Step 4] 整合结果...")
        final_report = self.integrate(user_request, plan, task_results)

        # Step 5: 断开连接
        self.disconnect_all()
        self.stop_workers()

        print(f"\n{'='*60}")
        print("[OrchestratorV4] 完成")
        print(f"{'='*60}")

        return {
            "request": user_request,
            "plan": plan,
            "results": task_results,
            "final_report": final_report,
            "state_summaries": {
                tid: sm.summary()
                for tid, sm in self.task_state_machines.items()
            },
            "tool_stats": self.registry.get_stats(),
        }


# ========== 入口 ==========

if __name__ == "__main__":
    orch = OrchestratorV4(verbose=True)

    # 示例：通过 MCP 工具链完成任务
    result = orch.run(
        "列出当前目录文件，读取 README.md 的前 10 行，然后统计行数",
        project_path=PROJECT_ROOT,
    )

    print("\n📊 工具调用统计:")
    stats = result["tool_stats"]
    print(f"  总调用: {stats['total_calls']}")
    print(f"  成功: {stats['success']}")
    print(f"  失败: {stats['failed']}")
    print(f"  按来源: {stats['by_source']}")

    print("\n📋 最终报告:\n")
    print(result["final_report"])
