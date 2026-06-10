#!/usr/bin/env python3
"""
agents/debate.py — 辩论模式（Debate Pattern）

核心设计原则：
1. Pro Agent 提出论点
2. Con Agent 反驳
3. Judge（Verifier）最终裁决
4. 适用场景：技术方案选型、架构决策、风险评估

辩论流程：
  Round 1: Pro 论点 → Con 反驳
  Round 2: Pro 回应 → Con 再反驳
  Judge: 基于双方论点做最终决策

使用方式：
    debate = Debate(pro_agent=agent_a, con_agent=agent_b, judge=verifier)
    result = debate.run(topic="用 React 还是 Vue？", context="...")
    print(result.decision)
    print(result.reasoning)
"""

import json
import os
import sys
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
sys.path.insert(0, AGENT_DIR)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class DebateArgument:
    """单条论点"""
    side: str              # "pro" / "con"
    round: int             # 第几轮
    content: str           # 论点内容
    evidence: List[str] = field(default_factory=list)  # 支撑证据
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "side": self.side,
            "round": self.round,
            "content": self.content,
            "evidence": self.evidence,
        }


@dataclass
class DebateResult:
    """辩论结果"""
    topic: str = ""
    decision: str = ""           # 最终决策
    winner: str = ""             # "pro" / "con" / "draw"
    reasoning: str = ""          # 裁决理由
    confidence: float = 0.0      # 置信度 0~1
    rounds: int = 0              # 辩论轮数
    arguments: List[DebateArgument] = field(default_factory=list)  # 所有论点
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "decision": self.decision,
            "winner": self.winner,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "rounds": self.rounds,
            "arguments": [a.to_dict() for a in self.arguments],
            "duration_ms": self.duration_ms,
        }

    def summary(self) -> str:
        """人类可读摘要"""
        lines = [
            f"【辩论结果】{self.topic}",
            f"胜方: {self.winner} | 置信度: {self.confidence:.0%}",
            f"决策: {self.decision}",
            f"理由: {self.reasoning}",
            f"轮数: {self.rounds} | 耗时: {self.duration_ms}ms",
            f"论点数: {len(self.arguments)}",
        ]
        return "\n".join(lines)


# ============================================================
# Agent 接口（可替换）
# ============================================================

class DebateAgent:
    """
    辩论参与者

    可以是 LLM 调用、本地函数、或子 Agent。
    默认使用 LLM 调用。
    """

    def __init__(self, name: str, side: str, model_router=None, system_prompt: str = ""):
        """
        Args:
            name: Agent 名称
            side: "pro" / "con"
            model_router: 模型路由器
            system_prompt: 系统 prompt
        """
        self.name = name
        self.side = side
        self.model_router = model_router
        self.system_prompt = system_prompt or self._default_prompt()

    def _default_prompt(self) -> str:
        if self.side == "pro":
            return (
                "你是正方辩论者。你的任务是支持给定的方案或观点。\n"
                "规则：\n"
                "1. 每个论点必须有明确的支撑理由\n"
                "2. 引用具体事实或数据\n"
                "3. 针对对方的反驳进行回应\n"
                "4. 输出 JSON：{\"content\": \"论点内容\", \"evidence\": [\"证据1\", \"证据2\"]}"
            )
        else:
            return (
                "你是反方辩论者。你的任务是反驳给定的方案或观点。\n"
                "规则：\n"
                "1. 指出方案的缺陷和风险\n"
                "2. 提出替代方案\n"
                "3. 用事实和数据支撑反驳\n"
                "4. 输出 JSON：{\"content\": \"反驳内容\", \"evidence\": [\"证据1\", \"证据2\"]}"
            )

    def argue(self, topic: str, context: str, history: List[DebateArgument]) -> DebateArgument:
        """
        提出论点

        Args:
            topic: 辩论主题
            context: 额外上下文
            history: 之前的论点历史

        Returns:
            DebateArgument
        """
        # 构建消息
        history_text = ""
        if history:
            history_lines = []
            for arg in history[-4:]:  # 只取最近 4 条
                side_label = "正方" if arg.side == "pro" else "反方"
                history_lines.append(f"[{side_label} R{arg.round}]: {arg.content}")
            history_text = "\n".join(history_lines)

        prompt = f"辩论主题: {topic}\n"
        if context:
            prompt += f"背景: {context}\n"
        if history_text:
            prompt += f"\n之前的论点:\n{history_text}\n"
        prompt += f"\n请作为{'正方' if self.side == 'pro' else '反方'}提出你的论点。"

        # LLM 调用
        content = ""
        evidence = []
        if self.model_router:
            try:
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ]
                response = self.model_router.chat(
                    messages=messages,
                    task_type="light",
                    temperature=0.7,
                )
                raw = response.get("content", "")
                # 尝试解析 JSON
                try:
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', raw)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        content = parsed.get("content", raw[:500])
                        evidence = parsed.get("evidence", [])
                    else:
                        content = raw[:500]
                except Exception:
                    content = raw[:500]
            except Exception as e:
                content = f"(LLM 调用失败: {e})"

        # 降级
        if not content:
            content = f"[{self.side}] 关于 '{topic}' 的论点（LLM 不可用，降级处理）"

        round_num = max((a.round for a in history), default=0) + 1

        return DebateArgument(
            side=self.side,
            round=round_num,
            content=content,
            evidence=evidence,
        )


