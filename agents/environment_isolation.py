"""
environment_isolation.py — 三级环境隔离

核心思路（学自 OpenVibeCoding）：
- shared:    所有人共用一个环境（省钱，适合个人项目）
- isolated:  每用户/每 Worker 独立环境（适合团队）
- task:      每任务独立环境 + 独立资源配额（适合多租户 SaaS）

不依赖具体沙箱技术（Docker/进程/CloudBase），只定义隔离策略。
具体实现由 HandsInterface 的子类完成。
"""

import os
import sys
import json
import uuid
import shutil
import tempfile
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
SANDBOX_ROOT = os.path.join(PROJECT_ROOT, ".sandboxes")


# ============================================================
# 隔离级别
# ============================================================

class IsolationLevel(Enum):
    """环境隔离级别"""
    SHARED = "shared"        # 所有人共用（默认，向后兼容）
    ISOLATED = "isolated"    # 每 Worker 独立环境
    TASK = "task"            # 每任务独立环境（最严格）


# ============================================================
# 资源配额
# ============================================================

@dataclass
class ResourceQuota:
    """资源配额限制"""
    max_files: int = 100           # 最大文件数
    max_file_size_mb: float = 10   # 单文件最大 MB
    max_total_size_mb: float = 100 # 总空间最大 MB
    max_processes: int = 5         # 最大并发进程数
    max_cpu_percent: float = 50    # CPU 使用上限 %
    max_memory_mb: float = 512     # 内存上限 MB
    max_network_requests: int = 50 # 网络请求数上限
    timeout_seconds: float = 120   # 执行超时

    def to_dict(self) -> dict:
        return {
            "max_files": self.max_files,
            "max_file_size_mb": self.max_file_size_mb,
            "max_total_size_mb": self.max_total_size_mb,
            "max_processes": self.max_processes,
            "max_cpu_percent": self.max_cpu_percent,
            "max_memory_mb": self.max_memory_mb,
            "max_network_requests": self.max_network_requests,
            "timeout_seconds": self.timeout_seconds,
        }


# ============================================================
# 环境描述
# ============================================================

@dataclass
class Environment:
    """执行环境描述"""
    env_id: str = ""
    level: IsolationLevel = IsolationLevel.SHARED
    root_path: str = ""            # 环境根目录
    owner_id: str = ""             # 所有者（worker_id 或 task_id）
    quota: ResourceQuota = field(default_factory=ResourceQuota)
    created_at: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)
    _active: bool = True

    @property
    def is_active(self) -> bool:
        return self._active

    def to_dict(self) -> dict:
        return {
            "env_id": self.env_id,
            "level": self.level.value,
            "root_path": self.root_path,
            "owner_id": self.owner_id,
            "quota": self.quota.to_dict(),
            "created_at": self.created_at,
            "active": self._active,
        }


# ============================================================
# 环境管理器
# ============================================================

