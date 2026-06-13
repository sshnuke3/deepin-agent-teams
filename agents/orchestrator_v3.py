#!/usr/bin/env python3
"""
agents/orchestrator_v3.py - 集成状态机 + Verifier 的多 Agent 编排器（v3）

基于 orchestrator_extensible，集成：
1. TaskStateMachine 状态机驱动（所有停止条件写死代码）
2. Verifier 独立质检（Worker 产出全部过 Verifier，不通过打回重做）

流程：
  spawn_workers()
    ↓
  decompose_with_erniebot() → 任务列表
    ↓
  submit_tasks() → PENDING
    ↓
  ┌──────────────────────────────┐
  │  for each task:              │
  │    claim_task() → CLAIMED    │
  │    Worker 执行 → RUNNING     │
  │    Verifier 验收 → VERIFIED  │
  │    PASS → COMPLETED          │
  │    FAIL → RETRY（≤3次）      │
  │    超时 → FAILED             │
  └──────────────────────────────┘
    ↓
  integrate_with_erniebot()
"""
import json
import os
import sys
import time
import subprocess
import threading
import traceback
from typing import Optional

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registry import AgentRegistry
from task_state_machine import TaskStateMachine, TaskState, TransitionContext, MAX_RETRY
from verifier import Verifier

# 双文心模型路由（ernie-lite + ernie-3.5）
from model_router import get_router

# 向后兼容：保留 init_ernie，但不再直接使用
def init_ernie():
    """已废弃，请使用 model_router.get_router()"""
    pass


