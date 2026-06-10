#!/usr/bin/env python3
"""
agents/context_manager.py — 上下文窗口管理 + 子Agent摘要压缩

核心设计原则：
1. 滑动窗口：保留最近 K 轮完整对话，早期对话压缩为摘要
2. 子Agent摘要回传：Worker 执行完毕后输出压缩的 summary，不注入原始对话
3. Token 计数器：实时跟踪上下文 token 量，超限触发压缩
4. 重要信息提取：entities / decisions / constraints 结构化保留

使用方式：
    ctx = ContextWindow(max_recent_turns=10, max_tokens=4000)
    ctx.add_turn("user", "帮我分析代码")
    ctx.add_turn("assistant", "分析结果如下...")

    # 超过阈值时自动压缩
    messages = ctx.get_messages()  # 返回压缩后的消息列表

    # 子Agent摘要回传
    ctx.add_subagent_summary(summary)
"""

import json
import os
import sys
import time
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import deque

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
sys.path.insert(0, AGENT_DIR)


# ============================================================
# Token 估算器（不依赖 tiktoken，纯 Python 近似）
# ============================================================

def estimate_tokens(text: str) -> int:
    """
    粗略估算文本的 token 数

    规则：
    - 英文：~4 chars per token
    - 中文：~1.5 chars per token（UTF-8 编码）
    - 混合文本：按字符类型分别计算
    """
    if not text:
        return 0
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - cn_chars
    return int(cn_chars / 1.5 + other_chars / 4)


# ============================================================
# 对话轮次
# ============================================================

@dataclass
class Turn:
    """单轮对话"""
    role: str         # "user" / "assistant" / "system" / "subagent_summary"
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    token_count: int = 0
    is_summary: bool = False  # 是否是压缩后的摘要
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = estimate_tokens(self.content)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "is_summary": self.is_summary,
        }


# ============================================================
# 子Agent摘要
# ============================================================

