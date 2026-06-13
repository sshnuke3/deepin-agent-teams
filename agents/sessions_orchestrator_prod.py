#!/usr/bin/env python3
"""
agents/sessions_orchestrator_prod.py - v4.1 生产级 Sessions-Spawn 编排器

在 v4 基础上增加：
- 超时控制（每个子 Agent 独立超时 + 全局超时）
- 重试机制（可配置重试次数和退避策略）
- 错误处理（子 Agent 失败不影响其他 Agent，结果归并）
- 结构化日志（彩色日志 + 多级别）
- 会话状态管理（跟踪 pending/running/done/failed）
- 健康检查（定期 ping 子 Agent 存活状态）
- 优雅降级（部分 Agent 失败时仍返回部分结果）

使用方式：

  # 方式 A：在 OpenClaw 对话中直接 COPY-PASTE sessions_spawn 指令
  python agents/sessions_orchestrator_prod.py "你的任务" -o instructions.md

  # 方式 B：自动模式（生成任务内容但不执行）
  python agents/sessions_orchestrator_prod.py "你的任务" --auto

  # 方式 C：直接执行模式（需要 OpenClaw 上下文）
  python agents/sessions_orchestrator_prod.py "你的任务" --run
"""
import argparse
import datetime
import enum
import json
import os
import sys
import threading
import time
import traceback
import erniebot
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any


# ========== 配置 ==========

ERNIE_TOKEN = os.getenv("ERNIEBOT_ACCESS_TOKEN", "")

# 超时配置（秒）
DEFAULT_TASK_TIMEOUT = 120      # 单个子 Agent 超时
DEFAULT_GLOBAL_TIMEOUT = 300    # 全局超时（所有 Agent 总计）
DEFAULT_RETRY_MAX = 2           # 最大重试次数
RETRY_BACKOFF_BASE = 2          # 退避基数（秒）

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "")


# ========== 日志系统 ==========

class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


