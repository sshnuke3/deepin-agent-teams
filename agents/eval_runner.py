"""
eval_runner.py — 离线评测框架

核心思路（来自 Agent 生产级架构与质量保障实践）：
- AIMock：确定性 Fixture，CI 零 API 消耗
- 评测管道：定义输入 → 执行 Agent → 对比期望输出 → 生成报告
- 集成到 CI：每次提交自动跑评测

参考：promptfoo 架构，但不依赖外部工具，纯 Python 实现。
"""

import json
import os
import sys
import time
import hashlib
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from pathlib import Path

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
FIXTURES_DIR = os.path.join(PROJECT_ROOT, "tests", "fixtures")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "tests", "reports")


# ============================================================
# AIMock — 确定性 Fixture（CI 零 API 消耗）
# ============================================================

@dataclass
class AIMockResponse:
    """AIMock 返回的确定性响应"""
    content: str
    tool_calls: List[Dict] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0, "total": 0})


class AIMock:
    """
    确定性 Mock — 替代真实 LLM 调用

    工作原理：
    1. 预录制一组 fixture（prompt → response 的映射）
    2. 测试时用 fixture 替代真实 API 调用
    3. 确定性输入 → 确定性输出，无需网络，零成本

    使用方式：
        mock = AIMock.load("task_001")
        response = mock.chat("分析代码结构")
        # 返回预录制的确定性响应
    """

    def __init__(self, fixtures: Dict[str, AIMockResponse] = None):
        self._fixtures = fixtures or {}
        self._call_log: List[Dict] = []

    @classmethod
    def load(cls, fixture_name: str) -> "AIMock":
        """从 fixture 文件加载"""
        fixture_path = os.path.join(FIXTURES_DIR, f"{fixture_name}.json")
        if not os.path.exists(fixture_path):
            return cls()

        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        fixtures = {}
        for key, val in data.get("responses", {}).items():
            fixtures[key] = AIMockResponse(
                content=val.get("content", ""),
                tool_calls=val.get("tool_calls", []),
                token_usage=val.get("token_usage", {"input": 0, "output": 0, "total": 0}),
            )
        return cls(fixtures)

    def chat(self, prompt: str, **kwargs) -> AIMockResponse:
        """匹配 prompt 返回确定性响应"""
        # 精确匹配
        if prompt in self._fixtures:
            resp = self._fixtures[prompt]
            self._call_log.append({"prompt_hash": hashlib.md5(prompt.encode()).hexdigest()[:8], "match": "exact"})
            return resp

        # 模糊匹配（包含关键词）
        for key, resp in self._fixtures.items():
            if key in prompt or prompt in key:
                self._call_log.append({"prompt_hash": hashlib.md5(prompt.encode()).hexdigest()[:8], "match": "fuzzy"})
                return resp

        # 默认响应
        self._call_log.append({"prompt_hash": hashlib.md5(prompt.encode()).hexdigest()[:8], "match": "default"})
        return AIMockResponse(content="[AIMock] 无匹配 fixture", token_usage={"input": 0, "output": 0, "total": 0})

    @property
    def call_count(self) -> int:
        return len(self._call_log)

    def save_fixture(self, name: str, responses: Dict[str, Dict]):
        """保存 fixture 到文件"""
        os.makedirs(FIXTURES_DIR, exist_ok=True)
        fixture_path = os.path.join(FIXTURES_DIR, f"{name}.json")
        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump({"name": name, "responses": responses}, f, ensure_ascii=False, indent=2)


# ============================================================
# 评测用例
# ============================================================

@dataclass
class EvalCase:
    """单个评测用例"""
    id: str
    description: str
    input_task: Dict[str, Any]
    expected: Dict[str, Any]
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "input_task": self.input_task,
            "expected": self.expected,
            "tags": self.tags,
        }


@dataclass
class EvalResult:
    """单个用例的评测结果"""
    case_id: str
    passed: bool
    actual: Dict[str, Any]
    expected: Dict[str, Any]
    details: List[str] = field(default_factory=list)
    duration_ms: float = 0
    token_usage: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "token_usage": self.token_usage,
        }


# ============================================================
# 评测断言器
# ============================================================

