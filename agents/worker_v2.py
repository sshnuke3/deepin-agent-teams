#!/usr/bin/env python3
"""
agents/worker_v2.py - 基于 Registry 的可扩展 Worker（v2 API）
在 worker_base 基础上添加 stdout 通知和 CLI 参数支持
"""
import os
import sys
import time
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from worker_base import BaseWorker


class ExtensibleWorker(BaseWorker):
    """
    可扩展 Worker - 继承 BaseWorker，增加 stdout 通知
    """

    def __init__(self, role: str, capabilities: List[str]) -> None:
        super().__init__(role, capabilities)

    def register(self) -> str:
        self.agent_id = self.registry.register(
            capabilities=self.capabilities,
            metadata={"role": self.role, "pid": os.getpid()}
        )
        print(f"[{self.role}] Worker 注册完成: {self.agent_id}", flush=True)
        sys.stdout.write(f"REGISTERED:{self.agent_id}\n")
        sys.stdout.flush()
        return self.agent_id

    def can_handle(self, task: dict) -> bool:
        needed = set(task.get("capabilities_needed", []))
        available = set(self.capabilities)
        return bool(needed & available)

    def execute_task(self, task: dict) -> dict:
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
                    cap_params = {**params}
                    if "path" not in cap_params:
                        cap_params["path"] = params.get("project_path", "/root/.openclaw/workspace/deepin-agent-teams")
                    results[cap] = self.execute_capability(cap, cap_params)
                except Exception as e:
                    results[cap] = {"error": str(e)}
            else:
                results[cap] = {"error": f"不具备能力: {cap}"}

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

    def run(self) -> None:
        self.register()
        print(f"[{self.role}] Worker 主循环启动，等待 Registry 任务...", flush=True)
        while True:
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
                time.sleep(0.5)


# 保留 CapabilityExecutor 别名以便向后兼容
class CapabilityExecutor:
    """遗留兼容别名，请使用 ExtensibleWorker"""
    CAPABILITY_MAP = {}

    @staticmethod
    def execute(capability: str, params: dict) -> dict:
        return {"error": f"CapabilityExecutor 已废弃，请使用 ExtensibleWorker"}


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
