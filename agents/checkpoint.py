#!/usr/bin/env python3
"""
agents/checkpoint.py — 任务检查点持久化

将任务状态保存到 SQLite，支持：
1. 任务检查点保存（状态/上下文/token消耗/阶段）
2. 从检查点恢复任务
3. 任务列表查询
4. 清理过期检查点
"""
import os
import sys
import time
import json
import sqlite3
from typing import Optional, Dict, Any, List
from dataclasses import asdict

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
CHECKPOINT_DIR = os.path.join(PROJECT_ROOT, "data", "checkpoints")
os.makedirs(CHECKPOINT_DIR, exist_ok=True)

DB_PATH = os.path.join(CHECKPOINT_DIR, "checkpoints.db")


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（自动创建表）"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            task_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            phase TEXT,
            worker_id TEXT,
            retry_count INTEGER DEFAULT 0,
            token_used INTEGER DEFAULT 0,
            token_budget INTEGER DEFAULT 0,
            context_json TEXT,
            trace_json TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            error_msg TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_checkpoints_state ON checkpoints(state)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_checkpoints_updated ON checkpoints(updated_at)
    """)
    conn.commit()
    return conn


def save_checkpoint(
    task_id: str,
    state: str,
    phase: str = None,
    worker_id: str = None,
    retry_count: int = 0,
    token_used: int = 0,
    token_budget: int = 0,
    context: Dict = None,
    trace: List[Dict] = None,
    error_msg: str = None,
) -> bool:
    """
    保存任务检查点

    Args:
        task_id: 任务ID
        state: 当前状态（pending/claimed/planning/running/verified/completed/failed/retry）
        phase: RUNNING内部阶段（plan/gather/analyze/execute）
        worker_id: 执行者ID
        retry_count: 重试次数
        token_used: 已用token数
        token_budget: token预算
        context: 任务上下文（JSON序列化）
        trace: 状态跳转历史（JSON序列化）
        error_msg: 错误信息

    Returns:
        True = 保存成功
    """
    try:
        now = time.time()
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO checkpoints
            (task_id, state, phase, worker_id, retry_count, token_used, token_budget,
             context_json, trace_json, created_at, updated_at, error_msg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id, state, phase, worker_id, retry_count, token_used, token_budget,
            json.dumps(context or {}, ensure_ascii=False),
            json.dumps(trace or [], ensure_ascii=False),
            now, now, error_msg,
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Checkpoint] save failed: {e}")
        return False


def load_checkpoint(task_id: str) -> Optional[Dict[str, Any]]:
    """
    加载任务检查点

    Args:
        task_id: 任务ID

    Returns:
        检查点字典，或 None（不存在）
    """
    try:
        conn = _get_conn()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM checkpoints WHERE task_id = ?", (task_id,)
        ).fetchone()
        conn.close()

        if row is None:
            return None

        return {
            "task_id": row["task_id"],
            "state": row["state"],
            "phase": row["phase"],
            "worker_id": row["worker_id"],
            "retry_count": row["retry_count"],
            "token_used": row["token_used"],
            "token_budget": row["token_budget"],
            "context": json.loads(row["context_json"] or "{}"),
            "trace": json.loads(row["trace_json"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "error_msg": row["error_msg"],
        }
    except Exception as e:
        print(f"[Checkpoint] load failed: {e}")
        return None


def list_checkpoints(
    state: str = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    列出检查点

    Args:
        state: 按状态过滤（可选）
        limit: 返回数量上限
        offset: 偏移量

    Returns:
        检查点列表
    """
    try:
        conn = _get_conn()
        conn.row_factory = sqlite3.Row

        if state:
            rows = conn.execute(
                "SELECT * FROM checkpoints WHERE state = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (state, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM checkpoints ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()

        conn.close()

        return [{
            "task_id": r["task_id"],
            "state": r["state"],
            "phase": r["phase"],
            "worker_id": r["worker_id"],
            "retry_count": r["retry_count"],
            "token_used": r["token_used"],
            "updated_at": r["updated_at"],
            "error_msg": r["error_msg"],
        } for r in rows]
    except Exception as e:
        print(f"[Checkpoint] list failed: {e}")
        return []


def delete_checkpoint(task_id: str) -> bool:
    """删除检查点"""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM checkpoints WHERE task_id = ?", (task_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Checkpoint] delete failed: {e}")
        return False