class EnvironmentManager:
    """
    环境管理器

    负责创建、销毁、查询执行环境。
    不关心底层用什么技术隔离（Docker/进程/目录），只管理策略。
    """

    def __init__(self, sandbox_root: str = None) -> None:
        self._root = sandbox_root or SANDBOX_ROOT
        self._environments: Dict[str, Environment] = {}
        self._shared_env: Optional[Environment] = None

    def get_or_create(
        self,
        level: IsolationLevel,
        owner_id: str = "",
        quota: ResourceQuota = None,
    ) -> Environment:
        """获取或创建环境"""
        if level == IsolationLevel.SHARED:
            return self._get_shared_env()
        elif level == IsolationLevel.ISOLATED:
            return self._get_isolated_env(owner_id, quota)
        elif level == IsolationLevel.TASK:
            return self._create_task_env(owner_id, quota)
        else:
            raise ValueError(f"Unknown isolation level: {level}")

    def _get_shared_env(self) -> Environment:
        """获取共享环境（所有人共用）"""
        if self._shared_env is None:
            env_id = "shared-default"
            root = os.path.join(self._root, "shared")
            os.makedirs(root, exist_ok=True)
            self._shared_env = Environment(
                env_id=env_id,
                level=IsolationLevel.SHARED,
                root_path=root,
                owner_id="all",
                quota=ResourceQuota(),  # 默认配额
            )
            self._environments[env_id] = self._shared_env
        return self._shared_env

    def _get_isolated_env(self, owner_id: str, quota: ResourceQuota = None) -> Environment:
        """获取隔离环境（每 Worker 独立）"""
        env_id = f"isolated-{owner_id}"

        if env_id in self._environments and self._environments[env_id].is_active:
            return self._environments[env_id]

        root = os.path.join(self._root, "isolated", owner_id)
        os.makedirs(root, exist_ok=True)

        env = Environment(
            env_id=env_id,
            level=IsolationLevel.ISOLATED,
            root_path=root,
            owner_id=owner_id,
            quota=quota or ResourceQuota(),
        )
        self._environments[env_id] = env
        return env

    def _create_task_env(self, owner_id: str, quota: ResourceQuota = None) -> Environment:
        """创建任务环境（每任务独立，最严格隔离）"""
        env_id = f"task-{owner_id}-{uuid.uuid4().hex[:6]}"
        root = os.path.join(self._root, "tasks", env_id)
        os.makedirs(root, exist_ok=True)

        env = Environment(
            env_id=env_id,
            level=IsolationLevel.TASK,
            root_path=root,
            owner_id=owner_id,
            quota=quota or ResourceQuota(
                max_files=50,
                max_file_size_mb=5,
                max_total_size_mb=50,
                max_processes=3,
                timeout_seconds=60,
            ),
        )
        self._environments[env_id] = env
        return env

    def destroy(self, env_id: str) -> None:
        """销毁环境（清理资源）"""
        env = self._environments.get(env_id)
        if not env:
            return

        env._active = False

        # 清理文件系统
        if env.level in (IsolationLevel.TASK, IsolationLevel.ISOLATED):
            if os.path.exists(env.root_path):
                try:
                    shutil.rmtree(env.root_path)
                except Exception as e:
                    print(f"[EnvManager] 清理失败: {env.root_path} - {e}")

        del self._environments[env_id]

    def destroy_all(self) -> None:
        """销毁所有环境"""
        env_ids = list(self._environments.keys())
        for env_id in env_ids:
            if env_id != "shared-default":  # 保留共享环境
                self.destroy(env_id)

    def list_environments(self) -> List[Dict]:
        """列出所有活跃环境"""
        return [env.to_dict() for env in self._environments.values() if env.is_active]

    def get_env(self, env_id: str) -> Optional[Environment]:
        """获取环境"""
        return self._environments.get(env_id)

    def check_quota(self, env_id: str) -> Dict[str, Any]:
        """检查环境的资源使用情况"""
        env = self._environments.get(env_id)
        if not env or not env.is_active:
            return {"valid": False, "reason": "环境不存在或已销毁"}

        root = env.root_path
        if not os.path.exists(root):
            return {"valid": True, "used_files": 0, "used_size_mb": 0}

        # 统计文件数和大小
        file_count = 0
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(root):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                    file_count += 1
                except OSError:
                    pass

        total_size_mb = total_size / (1024 * 1024)
        quota = env.quota

        violations = []
        if file_count > quota.max_files:
            violations.append(f"文件数超限: {file_count}/{quota.max_files}")
        if total_size_mb > quota.max_total_size_mb:
            violations.append(f"总大小超限: {total_size_mb:.1f}/{quota.max_total_size_mb} MB")

        return {
            "valid": len(violations) == 0,
            "env_id": env_id,
            "used_files": file_count,
            "used_size_mb": round(total_size_mb, 2),
            "quota": quota.to_dict(),
            "violations": violations,
        }


# ============================================================
# 隔离策略预设
# ============================================================