# ============================================================
# Judge — 裁判
# ============================================================

class DebateJudge:
    """
    辩论裁判

    基于双方论点做出最终裁决。
    可以使用 Verifier 或 LLM。
    """

    def __init__(self, model_router=None, verifier=None):
        self.model_router = model_router
        self.verifier = verifier

    def judge(self, topic: str, arguments: List[DebateArgument]) -> DebateResult:
        """
        裁决辩论

        Args:
            topic: 辩论主题
            arguments: 所有论点

        Returns:
            DebateResult
        """
        pro_args = [a for a in arguments if a.side == "pro"]
        con_args = [a for a in arguments if a.side == "con"]

        # 构建裁决 prompt
        pro_text = "\n".join([f"[R{a.round}] {a.content}" + 
                              (f"\n  证据: {'; '.join(a.evidence)}" if a.evidence else "")
                              for a in pro_args])
        con_text = "\n".join([f"[R{a.round}] {a.content}" +
                              (f"\n  证据: {'; '.join(a.evidence)}" if a.evidence else "")
                              for a in con_args])

        judge_prompt = f"""请裁决以下辩论。

主题: {topic}

正方论点:
{pro_text}

反方论点:
{con_text}

请输出 JSON:
{{
  "winner": "pro | con | draw",
  "decision": "最终决策（一句话）",
  "reasoning": "裁决理由（100字以内）",
  "confidence": 0.0到1.0的置信度
}}"""

        # LLM 裁决
        winner = "draw"
        decision = ""
        reasoning = ""
        confidence = 0.5

        if self.model_router:
            try:
                messages = [
                    {"role": "system", "content": "你是辩论裁判。基于双方论点的逻辑性、证据强度做出公正裁决。只输出 JSON。"},
                    {"role": "user", "content": judge_prompt},
                ]
                response = self.model_router.chat(
                    messages=messages,
                    task_type="light",
                    temperature=0.3,
                )
                raw = response.get("content", "")
                try:
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', raw)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        winner = parsed.get("winner", "draw")
                        decision = parsed.get("decision", "")
                        reasoning = parsed.get("reasoning", "")
                        confidence = float(parsed.get("confidence", 0.5))
                except Exception:
                    reasoning = raw[:200]
            except Exception as e:
                reasoning = f"LLM 调用失败: {e}"

        # 降级：基于论点数量和证据数量简单判断
        if not decision:
            pro_score = sum(len(a.evidence) for a in pro_args) + len(pro_args)
            con_score = sum(len(a.evidence) for a in con_args) + len(con_args)
            if pro_score > con_score:
                winner = "pro"
            elif con_score > pro_score:
                winner = "con"
            else:
                winner = "draw"
            decision = f"基于论点和证据数量的简单裁决（pro={pro_score}, con={con_score}）"
            reasoning = "LLM 不可用，基于论点数量降级裁决"
            confidence = 0.4

        return DebateResult(
            topic=topic,
            decision=decision,
            winner=winner,
            reasoning=reasoning,
            confidence=confidence,
            rounds=max(a.round for a in arguments) if arguments else 0,
            arguments=arguments,
        )