class OrchestratorV3:
    """
    集成状态机 + Verifier 的编排器

    核心改进（vs orchestrator_extensible）：
    1. 每个任务独立状态机，不靠轮询超时就认为"完成了"
    2. Worker 执行后强制过 Verifier，不通过打回重做
    3. 所有状态跳转写 trace，可追溯
    4. 停止条件代码写死，不是模型感觉
    """

    def __init__(self, verbose: bool = True):
        import warnings
        warnings.warn(
            "OrchestratorV3 已废弃，请使用 agents.orchestrator.Orchestrator",
            DeprecationWarning, stacklevel=2
        )
        self.verbose = verbose
        self.registry = AgentRegistry()
        self.verifier = Verifier()
        self.workers = []
        self.task_state_machines: dict = {}  # task_id → TaskStateMachine

    def spawn_workers(self):
        """启动 Worker 池"""
        if self.verbose:
            print("\n[OrchestratorV3] 启动 Worker 池...")

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
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            self.workers.append((role, caps, proc))
            if self.verbose:
                print(f"[OrchestratorV3] 启动 {role} Worker (PID={proc.pid})", flush=True)

        # 等待注册完成
        deadline = time.time() + 15
        registered = set()

        while time.time() < deadline and len(registered) < len(self.workers):
            for role, _, proc in self.workers:
                if role in registered:
                    continue
                import select
                if select.select([proc.stdout], [], [], 0.1)[0]:
                    line = proc.stdout.readline()
                    if "REGISTERED:" in line:
                        registered.add(role)
                        if self.verbose:
                            print(f"[OrchestratorV3] ✓ {role} 注册完成", flush=True)
            time.sleep(0.1)

        time.sleep(0.5)
        if self.verbose:
            agents = self.registry.list_agents()
            print(f"[OrchestratorV3] 当前注册 Worker: {len(agents)}")

    def decompose_with_erniebot(self, user_request: str) -> dict:
        """erniebot 分解任务（不指定谁来执行）"""
        import erniebot
        prompt = f"""用户需求：{user_request}

请将上述需求分解为具体的能力任务。

输出格式为纯 JSON：
{{
  "tasks": [
    {{
      "id": "task-1",
      "description": "详细描述这个子任务",
      "capabilities_needed": ["cap1", "cap2"],
      "type": "code_analysis | file_reader | shell_executor | ...",
      "params": {{"path": "...", ...}}
    }}
  ],
  "summary": "一句话总结"
}}

可用能力（选最合适的）：
- file_reader, dir_scanner, code_analyzer, ast_parser, syntax_checker
- dependency_analyzer, shell_executor, git_analyzer
- web_search, web_fetcher, markdown_writer

规则：
- 每个 task 至少需要 1 个 capability
- type 字段要填，用于 Verifier 分叉验收标准
- 只输出 JSON，不要其他内容"""

        try:
            router = get_router(verbose=self.verbose)
            resp = router.chat(prompt, task_type="task_plan")
            if resp["success"]:
                return json.loads(resp["result"])
            else:
                raise Exception(resp.get("error", "router call failed"))
        except Exception as e:
            if self.verbose:
                print(f"[OrchestratorV3] 分解失败: {e}")
            return {
                "tasks": [{"id": f"task-{int(time.time())}", "description": user_request,
                          "capabilities_needed": ["shell_executor"], "type": "shell_executor", "params": {}}],
                "summary": user_request,
            }

    def submit_tasks(self, tasks: list) -> list:
        """提交任务到 Registry + 初始化状态机"""
        import erniebot
        task_ids = []
        for task in tasks:
            task_id = self.registry.submit_task(task)
            task_ids.append(task_id)

            # 初始化状态机
            sm = TaskStateMachine(task_id)
            self.task_state_machines[task_id] = sm

            if self.verbose:
                caps = task.get("capabilities_needed", [])
                print(f"[OrchestratorV3] 任务入队: {task_id} [{', '.join(caps)}] state={sm.state.value}")
        return task_ids

    def execute_single_task(self, task: dict, task_id: str) -> dict:
        """
        单任务执行流程（含状态机 + Verifier）

        PENDING → CLAIMED → RUNNING → VERIFIED → COMPLETED
                              ↓
                            RETRY（≤3次）
                              ↓
                            FAILED
        """
        sm = self.task_state_machines[task_id]
        retry_count = 0

        while True:
            # === PENDING → CLAIMED ===
            worker_id = self.registry.find_best_agent(task.get("capabilities_needed", []))
            if not worker_id:
                if self.verbose:
                    print(f"[OrchestratorV3] {task_id}: 无可用 Worker")
                sm.transition(TaskState.FAILED, TransitionContext(
                    error_msg="no available worker",
                    verdict="FAIL",
                ))
                return {"status": "failed", "reason": "no worker"}

            ctx_claimed = TransitionContext(worker_id=worker_id)
            sm.transition(TaskState.CLAIMED, ctx_claimed)

            # === CLAIMED → RUNNING ===
            ctx_running = TransitionContext(start_time=time.time())
            sm.transition(TaskState.RUNNING, ctx_running)

            # === WORKER 执行 ===
            if self.verbose:
                print(f"[OrchestratorV3] {task_id}: Worker {worker_id} 执行中...")

            try:
                # 从 Registry 获取任务结果（Worker 自主认领并完成）
                result = self._wait_worker_result(task_id, worker_id, timeout=60)
                if result is None:
                    raise TimeoutError(f"task {task_id} timeout")

            except Exception as e:
                sm.transition(TaskState.FAILED, TransitionContext(
                    error_msg=str(e),
                    verdict="FAIL",
                    retry_count=retry_count,
                ))
                return {"status": "failed", "reason": str(e)}

            # === RUNNING → VERIFIED (Verifier 验收) ===
            if self.verbose:
                print(f"[OrchestratorV3] {task_id}: Verifier 验收中...")

            v = self.verifier.verify(task, {"result": result})
            v_ctx = TransitionContext(
                verdict=v.result,
                verdict_causes=v.causes,
                retry_count=retry_count,
            )

            if v.is_pass:
                sm.transition(TaskState.VERIFIED, v_ctx)
                sm.transition(TaskState.COMPLETED, TransitionContext())
                return {"status": "completed", "result": result, "trace": sm.get_trace()}

            else:
                # FAIL → RETRY 或 FAILED
                sm.transition(TaskState.RETRY, v_ctx)
                if retry_count < MAX_RETRY:
                    retry_count += 1
                    if self.verbose:
                        print(f"[OrchestratorV3] {task_id}: 打回重做 (retry={retry_count})")
                    sm.retry_with_increment()
                    continue
                else:
                    # 重试次数耗尽 → FAILED
                    sm.transition(TaskState.FAILED, TransitionContext(
                        error_msg="max retry exceeded",
                        verdict="FAIL",
                        causes=v.causes,
                    ))
                    return {"status": "failed", "reason": f"max retry exceeded: {v.causes}", "trace": sm.get_trace()}

    def _wait_worker_result(self, task_id: str, worker_id: str, timeout: float = 60) -> Optional[dict]:
        """等待 Worker 执行结果"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self.registry.get_result(task_id)
            if r:
                return r
            # 超时检查
            sm = self.task_state_machines.get(task_id)
            if sm:
                sm.check_timeout(timeout=timeout)
            time.sleep(0.5)
        return None

    def integrate_with_erniebot(self, user_request: str, plan: dict, results: dict) -> str:
        """整合所有任务结果"""
        import erniebot
        result_parts = []
        for task_id, data in results.items():
            state = self.task_state_machines.get(task_id, None)
            state_str = state.state.value if state else "unknown"
            if isinstance(data, dict):
                role = data.get("role", "unknown")
                result_val = data.get("result", {})
                if isinstance(result_val, dict):
                    summary = result_val.get("summary", result_val.get("description", ""))[:200]
                else:
                    summary = str(result_val)[:200]
            else:
                summary = str(data)[:200]
            result_parts.append(f"## {task_id} [{state_str}]\n{summary}")

        integration_prompt = f"""用户需求：{user_request}

