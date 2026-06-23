#!/usr/bin/env python3
"""
tools/checkpoint_manager.py - 检查点管理器

核心设计：
1. 每个 task 有独立 checkpoint 目录
2. 每个 capability 执行完写一条 checkpoint 记录
3. 失败重启时，从最近 checkpoint 恢复（跳过已完成的 capability）
4. 成功完成后清理 checkpoint

使用方式：
    cm = CheckpointManager(task_id)
    cm.save("code_analyzer", result)  # 每步完成时
    last = cm.last_checkpoint()       # 重启时恢复
    if last:
        resume_from(last["capability"])
    cm.cleanup()                      # 成功完成后
"""
import os
import json
import hashlib
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

CHECKPOINT_DIR = "data/checkpoints"


@dataclass
class Checkpoint:
    task_id: str
    capability: str
    completed_at: float
    result_hash: str       # 结果摘要（防篡改）
    result_size: int       # 结果大小
    step: int              # 第几步

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "capability": self.capability,
            "completed_at": self.completed_at,
            "result_hash": self.result_hash,
            "result_size": self.result_size,
            "step": self.step,
        }


class CheckpointManager:
    """
    检查点管理器

    文件结构：
    data/checkpoints/
        {task_id}/
            metadata.json          # task 级元信息（创建时间、重试次数）
            {capability}-meta.json  # 单个 capability 的 checkpoint
            {capability}-result.json # capability 执行结果
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.base_dir = os.path.join(CHECKPOINT_DIR, task_id)
        os.makedirs(self.base_dir, exist_ok=True)
        self._meta_path = os.path.join(self.base_dir, "metadata.json")
        self._load_meta()

    def _load_meta(self):
        if os.path.exists(self._meta_path):
            with open(self._meta_path) as f:
                self.meta = json.load(f)
        else:
            self.meta = {
                "task_id": self.task_id,
                "created_at": None,
                "attempts": 0,
                "completed_steps": [],  # 已完成的 capability 列表
            }

    def _save_meta(self):
        with open(self._meta_path, "w") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)

    def init(self, retry_count: int = 0):
        """初始化 metadata（第一次创建或重试时）"""
        import time
        self.meta["created_at"] = time.time()
        self.meta["attempts"] = retry_count
        self._save_meta()

    def save(self, capability: str, result: Any) -> Checkpoint:
        """
        保存 capability 执行结果为 checkpoint

        流程：
        1. 写 result.json（实际结果）
        2. 写 meta.json（摘要信息）
        3. 更新 metadata（completed_steps）
        """
        import time
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        result_bytes = result_str.encode("utf-8")
        result_hash = hashlib.sha256(result_bytes).hexdigest()[:16]

        step = len(self.meta["completed_steps"])

        cp = Checkpoint(
            task_id=self.task_id,
            capability=capability,
            completed_at=time.time(),
            result_hash=result_hash,
            result_size=len(result_bytes),
            step=step,
        )

        # 写结果
        result_path = os.path.join(self.base_dir, f"{capability}-result.json")
        meta_path = os.path.join(self.base_dir, f"{capability}-meta.json")

        with open(result_path, "w") as f:
            f.write(result_str)
        with open(meta_path, "w") as f:
            json.dump(cp.to_dict(), f, ensure_ascii=False, indent=2)

        # 更新 metadata
        if capability not in self.meta["completed_steps"]:
            self.meta["completed_steps"].append(capability)
        self._save_meta()

        return cp

    def is_completed(self, capability: str) -> bool:
        """检查某个 capability 是否已完成"""
        return capability in self.meta["completed_steps"]

    def last_checkpoint(self) -> Optional[Dict]:
        """
        获取最后一个 checkpoint（用于恢复）

        Returns:
            {
                "capability": "code_analyzer",
                "result": {...},        # capability 执行结果
                "checkpoint": {...}    # Checkpoint 对象 dict
            }
            or None if无 checkpoint
        """
        completed = self.meta.get("completed_steps", [])
        if not completed:
            return None

        last_cap = completed[-1]
        result_path = os.path.join(self.base_dir, f"{last_cap}-result.json")
        meta_path = os.path.join(self.base_dir, f"{last_cap}-meta.json")

        if not os.path.exists(result_path):
            return None

        with open(result_path) as f:
            result = json.load(f)
        with open(meta_path) as f:
            checkpoint = json.load(f)

        return {
            "capability": last_cap,
            "result": result,
            "checkpoint": checkpoint,
        }

    def get_completed_capabilities(self) -> List[str]:
        """获取所有已完成的 capability"""
        return self.meta.get("completed_steps", [])

    def verify(self, capability: str, result: Any) -> bool:
        """
        验证 result 是否与 checkpoint 一致（防篡改）

        用于恢复后验证数据完整性
        """
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        result_hash = hashlib.sha256(result_str.encode("utf-8")).hexdigest()[:16]
        meta_path = os.path.join(self.base_dir, f"{capability}-meta.json")

        if not os.path.exists(meta_path):
            return False

        with open(meta_path) as f:
            cp_data = json.load(f)

        return cp_data.get("result_hash") == result_hash

    def cleanup(self):
        """清理 task 的所有 checkpoint 文件（任务成功后调用）"""
        import shutil
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)

    def summary(self) -> dict:
        """当前 snapshot"""
        return {
            "task_id": self.task_id,
            "attempts": self.meta.get("attempts", 0),
            "completed": self.meta.get("completed_steps", []),
            "step": len(self.meta.get("completed_steps", [])),
        }


# ========== 单元测试 ==========

def _test():
    import time, shutil

    print("\n=== Checkpoint 单元测试 ===\n")

    task_id = f"test-cp-{int(time.time())}"
    cm = CheckpointManager(task_id)
    cm.init(retry_count=0)

    # Test 1: 初始状态
    print("Test 1: init + 初始状态")
    assert cm.get_completed_capabilities() == []
    print("  ✅ PASS\n")

    # Test 2: 保存 checkpoint
    print("Test 2: 保存 + 查询")
    cm.save("file_reader", {"path": "/tmp/a.txt", "size": 123})
    cm.save("code_analyzer", {"lines": 456, "functions": ["run", "stop"]})
    completed = cm.get_completed_capabilities()
    assert completed == ["file_reader", "code_analyzer"], f"got {completed}"
    print("  ✅ PASS\n")

    # Test 3: last_checkpoint 恢复
    print("Test 3: last_checkpoint 恢复")
    last = cm.last_checkpoint()
    assert last is not None
    assert last["capability"] == "code_analyzer"
    assert last["result"]["lines"] == 456
    print(f"  ✅ PASS (last={last['capability']})\n")

    # Test 4: is_completed
    print("Test 4: is_completed")
    assert cm.is_completed("file_reader") == True
    assert cm.is_completed("web_search") == False
    print("  ✅ PASS\n")

    # Test 5: 新建 manager 实例读取（跨进程）
    print("Test 5: 跨进程读取")
    cm2 = CheckpointManager(task_id)
    assert cm2.is_completed("file_reader") == True
    assert cm2.last_checkpoint()["result"]["lines"] == 456
    print("  ✅ PASS\n")

    # Test 6: cleanup
    print("Test 6: cleanup")
    cm.cleanup()
    assert not os.path.exists(cm.base_dir)
    print("  ✅ PASS\n")

    print("=== 所有测试通过 ===\n")


if __name__ == "__main__":
    _test()
