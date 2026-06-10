#!/usr/bin/env python3
"""
agents/planner.py - Plan-and-Solve 规划模块

核心设计原则（来自 W3 Agent 架构课程）：
1. 先列计划再执行 — Plan-and-Solve 策略
2. TodoManager 跟踪每步进度 — [ ] 待办 → [>] 进行中 → [x] 已完成
3. Nag Reminder — 连续 N 轮无进展则注入提醒
4. 计划可修订 — 执行中发现新信息可以 plan revision

使用方式：
    planner = Planner(model_router=router)
    plan = planner.create_plan("分析项目代码结构", context="...")
    todo = TodoManager(plan)

    # 每轮执行前
    current = todo.current_step()
    # 执行完毕后
    todo.mark_done(step_id)

    # 检查 nag
    if todo.should_nag():
        inject_reminder(todo.nag_message())
"""
import json
import os
import sys
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
sys.path.insert(0, AGENT_DIR)


# ============================================================
# TodoItem — 单个步骤
# ============================================================

class TodoStatus(Enum):
    PENDING = "pending"        # [ ] 待办
    IN_PROGRESS = "in_progress"  # [>] 进行中
    DONE = "done"              # [x] 已完成
    SKIPPED = "skipped"        # [-] 跳过（不再需要）


@dataclass
class TodoItem:
    """单个计划步骤"""
    id: str = field(default_factory=lambda: f"step-{uuid.uuid4().hex[:6]}")
    description: str = ""
    status: TodoStatus = TodoStatus.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result_summary: str = ""  # 执行完毕后的简短结果
    dependencies: List[str] = field(default_factory=list)  # 依赖的步骤 id

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result_summary": self.result_summary,
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TodoItem":
        return cls(
            id=d.get("id", ""),
            description=d.get("description", ""),
            status=TodoStatus(d.get("status", "pending")),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            result_summary=d.get("result_summary", ""),
            dependencies=d.get("dependencies", []),
        )


# ============================================================
# TaskPlan — 完整计划
# ============================================================

@dataclass
class TaskPlan:
    """任务执行计划"""
    plan_id: str = field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    task_description: str = ""
    steps: List[TodoItem] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    revised_at: Optional[float] = None
    revision_count: int = 0
    reasoning: str = ""  # 规划推理过程

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "task_description": self.task_description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "revised_at": self.revised_at,
            "revision_count": self.revision_count,
            "reasoning": self.reasoning,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "TaskPlan":
        return cls(
            plan_id=d.get("plan_id", ""),
            task_description=d.get("task_description", ""),
            steps=[TodoItem.from_dict(s) for s in d.get("steps", [])],
            created_at=d.get("created_at", 0),
            revised_at=d.get("revised_at"),
            revision_count=d.get("revision_count", 0),
            reasoning=d.get("reasoning", ""),
        )


# ============================================================
# TodoManager — 进度跟踪 + Nag Reminder
# ============================================================

# 连续无进展轮数阈值
NAG_THRESHOLD = 3
# 规划超时（秒）
PLAN_TIMEOUT = 30