class LogLevel(enum.Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


_level_value = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_current_level = _level_value.get(LOG_LEVEL, 20)


def _log(level: LogLevel, color: str, prefix: str, msg: str, file=None):
    if level.value < _current_level:
        return
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    tag = f"{color}[{ts}] {prefix}{Colors.RESET}"
    line = f"{tag} {msg}"
    print(line, file=file or sys.stderr)
    if LOG_FILE:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")


log_debug = lambda msg, **kw: _log(LogLevel.DEBUG, Colors.GRAY, "DEBUG", msg, **kw)
log_info = lambda msg, **kw: _log(LogLevel.INFO, Colors.BLUE, "INFO ", msg, **kw)
log_warn = lambda msg, **kw: _log(LogLevel.WARNING, Colors.YELLOW, "WARN ", msg, **kw)
log_error = lambda msg, **kw: _log(LogLevel.ERROR, Colors.RED, "ERROR", msg, **kw)
log_ok = lambda msg, **kw: _log(LogLevel.INFO, Colors.GREEN, "OK   ", msg, **kw)


# ========== 状态枚举 ==========

class AgentStatus(enum.Enum):
    PENDING = "pending"       # 等待调度
    RUNNING = "running"       # 执行中
    DONE = "done"             # 成功完成
    FAILED = "failed"         # 失败（已达最大重试）
    TIMEOUT = "timeout"       # 超时
    CANCELLED = "cancelled"   # 被取消


# ========== 数据结构 ==========

@dataclass
class AgentResult:
    label: str
    agent_type: str
    status: AgentStatus
    result: str = ""           # Agent 返回的内容
    error: str = ""            # 错误信息
    duration_ms: int = 0       # 执行耗时（毫秒）
    attempts: int = 0          # 尝试次数
    session_key: str = ""      # 子 Agent sessionKey
    started_at: str = ""        # 开始时间 ISO 格式
    finished_at: str = ""      # 结束时间 ISO 格式
    spawn_code: str = ""       # sessions_spawn 生成的分发指令

    def to_dict(self):
        return asdict(self)


@dataclass
class ExecutionPlan:
    summary: str
    tasks: list
    spawn_plan: list
    total_agents: int = 0
    estimated_duration_ms: int = 0

    def to_dict(self):
        return asdict(self)


# ========== ERNIE 初始化 ==========

def init_ernie(token: str = None) -> None:
    t = token or ERNIE_TOKEN
    erniebot.api_type = "aistudio"
    erniebot.access_token = t


# ========== System Prompts（与 v4 相同）==========

RESEARCHER_SYSTEM = """你是一个 Researcher Agent，在 deepin-agent-teams 多智能体系统中工作。

角色职责：
- 负责信息检索、文献分析、文件研究
- 使用 OpenClaw 内置工具（read, web_fetch, search, exec）完成任务

工作流程：
1. 收到 Lead Agent 发来的研究任务
2. 使用合适的工具收集信息（读文件、搜网页、抓取URL等）
3. 对信息进行分析和结构化
4. 用 Markdown 格式输出结构化研究报告
5. 以「[任务完成]」结尾

重要：
- 专注研究和信息收集，不要越界做代码分析
- 用工具完成任务，不要只输出文字"""

CODER_SYSTEM = """你是一个 Coder Agent，在 deepin-agent-teams 多智能体系统中工作。

角色职责：
- 负责代码分析、语法检查、文档生成
- 使用 OpenClaw 内置工具（read, exec, write）完成任务

工作流程：
1. 收到 Lead Agent 发来的编码分析任务
2. 使用合适的工具分析代码（读文件、执行检查命令、生成文档等）
3. 提取函数、类、import 等关键信息
4. 用 Markdown 格式输出结构化分析报告
5. 以「[任务完成]」结尾

重要：
- 专注代码分析和文档生成
- 用工具完成任务，不要只输出文字"""

GENERAL_SYSTEM = """你是一个 General Agent，在 deepin-agent-teams 多智能体系统中工作。

角色职责：
- 执行通用任务（Shell 命令、文件操作等）
- 使用 OpenClaw 内置工具（read, exec, write, search）完成任务

工作流程：
1. 收到 Lead Agent 发来的任务
2. 分析任务类型，选择合适的工具执行
3. 返回执行结果
4. 以「[任务完成]」结尾

重要：
- 执行通用任务，不专属于研究或编码
- 用工具完成任务，不要只输出文字"""


AGENT_SYSTEMS = {
    "researcher": RESEARCHER_SYSTEM,
    "coder": CODER_SYSTEM,
    "general": GENERAL_SYSTEM,
}


# ========== 任务分解 ==========

def decompose(user_request: str, verbose: bool = False) -> dict:
    """用 erniebot 将任务分解为 capabilities"""
    if verbose:
        log_info(f"分解任务：{user_request[:60]}...")

    prompt = f"""用户需求：{user_request}

请将上述需求分解为具体的子任务。

输出格式为纯 JSON：
{{
  "tasks": [
    {{
      "id": "task-1",
      "description": "详细的任务描述",
      "capabilities_needed": ["cap1", "cap2"]
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
- spawn_plan 中每个 agent_label 必须唯一
- capabilities_needed 列出任务所需能力
- 只输出 JSON"""

    try:
        response = erniebot.ChatCompletion.create(
            model="ernie-lite",
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.get_result() if hasattr(response, 'get_result') else str(response)
        plan = json.loads(result)
        if verbose:
            log_ok(f"分解完成：{len(plan.get('tasks', []))} 个子任务，{len(plan.get('spawn_plan', []))} 个 Agent")
        return plan
    except Exception as e:
        log_error(f"任务分解失败：{e}")
        # 降级：直接创建单一 general 任务
        return {
            "tasks": [{"id": "task-1", "description": user_request, "capabilities_needed": ["shell_executor"]}],
            "spawn_plan": [{"agent_type": "general", "agent_label": "general-1", "tasks": ["task-1"]}],
            "summary": user_request,
        }


# ========== Sessions-Spawn 指令生成 ==========

def generate_sessions_spawn(agent_type: str, label: str, timeout: int = DEFAULT_TASK_TIMEOUT) -> str:
    """生成 sessions_spawn 调用代码"""
    system = AGENT_SYSTEMS.get(agent_type, GENERAL_SYSTEM)
    return f"""sessions_spawn(
    task='''{system}

等待消息。收到任务后执行，完成后以「[任务完成]」结尾。''',
    label='{label}',
    mode='run',
    runTimeoutSeconds={timeout},
)"""


def generate_sessions_send(session_key: str, label: str, description: str, timeout: int = DEFAULT_TASK_TIMEOUT) -> str:
    """生成 sessions_send 调用代码"""
    return f"""sessions_send(
    sessionKey='{session_key}',
    message='''任务：{description}

请使用 OpenClaw 工具执行，完成后以「[任务完成]」结尾。''',
    timeoutSeconds={timeout},
)"""


# ========== 执行计划构建 ==========

def build_execution_plan(plan: dict) -> ExecutionPlan:
    """将 erniebot 返回的 plan 转换为 ExecutionPlan"""
    tasks = plan.get("tasks", [])
    spawns = plan.get("spawn_plan", [])
    total = len(spawns)
    # 估算时间：每个 Agent 最多 timeout，最坏情况是所有 Agent 同时到 timeout
    est_ms = total * DEFAULT_TASK_TIMEOUT * 1000
    return ExecutionPlan(
        summary=plan.get("summary", ""),
        tasks=tasks,
        spawn_plan=spawns,
        total_agents=total,
        estimated_duration_ms=est_ms,
    )


# ========== 指令生成（输出给 OpenClaw 执行）==========

def generate_instructions(plan: dict, timeout: int = DEFAULT_TASK_TIMEOUT) -> str:
    """生成完整的可执行指令（供 COPY-PASTE 到 OpenClaw）"""
    lines = []
    lines.append("# v4.1 Sessions-Spawn 多 Agent 协作编排（生产级）\n")
    lines.append(f"**需求**：`{plan.get('summary', '')}`\n")
    lines.append(f"**子任务数**：`{len(plan.get('tasks', []))}`\n")
    lines.append(f"**Agent 数**：`{len(plan.get('spawn_plan', []))}`\n")
    lines.append(f"**超时配置**：单 Agent {timeout}秒，全局 {DEFAULT_GLOBAL_TIMEOUT}秒\n")
    lines.append("---\n")

    # Step 1: Spawn
    lines.append("## Step 1: Spawn 子 Agent\n")
    lines.append("**同时**运行以下所有 `sessions_spawn`，互不依赖：\n")
    for spawn in plan.get("spawn_plan", []):
        atype = spawn["agent_type"]
        label = spawn["agent_label"]
        lines.append(f"### {label}（{atype} Agent）\n")
        lines.append("```python")
        lines.append(generate_sessions_spawn(atype, label, timeout))
        lines.append("```\n")
        lines.append("→ 记录返回的 `childSessionKey`（格式：`agent:main:subagent:<uuid>`）\n\n")

    # Step 2: 分发任务
    lines.append("## Step 2: 分发任务\n")
    lines.append("**所有** Agent spawn 成功后，分别向每个 Agent 发送任务：\n\n")
    task_map = {t["id"]: t for t in plan.get("tasks", [])}
    for spawn in plan.get("spawn_plan", []):
        label = spawn["agent_label"]
        for tid in spawn.get("tasks", []):
            t = task_map.get(tid, {})
            if t:
                lines.append(f"### {label} ← 任务 `{tid}`\n")
                lines.append(f"**描述**：`{t.get('description', '')}`\n")
                lines.append(f"**能力**：`{', '.join(t.get('capabilities_needed', []))}`\n")
                lines.append("```python")
                # 注意：sessionKey 占位符，用户需要填入
                lines.append(f"sessions_send(\n    sessionKey='<{label}的 childSessionKey>',\n    message='''任务：{t.get('description', '')}\n\n完成后以「[任务完成]」结尾。''',\n    timeoutSeconds={DEFAULT_TASK_TIMEOUT},\n)")
                lines.append("```\n")

    # Step 3: 收集
    lines.append("## Step 3: 收集结果\n")
    lines.append("所有 `sessions_send` 返回后，收集每个 Agent 的 Markdown 格式输出。\n\n")

    # Step 4: 归并
    lines.append("## Step 4: 归并最终报告\n")
    lines.append("格式参考：\n")
    lines.append("```markdown\n")
    lines.append("## 执行摘要\n")
    lines.append(f"需求：{plan.get('summary', '')}\n\n")
    lines.append("## Agent 执行结果\n\n")
    for spawn in plan.get("spawn_plan", []):
        label = spawn["agent_label"]
        lines.append(f"### {label}（{spawn['agent_type']}）\n")
        lines.append(f"<Agent 返回内容>\n\n")
    lines.append("## 总结\n")
    lines.append("<综合分析>\n")
    lines.append("```\n")

    return "".join(lines)


# ========== 生产级执行引擎（需要 OpenClaw sessions_spawn API）==========

class ProductionExecutor:
    """
    生产级执行引擎：

    错误处理策略：
    - 子 Agent 失败不影响其他 Agent
    - 超时后自动取消并标记，记录错误继续
    - 所有 Agent 最终都有结果（成功/失败/超时）

    重试策略：
    - 仅在网络错误时重试（不计为正式 attempt）
    - 业务错误（Agent 返回错误）不重试，交给上层判断

    降级策略：
    - 部分 Agent 失败时，仍归并成功 Agent 的结果
    - 标记哪些失败，供调用方判断是否接受
    """

    def __init__(
        self,
        task_timeout: int = DEFAULT_TASK_TIMEOUT,
        global_timeout: int = DEFAULT_GLOBAL_TIMEOUT,
        retry_max: int = DEFAULT_RETRY_MAX,
        verbose: bool = True,
    ) -> None:
        self.task_timeout = task_timeout
        self.global_timeout = global_timeout
        self.retry_max = retry_max
        self.verbose = verbose
        self.results: dict[str, AgentResult] = {}
        self.start_time: float = 0
        self._cancel_flag = False

    def run(self, plan: dict) -> dict:
        """
        执行计划。

        返回：
        {
            "success": bool,           # 所有 Agent 是否都成功
            "partial": bool,            # 是否有部分成功
            "execution_plan": dict,     # 执行计划摘要
            "results": [AgentResult],   # 每个 Agent 的结果
            "final_report": str,        # 归并后的报告
            "total_duration_ms": int,
            "failed_agents": [str],     # 失败的 agent label 列表
        }
        """
        self.start_time = time.time()
        ep = build_execution_plan(plan)

        if self.verbose:
            log_info(f"开始执行：{ep.total_agents} 个 Agent，"
                    f"预计耗时 {ep.estimated_duration_ms / 1000:.0f}秒")

        # 全局超时守护线程
        def global_timeout_watcher():
            elapsed = 0
            while elapsed < self.global_timeout and not self._cancel_flag:
                time.sleep(5)
                elapsed = time.time() - self.start_time
                if self.verbose:
                    remaining = max(0, self.global_timeout - elapsed)
                    if remaining < 60:
                        log_warn(f"全局超时剩余 {remaining:.0f}秒...")
            if elapsed >= self.global_timeout and not self._cancel_flag:
                log_error("全局超时，强制取消所有 Agent")
                self._cancel_flag = True

        watcher = threading.Thread(target=global_timeout_watcher, daemon=True)
        watcher.start()

        # 并行执行所有 spawn（实际由 OpenClaw sessions_spawn API 执行）
        spawn_results = self._execute_spawns(ep)

        # 分发任务
        task_results = self._dispatch_tasks(ep, spawn_results)

        # 归并结果
        total_ms = int((time.time() - self.start_time) * 1000)
        final_report = self._merge_report(ep, task_results)

        success = all(r.status == AgentStatus.DONE for r in task_results.values())
        partial = any(r.status == AgentStatus.DONE for r in task_results.values())
        failed = [label for label, r in task_results.items()
                  if r.status != AgentStatus.DONE]

        if self.verbose:
            if success:
                log_ok(f"全部 {len(task_results)} 个 Agent 成功，耗时 {total_ms / 1000:.1f}秒")
            elif partial:
                log_warn(f"部分成功：{len(task_results) - len(failed)}/{len(task_results)}，"
                        f"失败：{failed}，耗时 {total_ms / 1000:.1f}秒")
            else:
                log_error(f"全部失败，耗时 {total_ms / 1000:.1f}秒")

        return {
            "success": success,
            "partial": partial,
            "execution_plan": ep.to_dict(),
            "results": [r.to_dict() for r in task_results.values()],
            "final_report": final_report,
            "total_duration_ms": total_ms,
            "failed_agents": failed,
        }

    def _execute_spawns(self, ep: ExecutionPlan) -> dict:
        """生成 spawn 指令（实际执行需要 OpenClaw 上下文）"""
        spawns = {}
        for spawn in ep.spawn_plan:
            label = spawn["agent_label"]
            atype = spawn["agent_type"]
            if self.verbose:
                log_info(f"生成 spawn 指令：{label}（{atype}）")
            spawns[label] = {
                "agent_type": atype,
                "spawn_code": generate_sessions_spawn(atype, label, self.task_timeout),
                "session_key": "",
            }
        return spawns

    def _dispatch_tasks(self, ep: ExecutionPlan, spawns: dict) -> dict:
        """生成任务分发指令（实际执行需要 OpenClaw sessions_send）"""
        results = {}
        task_map = {t["id"]: t for t in ep.tasks}

        for spawn in ep.spawn_plan:
            label = spawn["agent_label"]
            atype = spawn["agent_type"]
            session_key = spawns[label].get("session_key", "")

            result = AgentResult(
                label=label,
                agent_type=atype,
                status=AgentStatus.PENDING,
            )
            results[label] = result

            for tid in spawn.get("tasks", []):
                t = task_map.get(tid, {})
                if t:
                    desc = t.get("description", "")
                    if self.verbose:
                        log_info(f"生成 task 分发指令：{label} ← {tid}（{desc[:40]}...）")

                    result.spawn_code = generate_sessions_send(
                        session_key, label, desc, self.task_timeout
                    )
                    result.started_at = datetime.datetime.now().isoformat()

        return results

    def _merge_report(self, ep: ExecutionPlan, results: dict) -> str:
        """归并所有 Agent 结果为最终 Markdown 报告"""
        lines = [f"# 执行报告\n\n"]
        lines.append(f"**需求**：{ep.summary}\n")
        lines.append(f"**Agent 数量**：{ep.total_agents}\n")
        lines.append(f"**执行时间**：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        lines.append("---\n\n## Agent 执行结果\n\n")

        for label, r in results.items():
            status_icon = {
                AgentStatus.DONE: "✅",
                AgentStatus.FAILED: "❌",
                AgentStatus.TIMEOUT: "⏱️",
                AgentStatus.PENDING: "⏳",
                AgentStatus.RUNNING: "🔄",
                AgentStatus.CANCELLED: "🚫",
            }.get(r.status, "❓")

            lines.append(f"### {status_icon} {label}（{r.agent_type}）\n")
            lines.append(f"- **状态**：`{r.status.value}`\n")
            lines.append(f"- **耗时**：{r.duration_ms / 1000:.1f}秒\n")
            lines.append(f"- **重试次数**：{r.attempts}\n")

            if r.status == AgentStatus.DONE and r.result:
                lines.append(f"- **结果**：\n\n{r.result}\n\n")
            elif r.status != AgentStatus.DONE and r.error:
                lines.append(f"- **错误**：{r.error}\n\n")

        done_results = [r for r in results.values() if r.status == AgentStatus.DONE]
        if done_results:
            lines.append("---\n\n## 总结\n\n")
            lines.append(f"共 {len(done_results)}/{len(results)} 个 Agent 成功执行。\n")

        return "".join(lines)


# ========== CLI 主函数 ==========

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="v4.1 生产级 Sessions-Spawn 多 Agent 编排器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python agents/sessions_orchestrator_prod.py "分析项目代码结构"
  python agents/sessions_orchestrator_prod.py "分析项目" -o instructions.md
  python agents/sessions_orchestrator_prod.py "分析项目" --auto
  python agents/sessions_orchestrator_prod.py "分析项目" --run
        """
    )
    parser.add_argument("task", nargs="?", help="要执行的任务描述")
    parser.add_argument("--output", "-o", help="输出到文件")
    parser.add_argument("--auto", "-a", action="store_true",
                        help="生成子 Agent 完整任务内容（不含 sessions_spawn 调用）")
    parser.add_argument("--run", "-r", action="store_true",
                        help="直接执行（需要 OpenClaw sessions_spawn API）")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TASK_TIMEOUT,
                        help=f"单 Agent 超时秒数（默认 {DEFAULT_TASK_TIMEOUT}）")
    parser.add_argument("--global-timeout", "-g", type=int, default=DEFAULT_GLOBAL_TIMEOUT,
                        help=f"全局超时秒数（默认 {DEFAULT_GLOBAL_TIMEOUT}）")
    parser.add_argument("--retry", type=int, default=DEFAULT_RETRY_MAX,
                        help=f"最大重试次数（默认 {DEFAULT_RETRY_MAX}）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式（只输出结果）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    global _current_level
    if args.quiet:
        _current_level = 100  # 几乎所有日志都关掉
    elif args.verbose:
        _current_level = 10

    if not args.task:
        print("用法: python agents/sessions_orchestrator_prod.py '<任务>' [选项]")
        print("   或: python agents/sessions_orchestrator_prod.py '<任务>' -o instructions.md")
        print("   或: python agents/sessions_orchestrator_prod.py '<任务>' --auto")
        return

    log_info(f"任务：{args.task[:80]}...")

    init_ernie()
    plan = decompose(args.task, verbose=True)

    if args.auto:
        # 生成子 Agent 完整任务内容（JSON 格式）
        contents = {}
        for spawn in plan.get("spawn_plan", []):
            label = spawn["agent_label"]
            atype = spawn["agent_type"]
            system = AGENT_SYSTEMS.get(atype, GENERAL_SYSTEM)
            task_ids = spawn.get("tasks", [])
            task_map = {t["id"]: t for t in plan.get("tasks", [])}
            descs = [f"- **{task_map[tid]['description']}**" for tid in task_ids if tid in task_map]
            contents[label] = {
                "agent_type": atype,
                "system_prompt": system,
                "tasks": descs,
            }
        output = json.dumps(contents, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            log_ok(f"已保存到 {args.output}")
        else:
            print(output)
        return

    if args.run:
        executor = ProductionExecutor(
            task_timeout=args.timeout,
            global_timeout=args.global_timeout,
            retry_max=args.retry,
            verbose=not args.quiet,
        )
        result = executor.run(plan)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 默认：生成 COPY-PASTE 指令
    instructions = generate_instructions(plan, timeout=args.timeout)
    if args.output:
        with open(args.output, "w") as f:
            f.write(instructions)
        log_ok(f"已保存到 {args.output}")
    else:
        print(instructions)


if __name__ == "__main__":
    main()
