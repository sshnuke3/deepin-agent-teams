#!/usr/bin/env python3
"""
agents/orchestrator.py - 统一多 Agent 编排器

合并 orchestrator_v3（状态机+Verifier）、orchestrator_v4（MCP工具驱动）、
sessions_orchestrator_prod（生产级超时/重试/降级）的最佳特性。

执行模式：
  - "tools"  模式：通过 ToolRegistry + MCP 直接调用工具（默认，推荐）
  - "workers" 模式：启动子进程 Worker 池，通过 AgentRegistry 分发任务

核心特性：
  1. TaskStateMachine 状态机驱动，所有状态跳转代码写死
  2. Verifier 独立质检，Worker 产出必须过验收
  3. MCP 工具自动发现（ToolRegistry），零侵入扩展
  4. 可配置超时（单任务 + 全局），带守护线程
  5. 可配置重试（指数退避）
  6. 优雅降级：部分任务失败仍返回已成功的结果
  7. 结构化日志 + trace 可追溯

使用方式：
    # tools 模式（MCP 工具驱动，推荐）
    orch = Orchestrator(verbose=True)
    orch.connect_mcp_servers()         # 或 auto_connect_mcp_servers()
    result = orch.run("分析项目代码结构", project_path="/path/to/project")

    # workers 模式（子进程 Worker 池）
    orch = Orchestrator(execution_mode="workers", verbose=True)
    result = orch.run("分析项目代码结构", project_path="/path/to/project")
"""

import json
import os
import sys
import time
import subprocess
import threading
import select
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

# 路径设置
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
sys.path.insert(0, AGENT_DIR)
sys.path.insert(0, PROJECT_ROOT)

# 内部模块
from task_state_machine import TaskStateMachine, TaskState, TransitionContext, MAX_RETRY
from verifier import Verifier
from registry import AgentRegistry

# 工具层（MCP 模式）
try:
    from tools.tool_registry import ToolRegistry, CallResult
except ImportError:
    ToolRegistry = None
    CallResult = None

# 模型路由（可选）
try:
    from model_router import get_router
except ImportError:
    get_router = None

# erniebot（可选，用于直接 LLM 调用）
try:
    import erniebot
except ImportError:
    erniebot = None


# ==================== 配置常量 ====================

DEFAULT_TASK_TIMEOUT = 120          # 单任务超时（秒）
DEFAULT_GLOBAL_TIMEOUT = 600        # 全局超时（秒）
DEFAULT_RETRY_MAX = 3               # 最大重试次数
RETRY_BACKOFF_BASE = 2              # 退避基数（秒）
WORKER_REGISTER_TIMEOUT = 15        # Worker 注册等待超时（秒）
WORKER_POLL_INTERVAL = 0.5          # Worker 结果轮询间隔（秒）


# ==================== 数据结构 ====================