class EvalAssert:
    """评测断言工具集"""

    @staticmethod
    def assert_state(actual_state: str, expected_state: str) -> Optional[str]:
        if actual_state != expected_state:
            return f"状态不匹配: 期望={expected_state}, 实际={actual_state}"
        return None

    @staticmethod
    def assert_has_capability(result: dict, capability: str) -> Optional[str]:
        caps = result.get("capabilities_used", [])
        if capability not in caps:
            return f"缺少能力: {capability}, 实际使用: {caps}"
        return None

    @staticmethod
    def assert_no_error(result: dict) -> Optional[str]:
        if "error" in result and result["error"]:
            return f"执行出错: {result['error']}"
        return None

    @staticmethod
    def assert_verdict(result: dict, expected_verdict: str) -> Optional[str]:
        actual = result.get("verdict", result.get("verification", {}).get("verdict", ""))
        if actual != expected_verdict:
            return f"判定不匹配: 期望={expected_verdict}, 实际={actual}"
        return None

    @staticmethod
    def assert_token_budget(result: dict, max_tokens: int) -> Optional[str]:
        total = result.get("tokens", {}).get("total_tokens", 0)
        if total > max_tokens:
            return f"Token 超限: {total}/{max_tokens}"
        return None

    @staticmethod
    def assert_tool_compliance(result: dict, allowed_tools: List[str]) -> Optional[str]:
        tools = result.get("tools_used", result.get("capabilities_used", []))
        violations = [t for t in tools if t not in allowed_tools]
        if violations:
            return f"违规工具: {violations}, 允许: {allowed_tools}"
        return None

    @staticmethod
    def assert_contains(text: str, substring: str) -> Optional[str]:
        if substring not in text:
            return f"文本中未找到: '{substring}'"
        return None


# ============================================================
# 评测运行器
# ============================================================