需求分解：
{json.dumps(plan, ensure_ascii=False, indent=2)}

Worker 执行结果：
{chr(10).join(result_parts)}

请生成 Markdown 格式报告，包含：
1. 执行概述（哪些任务成功/失败）
2. 各子任务执行情况
3. 关键发现
4. 最终结论和建议

只用 Markdown 输出。"""

        try:
            router = get_router(verbose=self.verbose)
            resp = router.chat(integration_prompt, task_type="report")
            if resp["success"]:
                return resp["result"]
            else:
                raise Exception(resp.get("error", "router call failed"))
        except Exception as e:
            return f"# 整合失败\n\n{e}\n\n原始结果：\n{json.dumps(results, ensure_ascii=False, indent=2)}"

    def stop_workers(self):
        for role, caps, proc in self.workers:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                import logging
                logging.getLogger(__name__).warning("Failed to terminate worker %s", role)

    def run(self, user_request: str, project_path: str = "") -> dict:
        """主流程"""
        print(f"\n{'='*60}")
        print(f"[OrchestratorV3] 启动（状态机 + Verifier 模式）")
        print(f"请求: {user_request[:50]}...")
        print(f"{'='*60}")

        # Step 0: 启动 Worker
        self.spawn_workers()

        # Step 1: 分解任务
        print("\n[Step 1] 分解任务...")
        plan = self.decompose_with_erniebot(user_request)
        tasks = plan.get("tasks", [])
        print(f"  → {len(tasks)} 个子任务")

        if project_path:
            for t in tasks:
                if "params" not in t:
                    t["params"] = {}
                t["params"].setdefault("path", project_path)
                t["params"].setdefault("project_path", project_path)

        # Step 2: 提交 + 初始化状态机
        print("\n[Step 2] 任务入队 + 状态机初始化...")
        task_ids = self.submit_tasks(tasks)

        # Step 3: 逐个执行（含状态机 + Verifier）
        print("\n[Step 3] 执行（含状态机驱动 + 独立质检）...")
        task_results = {}
        for task, task_id in zip(tasks, task_ids):
            if self.verbose:
                print(f"\n--- 处理任务: {task_id} ---")
            task_results[task_id] = self.execute_single_task(task, task_id)
            sm = self.task_state_machines.get(task_id)
            if sm:
                print(f"[OrchestratorV3] {task_id}: 最终状态 = {sm.state.value}")

        # Step 4: 整合结果
        print("\n[Step 4] 整合结果...")
        final_report = self.integrate_with_erniebot(user_request, plan, task_results)

        self.stop_workers()

        print(f"\n{'='*60}")
        print("[OrchestratorV3] 完成")
        print(f"{'='*60}")

        return {
            "request": user_request,
            "plan": plan,
            "results": task_results,
            "final_report": final_report,
            "state_summaries": {tid: self.task_state_machines[tid].summary()
                                for tid in task_ids if tid in self.task_state_machines},
        }


if __name__ == "__main__":
    init_ernie()
    orch = OrchestratorV3(verbose=True)
    result = orch.run(
        "分析 deepin-agent-teams 项目的代码结构，生成文档",
        project_path="/root/.openclaw/workspace/deepin-agent-teams"
    )
    print("\n最终报告：\n")
    print(result["final_report"])