class TaskStatus(Enum):
    """任务执行状态（与 TaskState 解耦，面向结果汇报）"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """单任务执行结果"""
    task_id: str
    status: TaskStatus
    result: Any = None
    error: str = ""
    duration_ms: int = 0
    retry_count: int = 0
    tool_name: str = ""
    trace: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OrchestrationResult:
    """编排器完整结果"""
    success: bool
    partial: bool
    request: str
    plan: dict
    task_results: Dict[str, TaskResult]
    final_report: str
    total_duration_ms: int
    failed_task_ids: List[str]
    tool_stats: Optional[dict] = None
    state_summaries: Optional[dict] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # 嵌套 dataclass 需要手动序列化
        d["task_results"] = {k: v.to_dict() for k, v in self.task_results.items()}
        return d


# ==================== 日志 ====================

class _Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


def _log(color: str, prefix: str, msg: str, verbose: bool = True):
    if not verbose:
        return
    ts = time.strftime("%H:%M:%S")
    print(f"{color}[{ts}] {prefix}{_Colors.RESET} {msg}", flush=True)


def log_info(msg: str, verbose: bool = True):
    _log(_Colors.BLUE, "INFO ", msg, verbose)


def log_ok(msg: str, verbose: bool = True):
    _log(_Colors.GREEN, "OK   ", msg, verbose)


def log_warn(msg: str, verbose: bool = True):
    _log(_Colors.YELLOW, "WARN ", msg, verbose)


def log_error(msg: str, verbose: bool = True):
    _log(_Colors.RED, "ERROR", msg, verbose)


# ==================== 统一编排器 ====================

class Orchestrator:
    """
    统一多 Agent 编排器

    支持两种执行模式：
    - "tools"：通过 ToolRegistry（含 MCP）直接调用工具
    - "workers"：启动子进程 Worker 池，通过 Registry 分发

    生命周期：
      1. __init__（配置）
      2. connect_mcp_servers / spawn_workers（准备工具/Worker）
      3. run（分解 → 执行 → 验收 → 整合 → 清理）
    """

    def __init__(
        self,
        execution_mode: str = "tools",
        verbose: bool = True,
        task_timeout: int = DEFAULT_TASK_TIMEOUT,
        global_timeout: int = DEFAULT_GLOBAL_TIMEOUT,
        retry_max: int = DEFAULT_RETRY_MAX,
        enable_verifier: bool = True,
    ):
        """
        Args:
            execution_mode: "tools"（MCP/ToolRegistry）或 "workers"（子进程 Worker 池）
            verbose: 是否输出详细日志
            task_timeout: 单任务超时秒数
            global_timeout: 全局超时秒数
            retry_max: 最大重试次数
            enable_verifier: 是否启用 Verifier 验收
        """
        assert execution_mode in ("tools", "workers"), f"不支持的模式: {execution_mode}"
        self.execution_mode = execution_mode
        self.verbose = verbose
        self.task_timeout = task_timeout
        self.global_timeout = global_timeout
        self.retry_max = retry_max
        self.enable_verifier = enable_verifier

        # 核心组件
        self.verifier = Verifier() if enable_verifier else None
        self.task_state_machines: Dict[str, TaskStateMachine] = {}

        # tools 模式组件
        self.tool_registry: Optional[ToolRegistry] = None
        if execution_mode == "tools" and ToolRegistry is not None:
            self.tool_registry = ToolRegistry()

        # workers 模式组件
        self.registry: Optional[AgentRegistry] = None
        self.workers: List[tuple] = []  # [(role, caps, proc)]
        if execution_mode == "workers":
            self.registry = AgentRegistry()

        self._cancel_flag = False
        self._start_time: float = 0

    # ==================== MCP Server 管理（tools 模式）====================

    def connect_mcp_server(self, name: str, command: str, args: List[str]):
        """
        连接一个 MCP Server

        Args:
            name: Server 名称（如 "file-service"）
            command: 启动命令（如 "python3"）
            args: 启动参数（如 ["mcp_servers/file_server.py"]）
        """
        if self.tool_registry is None:
            raise RuntimeError("tools 模式未初始化，无法连接 MCP Server")
        try:
            from mcp_servers.mcp_protocol import MCPClient
        except ImportError:
            log_warn("mcp_protocol 模块不可用，跳过 MCP 连接", self.verbose)
            return

        client = MCPClient()
        client.connect(command, args)

        self.tool_registry.connect_mcp_server(name, client)
        tools = client.list_tools()
        self.tool_registry.register_from_mcp_server(name, tools)

        log_ok(f"MCP Server 已连接: {name} → {[t['name'] for t in tools]}", self.verbose)

    def auto_connect_mcp_servers(self, servers_dir: str = None):
        """
        自动扫描并连接所有内置 MCP Server

        Args:
            servers_dir: MCP Server 目录，默认 <PROJECT_ROOT>/mcp_servers/
        """
        servers_dir = servers_dir or os.path.join(PROJECT_ROOT, "mcp_servers")
        default_servers = [
            ("model-service", "model_server.py"),
            ("file-service", "file_server.py"),
            ("system-service", "system_server.py"),
        ]
        for name, filename in default_servers:
            path = os.path.join(servers_dir, filename)
            if os.path.exists(path):
                try:
                    self.connect_mcp_server(name, "python3", [path])
                except Exception as e:
                    log_warn(f"MCP Server {name} 连接失败: {e}", self.verbose)
            else:
                log_warn(f"MCP Server 文件不存在: {path}", self.verbose)

    def register_local_tool(
        self, name: str, handler: Callable,
        schema: dict = None, description: str = "",
        requires_confirm: bool = False,
    ):
        """注册本地工具（tools 模式下）"""
        if self.tool_registry is None:
            raise RuntimeError("tools 模式未初始化")
        self.tool_registry.register(
            name=name, handler=handler, schema=schema,
            description=description, source="local",
            requires_confirm=requires_confirm,
        )

    # ==================== Worker 管理（workers 模式）====================

    def spawn_workers(self, worker_configs: List[tuple] = None):
        """
        启动 Worker 子进程池

        Args:
            worker_configs: [(role, [capabilities])] 列表，默认使用标准三角色配置
        """
        if self.registry is None:
            raise RuntimeError("workers 模式未初始化")

        if worker_configs is None:
            worker_configs = [
                ("researcher", ["file_reader", "dir_scanner", "code_analyzer",
                                "dependency_analyzer", "web_search", "web_fetcher",
                                "markdown_writer"]),
                ("coder", ["file_reader", "code_analyzer", "ast_parser", "syntax_checker",
                           "shell_executor", "git_analyzer", "markdown_writer"]),
                ("general", ["file_reader", "dir_scanner", "code_analyzer", "ast_parser",
                             "syntax_checker", "shell_executor", "markdown_writer"]),
            ]

        worker_script = os.path.join(AGENT_DIR, "worker_v2.py")
        if not os.path.exists(worker_script):
            log_warn("worker_v2.py 不存在，跳过 Worker 启动", self.verbose)
            return

        for role, caps in worker_configs:
            proc = subprocess.Popen(
                ["python3", worker_script, "--role", role, "--caps"] + caps,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            self.workers.append((role, caps, proc))
            log_info(f"启动 {role} Worker (PID={proc.pid})", self.verbose)

        # 等待所有 Worker 注册完成
        deadline = time.time() + WORKER_REGISTER_TIMEOUT
        registered = set()
        while time.time() < deadline and len(registered) < len(self.workers):
            for role, _, proc in self.workers:
                if role in registered:
                    continue
                if select.select([proc.stdout], [], [], 0.1)[0]:
                    line = proc.stdout.readline()
                    if "REGISTERED:" in line:
                        registered.add(role)
                        log_ok(f"{role} Worker 注册完成", self.verbose)
            time.sleep(0.1)

        time.sleep(0.5)
        agents = self.registry.list_agents()
        log_ok(f"Worker 池就绪: {len(agents)} 个已注册", self.verbose)

    def stop_workers(self):
        """终止所有 Worker 子进程"""
        for role, _, proc in self.workers:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.workers.clear()

    # ==================== 任务分解 ====================

    def decompose(self, user_request: str, project_path: str = "") -> dict:
        """
        使用 LLM 将用户请求分解为子任务

        Returns:
            {
              "tasks": [{"id": "task-1", "description": "...", "capabilities_needed": [...],
                         "tool_name": "...", "params": {}, "type": "..."}],
              "spawn_plan": [{"agent_type": "...", "agent_label": "...", "tasks": [...]}],
              "summary": "..."
            }
        """
        # 构建工具描述
        tools_section = ""
        if self.tool_registry:
            tools_list = self.tool_registry.list_for_llm()
            if tools_list:
                tools_desc = json.dumps(tools_list, ensure_ascii=False, indent=2)
                tools_section = "可用工具（MCP 协议）：\n" + tools_desc + "\n"

        prompt = f"""用户需求：{user_request}