class EvalRunner:
    """
    评测运行器

    工作流：
    1. 加载评测用例（从文件或代码定义）
    2. 逐个执行用例（可选 AIMock 替代真实 LLM）
    3. 对比期望输出，生成评测报告
    4. 输出到 reports/ 目录
    """

    def __init__(self, name: str, agent_fn: Callable = None, use_mock: bool = True):
        self.name = name
        self.agent_fn = agent_fn  # Agent 执行函数
        self.use_mock = use_mock
        self.cases: List[EvalCase] = []
        self.results: List[EvalResult] = []
        self.assertions: List[Callable] = []

    def add_case(self, case: EvalCase):
        """添加评测用例"""
        self.cases.append(case)
        return self

    def add_assertion(self, fn: Callable):
        """添加自定义断言"""
        self.assertions.append(fn)
        return self

    def run(self) -> Dict[str, Any]:
        """运行所有评测用例"""
        print(f"\n{'='*50}")
        print(f"  评测: {self.name}")
        print(f"  用例数: {len(self.cases)}")
        print(f"  Mock 模式: {self.use_mock}")
        print(f"{'='*50}\n")

        self.results = []
        passed = 0
        failed = 0
        total_tokens = 0
        total_duration = 0

        for i, case in enumerate(self.cases, 1):
            print(f"  [{i}/{len(self.cases)}] {case.id}: {case.description}")

            start_time = time.time()

            if self.agent_fn:
                try:
                    actual = self.agent_fn(case.input_task)
                except Exception as e:
                    actual = {"error": str(e), "error_type": type(e).__name__}
            else:
                actual = {"note": "no agent_fn provided"}

            duration_ms = (time.time() - start_time) * 1000

            # 运行断言
            details = []
            all_pass = True

            for key, expected_val in case.expected.items():
                if key == "state":
                    err = EvalAssert.assert_state(actual.get("state", ""), expected_val)
                elif key == "verdict":
                    err = EvalAssert.assert_verdict(actual, expected_val)
                elif key == "no_error":
                    err = EvalAssert.assert_no_error(actual) if expected_val else None
                elif key == "max_tokens":
                    err = EvalAssert.assert_token_budget(actual, expected_val)
                elif key == "allowed_tools":
                    err = EvalAssert.assert_tool_compliance(actual, expected_val)
                elif key == "contains":
                    err = EvalAssert.assert_contains(str(actual), expected_val)
                else:
                    # 通用比较
                    if actual.get(key) != expected_val:
                        err = f"{key}: 期望={expected_val}, 实际={actual.get(key)}"
                    else:
                        err = None

                if err:
                    details.append(err)
                    all_pass = False

            # 自定义断言
            for assertion_fn in self.assertions:
                err = assertion_fn(case, actual)
                if err:
                    details.append(err)
                    all_pass = False

            token_usage = actual.get("tokens", {})
            result = EvalResult(
                case_id=case.id,
                passed=all_pass,
                actual=actual,
                expected=case.expected,
                details=details,
                duration_ms=duration_ms,
                token_usage=token_usage,
            )
            self.results.append(result)

            if all_pass:
                passed += 1
                print(f"      ✅ PASS")
            else:
                failed += 1
                print(f"      ❌ FAIL: {'; '.join(details)}")

            total_tokens += token_usage.get("total_tokens", 0)
            total_duration += duration_ms

        # 汇总
        summary = {
            "name": self.name,
            "total": len(self.cases),
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{passed / len(self.cases) * 100:.1f}%" if self.cases else "N/A",
            "total_tokens": total_tokens,
            "total_duration_ms": round(total_duration, 1),
            "mock_mode": self.use_mock,
        }

        print(f"\n{'='*50}")
        print(f"  结果: {passed}/{len(self.cases)} PASS ({summary['pass_rate']})")
        print(f"  Token: {total_tokens} | 耗时: {total_duration:.0f}ms")
        print(f"{'='*50}\n")

        return summary

    def save_report(self, summary: Dict):
        """保存评测报告"""
        os.makedirs(REPORTS_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report = {
            "summary": summary,
            "cases": [r.to_dict() for r in self.results],
            "timestamp": timestamp,
        }
        report_path = os.path.join(REPORTS_DIR, f"{self.name}_{timestamp}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  报告已保存: {report_path}")
        return report_path


# ============================================================
# 内置测试
# ============================================================

if __name__ == "__main__":
    print("=== eval_runner.py 测试 ===\n")

    # Test 1: AIMock 基本功能
    print("Test 1: AIMock 基本功能")
    mock = AIMock({
        "分析代码": AIMockResponse(
            content="代码结构良好",
            tool_calls=[{"name": "code_analyzer", "args": {"path": "."}}],
            token_usage={"input": 100, "output": 50, "total": 150},
        ),
    })
    resp = mock.chat("分析代码")
    assert resp.content == "代码结构良好"
    assert mock.call_count == 1
    print("  ✅ PASS\n")

    # Test 2: AIMock 无匹配
    print("Test 2: AIMock 无匹配返回默认")
    resp2 = mock.chat("不存在的prompt")
    assert "无匹配" in resp2.content
    assert mock.call_count == 2
    print("  ✅ PASS\n")

    # Test 3: EvalCase 构造
    print("Test 3: EvalCase 构造")
    case = EvalCase(
        id="eval-001",
        description="测试文件读取",
        input_task={"type": "file_read", "path": "/etc/hosts"},
        expected={"state": "VERIFIED", "no_error": True},
        tags=["basic", "file"],
    )
    assert case.id == "eval-001"
    d = case.to_dict()
    assert d["expected"]["state"] == "VERIFIED"
    print("  ✅ PASS\n")

    # Test 4: EvalAssert 断言
    print("Test 4: EvalAssert 断言")
    assert EvalAssert.assert_state("VERIFIED", "VERIFIED") is None
    assert EvalAssert.assert_state("FAILED", "VERIFIED") is not None
    assert EvalAssert.assert_no_error({"result": "ok"}) is None
    assert EvalAssert.assert_no_error({"error": "fail"}) is not None
    assert EvalAssert.assert_token_budget({"tokens": {"total_tokens": 100}}, 500) is None
    assert EvalAssert.assert_token_budget({"tokens": {"total_tokens": 600}}, 500) is not None
    print("  ✅ PASS\n")

    # Test 5: EvalRunner 完整流程（mock agent）
    print("Test 5: EvalRunner 完整流程")
    def mock_agent(task):
        return {
            "state": "VERIFIED",
            "verdict": "PASS",
            "capabilities_used": ["file_reader"],
            "tokens": {"total_tokens": 200},
        }

    runner = EvalRunner("test_eval", agent_fn=mock_agent, use_mock=True)
    runner.add_case(EvalCase(
        id="e1", description="文件读取评测",
        input_task={"type": "file_read"},
        expected={"state": "VERIFIED", "verdict": "PASS", "no_error": True, "max_tokens": 500},
    ))
    runner.add_case(EvalCase(
        id="e2", description="工具合规评测",
        input_task={"type": "file_read"},
        expected={"allowed_tools": ["file_reader", "dir_scanner"]},
    ))
    summary = runner.run()
    assert summary["passed"] == 2
    assert summary["failed"] == 0
    print("  ✅ PASS\n")

    # Test 6: 保存报告
    print("Test 6: 保存报告")
    report_path = runner.save_report(summary)
    assert os.path.exists(report_path)
    with open(report_path) as f:
        report = json.load(f)
    assert report["summary"]["passed"] == 2
    os.remove(report_path)
    print("  ✅ PASS\n")

    print("=== 所有测试通过 ===\n")
