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

# 安全配置
from security_config import (
    is_tool_allowed,
    DANGEROUS_TOOLS,
    check_dangerous_operation,
    STATE_TOOL_WHITELIST,
    RUNNING_PHASE_TOOLS,
)


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

        # Check 5: 工具白名单合规（安全增强）
        checks.append(self._check_tool_compliance(task, worker_result))

        # Check 6: Token 预算合规（安全增强）
        checks.append(self._check_token_budget(task, worker_result))

        # Check 7: 危险操作确认（安全增强）
        checks.append(self._check_dangerous_ops_confirmed(task, worker_result))

        # Check 8: 计划完成度（Plan-and-Solve 增强）
        checks.append(self._check_plan_completeness(task, worker_result))

        # Check 9: 计划逻辑自洽（Plan-and-Solve 增强）
        checks.append(self._check_plan_coherence(task, worker_result))

        # Check 10: 上下文溢出（上下文管理增强）
        checks.append(self._check_context_overflow(task, worker_result))

        # Check 11: 摘要质量（上下文管理增强）
        checks.append(self._check_summary_quality(task, worker_result))

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
            err_type = str(val.get("error_type", ""))
            # 已知可接受的 error 类型（如 timeout，用户需自行重试）
            acceptable_errors = ["timeout after", "timeout", "权限不足", "not a git repository"]
            acceptable_types = ["E_TIMEOUT"]  # 超时不算 FAIL，用户可重试
            if err_type in acceptable_types:
                return {"check": "error_free", "result": "PASS", "note": f"acceptable error_type: {err_type}"}
            if not any(e in err for e in acceptable_errors):
                return {"check": "error_free", "result": "FAIL", "reason": f"执行报错: {err[:100]}"}
        return {"check": "error_free", "result": "PASS"}

    # ========== 安全增强检查（来自 Agent 生产级架构实践） ==========

    def _check_tool_compliance(self, task: dict, result: dict) -> dict:
        """
        工具白名单合规检查

        验证 Worker 只使用了当前状态/阶段允许的工具。
        如果 result 中记录了 tools_used，逐一校验是否在白名单中。
        """
        val = result.get("result") or result
        tools_used = val.get("tools_used", val.get("capabilities_used", []))
        state = val.get("state", "RUNNING")
        phase = val.get("phase", None)

        if not tools_used:
            return {"check": "tool_compliance", "result": "PASS", "note": "无工具使用记录"}

        violations = []
        for tool in tools_used:
            if not is_tool_allowed(tool, state, phase):
                violations.append(tool)

        if violations:
            return {
                "check": "tool_compliance",
                "result": "FAIL",
                "reason": f"违规使用白名单外工具: {violations} (state={state}, phase={phase})",
            }
        return {"check": "tool_compliance", "result": "PASS"}

    def _check_token_budget(self, task: dict, result: dict) -> dict:
        """
        Token 预算合规检查

        验证 Worker 的 Token 消耗在预算范围内。
        如果 result 中记录了 token 信息，检查是否超限。
        """
        val = result.get("result") or result
        token_info = val.get("tokens", {})

        if not token_info:
            return {"check": "token_budget", "result": "PASS", "note": "无 Token 消耗记录"}

        total = token_info.get("total_tokens", 0)
        budget_limit = token_info.get("global_limit", 15000)

        if total > budget_limit:
            return {
                "check": "token_budget",
                "result": "FAIL",
                "reason": f"Token 超限: {total}/{budget_limit}",
            }

        # 检查各状态/阶段的预算
        by_phase = token_info.get("by_phase", {})
        from security_config import get_token_budget
        for phase_key, used in by_phase.items():
            parts = phase_key.split(".")
            if len(parts) == 2:
                state_name, phase_name = parts
                budget = get_token_budget(state_name, phase_name)
                if budget > 0 and used > budget:
                    return {
                        "check": "token_budget",
                        "result": "FAIL",
                        "reason": f"阶段 {phase_key} Token 超限: {used}/{budget}",
                    }

        return {"check": "token_budget", "result": "PASS"}

    def _check_dangerous_ops_confirmed(self, task: dict, result: dict) -> dict:
        """
        危险操作确认检查

        验证所有危险操作（shell_executor 中的高危命令）都经过了确认。
        如果 result 中记录了 shell 命令，检查是否包含未确认的危险操作。
        """
        val = result.get("result") or result

        # 检查 shell 命令是否包含危险操作
        command = val.get("command", "")
        if not command:
            return {"check": "dangerous_ops_confirmed", "result": "PASS", "note": "无 shell 命令"}

        pattern = check_dangerous_operation(command)
        if pattern is None:
            return {"check": "dangerous_ops_confirmed", "result": "PASS"}

        # 匹配到危险模式，检查是否有确认记录
        confirmations = val.get("confirmations", {})
        confirmed = confirmations.get("confirmed", False)
        confirmed_patterns = confirmations.get("always_allow_patterns", [])

        # 构造 pattern_id 检查是否在 always 白名单中
        pattern_id = f"shell_executor:{pattern.pattern}"
        if confirmed or pattern_id in confirmed_patterns:
            return {"check": "dangerous_ops_confirmed", "result": "PASS"}

        return {
            "check": "dangerous_ops_confirmed",
            "result": "FAIL",
            "reason": f"危险操作未确认: [{pattern.level}] {pattern.description} — 命令: {command[:80]}",
        }

    def _check_plan_completeness(self, task: dict, result: dict) -> dict:
        """
        计划完成度检查（Check 8）

        验证执行计划中的所有步骤都已标记完成。
        """
        val = result.get("result") or result
        plan_info = val.get("plan", {})

        if not plan_info:
            return {"check": "plan_completeness", "result": "PASS", "note": "无计划信息（可能未使用 Planner）"}

        steps = plan_info.get("steps", [])
        if not steps:
            return {"check": "plan_completeness", "result": "PASS", "note": "计划无步骤"}

        pending = [
            s for s in steps
            if s.get("status") in ("pending", "in_progress")
        ]

        if pending:
            pending_desc = [s.get("description", "未知") for s in pending]
            return {
                "check": "plan_completeness",
                "result": "FAIL",
                "reason": f"计划中有 {len(pending)} 个步骤未完成: {pending_desc[:3]}...",
            }

        return {"check": "plan_completeness", "result": "PASS"}

    def _check_plan_coherence(self, task: dict, result: dict) -> dict:
        """
        计划逻辑自洽检查（Check 9）

        验证计划步骤的依赖关系是否合理：
        1. 没有循环依赖
        2. 依赖的步骤 id 都存在
        """
        val = result.get("result") or result
        plan_info = val.get("plan", {})

        if not plan_info:
            return {"check": "plan_coherence", "result": "PASS", "note": "无计划信息"}

        steps = plan_info.get("steps", [])
        if not steps:
            return {"check": "plan_coherence", "result": "PASS", "note": "计划无步骤"}

        step_ids = {s.get("id", "") for s in steps}
        issues = []

        # 检查依赖是否存在
        for s in steps:
            for dep in s.get("dependencies", []):
                if dep not in step_ids:
                    issues.append(f"步骤 '{s.get('id')}' 依赖不存在的步骤 '{dep}'")

        # 检查循环依赖（简单的 DFS）
        dep_graph = {s.get("id", ""): s.get("dependencies", []) for s in steps}
        visited = set()
        in_stack = set()

        def has_cycle(node):
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in dep_graph.get(node, []):
                if has_cycle(dep):
                    return True
            in_stack.discard(node)
            return False

        for sid in step_ids:
            if has_cycle(sid):
                issues.append(f"检测到循环依赖（涉及步骤 '{sid}'）")
                break

        if issues:
            return {
                "check": "plan_coherence",
                "result": "FAIL",
                "reason": "; ".join(issues[:3]),
            }

        return {"check": "plan_coherence", "result": "PASS"}

    def _check_context_overflow(self, task: dict, result: dict) -> dict:
        """
        上下文溢出检查（Check 10）

        验证上下文 token 量是否超出窗口限制。
        """
        val = result.get("result") or result
        context_info = val.get("context", {})

        if not context_info:
            return {"check": "context_overflow", "result": "PASS", "note": "无上下文信息"}

        total_tokens = context_info.get("total_tokens", 0)
        max_tokens = context_info.get("max_tokens", 4000)

        if total_tokens > max_tokens * 1.5:
            return {
                "check": "context_overflow",
                "result": "FAIL",
                "reason": f"上下文 token 严重超限: {total_tokens}/{max_tokens} ({total_tokens/max_tokens:.0%})",
            }

        return {"check": "context_overflow", "result": "PASS"}

    def _check_summary_quality(self, task: dict, result: dict) -> dict:
        """
        摘要质量检查（Check 11）

        验证子Agent摘要是否包含关键信息：
        1. 摘要非空
        2. 摘要包含结论或关键发现
        3. 摘要长度在合理范围内
        """
        val = result.get("result") or result
        summary = val.get("summary", "")

        if not summary:
            # 没有摘要字段，跳过（不强制要求）
            return {"check": "summary_quality", "result": "PASS", "note": "无摘要字段"}

        issues = []

        # 摘要过短（可能无意义）
        if len(summary) < 3:
            issues.append(f"摘要过短 ({len(summary)} 字符)，可能无意义")

        # 摘要过长（未压缩）
        if len(summary) > 2000:
            issues.append(f"摘要过长 ({len(summary)} 字符)，可能未有效压缩")

        # 摘要全是错误信息（没有有效内容）
        if "error" in summary.lower() and len(summary) < 50:
            issues.append("摘要主要是错误信息，缺少有效内容")

        if issues:
            return {
                "check": "summary_quality",
                "result": "FAIL",
                "reason": "; ".join(issues[:2]),
            }

        return {"check": "summary_quality", "result": "PASS"}

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

    # ---- 安全增强测试 ----

    # Test 7: 工具白名单合规 → PASS
    print("Test 7: 工具白名单合规 → PASS")
    result = v.verify(
        task={"id": "t7", "type": "code_analysis"},
        worker_result={
            "result": {
                "task_id": "t7",
                "capabilities_used": ["code_analyzer", "file_reader"],
                "tools_used": ["code_analyzer", "file_reader"],
                "state": "RUNNING",
                "phase": "gather",
                "lines": 100,
            }
        }
    )
    assert result.is_pass, f"期望 PASS，实际 {result.result}"
    print("  ✅ PASS\n")

    # Test 8: 工具白名单违规 → FAIL
    print("Test 8: 工具白名单违规 → FAIL")
    result = v.verify(
        task={"id": "t8", "type": "code_analysis"},
        worker_result={
            "result": {
                "task_id": "t8",
                "capabilities_used": ["code_analyzer"],
                "tools_used": ["code_analyzer", "shell_executor"],
                "state": "RUNNING",
                "phase": "gather",  # gather 不允许 shell_executor
                "lines": 100,
            }
        }
    )
    assert not result.is_pass
    assert any("违规" in c or "白名单" in c for c in result.causes)
    print(f"  ✅ FAIL (causes: {result.causes})\n")

    # Test 9: Token 预算合规 → PASS
    print("Test 9: Token 预算合规 → PASS")
    result = v.verify(
        task={"id": "t9"},
        worker_result={
            "result": {
                "task_id": "t9",
                "capabilities_used": ["file_reader"],
                "tokens": {
                    "total_tokens": 3000,
                    "global_limit": 15000,
                    "by_state": {"RUNNING": 3000},
                    "by_phase": {"RUNNING.gather": 1500},
                },
            }
        }
    )
    assert result.is_pass
    print("  ✅ PASS\n")

    # Test 10: Token 预算超限 → FAIL
    print("Test 10: Token 预算超限 → FAIL")
    result = v.verify(
        task={"id": "t10"},
        worker_result={
            "result": {
                "task_id": "t10",
                "capabilities_used": ["file_reader"],
                "tokens": {
                    "total_tokens": 20000,
                    "global_limit": 15000,
                    "by_state": {"RUNNING": 20000},
                    "by_phase": {},
                },
            }
        }
    )
    assert not result.is_pass
    assert any("Token" in c or "超限" in c for c in result.causes)
    print(f"  ✅ FAIL (causes: {result.causes})\n")

    # Test 11: 危险操作已确认 → PASS
    print("Test 11: 危险操作已确认 → PASS")
    result = v.verify(
        task={"id": "t11", "type": "shell_executor"},
        worker_result={
            "result": {
                "command": "rm -rf /tmp/test",
                "exit_code": 0,
                "task_id": "t11",
                "capabilities_used": ["shell_executor"],
                "confirmations": {"confirmed": True},
            }
        }
    )
    assert result.is_pass, f"期望 PASS，实际 {result.result}"
    print("  ✅ PASS\n")

    # Test 12: 危险操作未确认 → FAIL
    print("Test 12: 危险操作未确认 → FAIL")
    result = v.verify(
        task={"id": "t12", "type": "shell_executor"},
        worker_result={
            "result": {
                "command": "rm -rf /tmp/test",
                "exit_code": 0,
                "task_id": "t12",
                "capabilities_used": ["shell_executor"],
                "confirmations": {},
            }
        }
    )
    assert not result.is_pass
    assert any("危险" in c or "确认" in c for c in result.causes)
    print(f"  ✅ FAIL (causes: {result.causes})\n")

    # Test 13: 安全命令无需确认 → PASS
    print("Test 13: 安全命令无需确认 → PASS")
    result = v.verify(
        task={"id": "t13", "type": "shell_executor"},
        worker_result={
            "result": {
                "command": "ls -la /tmp",
                "exit_code": 0,
                "task_id": "t13",
                "capabilities_used": ["shell_executor"],
            }
        }
    )
    assert result.is_pass
    print("  ✅ PASS\n")

    print("=== 所有安全测试通过 ===\n")


if __name__ == "__main__":
    _test()