{tools_section}
请将上述需求分解为具体的子任务。

输出格式为纯 JSON：
{{
  "tasks": [
    {{
      "id": "task-1",
      "description": "详细的任务描述",
      "capabilities_needed": ["cap1", "cap2"],
      "tool_name": "使用的工具名（如有）",
      "params": {{}},
      "type": "任务类型"
    }}
  ],
  "spawn_plan": [
    {{
      "agent_type": "researcher | coder | general",
      "agent_label": "如 researcher-1",
      "tasks": ["task-id-1"]
    }}
  ],
  "summary": "一句话总结"
}}

可用能力：file_reader, dir_scanner, file_writer, code_analyzer, ast_parser,
syntax_checker, dependency_analyzer, shell_executor, git_analyzer,
web_search, web_fetcher, doc_generator, markdown_writer

capability → agent_type 映射：
- web_search/web_fetcher → researcher
- code_analyzer/ast_parser/syntax_checker/dependency_analyzer/git_analyzer → coder
- 其余 → general

规则：
- 每个 task 至少需要 1 个 capability
- spawn_plan 中每个 agent_label 必须唯一
- 只输出 JSON"""

        # 通过可用的 LLM 通道调用
        plan_text = self._call_llm(prompt, task_type="task_plan")
        if plan_text:
            try:
                text = plan_text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    text = text.rstrip("`").strip()
                plan = json.loads(text)
                log_ok(f"分解完成: {len(plan.get('tasks', []))} 个子任务", self.verbose)
                return plan
            except (json.JSONDecodeError, KeyError) as e:
                log_warn(f"JSON 解析失败: {e}，降级为单任务", self.verbose)

        # 降级：单任务
        return {
            "tasks": [{
                "id": f"task-{int(time.time())}",
                "description": user_request,
                "capabilities_needed": ["shell_executor"],
                "tool_name": "exec_command",
                "params": {},
                "type": "general",
            }],
            "spawn_plan": [{
                "agent_type": "general",
                "agent_label": "general-1",
                "tasks": [f"task-{int(time.time())}"],
            }],
            "summary": user_request,
        }

    # ==================== 任务执行 ====================

    def execute_task(self, task: dict, task_id: str) -> TaskResult:
        """
        执行单个任务（含状态机 + 验收 + 重试）

        状态机流程：
          PENDING → CLAIMED → RUNNING → VERIFIED → COMPLETED
                                ↓
                              RETRY（≤ retry_max 次）
                                ↓
                              FAILED
        """
        sm = TaskStateMachine(task_id)
        self.task_state_machines[task_id] = sm
        start_time = time.time()
        retry_count = 0

        while True:
            # === PENDING → CLAIMED ===
            worker_id = self._claim_task(task, task_id, sm)
            if worker_id is None:
                sm.transition(TaskState.FAILED, TransitionContext(
                    error_msg="no available worker/tool",
                    verdict="FAIL",
                ))
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error="no available worker/tool",
                    duration_ms=int((time.time() - start_time) * 1000),
                    retry_count=retry_count,
                    trace=sm.get_trace(),
                )

            # === CLAIMED → RUNNING ===
            sm.transition(TaskState.RUNNING, TransitionContext(start_time=time.time()))

            # === 执行 ===
            try:
                result_data = self._do_execute(task, task_id, sm)
            except TimeoutError as e:
                result_data = {"error": str(e), "error_type": "E_TIMEOUT"}
            except Exception as e:
                result_data = {"error": str(e)}

            # 检查全局取消
            if self._cancel_flag:
                sm.transition(TaskState.FAILED, TransitionContext(
                    error_msg="global timeout cancelled",
                    verdict="FAIL",
                ))
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.CANCELLED,
                    error="global timeout cancelled",
                    duration_ms=int((time.time() - start_time) * 1000),
                    retry_count=retry_count,
                    trace=sm.get_trace(),
                )

            # === Verifier 验收 ===
            if self.enable_verifier and self.verifier:
                v = self.verifier.verify(task, {"result": result_data})
                verdict = v.result
                causes = v.causes
                is_pass = v.is_pass
            else:
                # 无 Verifier 时，检查是否有 error 字段
                has_error = isinstance(result_data, dict) and result_data.get("error")
                verdict = "FAIL" if has_error else "PASS"
                causes = [str(result_data.get("error", ""))] if has_error else []
                is_pass = not has_error

            if is_pass:
                # PASS → VERIFIED → COMPLETED
                sm.transition(TaskState.VERIFIED, TransitionContext(verdict="PASS"))
                sm.transition(TaskState.COMPLETED, TransitionContext())
                duration = int((time.time() - start_time) * 1000)
                log_ok(f"{task_id}: 完成 (耗时 {duration}ms)", self.verbose)
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    result=result_data,
                    duration_ms=duration,
                    retry_count=retry_count,
                    tool_name=task.get("tool_name", ""),
                    trace=sm.get_trace(),
                )

            # FAIL → RETRY 或 FAILED
            if retry_count < self.retry_max:
                retry_count += 1
                backoff = RETRY_BACKOFF_BASE ** retry_count
                log_warn(f"{task_id}: 验收失败，{backoff}s 后重试 ({retry_count}/{self.retry_max}) "
                         f"原因: {causes}", self.verbose)
                sm.transition(TaskState.RETRY, TransitionContext(
                    verdict="FAIL", verdict_causes=causes, retry_count=retry_count,
                ))
                sm.retry_with_increment()
                time.sleep(backoff)
                continue
            else:
                # 重试耗尽 → FAILED
                sm.transition(TaskState.FAILED, TransitionContext(
                    error_msg=f"max retry ({self.retry_max}) exceeded",
                    verdict="FAIL", verdict_causes=causes, retry_count=retry_count,
                ))
                duration = int((time.time() - start_time) * 1000)
                log_error(f"{task_id}: 失败 (重试耗尽) 原因: {causes}", self.verbose)
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error=f"max retry exceeded: {causes}",
                    duration_ms=duration,
                    retry_count=retry_count,
                    trace=sm.get_trace(),
                )

    def _claim_task(self, task: dict, task_id: str, sm: TaskStateMachine) -> Optional[str]:
        """
        认领任务，返回 worker_id / tool_name，失败返回 None
        """
        if self.execution_mode == "tools":
            tool_name = task.get("tool_name", "exec_command")
            if self.tool_registry and self.tool_registry.has(tool_name):
                sm.transition(TaskState.CLAIMED, TransitionContext(worker_id=tool_name))
                return tool_name
            # 回退：尝试用第一个可用 capability 对应的工具
            for cap in task.get("capabilities_needed", []):
                if self.tool_registry and self.tool_registry.has(cap):
                    sm.transition(TaskState.CLAIMED, TransitionContext(worker_id=cap))
                    return cap
            log_warn(f"{task_id}: 无匹配工具 (tool={tool_name}, caps={task.get('capabilities_needed')})",
                     self.verbose)
            return None

        else:  # workers 模式
            worker_id = self.registry.find_best_agent(task.get("capabilities_needed", []))
            if worker_id:
                sm.transition(TaskState.CLAIMED, TransitionContext(worker_id=worker_id))
            return worker_id

    def _do_execute(self, task: dict, task_id: str, sm: TaskStateMachine) -> Any:
        """
        实际执行任务逻辑，返回结果数据

        Raises:
            TimeoutError: 执行超时
        """
        if self.execution_mode == "tools":
            return self._execute_via_tools(task, task_id, sm)
        else:
            return self._execute_via_workers(task, task_id, sm)

    def _execute_via_tools(self, task: dict, task_id: str, sm: TaskStateMachine) -> Any:
        """通过 ToolRegistry 执行"""
        tool_name = task.get("tool_name", "exec_command")
        params = task.get("params", {})

        result = self.tool_registry.call(tool_name, params)
        if not result.success:
            raise Exception(f"工具调用失败: {result.error}")

        return result.output

    def _execute_via_workers(self, task: dict, task_id: str, sm: TaskStateMachine) -> Any:
        """通过 Worker 子进程执行"""
        worker_id = sm._ctx.worker_id

        # 等待 Worker 自主认领并完成任务
        deadline = time.time() + self.task_timeout
        while time.time() < deadline:
            r = self.registry.get_result(task_id)
            if r:
                return r
            # 超时检查
            sm.check_timeout(timeout=self.task_timeout)
            if sm.state == TaskState.FAILED:
                raise TimeoutError(f"task {task_id} timeout after {self.task_timeout}s")
            time.sleep(WORKER_POLL_INTERVAL)

        raise TimeoutError(f"task {task_id} timeout after {self.task_timeout}s")

    # ==================== 结果整合 ====================

    def integrate(self, user_request: str, plan: dict,
                  task_results: Dict[str, TaskResult]) -> str:
        """
        整合所有任务结果，生成最终 Markdown 报告
        """
        result_parts = []
        for task_id, tr in task_results.items():
            status_str = tr.status.value
            if tr.result is not None:
                if isinstance(tr.result, dict):
                    summary = json.dumps(tr.result, ensure_ascii=False)[:300]
                else:
                    summary = str(tr.result)[:300]
            else:
                summary = tr.error[:300] if tr.error else "无结果"
            result_parts.append(f"## {task_id} [{status_str}]\n{summary}")

        prompt = f"""用户需求：{user_request}

