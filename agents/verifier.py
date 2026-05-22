#!/usr/bin/env python3
"""
agents/verifier.py - 独立质检员

核心设计原则：
1. 不读 Worker 上下文，完全独立世界观
2. 验收标准是清单，不是模型主观判断
3. 决策只有三种：PASS / FAIL(reasons) / RETRY(cause)
4. VERIFIER ≠ 执行者，不能是同一个认知主体
"""
import os
import sys
import hashlib
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

# 路径
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)


@dataclass
class Verdict:
    """验收决策"""
    result: str            # "PASS" / "FAIL" / "RETRY"
    checks: List[Dict]     # 每项检查的详细结果
    causes: List[str]      # 失败原因（供 trace 记录）
    task_id: str = ""
    verifier_version: str = "1.0"

    @property
    def is_pass(self) -> bool:
        return self.result == "PASS"

    def to_dict(self) -> dict:
        return {
            "verdict": self.result,
            "task_id": self.task_id,
            "verifier_version": self.verifier_version,
            "checks": self.checks,
            "causes": self.causes,
        }


class Verifier:
    """
    独立质检员

    使用方式：
    v = Verifier()
    result = v.verify(task={"id": "task-1", "type": "code_analysis"}, worker_result={...})
    if not result.is_pass:
        print(f"打回原因: {result.causes}")
    """

    def __init__(self, model: str = "ernie-lite"):
        self.model = model

    def verify(self, task: dict, worker_result: dict) -> Verdict:
        """
        验收 Worker 产出

        标准清单（按 task type 分叉）：
        1. deliverable_exists - 交付物存在
        2. functional_correctness - 功能正确性（按 type）
        3. trace_integrity - trace 字段完整
        4. error_free - 无异常错误标记
        """
        task_type = task.get("type", task.get("capabilities_needed", ["unknown"])[0] if task.get("capabilities_needed") else "unknown")
        task_id = task.get("id", "unknown")

        checks = []

        # Check 1: 交付物存在
        checks.append(self._check_deliverable_exists(task, worker_result))

        # Check 2: 功能正确性
        checks.append(self._check_functional_correctness(task, worker_result))

        # Check 3: trace 完整性
        checks.append(self._check_trace_integrity(task, worker_result))

        # Check 4: 无错误标记
        checks.append(self._check_error_free(worker_result))

        # 任何一项 FAIL，即打回
        failed = [c for c in checks if c["result"] == "FAIL"]
        causes = [c.get("reason", "unknown") for c in failed]

        if failed:
            verdict = Verdict(
                result="FAIL",
                checks=checks,
                causes=causes,
                task_id=task_id,
            )
        else:
            verdict = Verdict(
                result="PASS",
                checks=checks,
                causes=[],
                task_id=task_id,
            )

        print(f"[Verifier] task={task_id} verdict={verdict.result}" +
              (f" causes={causes}" if causes else ""))
        return verdict

    # ========== 四项标准检查 ==========

    def _check_deliverable_exists(self, task: dict, result: dict) -> dict:
        """交付物非空"""
        val = result.get("result") or result.get("data") or result
        if val is None or val == {} or val == [] or val == "":
            return {"check": "deliverable_exists", "result": "FAIL", "reason": "交付物为空"}
        # 检查 result 里是否有实质内容（至少有一个非 meta 字段）
        content_keys = [k for k in val.keys() if k not in ("task_id", "role", "capabilities_used", "agent_id", "status")]
        if not content_keys:
            return {"check": "deliverable_exists", "result": "FAIL", "reason": "交付物无实质内容字段"}
        return {"check": "deliverable_exists", "result": "PASS"}

    def _check_functional_correctness(self, task: dict, result: dict) -> dict:
        """功能正确性（按 task type）"""
        task_type = self._infer_task_type(task)
        val = result.get("result") or result

        handlers = {
            "code_analysis":    self._verify_code_analysis,
            "file_reader":      self._verify_file_reader,
            "dir_scanner":      self._verify_dir_scanner,
            "shell_executor":   self._verify_shell_executor,
            "ast_parser":       self._verify_ast_parser,
            "web_search":       self._verify_web_search,
            "web_fetcher":      self._verify_web_fetcher,
            "syntax_checker":  self._verify_syntax_checker,
        }

        handler = handlers.get(task_type)
        if handler:
            return handler(val, task)
        # 未知 type 默认 PASS（有 deliverable 就 OK）
        return {"check": "functional_correctness", "result": "PASS", "note": f"type={task_type} 无专项检查"}

    def _verify_code_analysis(self, val: dict, task: dict) -> dict:
        """代码分析验收：必须包含预期字段"""
        required = ["lines"]
        missing = [f for f in required if f not in val or not val[f]]
        if missing:
            return {"check": "code_analysis_fields", "result": "FAIL", "reason": f"缺少字段: {missing}"}
        # lines 应该是个正整数
        try:
            if int(val.get("lines", 0)) <= 0:
                return {"check": "code_analysis_lines", "result": "FAIL", "reason": "lines 必须 > 0"}
        except (TypeError, ValueError):
            return {"check": "code_analysis_lines", "result": "FAIL", "reason": "lines 格式错误"}
        return {"check": "code_analysis_fields", "result": "PASS"}

    def _verify_file_reader(self, val: dict, task: dict) -> dict:
        """文件读取验收"""
        required = ["path", "size"]
        missing = [f for f in required if f not in val]
        if missing:
            return {"check": "file_reader_fields", "result": "FAIL", "reason": f"缺少字段: {missing}"}
        if val.get("truncated") and not val.get("content_preview"):
            return {"check": "file_reader_content", "result": "FAIL", "reason": "标记 truncated 但无 content_preview"}
        return {"check": "file_reader_fields", "result": "PASS"}

    def _verify_dir_scanner(self, val: dict, task: dict) -> dict:
        """目录扫描验收"""
        if "entries" not in val and "count" not in val:
            return {"check": "dir_scanner_fields", "result": "FAIL", "reason": "缺少 entries 或 count 字段"}
        return {"check": "dir_scanner_fields", "result": "PASS"}

    def _verify_shell_executor(self, val: dict, task: dict) -> dict:
        """Shell 执行验收"""
        required = ["command", "exit_code"]
        missing = [f for f in required if f not in val]
        if missing:
            return {"check": "shell_executor_fields", "result": "FAIL", "reason": f"缺少字段: {missing}"}
        return {"check": "shell_executor_fields", "result": "PASS"}

    def _verify_ast_parser(self, val: dict, task: dict) -> dict:
        """AST 解析验收"""
        if "ast_nodes" not in val:
            return {"check": "ast_parser_fields", "result": "FAIL", "reason": "缺少 ast_nodes 字段"}
        return {"check": "ast_parser_fields", "result": "PASS"}

    def _verify_web_search(self, val: dict, task: dict) -> dict:
        """网页搜索验收"""
        if val.get("note", "").startswith("需要配置"):
            return {"check": "web_search_impl", "result": "FAIL", "reason": "web_search 尚未实现"}
        if "results" not in val and "query" not in val:
            return {"check": "web_search_fields", "result": "FAIL", "reason": "缺少 results 或 query 字段"}
        return {"check": "web_search_fields", "result": "PASS"}

    def _verify_web_fetcher(self, val: dict, task: dict) -> dict:
        """网页获取验收"""
        if "url" not in val:
            return {"check": "web_fetcher_fields", "result": "FAIL", "reason": "缺少 url 字段"}
        return {"check": "web_fetcher_fields", "result": "PASS"}

    def _verify_syntax_checker(self, val: dict, task: dict) -> dict:
        """语法检查验收"""
        required = ["path", "ok"]
        missing = [f for f in required if f not in val]
        if missing:
            return {"check": "syntax_checker_fields", "result": "FAIL", "reason": f"缺少字段: {missing}"}
        return {"check": "syntax_checker_fields", "result": "PASS"}

    def _check_trace_integrity(self, task: dict, result: dict) -> dict:
        """trace 记录完整性"""
        val = result.get("result") or result
        required = ["task_id", "capabilities_used"]
        missing = [f for f in required if f not in val]
        if missing:
            return {"check": "trace_integrity", "result": "FAIL", "reason": f"缺少 trace 字段: {missing}"}
        return {"check": "trace_integrity", "result": "PASS"}

    def _check_error_free(self, result: dict) -> dict:
        """无异常错误标记"""
        val = result.get("result") or result
        # 如果 result 里有 error 字段，说明执行过程出错了
        if "error" in val and val["error"]:
            err = str(val["error"])
            # 已知可接受的 error 类型（如 timeout，用户需自行重试）
            acceptable_errors = ["timeout after", "权限不足", "not a git repository"]
            if not any(e in err for e in acceptable_errors):
                return {"check": "error_free", "result": "FAIL", "reason": f"执行报错: {err[:100]}"}
        return {"check": "error_free", "result": "PASS"}

    def _infer_task_type(self, task: dict) -> str:
        """从 task 推断 type"""
        if task.get("type"):
            return task["type"]
        caps = task.get("capabilities_needed", [])
        return caps[0] if caps else "unknown"