# ============================================================
# Debate — 辩论引擎
# ============================================================

class Debate:
    """
    辩论引擎

    流程：Pro → Con → Pro → Con → Judge
    """

    def __init__(
        self,
        pro_agent: DebateAgent = None,
        con_agent: DebateAgent = None,
        judge: DebateJudge = None,
        max_rounds: int = 2,
    ):
        """
        Args:
            pro_agent: 正方 Agent
            con_agent: 反方 Agent
            judge: 裁判
            max_rounds: 辩论轮数（默认 2）
        """
        self.pro_agent = pro_agent or DebateAgent("pro-default", "pro")
        self.con_agent = con_agent or DebateAgent("con-default", "con")
        self.judge = judge or DebateJudge()
        self.max_rounds = max_rounds

    def run(self, topic: str, context: str = "") -> DebateResult:
        """
        运行辩论

        Args:
            topic: 辩论主题
            context: 额外上下文

        Returns:
            DebateResult
        """
        start_time = time.time()
        arguments: List[DebateArgument] = []

        print(f"[Debate] 开始辩论: {topic} (最多 {self.max_rounds} 轮)")

        for round_num in range(1, self.max_rounds + 1):
            print(f"[Debate] --- 第 {round_num} 轮 ---")

            # 正方发言
            pro_arg = self.pro_agent.argue(topic, context, arguments)
            pro_arg.round = round_num  # 强制覆盖轮次
            arguments.append(pro_arg)
            print(f"  [Pro R{round_num}] {pro_arg.content[:80]}...")

            # 反方发言
            con_arg = self.con_agent.argue(topic, context, arguments)
            con_arg.round = round_num  # 强制覆盖轮次
            arguments.append(con_arg)
            print(f"  [Con R{round_num}] {con_arg.content[:80]}...")

        # 裁判裁决
        print(f"[Debate] 裁判裁决...")
        result = self.judge.judge(topic, arguments)
        result.duration_ms = int((time.time() - start_time) * 1000)

        print(f"[Debate] 结果: winner={result.winner}, confidence={result.confidence:.0%}")
        return result


# ============================================================
# 便捷工厂函数
# ============================================================

def create_debate(
    topic: str,
    model_router=None,
    max_rounds: int = 2,
    pro_prompt: str = "",
    con_prompt: str = "",
) -> Debate:
    """
    快速创建辩论实例

    Args:
        topic: 辩论主题
        model_router: 模型路由器
        max_rounds: 辩论轮数
        pro_prompt: 正方自定义 prompt
        con_prompt: 反方自定义 prompt

    Returns:
        Debate 实例
    """
    pro = DebateAgent("pro", "pro", model_router=model_router, system_prompt=pro_prompt)
    con = DebateAgent("con", "con", model_router=model_router, system_prompt=con_prompt)
    judge = DebateJudge(model_router=model_router)
    return Debate(pro_agent=pro, con_agent=con, judge=judge, max_rounds=max_rounds)


# ========== 单元测试 ==========