class TodoManager:
    """
    进度管理器

    跟踪计划中每步的状态，提供 nag reminder 能力。
    """

    def __init__(self, plan: TaskPlan):
        self.plan = plan
        self._steps = {s.id: s for s in plan.steps}
        self._current_step_id: Optional[str] = None
        self._stalled_rounds: int = 0  # 连续无进展轮数
        self._last_progress_round: int = 0  # 最后有进展的轮次
        self._round: int = 0  # 当前轮次

    @property
    def total_steps(self) -> int:
        return len(self.plan.steps)

    @property
    def done_count(self) -> int:
        return sum(1 for s in self._steps.values() if s.status == TodoStatus.DONE)

    @property
    def progress(self) -> float:
        """完成百分比 0.0 ~ 1.0"""
        if self.total_steps == 0:
            return 1.0
        return self.done_count / self.total_steps

    def current_step(self) -> Optional[TodoItem]:
        """获取当前进行中的步骤"""
        if self._current_step_id:
            return self._steps.get(self._current_step_id)
        # 自动找到第一个 pending 步骤
        for step in self.plan.steps:
            if step.status == TodoStatus.PENDING:
                return step
        return None

    def start_step(self, step_id: str) -> bool:
        """开始执行某步骤"""
        step = self._steps.get(step_id)
        if not step:
            return False
        # 检查依赖是否完成
        for dep_id in step.dependencies:
            dep = self._steps.get(dep_id)
            if dep and dep.status != TodoStatus.DONE:
                print(f"[Planner] 步骤 {step_id} 的依赖 {dep_id} 未完成")
                return False
        step.status = TodoStatus.IN_PROGRESS
        step.started_at = time.time()
        self._current_step_id = step_id
        return True

    def mark_done(self, step_id: str, result_summary: str = "") -> bool:
        """标记步骤完成"""
        step = self._steps.get(step_id)
        if not step:
            return False
        step.status = TodoStatus.DONE
        step.completed_at = time.time()
        step.result_summary = result_summary
        self._current_step_id = None
        # 有进展，重置 nag 计数
        self._stalled_rounds = 0
        self._last_progress_round = self._round
        return True

    def mark_skipped(self, step_id: str, reason: str = "") -> bool:
        """标记步骤跳过"""
        step = self._steps.get(step_id)
        if not step:
            return False
        step.status = TodoStatus.SKIPPED
        step.completed_at = time.time()
        step.result_summary = reason or "skipped"
        self._current_step_id = None
        return True

    def advance_round(self) -> None:
        """推进一轮（每轮执行前调用）"""
        self._round += 1
        # 检查是否有进展
        if self._round - self._last_progress_round > 0:
            self._stalled_rounds = self._round - self._last_progress_round

    def should_nag(self) -> bool:
        """是否应该注入 nag reminder"""
        return self._stalled_rounds >= NAG_THRESHOLD

    def nag_message(self) -> str:
        """生成 nag reminder 消息"""
        current = self.current_step()
        step_desc = current.description if current else "未知步骤"
        return (
            f"⚠️ 你已经连续 {self._stalled_rounds} 轮没有推进任务了。\n"
            f"当前步骤: {step_desc}\n"
            f"进度: {self.done_count}/{self.total_steps} ({self.progress:.0%})\n"
            f"请立即采取行动推进任务，或者跳过当前步骤继续下一步。"
        )

    def all_done(self) -> bool:
        """所有步骤是否都已完成或跳过"""
        return all(
            s.status in (TodoStatus.DONE, TodoStatus.SKIPPED)
            for s in self._steps.values()
        )

    def summary(self) -> str:
        """生成进度摘要"""
        lines = [f"计划: {self.plan.task_description}"]
        lines.append(f"进度: {self.done_count}/{self.total_steps} ({self.progress:.0%})")
        lines.append("步骤:")
        for s in self.plan.steps:
            icon = {
                TodoStatus.PENDING: "[ ]",
                TodoStatus.IN_PROGRESS: "[>]",
                TodoStatus.DONE: "[x]",
                TodoStatus.SKIPPED: "[-]",
            }[s.status]
            lines.append(f"  {icon} {s.description}")
            if s.result_summary and s.status == TodoStatus.DONE:
                lines.append(f"       → {s.result_summary}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "plan": self.plan.to_dict(),
            "current_step_id": self._current_step_id,
            "stalled_rounds": self._stalled_rounds,
            "round": self._round,
            "progress": self.progress,
        }


# ============================================================
# Planner — 计划生成器
# ============================================================

# Prompt 加载器（热加载支持）
try:
    from prompt_loader import get_loader
except ImportError:
    get_loader = None

# 向后兼容：保留旧常量，但优先从 PromptLoader 加载
def _get_plan_system_prompt() -> str:
    """获取 planner system prompt（优先从文件加载）"""
    if get_loader is not None:
        loader = get_loader()
        content = loader.render("planner/plan_generation")
        if content and "不存在" not in content:
            return content
    # 降级：使用硬编码
    return PLAN_SYSTEM_PROMPT

PLAN_SYSTEM_PROMPT = """你是一个任务规划专家。给定一个任务描述，你需要将其拆解为可执行的步骤列表。

输出格式要求（严格 JSON）：
```json
{
  "reasoning": "简要说明你的规划思路",
  "steps": [
    {"description": "步骤1描述", "dependencies": []},
    {"description": "步骤2描述", "dependencies": ["step-1"]},
    {"description": "步骤3描述", "dependencies": ["step-2"]}
  ]
}
```

规则：
1. 每个步骤应该是独立可执行的原子操作
2. 步骤数控制在 1~7 步之间
3. 使用 dependencies 字段标注步骤间的依赖关系（引用步骤的 id）
4. 步骤描述要具体、可验证，不要模糊
5. 只输出 JSON，不要多余文字"""