任务分解：
{json.dumps(plan, ensure_ascii=False, indent=2)}

执行结果：
{chr(10).join(result_parts)}

请生成 Markdown 报告，包含：
1. 执行概述（哪些任务成功/失败）
2. 各子任务执行情况
3. 关键发现
4. 最终结论和建议

只用 Markdown 输出。"""

        report = self._call_llm(prompt, task_type="report")
        if report:
            return report

        # 降级：简单拼接
        return f"# 执行报告\n\n" + "\n\n".join(result_parts)

    # ==================== LLM 调用抽象 ====================

    def _call_llm(self, prompt: str, task_type: str = "default") -> Optional[str]:
        """
        统一 LLM 调用入口

        优先级：
        1. MCP model-service（tools 模式且已连接）
        2. model_router（双模型路由）
        3. erniebot 直接调用
        4. 返回 None（降级）
        """
        # 方式 1：通过 MCP tool_registry 调用 model-service
        if self.tool_registry and self.tool_registry.has("chat_completion"):
            try:
                result = self.tool_registry.call("chat_completion", {
                    "messages": [
                        {"role": "system", "content": "你是任务分解和报告整合专家。只输出 JSON 或 Markdown。"},
                        {"role": "user", "content": prompt},
                    ],
                    "model": "ernie-3.5",
                    "temperature": 0.3,
                })
                if result.success:
                    resp = result.output
                    if isinstance(resp, dict) and resp.get("success"):
                        return resp["result"]
            except Exception as e:
                log_warn(f"MCP model-service 调用失败: {e}", self.verbose)

        # 方式 2：model_router
        if get_router is not None:
            try:
                router = get_router(verbose=self.verbose)
                resp = router.chat(prompt, task_type=task_type)
                if resp.get("success"):
                    return resp["result"]
            except Exception as e:
                log_warn(f"model_router 调用失败: {e}", self.verbose)

        # 方式 3：erniebot 直接调用
        if erniebot is not None:
            try:
                response = erniebot.ChatCompletion.create(
                    model="ernie-lite",
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.get_result() if hasattr(response, 'get_result') else str(response)
            except Exception as e:
                log_warn(f"erniebot 调用失败: {e}", self.verbose)

        log_warn("所有 LLM 通道均不可用", self.verbose)
        return None

    # ==================== 主流程 ====================

    def run(self, user_request: str, project_path: str = "") -> OrchestrationResult:
        """
        主流程入口

        Args:
            user_request: 用户需求描述
            project_path: 项目路径（注入到每个 task 的 params 中）

        Returns:
            OrchestrationResult 完整编排结果
        """
        self._start_time = time.time()
        self._cancel_flag = False

        log_info(f"启动（模式: {self.execution_mode}，超时: {self.task_timeout}s/"
                 f"{self.global_timeout}s，重试: {self.retry_max}）", self.verbose)
        log_info(f"请求: {user_request[:80]}...", self.verbose)

        # Step 0: 准备工具/Worker
        if self.execution_mode == "workers":
            self.spawn_workers()

        # Step 1: 分解任务
        log_info("分解任务...", self.verbose)
        plan = self.decompose(user_request, project_path)
        tasks = plan.get("tasks", [])
        log_ok(f"分解完成: {len(tasks)} 个子任务", self.verbose)

        # 注入 project_path
        if project_path:
            for t in tasks:
                t.setdefault("params", {})
                t["params"].setdefault("path", project_path)
                t["params"].setdefault("project_path", project_path)

        # Step 2: 全局超时守护线程
        watcher = threading.Thread(target=self._global_timeout_watcher, daemon=True)
        watcher.start()

        # Step 3: 执行任务
        log_info("执行任务...", self.verbose)
        task_results: Dict[str, TaskResult] = {}
        for task in tasks:
            task_id = task.get("id", f"task-{int(time.time() * 1000)}")
            if self._cancel_flag:
                task_results[task_id] = TaskResult(
                    task_id=task_id, status=TaskStatus.CANCELLED,
                    error="global timeout cancelled",
                )
                continue
            log_info(f"--- {task_id}: {task.get('description', '')[:60]} ---", self.verbose)
            task_results[task_id] = self.execute_task(task, task_id)

        # Step 4: 整合结果
        log_info("整合结果...", self.verbose)
        final_report = self.integrate(user_request, plan, task_results)

        # Step 5: 清理
        self._cleanup()

        # 汇总
        total_ms = int((time.time() - self._start_time) * 1000)
        failed_ids = [tid for tid, tr in task_results.items()
                      if tr.status not in (TaskStatus.COMPLETED,)]
        success = len(failed_ids) == 0
        partial = any(tr.status == TaskStatus.COMPLETED for tr in task_results.values())

        if success:
            log_ok(f"全部 {len(task_results)} 个任务成功，耗时 {total_ms / 1000:.1f}s", self.verbose)
        elif partial:
            log_warn(f"部分成功: {len(task_results) - len(failed_ids)}/{len(task_results)}，"
                     f"失败: {failed_ids}，耗时 {total_ms / 1000:.1f}s", self.verbose)
        else:
            log_error(f"全部失败，耗时 {total_ms / 1000:.1f}s", self.verbose)

        return OrchestrationResult(
            success=success,
            partial=partial,
            request=user_request,
            plan=plan,
            task_results=task_results,
            final_report=final_report,
            total_duration_ms=total_ms,
            failed_task_ids=failed_ids,
            tool_stats=self.tool_registry.get_stats() if self.tool_registry else None,
            state_summaries={
                tid: sm.summary()
                for tid, sm in self.task_state_machines.items()
            },
        )

    def _global_timeout_watcher(self):
        """全局超时守护线程"""
        while True:
            elapsed = time.time() - self._start_time
            if elapsed >= self.global_timeout:
                log_error(f"全局超时 ({self.global_timeout}s)，强制取消", self.verbose)
                self._cancel_flag = True
                return
            if self._cancel_flag:
                return
            remaining = self.global_timeout - elapsed
            if remaining < 60:
                log_warn(f"全局超时剩余 {remaining:.0f}s...", self.verbose)
            time.sleep(min(5, remaining / 2))

    def _cleanup(self):
        """清理资源"""
        if self.execution_mode == "workers":
            self.stop_workers()
        if self.execution_mode == "tools" and self.tool_registry:
            # 断开 MCP 连接
            for name, client in list(self.tool_registry._mcp_clients.items()):
                try:
                    client.disconnect()
                    log_info(f"断开 MCP: {name}", self.verbose)
                except Exception:
                    pass
            self.tool_registry._mcp_clients.clear()


# ==================== 便捷工厂函数 ====================

def create_orchestrator(
    mode: str = "tools",
    mcp_servers: bool = True,
    **kwargs,
) -> Orchestrator:
    """
    创建并初始化编排器

    Args:
        mode: "tools" 或 "workers"
        mcp_servers: 是否自动连接 MCP Server（仅 tools 模式）
        **kwargs: 传递给 Orchestrator.__init__

    Returns:
        已初始化的 Orchestrator 实例
    """
    orch = Orchestrator(execution_mode=mode, **kwargs)
    if mode == "tools" and mcp_servers:
        orch.auto_connect_mcp_servers()
    return orch


# ==================== CLI 入口 ====================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="统一多 Agent 编排器")
    parser.add_argument("task", nargs="?", help="要执行的任务描述")
    parser.add_argument("--mode", choices=["tools", "workers"], default="tools",
                        help="执行模式（默认 tools）")
    parser.add_argument("--project", "-p", default="", help="项目路径")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TASK_TIMEOUT,
                        help=f"单任务超时秒数（默认 {DEFAULT_TASK_TIMEOUT}）")
    parser.add_argument("--global-timeout", "-g", type=int, default=DEFAULT_GLOBAL_TIMEOUT,
                        help=f"全局超时秒数（默认 {DEFAULT_GLOBAL_TIMEOUT}）")
    parser.add_argument("--retry", type=int, default=DEFAULT_RETRY_MAX,
                        help=f"最大重试次数（默认 {DEFAULT_RETRY_MAX}）")
    parser.add_argument("--no-verifier", action="store_true", help="禁用 Verifier")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式")
    parser.add_argument("--output", "-o", help="输出结果到文件")
    args = parser.parse_args()

    if not args.task:
        parser.print_help()
        sys.exit(1)

    orch = create_orchestrator(
        mode=args.mode,
        mcp_servers=(args.mode == "tools"),
        verbose=not args.quiet,
        task_timeout=args.timeout,
        global_timeout=args.global_timeout,
        retry_max=args.retry,
        enable_verifier=not args.no_verifier,
    )

    result = orch.run(args.task, project_path=args.project)

    output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        log_ok(f"结果已保存到 {args.output}", not args.quiet)
    else:
        print("\n" + output)

    print(f"\n{result.final_report}")