def _test():
    """Debate 模块测试"""
    print("\n=== Debate 单元测试 ===\n")

    # Test 1: DebateArgument 创建
    print("Test 1: DebateArgument 基本操作")
    arg = DebateArgument(side="pro", round=1, content="React 生态更好", evidence=["npm 下载量", "社区活跃度"])
    assert arg.side == "pro"
    assert arg.round == 1
    assert len(arg.evidence) == 2
    d = arg.to_dict()
    assert d["side"] == "pro"
    print("  ✅ PASS\n")

    # Test 2: DebateAgent 降级模式（无 LLM）
    print("Test 2: DebateAgent 降级模式")
    pro = DebateAgent("test-pro", "pro", model_router=None)
    arg = pro.argue("技术选型", "需要选择前端框架", [])
    assert arg.side == "pro"
    assert arg.content != ""
    assert arg.round == 1
    print(f"  论点: {arg.content[:60]}...")
    print("  ✅ PASS\n")

    # Test 3: DebateAgent 多轮论点
    print("Test 3: 多轮论点历史")
    con = DebateAgent("test-con", "con", model_router=None)
    history = [
        DebateArgument(side="pro", round=1, content="React 更好", evidence=["下载量高"]),
    ]
    arg2 = con.argue("技术选型", "", history)
    assert arg2.side == "con"
    assert arg2.round == 2
    print("  ✅ PASS\n")

    # Test 4: DebateJudge 降级裁决
    print("Test 4: DebateJudge 降级裁决")
    judge = DebateJudge(model_router=None)
    arguments = [
        DebateArgument(side="pro", round=1, content="论点A", evidence=["证据1", "证据2"]),
        DebateArgument(side="con", round=1, content="反驳B", evidence=["证据3"]),
    ]
    result = judge.judge("技术选型", arguments)
    assert result.winner in ("pro", "con", "draw")
    assert result.decision != ""
    assert result.confidence > 0
    print(f"  裁决: {result.winner} - {result.decision[:60]}")
    print("  ✅ PASS\n")

    # Test 5: 完整辩论流程（降级模式）
    print("Test 5: 完整辩论流程")
    debate = Debate(
        pro_agent=DebateAgent("pro", "pro", model_router=None),
        con_agent=DebateAgent("con", "con", model_router=None),
        judge=DebateJudge(model_router=None),
        max_rounds=2,
    )
    result = debate.run("用 React 还是 Vue？", context="企业级后台管理系统")
    assert result.rounds == 2
    assert len(result.arguments) == 4  # 2轮 × 2方
    assert result.duration_ms >= 0
    print(result.summary())
    print("  ✅ PASS\n")

    # Test 6: DebateResult 序列化
    print("Test 6: DebateResult 序列化")
    d = result.to_dict()
    assert d["topic"] == "用 React 还是 Vue？"
    assert len(d["arguments"]) == 4
    assert d["winner"] in ("pro", "con", "draw")
    print("  ✅ PASS\n")

    # Test 7: create_debate 工厂函数
    print("Test 7: create_debate 工厂函数")
    debate2 = create_debate("测试主题", max_rounds=1)
    assert debate2.max_rounds == 1
    result2 = debate2.run("测试主题")
    assert result2.rounds == 1
    assert len(result2.arguments) == 2  # 1轮 × 2方
    print("  ✅ PASS\n")

    # Test 8: 证据为空的裁决
    print("Test 8: 无证据裁决")
    judge2 = DebateJudge(model_router=None)
    args = [
        DebateArgument(side="pro", round=1, content="我觉得好"),
        DebateArgument(side="con", round=1, content="我觉得不好"),
    ]
    result3 = judge2.judge("无证据辩论", args)
    assert result3.winner == "draw"  # 无证据时应为平局
    print("  ✅ PASS\n")

    # Test 9: 单方论点
    print("Test 9: 单方论点裁决")
    args_pro_only = [
        DebateArgument(side="pro", round=1, content="论点A", evidence=["e1", "e2"]),
    ]
    result4 = judge2.judge("单方辩论", args_pro_only)
    assert result4.winner == "pro"  # 只有正方时正方胜
    print("  ✅ PASS\n")

    # Test 10: 空论点
    print("Test 10: 空论点裁决")
    result5 = judge2.judge("空辩论", [])
    assert result5.winner == "draw"
    assert result5.rounds == 0
    print("  ✅ PASS\n")

    print("=== 所有 Debate 测试通过 ===\n")


if __name__ == "__main__":
    _test()