class Planner:
    """
    计划生成器

    通过 LLM 调用生成结构化执行计划。
    """

    def __init__(self, model_router=None):
        """
        Args:
            model_router: 模型路由器实例（model_router.py 中的 ModelRouter）
        """
        self.model_router = model_router

    def create_plan(self, task_description: str, context: str = "") -> TaskPlan:
        """
        为任务生成执行计划

        Args:
            task_description: 任务描述
            context: 额外上下文信息（可选）

        Returns:
            TaskPlan 实例
        """
        prompt = f"任务: {task_description}"
        if context:
            prompt += f"\n\n上下文: {context}"

        # 尝试用 LLM 生成计划
        plan_data = None
        if self.model_router:
            try:
                plan_data = self._call_llm(prompt)
            except Exception as e:
                print(f"[Planner] LLM 调用失败，使用默认计划: {e}")

        # 降级：使用默认计划
        if plan_data is None:
            plan_data = self._default_plan(task_description)

        # 构建 TaskPlan
        steps = []
        for i, step_data in enumerate(plan_data.get("steps", [])):
            step_id = f"step-{i+1}"
            step = TodoItem(
                id=step_id,
                description=step_data.get("description", f"步骤 {i+1}"),
                dependencies=step_data.get("dependencies", []),
            )
            steps.append(step)

        # 修正依赖引用（LLM 可能用 "step-1" 或 "步骤1" 等格式）
        for step in steps:
            fixed_deps = []
            for dep in step.dependencies:
                # 尝试解析各种格式
                if dep in [s.id for s in steps]:
                    fixed_deps.append(dep)
                elif dep.startswith("step-"):
                    # "step-1" → "step-1"
                    if dep in [s.id for s in steps]:
                        fixed_deps.append(dep)
                else:
                    # 尝试提取数字
                    import re
                    m = re.search(r'(\d+)', dep)
                    if m:
                        candidate = f"step-{m.group(1)}"
                        if candidate in [s.id for s in steps]:
                            fixed_deps.append(candidate)
            step.dependencies = fixed_deps

        plan = TaskPlan(
            task_description=task_description,
            steps=steps,
            reasoning=plan_data.get("reasoning", ""),
        )
        print(f"[Planner] 生成计划: {len(steps)} 步")
        return plan

    def revise_plan(self, todo_manager: TodoManager, new_info: str) -> TaskPlan:
        """
        修订计划（执行中发现新信息时）

        Args:
            todo_manager: 当前进度管理器
            new_info: 新发现的信息

        Returns:
            修订后的 TaskPlan
        """
        # 保留已完成的步骤，重新规划未完成的
        done_steps = [
            s for s in todo_manager.plan.steps
            if s.status in (TodoStatus.DONE, TodoStatus.SKIPPED)
        ]
        remaining_desc = [
            s.description for s in todo_manager.plan.steps
            if s.status == TodoStatus.PENDING
        ]

        prompt = (
            f"原任务: {todo_manager.plan.task_description}\n"
            f"已完成步骤: {[s.description for s in done_steps]}\n"
            f"待完成步骤: {remaining_desc}\n"
            f"新信息: {new_info}\n\n"
            f"请基于新信息，重新规划剩余步骤。只输出未完成的步骤。"
        )

        plan_data = None
        if self.model_router:
            try:
                plan_data = self._call_llm(prompt)
            except Exception as e:
                print(f"[Planner] 修订计划 LLM 调用失败: {e}")

        if plan_data is None:
            # 降级：保持原计划
            return todo_manager.plan

        # 构建修订后的计划
        new_steps = list(done_steps)  # 保留已完成的
        offset = len(done_steps)
        for i, step_data in enumerate(plan_data.get("steps", [])):
            step = TodoItem(
                id=f"step-{offset + i + 1}",
                description=step_data.get("description", f"步骤 {offset + i + 1}"),
                dependencies=step_data.get("dependencies", []),
            )
            new_steps.append(step)

        revised_plan = TaskPlan(
            plan_id=todo_manager.plan.plan_id,
            task_description=todo_manager.plan.task_description,
            steps=new_steps,
            created_at=todo_manager.plan.created_at,
            revised_at=time.time(),
            revision_count=todo_manager.plan.revision_count + 1,
            reasoning=plan_data.get("reasoning", ""),
        )
        print(f"[Planner] 计划修订: {len(done_steps)} 步已完成 + {len(new_steps) - len(done_steps)} 步新规划")
        return revised_plan

    def _call_llm(self, prompt: str) -> dict:
        """调用 LLM 生成计划"""
        from model_router import ModelRouter

        router = self.model_router
        if router is None:
            router = ModelRouter()

        messages = [
            {"role": "system", "content": _get_plan_system_prompt()},
            {"role": "user", "content": prompt},
        ]

        response = router.chat(
            messages=messages,
            task_type="light",  # 规划用轻量模型
            temperature=0.3,    # 低温度，确定性输出
        )

        content = response.get("content", "")

        # 提取 JSON
        import re
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            json_str = content.strip()

        return json.loads(json_str)

    def _default_plan(self, task_description: str) -> dict:
        """降级默认计划"""
        return {
            "reasoning": "LLM 不可用，使用默认两步计划",
            "steps": [
                {"description": f"分析任务需求: {task_description}", "dependencies": []},
                {"description": "执行任务并输出结果", "dependencies": ["step-1"]},
            ],
        }