@dataclass
class SubagentSummary:
    """子Agent执行摘要（回传给父上下文）"""
    task_id: str = ""
    conclusion: str = ""           # 最终结论
    key_findings: List[str] = field(default_factory=list)  # 关键发现
    unfinished: List[str] = field(default_factory=list)    # 未完成项
    duration_ms: int = 0           # 耗时
    token_used: int = 0            # 消耗 token
    error: str = ""                # 错误信息（如果有）

    def to_text(self) -> str:
        """序列化为纯文本摘要"""
        parts = [f"[子Agent摘要] task={self.task_id}"]
        if self.conclusion:
            parts.append(f"结论: {self.conclusion}")
        if self.key_findings:
            parts.append(f"关键发现: {'; '.join(self.key_findings[:5])}")
        if self.unfinished:
            parts.append(f"未完成: {'; '.join(self.unfinished[:3])}")
        if self.error:
            parts.append(f"错误: {self.error}")
        parts.append(f"耗时: {self.duration_ms}ms | Token: {self.token_used}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SubagentSummary":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_task_result(cls, task_result: dict) -> "SubagentSummary":
        """从 TaskResult 构造摘要"""
        task_id = task_result.get("task_id", "unknown")
        result = task_result.get("result", {})
        if isinstance(result, str):
            return cls(task_id=task_id, conclusion=result[:500])

        error = task_result.get("error", "")
        if not error and isinstance(result, dict):
            error = result.get("error", "")

        # 提取关键信息
        conclusion = ""
        key_findings = []
        if isinstance(result, dict):
            # 从 summary 字段提取
            conclusion = result.get("summary", "")
            # 从 results 子字段提取
            inner = result.get("results", {})
            if isinstance(inner, dict):
                for cap, data in inner.items():
                    if isinstance(data, dict) and "error" not in data:
                        # 取前 200 字符作为发现
                        text = json.dumps(data, ensure_ascii=False)[:200]
                        key_findings.append(f"{cap}: {text}")
                    elif isinstance(data, dict) and "error" in data:
                        key_findings.append(f"{cap}: ❌ {data['error']}")

        return cls(
            task_id=task_id,
            conclusion=conclusion[:500],
            key_findings=key_findings[:5],
            duration_ms=task_result.get("duration_ms", 0),
            token_used=0,
            error=error,
        )


# ============================================================
# ContextWindow — 滑动窗口 + 压缩
# ============================================================

# 默认参数
DEFAULT_MAX_RECENT_TURNS = 10   # 最近保留的完整轮次
DEFAULT_MAX_TOKENS = 4000       # 上下文 token 上限
DEFAULT_COMPRESS_THRESHOLD = 20 # 超过此轮数触发压缩
DEFAULT_SUMMARY_MAX_TOKENS = 500  # 摘要最大 token 数


class ContextWindow:
    """
    上下文窗口管理器

    核心功能：
    1. 滑动窗口：保留最近 K 轮完整对话
    2. 自动压缩：超过阈值时将早期对话压缩为摘要
    3. 子Agent摘要注入：将子Agent结果以摘要形式注入上下文
    4. Token 计数：实时跟踪上下文 token 量
    """

    def __init__(
        self,
        max_recent_turns: int = DEFAULT_MAX_RECENT_TURNS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        compress_threshold: int = DEFAULT_COMPRESS_THRESHOLD,
        summary_max_tokens: int = DEFAULT_SUMMARY_MAX_TOKENS,
    ):
        self.max_recent_turns = max_recent_turns
        self.max_tokens = max_tokens
        self.compress_threshold = compress_threshold
        self.summary_max_tokens = summary_max_tokens

        self._turns: List[Turn] = []
        self._compressed_summary: str = ""  # 早期对话的压缩摘要
        self._total_tokens: int = 0

        # 结构化重要信息（压缩时提取）
        self._entities: List[str] = []      # 关键实体
        self._decisions: List[str] = []     # 已做出的决定
        self._constraints: List[str] = []   # 约束条件

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def compressed_summary(self) -> str:
        return self._compressed_summary

    def add_turn(self, role: str, content: str, metadata: Dict = None) -> Turn:
        """
        添加一轮对话

        Args:
            role: "user" / "assistant" / "system"
            content: 对话内容
            metadata: 附加元信息

        Returns:
            创建的 Turn 对象
        """
        turn = Turn(role=role, content=content, metadata=metadata or {})
        self._turns.append(turn)
        self._total_tokens += turn.token_count

        # 检查是否需要压缩
        if self._should_compress():
            self._compress()

        return turn

    def add_subagent_summary(self, summary: SubagentSummary) -> Turn:
        """
        注入子Agent摘要

        不注入原始对话，只注入压缩后的摘要。
        """
        text = summary.to_text()
        turn = Turn(
            role="subagent_summary",
            content=text,
            is_summary=True,
            metadata={"task_id": summary.task_id, "source": "subagent"},
        )
        self._turns.append(turn)
        self._total_tokens += turn.token_count
        return turn

    def get_messages(self, include_summary: bool = True) -> List[Dict[str, str]]:
        """
        获取压缩后的消息列表（用于 LLM 调用）

        返回格式：
        [
            {"role": "system", "content": "【上下文摘要】..."},
            {"role": "user", "content": "最近的消息"},
            {"role": "assistant", "content": "最近的回复"},
            ...
        ]
        """
        messages = []

        # 添加压缩摘要（如果有）
        if include_summary and self._compressed_summary:
            summary_content = f"【上下文摘要】\n{self._compressed_summary}"
            if self._entities:
                summary_content += f"\n\n【关键实体】{', '.join(self._entities[:10])}"
            if self._decisions:
                summary_content += f"\n【已做决定】{'; '.join(self._decisions[:5])}"
            if self._constraints:
                summary_content += f"\n【约束条件】{'; '.join(self._constraints[:5])}"
            messages.append({"role": "system", "content": summary_content})

        # 添加最近的完整轮次
        recent_turns = self._turns[-self.max_recent_turns:]
        for turn in recent_turns:
            # subagent_summary 作为 system 消息注入
            msg_role = "system" if turn.role == "subagent_summary" else turn.role
            messages.append({"role": msg_role, "content": turn.content})

        return messages

    def get_token_usage(self) -> Dict[str, Any]:
        """获取 token 使用统计"""
        return {
            "total_tokens": self._total_tokens,
            "turn_count": self.turn_count,
            "compressed_summary_tokens": estimate_tokens(self._compressed_summary),
            "recent_turns_tokens": sum(
                t.token_count for t in self._turns[-self.max_recent_turns:]
            ),
            "max_tokens": self.max_tokens,
            "usage_ratio": self._total_tokens / max(self.max_tokens, 1),
        }

    def is_overflow(self) -> bool:
        """是否超出 token 上限"""
        return self._total_tokens > self.max_tokens

    def reset(self) -> None:
        """重置上下文"""
        self._turns.clear()
        self._compressed_summary = ""
        self._total_tokens = 0
        self._entities.clear()
        self._decisions.clear()
        self._constraints.clear()

    # ========== 内部方法 ==========

    def _should_compress(self) -> bool:
        """判断是否应该触发压缩"""
        # 条件1：轮数超过阈值
        if len(self._turns) > self.compress_threshold:
            return True
        # 条件2：token 超限
        if self._total_tokens > self.max_tokens:
            return True
        return False

    def _compress(self) -> None:
        """
        压缩早期对话

        策略：
        1. 将前 N-K 轮压缩为摘要
        2. 保留最近 K 轮完整对话
        3. 提取关键实体/决定/约束
        """
        if len(self._turns) <= self.max_recent_turns:
            return

        # 分离早期对话和最近对话
        early_turns = self._turns[:-self.max_recent_turns]
        recent_turns = self._turns[-self.max_recent_turns:]

        # 生成早期对话的摘要
        early_text = self._turns_to_text(early_turns)
        new_summary = self._generate_summary(early_text)

        # 合并已有摘要和新摘要
        if self._compressed_summary:
            self._compressed_summary = f"{self._compressed_summary}\n\n{new_summary}"
        else:
            self._compressed_summary = new_summary

        # 摘要截断
        if estimate_tokens(self._compressed_summary) > self.summary_max_tokens:
            self._compressed_summary = self._truncate_to_tokens(
                self._compressed_summary, self.summary_max_tokens
            )

        # 提取结构化信息
        self._extract_structured_info(early_turns)

        # 更新 turns 列表（只保留最近的）
        self._turns = recent_turns

        # 重新计算 token
        self._total_tokens = (
            estimate_tokens(self._compressed_summary)
            + sum(t.token_count for t in self._turns)
        )

        print(f"[ContextManager] 压缩完成: 保留 {len(early_turns)} 轮摘要 + "
              f"{len(recent_turns)} 轮完整对话 (tokens: {self._total_tokens})")

    def _generate_summary(self, text: str) -> str:
        """
        生成摘要（LLM 不可用时的降级方案）

        注入 LLM 需要通过 model_router，这里提供确定性降级。
        """
        # 降级策略：截取前 N 句
        lines = text.strip().split('\n')
        summary_lines = []
        for line in lines[:20]:  # 最多 20 行
            line = line.strip()
            if line and len(line) > 10:
                summary_lines.append(line)
        return '\n'.join(summary_lines[:10]) if summary_lines else "（早期对话已压缩）"

    def _extract_structured_info(self, turns: List[Turn]) -> None:
        """从对话中提取结构化重要信息"""
        for turn in turns:
            content = turn.content.lower()
            # 提取决定（简单规则匹配）
            if any(kw in content for kw in ["决定", "选择", "确认", "方案是", "采用"]):
                decision = turn.content[:100].strip()
                if decision and decision not in self._decisions:
                    self._decisions.append(decision)
            # 提取约束（简单规则匹配）
            if any(kw in content for kw in ["不能", "必须", "要求", "限制", "约束"]):
                constraint = turn.content[:100].strip()
                if constraint and constraint not in self._constraints:
                    self._constraints.append(constraint)

        # 限制数量
        self._decisions = self._decisions[:10]
        self._constraints = self._constraints[:10]

    def _turns_to_text(self, turns: List[Turn]) -> str:
        """将轮次列表转为纯文本"""
        parts = []
        for t in turns:
            parts.append(f"[{t.role}]: {t.content}")
        return "\n".join(parts)

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """截断文本到指定 token 数"""
        current = 0
        for i, char in enumerate(text):
            # 粗略按字符估算
            current += 1.5 if '\u4e00' <= char <= '\u9fff' else 0.25
            if current > max_tokens:
                return text[:i] + "..."
        return text

    def to_dict(self) -> dict:
        return {
            "turn_count": self.turn_count,
            "total_tokens": self._total_tokens,
            "compressed_summary": self._compressed_summary,
            "entities": self._entities,
            "decisions": self._decisions[:3],
            "constraints": self._constraints[:3],
        }


# ============================================================
# 上下文感知的 LLM 调用封装
# ============================================================

class ContextAwareLLM:
    """
    带上下文管理的 LLM 调用封装

    自动注入上下文、管理窗口、压缩历史。
    """

    def __init__(self, model_router=None, max_recent_turns: int = 10, max_tokens: int = 4000):
        self.model_router = model_router
        self.context = ContextWindow(
            max_recent_turns=max_recent_turns,
            max_tokens=max_tokens,
        )

    def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        task_type: str = "default",
        temperature: float = 0.7,
    ) -> str:
        """
        带上下文的 LLM 调用

        自动注入历史消息，管理窗口大小。
        """
        # 添加用户消息到上下文
        self.context.add_turn("user", user_message)

        # 构建消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 注入上下文（含压缩摘要）
        messages.extend(self.context.get_messages(include_summary=True))

        # 调用 LLM
        if self.model_router is None:
            response = "(LLM 不可用，降级为确定性回复)"
        else:
            try:
                result = self.model_router.chat(
                    messages=messages,
                    task_type=task_type,
                    temperature=temperature,
                )
                response = result.get("content", str(result))
            except Exception as e:
                response = f"(LLM 调用失败: {e})"

        # 添加助手回复到上下文
        self.context.add_turn("assistant", response)

        return response

    def inject_subagent_result(self, task_result: dict) -> None:
        """注入子Agent结果（摘要形式）"""
        summary = SubagentSummary.from_task_result(task_result)
        self.context.add_subagent_summary(summary)

    def get_token_usage(self) -> dict:
        return self.context.get_token_usage()


