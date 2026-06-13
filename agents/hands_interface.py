"""
hands_interface.py — Brain/Hands 分离架构

核心思路（学自 OpenVibeCoding）：
- Brain（编排层）：任务拆解、状态管理、调度决策
- Hands（执行层）：代码写入、文件读取、命令执行
- 中间层（HandsInterface）：抽象接口，让 Brain 不直接依赖 Hands 实现

好处：
1. 换执行后端不影响编排逻辑（Docker → CloudBase → 本地进程）
2. 编排层可独立测试（Mock Hands）
3. 多种执行后端可并存（本地 + 远程沙箱）
"""

import os
import sys
import time
import json
import uuid
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)


# ============================================================
# 执行请求 / 响应（Brain → Hands 的统一协议）
# ============================================================

@dataclass
class ExecuteRequest:
    """执行请求（Brain 发给 Hands）"""
    request_id: str = field(default_factory=lambda: f"req-{uuid.uuid4().hex[:8]}")
    capability: str = ""           # 能力名称（如 file_reader, shell_executor）
    params: Dict[str, Any] = field(default_factory=dict)
    task_id: str = ""              # 关联的任务 ID
    timeout: float = 60            # 超时秒数
    security_context: Dict = field(default_factory=dict)  # 安全上下文

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "capability": self.capability,
            "params": self.params,
            "task_id": self.task_id,
            "timeout": self.timeout,
        }


@dataclass
class ExecuteResponse:
    """执行响应（Hands 返回给 Brain）"""
    request_id: str = ""
    success: bool = True
    result: Any = None
    error: str = ""
    error_type: str = ""
    duration_ms: float = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "request_id": self.request_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }
        if self.result is not None:
            d["result"] = self.result
        if self.error:
            d["error"] = self.error
            d["error_type"] = self.error_type
        if self.metadata:
            d["metadata"] = self.metadata
        return d


# ============================================================
# HandsInterface — 执行层抽象接口
# ============================================================

class HandsInterface(ABC):
    """
    执行层抽象接口

    Brain（编排层）只依赖这个接口，不直接依赖具体实现。
    换执行后端只需换 HandsInterface 的实现类。

    实现类：
    - LocalHands：本地进程执行（当前 deepin-agent-teams 的方式）
    - DockerHands：Docker 容器执行（未来扩展）
    - RemoteHands：远程沙箱执行（未来扩展）
    - MockHands：测试用 Mock
    """

    @abstractmethod
    def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        """执行一个能力调用"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """检查执行层是否可用"""
        ...

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """返回支持的能力列表"""
        ...

    def batch_execute(self, requests: List[ExecuteRequest]) -> List[ExecuteResponse]:
        """批量执行（默认串行，子类可重写为并行）"""
        return [self.execute(req) for req in requests]


# ============================================================
# LocalHands — 本地执行实现
# ============================================================

class LocalHands(HandsInterface):
    """
    本地执行实现

    直接调用 BaseWorker 的能力方法。
    这是当前 deepin-agent-teams 的默认执行方式。
    """

    def __init__(self, worker: Any = None) -> None:
        self._worker = worker
        self._capabilities = [
            "file_reader", "dir_scanner", "file_writer",
            "code_analyzer", "ast_parser", "syntax_checker", "dependency_analyzer",
            "shell_executor", "git_analyzer", "process_manager",
            "web_search", "web_fetcher",
            "doc_generator", "markdown_writer",
        ]

    def set_worker(self, worker: Any) -> None:
        """注入 Worker 实例"""
        self._worker = worker

    def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        """通过 Worker 执行能力"""
        start = time.time()

        if not self._worker:
            return ExecuteResponse(
                request_id=request.request_id,
                success=False,
                error="No worker attached",
                error_type="E_NO_WORKER",
            )

        try:
            result = self._worker.execute_capability(request.capability, request.params)
            duration = (time.time() - start) * 1000

            if isinstance(result, dict) and result.get("error"):
                return ExecuteResponse(
                    request_id=request.request_id,
                    success=False,
                    result=result,
                    error=str(result["error"]),
                    error_type=result.get("error_type", "E_UNKNOWN"),
                    duration_ms=duration,
                )

            return ExecuteResponse(
                request_id=request.request_id,
                success=True,
                result=result,
                duration_ms=duration,
            )

        except Exception as e:
            return ExecuteResponse(
                request_id=request.request_id,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=(time.time() - start) * 1000,
            )

    def health_check(self) -> bool:
        return self._worker is not None

    def get_capabilities(self) -> List[str]:
        return list(self._capabilities)


# ============================================================
# DockerHands — Docker 容器执行（预留接口）
# ============================================================

class DockerHands(HandsInterface):
    """
    Docker 容器执行实现（预留）

    每个任务在独立的 Docker 容器中执行，天然隔离。
    适合多租户 SaaS 场景。
    """

    def __init__(self, image: str = "python:3.12-slim") -> None:
        self._image = image

    def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        # TODO: 实现 Docker 容器执行
        return ExecuteResponse(
            request_id=request.request_id,
            success=False,
            error="DockerHands not implemented yet",
            error_type="E_NOT_IMPLEMENTED",
        )

    def health_check(self) -> bool:
        # TODO: 检查 Docker 是否可用
        return False

    def get_capabilities(self) -> List[str]:
        return []  # TODO


# ============================================================
# MockHands — 测试用 Mock
# ============================================================

class MockHands(HandsInterface):
    """
    测试用 Mock 执行层

    确定性输入 → 确定性输出，无需真实执行。
    用于编排层的单元测试和 CI。
    """

    def __init__(self) -> None:
        self._responses: Dict[str, ExecuteResponse] = {}
        self._call_log: List[ExecuteRequest] = []
        self._default_response = ExecuteResponse(
            success=True,
            result={"mock": True},
        )

    def set_response(self, capability: str, response: ExecuteResponse) -> None:
        """预设某个能力的响应"""
        self._responses[capability] = response

    def set_responses(self, responses: Dict[str, Any]) -> None:
        """批量预设响应"""
        for cap, result in responses.items():
            self._responses[cap] = ExecuteResponse(success=True, result=result)

    def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        self._call_log.append(request)
        resp = self._responses.get(request.capability, self._default_response)
        resp.request_id = request.request_id
        return resp

    def health_check(self) -> bool:
        return True

    def get_capabilities(self) -> List[str]:
        return list(self._responses.keys())

    @property
    def call_count(self) -> int:
        return len(self._call_log)

    def get_calls(self, capability: str = None) -> List[ExecuteRequest]:
        if capability:
            return [r for r in self._call_log if r.capability == capability]
        return list(self._call_log)


# ============================================================
# HandsFactory — 创建 Hands 实例的工厂
# ============================================================

class HandsFactory:
    """根据配置创建合适的 Hands 实现"""

    _registry: Dict[str, type] = {
        "local": LocalHands,
        "docker": DockerHands,
        "mock": MockHands,
    }

    @classmethod
    def create(cls, backend: str = "local", **kwargs) -> HandsInterface:
        """创建 Hands 实例"""
        hands_cls = cls._registry.get(backend)
        if not hands_cls:
            raise ValueError(f"Unknown hands backend: {backend}. Available: {list(cls._registry.keys())}")
        return hands_cls(**kwargs)

    @classmethod
    def register(cls, name: str, hands_cls: type) -> None:
        """注册新的 Hands 实现"""
        cls._registry[name] = hands_cls


# ============================================================
# 内置测试
# ============================================================

if __name__ == "__main__":
    print("=== hands_interface.py 测试 ===\n")

    # Test 1: ExecuteRequest / ExecuteResponse 构造
    print("Test 1: 请求/响应构造")
    req = ExecuteRequest(capability="file_reader", params={"path": "/etc/hosts"}, task_id="t-001")
    assert req.capability == "file_reader"
    assert req.request_id.startswith("req-")
    resp = ExecuteResponse(request_id=req.request_id, success=True, result={"content": "127.0.0.1"})
    assert resp.success
    d = resp.to_dict()
    assert d["request_id"] == req.request_id
    print("  ✅ PASS\n")

    # Test 2: MockHands 基本功能
    print("Test 2: MockHands 基本功能")
    mock = MockHands()
    mock.set_response("file_reader", ExecuteResponse(success=True, result={"content": "hello"}))
    mock.set_response("shell_executor", ExecuteResponse(success=False, error="blocked", error_type="E_BLOCKED"))

    req1 = ExecuteRequest(capability="file_reader", params={"path": "/etc/hosts"})
    resp1 = mock.execute(req1)
    assert resp1.success
    assert resp1.result["content"] == "hello"

    req2 = ExecuteRequest(capability="shell_executor", params={"command": "rm -rf /"})
    resp2 = mock.execute(req2)
    assert not resp2.success
    assert resp2.error_type == "E_BLOCKED"

    assert mock.call_count == 2
    print("  ✅ PASS\n")

    # Test 3: MockHands 调用记录
    print("Test 3: MockHands 调用记录")
    file_calls = mock.get_calls("file_reader")
    assert len(file_calls) == 1
    shell_calls = mock.get_calls("shell_executor")
    assert len(shell_calls) == 1
    all_calls = mock.get_calls()
    assert len(all_calls) == 2
    print("  ✅ PASS\n")

    # Test 4: HandsFactory
    print("Test 4: HandsFactory 创建")
    local = HandsFactory.create("local")
    assert isinstance(local, LocalHands)
    assert not local.health_check()  # 没有 worker

    mock_hands = HandsFactory.create("mock")
    assert isinstance(mock_hands, MockHands)
    assert mock_hands.health_check()

    docker = HandsFactory.create("docker")
    assert isinstance(docker, DockerHands)
    assert not docker.health_check()  # 未实现
    print("  ✅ PASS\n")

    # Test 5: HandsFactory 注册自定义实现
    print("Test 5: 自定义 Hands 注册")
    class CustomHands(HandsInterface):
        def execute(self, request):
            return ExecuteResponse(success=True, result={"custom": True})
        def health_check(self):
            return True
        def get_capabilities(self):
            return ["custom_cap"]

    HandsFactory.register("custom", CustomHands)
    custom = HandsFactory.create("custom")
    assert custom.health_check()
    assert "custom_cap" in custom.get_capabilities()
    print("  ✅ PASS\n")

    # Test 6: LocalHands 无 worker 时的优雅降级
    print("Test 6: LocalHands 无 worker 降级")
    local = LocalHands()
    req = ExecuteRequest(capability="file_reader", params={"path": "/etc/hosts"})
    resp = local.execute(req)
    assert not resp.success
    assert resp.error_type == "E_NO_WORKER"
    print("  ✅ PASS\n")

    # Test 7: MockHands 批量执行
    print("Test 7: 批量执行")
    mock2 = MockHands()
    mock2.set_responses({
        "file_reader": {"content": "file content"},
        "code_analyzer": {"lines": 100},
    })
    reqs = [
        ExecuteRequest(capability="file_reader", params={"path": "a.py"}),
        ExecuteRequest(capability="code_analyzer", params={"path": "b.py"}),
    ]
    resps = mock2.batch_execute(reqs)
    assert len(resps) == 2
    assert all(r.success for r in resps)
    print("  ✅ PASS\n")

    print("=== 所有测试通过 ===\n")