# ========== 单元测试 ==========

def _test():
    """Planner 模块测试"""
    print("\n=== Planner 单元测试 ===\n")

    # Test 1: TodoItem 创建和状态转换
    print("Test 1: TodoItem 基本操作")
    item = TodoItem(id="step-1", description="分析代码结构")
    assert item.status == TodoStatus.PENDING
    item.status = TodoStatus.IN_PROGRESS
    item.started_at = time.time()
    assert item.status == TodoStatus.IN_PROGRESS
    item.status = TodoStatus.DONE
    item.completed_at = time.time()
    assert item.status == TodoStatus.DONE
    print("  ✅ PASS\n")

    # Test 2: TodoManager 基本操作
    print("Test 2: TodoManager 步骤管理")
    plan = TaskPlan(
        task_description="测试任务",
        steps=[
            TodoItem(id="step-1", description="步骤一"),
            TodoItem(id="step-2", description="步骤二", dependencies=["step-1"]),
            TodoItem(id="step-3", description="步骤三", dependencies=["step-2"]),
        ],
    )
    todo = TodoManager(plan)
    assert todo.total_steps == 3
    assert todo.done_count == 0
    assert todo.progress == 0.0
    assert not todo.all_done()

    # 开始第一步
    current = todo.current_step()
    assert current.id == "step-1"
    todo.start_step("step-1")
    assert current.status == TodoStatus.IN_PROGRESS

    # 完成第一步
    todo.mark_done("step-1", "分析完成")
    assert todo.done_count == 1
    assert todo.progress == 1/3
    print("  ✅ PASS\n")

    # Test 3: 依赖检查
    print("Test 3: 依赖检查")
    # step-2 依赖 step-1（已完成），可以开始
    ok = todo.start_step("step-2")
    assert ok == True

    # step-3 依赖 step-2（未完成），不能开始
    ok = todo.start_step("step-3")
    assert ok == False
    print("  ✅ PASS\n")

    # Test 4: Nag Reminder
    print("Test 4: Nag Reminder")
    plan2 = TaskPlan(
        task_description="卡住的任务",
        steps=[
            TodoItem(id="step-1", description="会卡住的步骤"),
        ],
    )
    todo2 = TodoManager(plan2)
    todo2.start_step("step-1")

    # 模拟 3 轮无进展
    for i in range(3):
        todo2.advance_round()
    assert todo2.should_nag() == True
    msg = todo2.nag_message()
    assert "连续" in msg
    assert "3 轮" in msg
    print("  ✅ PASS\n")

    # Test 5: 进展重置 nag 计数
    print("Test 5: 进展重置 nag")
    todo2.mark_done("step-1")
    assert todo2.should_nag() == False
    print("  ✅ PASS\n")

    # Test 6: all_done
    print("Test 6: all_done 检查")
    todo.mark_done("step-2", "完成")
    assert not todo.all_done()
    todo.mark_done("step-3", "完成")
    assert todo.all_done()
    print("  ✅ PASS\n")

    # Test 7: summary
    print("Test 7: summary 输出")
    summary = todo.summary()
    assert "测试任务" in summary
    assert "[x]" in summary
    print("  ✅ PASS\n")

    # Test 8: 序列化/反序列化
    print("Test 8: 序列化")
    d = todo.to_dict()
    assert d["progress"] == 1.0
    assert d["plan"]["steps"][0]["status"] == "done"
    print("  ✅ PASS\n")

    # Test 9: 默认计划
    print("Test 9: 默认降级计划")
    planner = Planner(model_router=None)
    plan3 = planner.create_plan("测试任务")
    assert len(plan3.steps) == 2
    assert "分析" in plan3.steps[0].description
    print("  ✅ PASS\n")

    print("=== 所有 Planner 测试通过 ===\n")


if __name__ == "__main__":
    _test()
