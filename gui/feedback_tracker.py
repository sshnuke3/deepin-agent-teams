#!/usr/bin/env python3
"""
反馈追踪器
记录用户对每次建议的反馈行为，动态调整置信度

用户行为：
- accepted：用户接受了建议（执行了翻译/分析等）
- dismissed：用户关闭了弹窗/忽略了建议
- ignored：用户没有回应（超时）
- blocked：用户点了"别烦我"/关闭了该类感知

反馈影响置信度：
- accepted → +0.05
- ignored → -0.02
- dismissed → -0.05
- blocked → -0.20（大幅降低）
"""
import logging
import os
import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEvent:
    """单次反馈事件"""
    timestamp: str
    action_type: str      # translate / summarize / analyze_code / ...
    user_action: str      # accepted / dismissed / ignored / blocked
    confidence_before: float
    detail: str = ""


class FeedbackTracker:
    """
    反馈追踪器

    记录用户行为 → 调整同类场景的置信度
    """

    FEEDBACK_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", ".feedback_history.json"
    )

    # 每种用户行为对置信度的影响
    CONFIDENCE_DELTAS = {
        "accepted":  +0.05,
        "ignored":   -0.02,
        "dismissed": -0.05,
        "blocked":   -0.20,
    }

    def __init__(self, max_events: int = 200):
        self.max_events = max_events
        self.events: List[FeedbackEvent] = []
        self._load()

    def record(self, action_type: str, user_action: str, confidence_before: float, detail: str = ""):
        """记录一次反馈"""
        event = FeedbackEvent(
            timestamp=datetime.now().isoformat(),
            action_type=action_type,
            user_action=user_action,
            confidence_before=confidence_before,
            detail=detail,
        )
        self.events.append(event)

        # 限制内存
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

        self._save()

    def get_confidence_modifier(self, action_type: str) -> float:
        """
        根据历史反馈，计算置信度修正值

        逻辑：统计该 action_type 最近 20 次反馈，
        按 accepted/dismissed/ignored/blocked 的比例加权计算修正值
        """
        recent = [e for e in self.events if e.action_type == action_type][-20:]
        if not recent:
            return 0.0

        total = len(recent)
        weights = {"accepted": 0, "dismissed": 0, "ignored": 0, "blocked": 0}
        for e in recent:
            if e.user_action in weights:
                weights[e.user_action] += 1

        # 加权计算
        modifier = 0.0
        for action, count in weights.items():
            ratio = count / total
            modifier += ratio * self.CONFIDENCE_DELTAS.get(action, 0)

        # 限制修正范围 [-0.15, +0.10]
        return max(-0.15, min(0.10, modifier))

    def get_stats(self, action_type: Optional[str] = None) -> Dict:
        """获取统计信息"""
        events = self.events
        if action_type:
            events = [e for e in events if e.action_type == action_type]

        if not events:
            return {"total": 0}

        counts = {}
        for e in events:
            counts[e.user_action] = counts.get(e.user_action, 0) + 1

        return {
            "total": len(events),
            "counts": counts,
            "acceptance_rate": counts.get("accepted", 0) / len(events) if events else 0,
        }

    def should_suppress(self, action_type: str) -> bool:
        """
        判断是否应该抑制该类建议

        如果最近 10 次中 blocked > 50%，则抑制
        """
        recent = [e for e in self.events if e.action_type == action_type][-10:]
        if len(recent) < 3:
            return False
        blocked_count = sum(1 for e in recent if e.user_action == "blocked")
        return blocked_count > len(recent) * 0.5

    # ---- 持久化 ----

    def _load(self):
        """从文件加载历史"""
        try:
            path = os.path.abspath(self.FEEDBACK_FILE)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.events = [FeedbackEvent(**e) for e in data[-self.max_events:]]
        except Exception as e:
            logger.warning("Failed to load feedback history: %s", e)
            self.events = []

    def _save(self):
        """保存到文件"""
        try:
            path = os.path.abspath(self.FEEDBACK_FILE)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump([asdict(e) for e in self.events[-self.max_events:]],
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Failed to save feedback history: %s", e)
