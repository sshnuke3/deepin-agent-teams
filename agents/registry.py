"""
agents/registry.py - Agent 注册中心
每个 Agent 启动时注册自己的能力，任务路由基于能力匹配
"""
import json
import os
import time
import fcntl
import threading
from typing import Dict, List, Set


REGISTRY_FILE = "/tmp/agent_registry.json"
RESULT_DIR = "/tmp/agent_results"
LOCK_FILE = "/tmp/agent_registry.lock"

_lock_fd = None


def _get_lock():
    """获取文件锁（使用 fcntl.flock）"""
    global _lock_fd
    if _lock_fd is None:
        _lock_fd = open(LOCK_FILE, 'w')
    return _lock_fd


def acquire_lock():
    """获取文件锁"""
    lock_fd = _get_lock()
    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)


def release_lock():
    """释放文件锁"""
    lock_fd = _get_lock()
    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)


def read_registry() -> Dict:
    acquire_lock()
    try:
        if os.path.exists(REGISTRY_FILE):
            with open(REGISTRY_FILE, 'r') as f:
                return json.load(f)
        return {"agents": {}, "task_queue": []}
    finally:
        release_lock()


def write_registry(registry: Dict):
    acquire_lock()
    try:
        os.makedirs(os.path.dirname(REGISTRY_FILE) or '.', exist_ok=True)
        tmp = REGISTRY_FILE + f".{os.getpid()}.tmp"
        with open(tmp, 'w') as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        os.rename(tmp, REGISTRY_FILE)  # atomic
    finally:
        release_lock()


class AgentRegistry:
    """
    Agent 注册中心 - 负责：
    1. Agent 注册自己的能力和元数据
    2. 任务路由：根据能力匹配合适的 Agent
    3. 任务队列管理
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.my_id = f"agent-{os.getpid()}"
        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(RESULT_DIR, exist_ok=True)

    def register(self, capabilities: List[str], metadata: Dict = None) -> str:
        """
        注册 Agent 及其能力

        Args:
            capabilities: ["file_reader", "code_analysis", "web_search", ...]
            metadata: {role, description, ...}

        Returns:
            agent_id
        """
        acquire_lock()
        try:
            registry = read_registry()

            agent_id = f"{metadata.get('role', 'unknown')}-{os.getpid()}-{int(time.time())}"

            registry["agents"][agent_id] = {
                "capabilities": capabilities,
                "metadata": metadata or {},
                "registered_at": time.time(),
                "last_heartbeat": time.time(),
                "status": "idle",  # idle, working, dead
            }

            write_registry(registry)
            self.my_id = agent_id

            if self._initialized:
                pass

            return agent_id
        finally:
            release_lock()

    def unregister(self):
        """注销当前 Agent"""
        acquire_lock()
        try:
            registry = read_registry()
            if self.my_id in registry["agents"]:
                del registry["agents"][self.my_id]
                write_registry(registry)
        finally:
            release_lock()

    def heartbeat(self):
        """更新心跳"""
        acquire_lock()
        try:
            registry = read_registry()
            if self.my_id in registry["agents"]:
                registry["agents"][self.my_id]["last_heartbeat"] = time.time()
                write_registry(registry)
        finally:
            release_lock()

    def find_agents_by_capability(self, capability: str) -> List[Dict]:
        """根据能力查找 Agent"""
        registry = read_registry()
        matching = []

        now = time.time()
        for agent_id, info in registry["agents"].items():
            # 检查心跳（30秒内有响应才算活）
            if now - info.get("last_heartbeat", 0) > 30:
                continue
            if capability in info.get("capabilities", []):
                matching.append({"id": agent_id, **info})

        return matching

    def find_best_agent(self, capabilities_needed: List[str]) -> str:
        """找到最适合的 Agent（优先级：idle > working）"""
        candidates = []

        for cap in capabilities_needed:
            agents = self.find_agents_by_capability(cap)
            for agent in agents:
                if agent["status"] == "idle":
                    candidates.append(agent)
                    break

        if not candidates:
            return None

        # 优先 idle 的
        for c in candidates:
            if c["status"] == "idle":
                return c["id"]
        return candidates[0]["id"] if candidates else None

    def update_status(self, agent_id: str, status: str):
        """更新 Agent 状态"""
        acquire_lock()
        try:
            registry = read_registry()
            if agent_id in registry["agents"]:
                registry["agents"][agent_id]["status"] = status
                registry["agents"][agent_id]["last_heartbeat"] = time.time()
                write_registry(registry)
        finally:
            release_lock()

    def submit_task(self, task: Dict) -> str:
        """
        提交任务到队列

        task = {
            "id": "task-xxx",
            "capabilities_needed": ["file_reader", "code_analysis"],
            "description": "分析这个项目的代码结构",
            "priority": "normal",
        }
        """
        task_id = task.get("id") or f"task-{int(time.time())}"
        task["id"] = task_id
        task["submitted_at"] = time.time()
        task["status"] = "pending"

        acquire_lock()
        try:
            registry = read_registry()
            registry["task_queue"].append(task)
            write_registry(registry)
        finally:
            release_lock()

        return task_id

    def claim_task(self, agent_id: str, timeout: int = 5) -> Dict:
        """Agent 认领一个任务（基于能力匹配）"""
        deadline = time.time() + timeout

        while time.time() < deadline:
            acquire_lock()
            try:
                registry = read_registry()
                queue = registry["task_queue"]

                for i, task in enumerate(queue):
                    if task["status"] != "pending":
                        continue
                    caps_needed = task.get("capabilities_needed", [])
                    if not caps_needed:
                        continue

                    # 找到有匹配能力的 Agent
                    for cap in caps_needed:
                        agents = self.find_agents_by_capability(cap)
                        if any(a["id"] == agent_id for a in agents):
                            # 认领
                            task["status"] = "claimed"
                            task["claimed_by"] = agent_id
                            task["claimed_at"] = time.time()
                            queue[i] = task
                            registry["task_queue"] = queue
                            self.update_status(agent_id, "working")
                            write_registry(registry)
                            return task

                # 没有匹配的任务，短暂等待
            finally:
                release_lock()

            time.sleep(0.5)

        return None

    def complete_task(self, task_id: str, result: Dict):
        """标记任务完成"""
        acquire_lock()
        try:
            registry = read_registry()
            queue = registry["task_queue"]

            for i, task in enumerate(queue):
                if task["id"] == task_id:
                    task["status"] = "completed"
                    task["completed_at"] = time.time()
                    task["result"] = result
                    queue[i] = task

                    # Agent 状态恢复 idle
                    if task.get("claimed_by"):
                        self.update_status(task["claimed_by"], "idle")

                    registry["task_queue"] = queue
                    write_registry(registry)
                    return

        finally:
            release_lock()

    def get_result(self, task_id: str) -> Dict:
        """获取任务结果"""
        acquire_lock()
        try:
            registry = read_registry()
            for task in registry["task_queue"]:
                if task["id"] == task_id and task["status"] == "completed":
                    return task.get("result", {})
        finally:
            release_lock()
        return None

    def list_agents(self) -> Dict:
        """列出所有注册 Agent"""
        return read_registry()["agents"]

    def list_tasks(self, status: str = None) -> List[Dict]:
        """列出任务"""
        registry = read_registry()
        tasks = registry.get("task_queue", [])
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks
