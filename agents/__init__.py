"""
agents/__init__.py

deepin-agent-teams 多智能体模块

核心组件：
  - Orchestrator: 统一多 Agent 编排器（支持 tools/workers 两种模式）
  - TaskStateMachine: 任务状态机引擎
  - Verifier: 独立质检员
  - AgentRegistry: Agent 注册中心
  - BaseWorker / GeneralWorker / ExtensibleWorker: Worker 实现

快速使用：
    from agents import Orchestrator, create_orchestrator

    orch = create_orchestrator(mode="tools")
    result = orch.run("分析项目代码结构", project_path="/path/to/project")
    print(result.final_report)
"""

# 统一编排器（推荐）
from .orchestrator import (
    Orchestrator,
    create_orchestrator,
    TaskResult,
    TaskStatus,
    OrchestrationResult,
)

# 子组件（按需导入）
from .task_state_machine import (
    TaskStateMachine,
    TaskState,
    TransitionContext,
    TransitionRule,
    MAX_RETRY,
)

from .verifier import Verifier, Verdict

from .registry import AgentRegistry

# Worker 实现
from .worker_base import BaseWorker, GeneralWorker
from .worker_v2 import ExtensibleWorker, CapabilityExecutor

# 兼容旧版导入（已废弃，请使用 Orchestrator）
from .orchestrator_v3 import OrchestratorV3
from .orchestrator_v4 import OrchestratorV4

__all__ = [
    # 推荐 API
    "Orchestrator",
    "create_orchestrator",
    "TaskResult",
    "TaskStatus",
    "OrchestrationResult",

    # 状态机
    "TaskStateMachine",
    "TaskState",
    "TransitionContext",
    "TransitionRule",
    "MAX_RETRY",

    # 验收
    "Verifier",
    "Verdict",

    # 注册中心
    "AgentRegistry",

    # Worker
    "BaseWorker",
    "GeneralWorker",
    "ExtensibleWorker",
    "CapabilityExecutor",

    # 兼容旧版（已废弃）
    "OrchestratorV3",
    "OrchestratorV4",
]
