#!/usr/bin/env python3
"""
agents/orchestrator.py - 多 Agent 协作调度器

真正的多进程架构：
1. Lead 进程（erniebot 推理 + 任务协调）
2. Researcher 子进程（独立进程，有自己的工具能力）
3. Coder 子进程（独立进程，有自己的工具能力）

进程间通信：
- Lead → Worker: 写 /tmp/agent_task_{role}.json
- Worker → Lead: 写 /tmp/agent_result_{role}.json
- Worker → Lead: stdout 通知
"""
import json
import os
import time
import subprocess
import threading
import erniebot
from typing import Dict, Any, Optional


TASK_FILE_RESEARCHER = "/tmp/agent_task_researcher.json"
TASK_FILE_CODER = "/tmp/agent_task_coder.json"
RESULT_FILE_RESEARCHER = "/tmp/agent_result_researcher.json"
RESULT_FILE_CODER = "/tmp/agent_result_coder.json"

ERNIE_TOKEN = "0b93205ac0fc59d69166edb8e24cf1bc48aed453"


def init_ernie():
    erniebot.api_type = "aistudio"
    erniebot.access_token = ERNIE_TOKEN


class SubAgent:
    """子 Agent 进程封装"""

    def __init__(self, role: str, worker_script: str):
        self.role = role
        self.worker_script = worker_script
        self.process: Optional[subprocess.Popen] = None
        self.ready = False

    def spawn(self):
        """启动子进程"""
        self.process = subprocess.Popen(
            ["python3", self.worker_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # 等待 READY 信号
        for _ in range(20):
            line = self.process.stdout.readline()
            if line and "READY" in line:
                self.ready = True
                print(f"[Orchestrator] {self.role} Agent 就绪 (PID={self.process.pid})")
                return
            time.sleep(0.2)
        print(f"[Orchestrator] {self.role} Agent 启动超时")

    def send_task(self, task: dict):
        """发送任务"""
        if not self.ready:
            print(f"[Orchestrator] {self.role} 未就绪，跳过任务")
            return

        # 写任务文件
        task_file = f"/tmp/agent_task_{self.role}.json"
        with open(task_file, 'w') as f:
            json.dump(task, f, ensure_ascii=False)
        
        print(f"[Orchestrator] → {self.role} 任务已分发: {task.get('type')}")

    def get_result(self, timeout: float = 30) -> Optional[dict]:
        """获取结果（等待 Worker 通知）"""
        result_file = f"/tmp/agent_result_{self.role}.json"

        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.exists(result_file):
                with open(result_file, 'r') as f:
                    result = json.load(f)
                os.remove(result_file)
                print(f"[Orchestrator] ← {self.role} 结果返回: {result.get('summary', '')[:60]}")
                return result
            time.sleep(0.3)

        print(f"[Orchestrator] ← {self.role} 结果等待超时")
        return None

    def stop(self):
        """停止子进程"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            print(f"[Orchestrator] {self.role} Agent 已停止")


class Orchestrator:
    """
    多 Agent 协作调度器

    流程：
    1. spawn_researcher() 和 spawn_coder() 并行启动子进程
    2. erniebot 推理任务拆解
    3. 并行分发任务给各子 Agent
    4. 收集子 Agent 结果
    5. erniebot 整合最终报告
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.researcher = SubAgent(
            "researcher",
            os.path.join(os.path.dirname(__file__), "worker_researcher.py")
        )
        self.coder = SubAgent(
            "coder",
            os.path.join(os.path.dirname(__file__), "worker_coder.py")
        )
        self.init_ernie()

    def init_ernie(self):
        init_ernie()

    def decompose(self, user_request: str) -> dict:
        """用 erniebot 做任务拆解"""
        prompt = f"""用户需求：{user_request}

请将上述需求拆解为具体的子任务。
输出格式为纯 JSON：
{{
  "tasks": [
    {{
      "type": "research | code | summarize",
      "description": "详细的任务描述",
      "assignee": "researcher | coder | lead"
    }}
  ],
  "parallel": true或false（是否有可并行的独立子任务）
}}

规则：
- assignee=researcher：需要信息检索、文件读取、结构分析
- assignee=coder：需要代码分析、语法检查、文档生成
- assignee=lead：需要综合判断、最终整合
- parallel=true 表示 researcher 和 coder 可同时工作
- 只输出 JSON，不要其他"""

        response = erniebot.ChatCompletion.create(
            model="ernie-lite",
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.get_result() if hasattr(response, 'get_result') else str(response)

        try:
            plan = json.loads(result)
            return plan
        except:
            return {
                "tasks": [{"type": "research", "description": user_request, "assignee": "researcher"}],
                "parallel": True,
            }

    def run(self, user_request: str, project_path: str = "") -> dict:
        """执行多 Agent 协作"""
        print(f"\n{'='*60}")
        print(f"[Orchestrator] 启动多 Agent 协作")
        print(f"[Orchestrator] 请求: {user_request[:50]}...")
        print(f"{'='*60}")

        # Step 1: 并行启动子 Agent
        print("\n[Step 1] 启动子 Agent...")
        self.researcher.spawn()
        self.coder.spawn()

        # Step 2: erniebot 任务拆解
        print("\n[Step 2] Lead Agent (erniebot) 推理任务拆解...")
        plan = self.decompose(user_request)
        tasks = plan.get("tasks", [])
        can_parallel = plan.get("parallel", False)

        print(f"  拆解出 {len(tasks)} 个子任务")
        print(f"  可并行: {can_parallel}")
        for t in tasks:
            print(f"  → [{t.get('assignee', '?')}] {t.get('description', '')[:40]}...")

        # 准备共享数据
        shared_data = {"project_path": project_path or os.getcwd()}

        # Step 3: 准备各子 Agent 的任务
        research_tasks = [t for t in tasks if t.get("assignee") == "researcher"]
        coder_tasks = [t for t in tasks if t.get("assignee") == "coder"]

        # Step 4: 并行/串行分发
        print("\n[Step 3] 分发任务...")

        if can_parallel and (research_tasks or coder_tasks):
            # 并行分发
            results = {}

            def dispatch_researcher():
                for t in research_tasks:
                    task_data = {**t, **shared_data}
                    self.researcher.send_task(task_data)
                if research_tasks:
                    results["researcher"] = self.researcher.get_result(timeout=60)

            def dispatch_coder():
                for t in coder_tasks:
                    task_data = {**t, **shared_data}
                    self.coder.send_task(task_data)
                if coder_tasks:
                    results["coder"] = self.coder.get_result(timeout=60)

            # 真正并行执行
            t1 = threading.Thread(target=dispatch_researcher)
            t2 = threading.Thread(target=dispatch_coder)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            all_results = results

        else:
            # 串行
            all_results = {}
            for t in tasks:
                assignee = t.get("assignee", "lead")
                task_data = {**t, **shared_data}

                if assignee == "researcher":
                    self.researcher.send_task(task_data)
                    all_results["researcher"] = self.researcher.get_result()
                elif assignee == "coder":
                    self.coder.send_task(task_data)
                    all_results["coder"] = self.coder.get_result()

        # Step 5: erniebot 整合结果
        print("\n[Step 4] Lead Agent (erniebot) 整合最终报告...")

        results_summary = []
        for agent, result in all_results.items():
            if result:
                if agent == "researcher":
                    findings = result.get("findings", [])
                    results_summary.append(f"=== {agent.upper()} 研究结果 ===")
                    results_summary.extend(findings)
                elif agent == "coder":
                    analysis = result.get("analysis", [])
                    results_summary.append(f"=== {agent.upper()} 分析结果 ===")
                    results_summary.extend(analysis)

        integration_prompt = f"""用户需求：{user_request}

各子 Agent 执行结果：
{chr(10).join(str(r) for r in results_summary)}

请整合以上结果，生成一份完整的 Markdown 格式报告，包含：
1. 执行概述
2. 研究发现（结构、文件、依赖）
3. 代码分析（函数、类、质量）
4. 最终结论和建议

只用 Markdown 输出。"""

        response = erniebot.ChatCompletion.create(
            model="ernie-lite",
            messages=[{"role": "user", "content": integration_prompt}],
        )
        final_report = response.get_result() if hasattr(response, 'get_result') else str(response)

        # 清理
        self.researcher.stop()
        self.coder.stop()

        print(f"\n{'='*60}")
        print("[Orchestrator] 多 Agent 协作完成")
        print(f"{'='*60}")

        return {
            "request": user_request,
            "plan": plan,
            "agent_results": all_results,
            "final_report": final_report,
        }


if __name__ == "__main__":
    # 测试
    init_ernie()
    orch = Orchestrator(verbose=True)
    result = orch.run(
        "分析 deepin-agent-teams 项目的代码结构和核心模块",
        project_path="/root/.openclaw/workspace/deepin-agent-teams"
    )
    print("\n最终报告：\n")
    print(result["final_report"])