# ========== 单元测试 ==========

def _test():
    """Verifier 基本测试"""
    print("\n=== Verifier 单元测试 ===\n")
    v = Verifier()

    # Test 1: 正常的 code_analysis 结果 → PASS
    print("Test 1: 正常 code_analysis → PASS")
    result = v.verify(
        task={"id": "t1", "type": "code_analysis"},
        worker_result={
            "result": {
                "task_id": "t1",
                "capabilities_used": ["code_analyzer"],
                "lines": 234,
                "functions": ["run", "stop"],
                "classes": ["Agent"],
            }
        }
    )
    assert result.is_pass, f"期望 PASS，实际 {result.result}"
    print("  ✅ PASS\n")

    # Test 2: 空交付物 → FAIL
    print("Test 2: 空交付物 → FAIL")
    result = v.verify(
        task={"id": "t2"},
        worker_result={"result": {}}
    )
    assert not result.is_pass
    print(f"  ✅ FAIL (causes: {result.causes})\n")

    # Test 3: code_analysis 缺少 lines 字段 → FAIL
    print("Test 3: code_analysis 缺少 lines → FAIL")
    result = v.verify(
        task={"id": "t3", "type": "code_analysis"},
        worker_result={
            "result": {
                "task_id": "t3",
                "capabilities_used": ["code_analyzer"],
                "functions": ["run"],
                "classes": [],
            }
        }
    )
    assert not result.is_pass
    print(f"  ✅ FAIL (causes: {result.causes})\n")

    # Test 4: web_search 未实现 → FAIL
    print("Test 4: web_search stub → FAIL")
    result = v.verify(
        task={"id": "t4", "type": "web_search"},
        worker_result={"result": {"query": "test", "note": "需要配置 web search API"}}
    )
    assert not result.is_pass
    print(f"  ✅ FAIL (causes: {result.causes})\n")

    # Test 5: 执行报错 → FAIL
    print("Test 5: 执行报错 → FAIL")
    result = v.verify(
        task={"id": "t5"},
        worker_result={"result": {"error": "文件不存在", "task_id": "t5", "capabilities_used": []}}
    )
    assert not result.is_pass
    print(f"  ✅ FAIL (causes: {result.causes})\n")

    # Test 6: shell_executor 正常 → PASS
    print("Test 6: shell_executor 正常 → PASS")
    result = v.verify(
        task={"id": "t6", "type": "shell_executor"},
        worker_result={
            "result": {
                "command": "ls /tmp",
                "exit_code": 0,
                "stdout": "a.txt\nb.txt",
                "task_id": "t6",
                "capabilities_used": ["shell_executor"],
            }
        }
    )
    assert result.is_pass, f"期望 PASS，实际 {result.result}"
    print("  ✅ PASS\n")

    print("=== 所有测试通过 ===\n")


if __name__ == "__main__":
    _test()
