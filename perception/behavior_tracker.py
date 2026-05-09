"""
行为序列追踪器
记录用户操作行为序列，学习工作模式，预测下一步操作
"""
import os
import json
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import Counter


@dataclass
class BehaviorEvent:
    """单次行为事件"""
    timestamp: str
    event_type: str  # window_switch, app_open, clipboard_change, command_exec
    detail: Dict     # 具体信息
    app: str = ""    # 关联的应用


class BehaviorTracker:
    """
    行为序列追踪器

    记录用户操作 → 分析模式 → 预测意图
    """

    def __init__(self, max_events: int = 500):
        self.events: List[BehaviorEvent] = []
        self.max_events = max_events
        self._last_window_title = ""
        self._last_clipboard_hash = ""

    def record(self, event_type: str, detail: Dict, app: str = ""):
        """记录一次行为事件"""
        event = BehaviorEvent(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            detail=detail,
            app=app,
        )
        self.events.append(event)

        # 限制内存中的事件数量
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    def check_and_record_window(self, window_title: str, app_class: str = ""):
        """检查窗口变化并记录"""
        if window_title != self._last_window_title:
            self.record("window_switch", {
                "from": self._last_window_title,
                "to": window_title,
            }, app=app_class)
            self._last_window_title = window_title

    def check_and_record_clipboard(self, clipboard_text: str):
        """检查剪贴板变化并记录"""
        text_hash = hash(clipboard_text[:200]) if clipboard_text else ""
        if text_hash != self._last_clipboard_hash and clipboard_text:
            self.record("clipboard_change", {
                "length": len(clipboard_text),
                "preview": clipboard_text[:100],
            })
            self._last_clipboard_hash = text_hash

    def get_recent_events(self, minutes: int = 30) -> List[BehaviorEvent]:
        """获取最近 N 分钟的事件"""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [e for e in self.events if datetime.fromisoformat(e.timestamp) > cutoff]

    def get_app_frequency(self, minutes: int = 60) -> Dict[str, int]:
        """获取最近应用使用频率"""
        recent = self.get_recent_events(minutes)
        apps = [e.app for e in recent if e.app]
        return dict(Counter(apps).most_common(10))

    def get_event_sequence(self, count: int = 10) -> List[Dict]:
        """获取最近的行为序列"""
        recent = self.events[-count:]
        return [{
            "type": e.event_type,
            "time": e.timestamp,
            "app": e.app,
            "summary": self._summarize_event(e),
        } for e in recent]

    def predict_next_action(self) -> Dict:
        """
        基于行为序列预测下一步操作

        简单实现：基于最近的应用使用模式和事件频率
        """
        recent = self.get_recent_events(30)
        if len(recent) < 3:
            return {"prediction": None, "confidence": 0, "reason": "行为数据不足"}

        # 分析最近的应用切换模式
        app_sequence = [e.app for e in recent if e.app]
        if not app_sequence:
            return {"prediction": None, "confidence": 0, "reason": "无应用数据"}

        # 最常用应用
        app_freq = Counter(app_sequence)
        top_app = app_freq.most_common(1)[0]

        # 最近的事件类型
        event_types = Counter(e.event_type for e in recent)
        most_common_event = event_types.most_common(1)[0]

        # 基于模式的预测
        predictions = []

        # 模式1：频繁切换到编辑器 → 可能需要代码帮助
        if any("editor" in e.app.lower() or "code" in e.app.lower()
               for e in recent[-5:] if e.app):
            predictions.append({
                "action": "code_help",
                "confidence": 0.6,
                "reason": "频繁使用代码编辑器",
            })

        # 模式2：频繁使用剪贴板 → 可能需要信息整理
        if event_types.get("clipboard_change", 0) >= 3:
            predictions.append({
                "action": "summarize",
                "confidence": 0.5,
                "reason": "频繁复制内容",
            })

        # 模式3：窗口快速切换 → 可能需要信息汇总
        if event_types.get("window_switch", 0) >= 5:
            predictions.append({
                "action": "information_gather",
                "confidence": 0.4,
                "reason": "频繁切换窗口",
            })

        if predictions:
            best = max(predictions, key=lambda x: x["confidence"])
            return {
                "prediction": best["action"],
                "confidence": best["confidence"],
                "reason": best["reason"],
                "top_app": top_app[0],
                "recent_apps": [a for a, _ in app_freq.most_common(3)],
            }

        return {
            "prediction": None,
            "confidence": 0,
            "reason": "未识别到明确模式",
            "top_app": top_app[0],
        }

    def _summarize_event(self, event: BehaviorEvent) -> str:
        """生成事件摘要"""
        if event.event_type == "window_switch":
            return f"切换窗口: {event.detail.get('to', '')[:40]}"
        elif event.event_type == "clipboard_change":
            return f"复制内容 ({event.detail.get('length', 0)}字)"
        elif event.event_type == "app_open":
            return f"打开应用: {event.app}"
        elif event.event_type == "command_exec":
            return f"执行命令: {event.detail.get('command', '')[:40]}"
        return f"{event.event_type}"

    def get_summary(self) -> Dict:
        """获取行为摘要"""
        total = len(self.events)
        recent_1h = self.get_recent_events(60)
        app_freq = self.get_app_frequency(60)
        prediction = self.predict_next_action()

        return {
            "total_events": total,
            "events_last_hour": len(recent_1h),
            "top_apps": app_freq,
            "prediction": prediction,
            "event_types": dict(Counter(e.event_type for e in recent_1h).most_common()),
        }

    def save(self, path: str = None):
        """保存行为记录到文件"""
        if path is None:
            path = os.path.expanduser("~/.deepin-agent-teams/behavior_log.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = [asdict(e) for e in self.events[-200:]]  # 只保存最近200条
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str = None):
        """从文件加载行为记录"""
        if path is None:
            path = os.path.expanduser("~/.deepin-agent-teams/behavior_log.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.events = [BehaviorEvent(**e) for e in data]
        except Exception:
            pass


# 全局单例
_tracker: Optional[BehaviorTracker] = None


def get_tracker() -> BehaviorTracker:
    global _tracker
    if _tracker is None:
        _tracker = BehaviorTracker()
        _tracker.load()  # 尝试加载历史记录
    return _tracker
