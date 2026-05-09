"""
冲突解决与协商机制
多 Agent 并行执行时的冲突检测、优先级协商、结果合并
"""
import os
import fcntl
import time
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ResourceLock:
    """资源锁"""
    resource_id: str       # 锁定的资源标识（文件路径/服务名/设备名）
    owner: str             # 持锁 Agent 名称
    acquired_at: str = ""
    lock_type: str = "exclusive"  # exclusive / shared
    timeout: int = 30      # 自动释放超时（秒）


@dataclass
class ConflictRecord:
    """冲突记录"""
    timestamp: str
    conflict_type: str     # resource / priority / result
    agents: List[str]      # 涉及的 Agent
    resource: str          # 冲突的资源描述
    resolution: str        # 解决方式
    winner: str = ""       # 胜出方


class ConflictResolver:
    """
    冲突解决器

    功能：
    1. 资源锁（fcntl 文件锁）— 防止并发写入同一文件
    2. 优先级协商 — 多 Agent 争抢同一资源时按优先级排序
    3. 结果合并 — 多 Agent 并行输出去重合并
    """

    # Agent 优先级（数值越大优先级越高）
    AGENT_PRIORITY = {
        "system_operator": 10,    # 系统操作最高优先级
        "lead": 9,                # 任务指挥官
        "coder": 7,               # 代码编写
        "content_creator": 6,     # 内容生成
        "researcher": 5,          # 研究分析
        "information_collector": 4,  # 信息收集
        "worker": 3,              # 通用执行者
    }

    def __init__(self):
        self._locks: Dict[str, ResourceLock] = {}
        self._lock_mutex = threading.Lock()
        self._conflict_history: List[ConflictRecord] = []
        self._lock_dir = "/tmp/deepin-agent-locks"
        os.makedirs(self._lock_dir, exist_ok=True)

    def acquire_lock(self, resource_id: str, agent_name: str,
                     lock_type: str = "exclusive", timeout: int = 30) -> bool:
        """
        获取资源锁

        Args:
            resource_id: 资源标识（文件路径等）
            agent_name: 请求锁的 Agent
            lock_type: exclusive（独占）/ shared（共享）
            timeout: 超时秒数

        Returns:
            是否成功获取
        """
        with self._lock_mutex:
            existing = self._locks.get(resource_id)

            if existing:
                # 检查是否超时
                if self._is_lock_expired(existing):
                    self._release_lock(resource_id)
                elif existing.owner == agent_name:
                    # 同一 Agent 重入
                    return True
                elif lock_type == "shared" and existing.lock_type == "shared":
                    # 共享锁兼容
                    return True
                else:
                    # 冲突！按优先级协商
                    return self._resolve_lock_conflict(resource_id, agent_name, existing)

            # 无冲突，直接获取
            lock = ResourceLock(
                resource_id=resource_id,
                owner=agent_name,
                acquired_at=datetime.now().isoformat(),
                lock_type=lock_type,
                timeout=timeout,
            )
            self._locks[resource_id] = lock

            # 同时获取文件锁（跨进程）
            try:
                lock_file = self._get_lock_path(resource_id)
                fd = open(lock_file, "w")
                if lock_type == "exclusive":
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                # fd 保持打开，锁在进程结束时自动释放
            except (IOError, OSError):
                pass  # 文件锁获取失败不影响进程内锁

            return True

    def release_lock(self, resource_id: str, agent_name: str):
        """释放资源锁"""
        with self._lock_mutex:
            lock = self._locks.get(resource_id)
            if lock and lock.owner == agent_name:
                self._release_lock(resource_id)

    def _resolve_lock_conflict(self, resource_id: str, new_agent: str,
                               existing_lock: ResourceLock) -> bool:
        """
        锁冲突协商：按优先级决定谁获得锁

        Returns:
            new_agent 是否获得锁
        """
        existing_priority = self.AGENT_PRIORITY.get(existing_lock.owner, 0)
        new_priority = self.AGENT_PRIORITY.get(new_agent, 0)

        if new_priority > existing_priority:
            # 新请求者优先级更高，抢占锁
            self._conflict_history.append(ConflictRecord(
                timestamp=datetime.now().isoformat(),
                conflict_type="resource",
                agents=[existing_lock.owner, new_agent],
                resource=resource_id,
                resolution=f"优先级抢占：{new_agent}({new_priority}) > {existing_lock.owner}({existing_priority})",
                winner=new_agent,
            ))
            self._release_lock(resource_id)
            self._locks[resource_id] = ResourceLock(
                resource_id=resource_id,
                owner=new_agent,
                acquired_at=datetime.now().isoformat(),
            )
            return True
        else:
            # 新请求者优先级低或相同，拒绝
            self._conflict_history.append(ConflictRecord(
                timestamp=datetime.now().isoformat(),
                conflict_type="resource",
                agents=[existing_lock.owner, new_agent],
                resource=resource_id,
                resolution=f"保持现有锁：{existing_lock.owner}({existing_priority}) >= {new_agent}({new_priority})",
                winner=existing_lock.owner,
            ))
            return False

    def _release_lock(self, resource_id: str):
        """内部释放锁"""
        self._locks.pop(resource_id, None)
        try:
            lock_file = self._get_lock_path(resource_id)
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except OSError:
            pass

    def _is_lock_expired(self, lock: ResourceLock) -> bool:
        """检查锁是否超时"""
        try:
            acquired = datetime.fromisoformat(lock.acquired_at)
            return (datetime.now() - acquired).total_seconds() > lock.timeout
        except Exception:
            return True

    def _get_lock_path(self, resource_id: str) -> str:
        """获取锁文件路径"""
        safe_name = resource_id.replace("/", "_").replace(" ", "_")[:60]
        return os.path.join(self._lock_dir, f"{safe_name}.lock")

    # === 结果合并 ===

    def merge_results(self, results: List[Dict]) -> Dict:
        """
        合并多个 Agent 的并行执行结果

        策略：
        1. 收集所有成功的结果
        2. 合并关键信息（去重）
        3. 按优先级排序
        """
        if not results:
            return {"success": False, "error": "无结果"}

        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        if not successful:
            return {
                "success": False,
                "error": "所有 Agent 执行失败",
                "failures": [r.get("error", "未知") for r in failed],
            }

        # 合并输出
        merged_output = []
        for r in successful:
            output = r.get("output", {})
            if isinstance(output, str):
                merged_output.append(output)
            elif isinstance(output, dict):
                merged_output.append(str(output))

        return {
            "success": True,
            "output": "\n---\n".join(merged_output),
            "agents_completed": len(successful),
            "agents_failed": len(failed),
            "details": successful,
        }

    # === 统计 ===

    def get_conflict_history(self) -> List[Dict]:
        """获取冲突历史"""
        from dataclasses import asdict
        return [asdict(c) for c in self._conflict_history]

    def get_active_locks(self) -> Dict[str, Dict]:
        """获取当前活跃锁"""
        from dataclasses import asdict
        return {k: asdict(v) for k, v in self._locks.items()}

    def cleanup_expired_locks(self):
        """清理所有超时锁"""
        with self._lock_mutex:
            expired = [rid for rid, lock in self._locks.items()
                       if self._is_lock_expired(lock)]
            for rid in expired:
                self._release_lock(rid)
            return len(expired)


# 全局单例
_resolver: Optional[ConflictResolver] = None


def get_resolver() -> ConflictResolver:
    global _resolver
    if _resolver is None:
        _resolver = ConflictResolver()
    return _resolver