class IsolationPolicy:
    """隔离策略预设（按场景推荐配置）"""

    @staticmethod
    def personal_project() -> tuple:
        """个人项目：共享环境，宽松配额"""
        return IsolationLevel.SHARED, ResourceQuota(
            max_files=500,
            max_file_size_mb=50,
            max_total_size_mb=1000,
            max_processes=10,
            timeout_seconds=300,
        )

    @staticmethod
    def team_project() -> tuple:
        """团队项目：每 Worker 隔离，中等配额"""
        return IsolationLevel.ISOLATED, ResourceQuota(
            max_files=200,
            max_file_size_mb=20,
            max_total_size_mb=500,
            max_processes=5,
            timeout_seconds=180,
        )

    @staticmethod
    def multi_tenant() -> tuple:
        """多租户 SaaS：每任务隔离，严格配额"""
        return IsolationLevel.TASK, ResourceQuota(
            max_files=50,
            max_file_size_mb=5,
            max_total_size_mb=50,
            max_processes=3,
            timeout_seconds=60,
        )


# ============================================================
# 内置测试
# ============================================================

if __name__ == "__main__":
    print("=== environment_isolation.py 测试 ===\n")

    import tempfile
    test_root = tempfile.mkdtemp(prefix="env_test_")
    mgr = EnvironmentManager(sandbox_root=test_root)

    # Test 1: 共享环境
    print("Test 1: 共享环境")
    shared = mgr.get_or_create(IsolationLevel.SHARED)
    assert shared.level == IsolationLevel.SHARED
    assert shared.is_active
    assert os.path.exists(shared.root_path)
    # 再次获取应该是同一个
    shared2 = mgr.get_or_create(IsolationLevel.SHARED)
    assert shared.env_id == shared2.env_id
    print("  ✅ PASS\n")

    # Test 2: 隔离环境
    print("Test 2: 隔离环境")
    iso1 = mgr.get_or_create(IsolationLevel.ISOLATED, "worker-001")
    iso2 = mgr.get_or_create(IsolationLevel.ISOLATED, "worker-002")
    assert iso1.env_id != iso2.env_id
    assert iso1.root_path != iso2.root_path
    assert os.path.exists(iso1.root_path)
    assert os.path.exists(iso2.root_path)
    # 再次获取应该复用
    iso1_again = mgr.get_or_create(IsolationLevel.ISOLATED, "worker-001")
    assert iso1.env_id == iso1_again.env_id
    print("  ✅ PASS\n")

    # Test 3: 任务环境（每任务独立）
    print("Test 3: 任务环境")
    task1 = mgr.get_or_create(IsolationLevel.TASK, "task-001")
    task2 = mgr.get_or_create(IsolationLevel.TASK, "task-001")  # 同任务不同环境
    assert task1.env_id != task2.env_id  # 每次都创建新环境
    assert os.path.exists(task1.root_path)
    print("  ✅ PASS\n")

    # Test 4: 资源配额检查
    print("Test 4: 资源配额检查")
    quota_check = mgr.check_quota(iso1.env_id)
    assert quota_check["valid"]
    assert quota_check["used_files"] == 0
    print("  ✅ PASS\n")

    # Test 5: 环境列表
    print("Test 5: 环境列表")
    envs = mgr.list_environments()
    assert len(envs) >= 4  # shared + 2 isolated + 2 task
    env_ids = [e["env_id"] for e in envs]
    assert "shared-default" in env_ids
    print("  ✅ PASS\n")

    # Test 6: 销毁环境
    print("Test 6: 销毁环境")
    mgr.destroy(task1.env_id)
    assert mgr.get_env(task1.env_id) is None
    envs_after = mgr.list_environments()
    assert len(envs_after) < len(envs)
    print("  ✅ PASS\n")

    # Test 7: 隔离策略预设
    print("Test 7: 隔离策略预设")
    level, quota = IsolationPolicy.personal_project()
    assert level == IsolationLevel.SHARED
    assert quota.max_files == 500

    level, quota = IsolationPolicy.multi_tenant()
    assert level == IsolationLevel.TASK
    assert quota.max_files == 50
    print("  ✅ PASS\n")

    # Test 8: 环境描述序列化
    print("Test 8: 环境序列化")
    d = iso1.to_dict()
    assert d["level"] == "isolated"
    assert d["owner_id"] == "worker-001"
    assert "quota" in d
    print("  ✅ PASS\n")

    # 清理
    mgr.destroy_all()
    shutil.rmtree(test_root, ignore_errors=True)

    print("=== 所有测试通过 ===\n")