def cleanup_stale(max_age_hours: int = 24) -> int:
    """
    清理过期检查点

    Args:
        max_age_hours: 最大保留小时数

    Returns:
        删除的记录数
    """
    try:
        cutoff = time.time() - max_age_hours * 3600
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM checkpoints WHERE updated_at < ? AND state IN ('completed', 'failed')",
            (cutoff,)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
    except Exception as e:
        print(f"[Checkpoint] cleanup failed: {e}")
        return 0


def resume_task(task_id: str) -> Optional[Dict[str, Any]]:
    """
    恢复任务（供 Orchestrator 使用）

    从检查点重建任务状态，返回恢复所需的所有信息。
    只恢复未完成的任务（retry/running/planning/claimed）。

    Args:
        task_id: 任务ID

    Returns:
        恢复上下文，或 None（不可恢复）
    """
    cp = load_checkpoint(task_id)
    if cp is None:
        return None

    # 只恢复未完成的任务
    resumable_states = {"retry", "running", "planning", "claimed"}
    if cp["state"] not in resumable_states:
        return None

    return {
        "task_id": cp["task_id"],
        "resume_state": cp["state"],
        "resume_phase": cp["phase"],
        "worker_id": cp["worker_id"],
        "retry_count": cp["retry_count"],
        "token_used": cp["token_used"],
        "token_budget": cp["token_budget"],
        "context": cp["context"],
        "trace": cp["trace"],
    }


# ========== 单元测试 ==========

def _test():
    print("\n=== Checkpoint 单元测试 ===\n")

    # Test 1: 保存和加载
    print("Test 1: 保存和加载")
    ok = save_checkpoint(
        task_id="test-cp-001",
        state="running",
        phase="gather",
        worker_id="coder-001",
        retry_count=1,
        token_used=1500,
        token_budget=6000,
        context={"user_input": "分析代码"},
        trace=[{"from": "pending", "to": "claimed", "ts": 1000}],
    )
    assert ok
    cp = load_checkpoint("test-cp-001")
    assert cp is not None
    assert cp["state"] == "running"
    assert cp["phase"] == "gather"
    assert cp["token_used"] == 1500
    assert cp["context"]["user_input"] == "分析代码"
    print("  ✅ PASS\n")

    # Test 2: 不存在的检查点
    print("Test 2: 不存在的检查点")
    cp2 = load_checkpoint("nonexistent")
    assert cp2 is None
    print("  ✅ PASS\n")

    # Test 3: 列出检查点
    print("Test 3: 列出检查点")
    save_checkpoint(task_id="test-cp-002", state="completed", token_used=5000)
    save_checkpoint(task_id="test-cp-003", state="failed", error_msg="timeout")
    items = list_checkpoints()
    assert len(items) >= 3
    print(f"  找到 {len(items)} 个检查点")
    print("  ✅ PASS\n")

    # Test 4: 按状态过滤
    print("Test 4: 按状态过滤")
    running = list_checkpoints(state="running")
    assert all(i["state"] == "running" for i in running)
    print(f"  running 状态: {len(running)} 个")
    print("  ✅ PASS\n")

    # Test 5: 恢复任务
    print("Test 5: 恢复任务")
    resume = resume_task("test-cp-001")
    assert resume is not None
    assert resume["resume_state"] == "running"
    assert resume["resume_phase"] == "gather"
    assert resume["token_used"] == 1500
    print(f"  恢复上下文: state={resume['resume_state']}, phase={resume['resume_phase']}")
    print("  ✅ PASS\n")

    # Test 6: 已完成任务不可恢复
    print("Test 6: 已完成任务不可恢复")
    resume2 = resume_task("test-cp-002")
    assert resume2 is None
    print("  ✅ PASS\n")

    # Test 7: 删除检查点
    print("Test 7: 删除检查点")
    ok = delete_checkpoint("test-cp-001")
    assert ok
    cp3 = load_checkpoint("test-cp-001")
    assert cp3 is None
    print("  ✅ PASS\n")

    # Test 8: 清理过期
    print("Test 8: 清理过期检查点")
    deleted = cleanup_stale(max_age_hours=0)  # 0小时 = 全部清理
    print(f"  清理了 {deleted} 个过期检查点")
    print("  ✅ PASS\n")

    # 清理测试数据
    delete_checkpoint("test-cp-002")
    delete_checkpoint("test-cp-003")

    print("=== 所有测试通过 ===\n")


if __name__ == "__main__":
    _test()