# ========== 单元测试 ==========

def _test():
    """ContextManager 模块测试"""
    print("\n=== ContextManager 单元测试 ===\n")

    # Test 1: 基本添加和获取
    print("Test 1: 基本添加和获取")
    ctx = ContextWindow(max_recent_turns=5, max_tokens=2000)
    ctx.add_turn("user", "你好")
    ctx.add_turn("assistant", "你好！有什么可以帮你的？")
    assert ctx.turn_count == 2
    messages = ctx.get_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    print("  ✅ PASS\n")

    # Test 2: Token 估算
    print("Test 2: Token 估算")
    tokens = estimate_tokens("hello world")
    assert tokens > 0
    cn_tokens = estimate_tokens("你好世界")
    assert cn_tokens > 0
    # 中文每字符 token 数应比英文多
    assert estimate_tokens("你好") > estimate_tokens("hi")
    print("  ✅ PASS\n")

    # Test 3: 子Agent摘要注入
    print("Test 3: 子Agent摘要注入")
    ctx2 = ContextWindow(max_recent_turns=5, max_tokens=2000)
    ctx2.add_turn("user", "帮我分析代码")
    summary = SubagentSummary(
        task_id="task-001",
        conclusion="发现 3 个潜在问题",
        key_findings=["函数 A 缺少异常处理", "变量 B 未使用"],
        duration_ms=1500,
    )
    ctx2.add_subagent_summary(summary)
    messages = ctx2.get_messages()
    assert len(messages) == 2
    assert messages[1]["role"] == "system"  # subagent_summary → system
    assert "task-001" in messages[1]["content"]
    print("  ✅ PASS\n")

    # Test 4: 自动压缩触发
    print("Test 4: 自动压缩触发")
    ctx3 = ContextWindow(max_recent_turns=3, max_tokens=500, compress_threshold=5)
    for i in range(8):
        ctx3.add_turn("user", f"这是第 {i} 轮对话，内容比较短")
        ctx3.add_turn("assistant", f"收到第 {i} 轮，这是回复")
    # 应该触发了压缩
    assert ctx3.compressed_summary != ""
    # 最近的轮次应该保留
    messages = ctx3.get_messages()
    assert len(messages) > 0
    # 应该有摘要
    assert any("摘要" in m.get("content", "") for m in messages)
    print(f"  压缩后: {ctx3.turn_count} 轮, {ctx3.total_tokens} tokens")
    print("  ✅ PASS\n")

    # Test 5: Token 超限压缩
    print("Test 5: Token 超限压缩")
    ctx4 = ContextWindow(max_recent_turns=3, max_tokens=100)
    # 添加大量文本触发压缩
    long_text = "这是一段很长的文本。" * 50
    ctx4.add_turn("user", long_text)
    ctx4.add_turn("assistant", "收到")
    ctx4.add_turn("user", "继续")
    ctx4.add_turn("assistant", "好的")
    # Token 应该在可控范围内
    assert ctx4.total_tokens < 500  # 压缩后应远小于未压缩
    print("  ✅ PASS\n")

    # Test 6: overflow 检测
    print("Test 6: overflow 检测")
    ctx5 = ContextWindow(max_recent_turns=2, max_tokens=10)
    ctx5.add_turn("user", "这是一段比较长的对话内容，用来测试 token 超限的情况")
    assert ctx5.is_overflow() == True
    print("  ✅ PASS\n")

    # Test 7: SubagentSummary 序列化
    print("Test 7: SubagentSummary 序列化/反序列化")
    s = SubagentSummary(
        task_id="t1",
        conclusion="结论",
        key_findings=["发现1", "发现2"],
        duration_ms=100,
    )
    text = s.to_text()
    assert "t1" in text
    assert "结论" in text
    d = s.to_dict()
    s2 = SubagentSummary.from_dict(d)
    assert s2.task_id == "t1"
    assert s2.conclusion == "结论"
    print("  ✅ PASS\n")

    # Test 8: from_task_result
    print("Test 8: 从 TaskResult 构造摘要")
    task_result = {
        "task_id": "task-100",
        "duration_ms": 2000,
        "result": {
            "summary": "代码分析完成",
            "results": {
                "code_analysis": {"lines": 100, "issues": 3},
                "file_read": {"error": "文件不存在"},
            },
        },
    }
    s3 = SubagentSummary.from_task_result(task_result)
    assert s3.task_id == "task-100"
    assert "代码分析" in s3.conclusion
    assert len(s3.key_findings) > 0
    print("  ✅ PASS\n")

    # Test 9: get_token_usage
    print("Test 9: Token 使用统计")
    ctx6 = ContextWindow(max_recent_turns=5, max_tokens=2000)
    ctx6.add_turn("user", "测试")
    usage = ctx6.get_token_usage()
    assert usage["turn_count"] == 1
    assert usage["total_tokens"] > 0
    assert "usage_ratio" in usage
    print("  ✅ PASS\n")

    # Test 10: reset
    print("Test 10: 重置上下文")
    ctx6.reset()
    assert ctx6.turn_count == 0
    assert ctx6.total_tokens == 0
    assert ctx6.compressed_summary == ""
    print("  ✅ PASS\n")

    # Test 11: ContextAwareLLM 降级模式
    print("Test 11: ContextAwareLLM 降级模式")
    cllm = ContextAwareLLM(model_router=None)
    response = cllm.chat("你好")
    assert "LLM 不可用" in response
    assert cllm.context.turn_count == 2  # user + assistant
    print("  ✅ PASS\n")

    print("=== 所有 ContextManager 测试通过 ===\n")


if __name__ == "__main__":
    _test()
