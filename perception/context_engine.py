"""
环境感知与意图识别引擎
整合屏幕感知、剪贴板、窗口上下文
"""
import os
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class UserContext:
    """用户当前上下文"""
    window_title: str = ""
    window_type: str = ""
    clipboard_text: str = ""
    screen_text: str = ""
    active_app: str = ""
    timestamp: str = ""


@dataclass
class IntentResult:
    """意图识别结果"""
    intent_type: str  # email / system_fix / search / code_help / other
    confidence: float
    key_entities: Dict  # {recipient, topic, component, ...}
    reasoning: str
    trigger_context: str  # 触发意图的具体上下文


class ContextEngine:
    """
    上下文感知引擎

    整合多源感知数据，辅助意图识别
    """

    def __init__(self):
        self.last_context: Optional[UserContext] = None
        # 行为追踪器
        self._behavior_tracker = None
        # 隐私保护
        self._privacy_guard = None

        # 意图触发规则
        self.intent_rules = {
            "email": {
                "keywords": ["发邮件", "发给", "写邮件", "email", "告知", "通知"],
                "context_triggers": {
                    "mail": 0.9,  # 邮件客户端打开时
                    "clipboard_has_at": 0.3,  # 剪贴板有@符号
                }
            },
            "system_fix": {
                "keywords": ["连不上", "没声音", "坏了", "不行", "错误", "故障",
                           "can't", "not working", "error", "broken"],
                "context_triggers": {
                    "error_content": 0.5,  # 屏幕有错误信息
                }
            },
            "code_help": {
                "keywords": ["代码", "报错", "debug", "怎么写", "帮我改",
                           "error", "exception", "bug"],
                "context_triggers": {
                    "editor": 0.4,  # 编辑器打开
                    "terminal": 0.3,  # 终端打开
                }
            },
            "search": {
                "keywords": ["搜", "找", "查", "search", "find", "look up"],
                "context_triggers": {}
            }
        }

    def gather_context(self) -> UserContext:
        """收集当前所有感知数据"""
        from datetime import datetime

        ctx = UserContext()
        ctx.timestamp = datetime.now().isoformat()

        # 窗口上下文
        try:
            from perception.window_manager import get_active_window, get_window_classification
            window = get_active_window()
            if window:
                ctx.window_title = window.title
                ctx.window_type = get_window_classification(window.title, window.class_name)
                ctx.active_app = window.class_name or window.title
        except Exception:
            pass  # 窗口感知不可用时静默降级

        # 剪贴板
        try:
            from perception.clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor()
            ctx.clipboard_text = monitor.get_text()[:500]  # 限制长度
        except Exception:
            pass  # 剪贴板不可用时静默降级

        # 屏幕 OCR
        try:
            from perception.screen_ocr import ocr_screen, understand_screen_context
            screen_result = ocr_screen()
            if screen_result.get("success"):
                ctx.screen_text = screen_result.get("full_text", "")[:1000]
        except Exception:
            pass  # OCR 不可用时静默降级

        # 隐私保护：脱敏处理
        ctx = self._apply_privacy_filter(ctx)

        self.last_context = ctx
        return ctx

    def _get_privacy_guard(self):
        """获取隐私保护器单例"""
        if self._privacy_guard is None:
            try:
                from perception.privacy_guard import get_privacy_guard
                self._privacy_guard = get_privacy_guard()
            except ImportError:
                self._privacy_guard = None
        return self._privacy_guard

    def _apply_privacy_filter(self, ctx: UserContext) -> UserContext:
        """对感知数据进行隐私脱敏"""
        guard = self._get_privacy_guard()
        if guard is None:
            return ctx
        try:
            if ctx.clipboard_text:
                ctx.clipboard_text = guard.mask_text(ctx.clipboard_text)
            if ctx.screen_text:
                ctx.screen_text = guard.mask_text(ctx.screen_text)
            # 记录审计日志
            guard.log_operation(
                operation="context_gather",
                agent="context_engine",
                detail=f"window={ctx.window_title[:50]}, clip_len={len(ctx.clipboard_text)}, screen_len={len(ctx.screen_text)}",
                sensitive=False,
            )
        except Exception:
            pass  # 隐私过滤失败不阻塞主流程
        return ctx

    def recognize_intent(self, user_input: str = None, context: UserContext = None) -> IntentResult:
        """
        识别用户意图

        Args:
            user_input: 用户输入文本
            context: 上下文（None 则自动收集）

        Returns:
            IntentResult
        """
        if context is None:
            context = self.last_context or self.gather_context()

        # 基础评分
        scores = {}
        for intent_type, rules in self.intent_rules.items():
            score = 0.0

            # 关键词匹配
            if user_input:
                text_lower = user_input.lower()
                for kw in rules["keywords"]:
                    if kw.lower() in text_lower:
                        score += 0.4

            # 上下文触发
            for trigger, boost in rules.get("context_triggers", {}).items():
                if trigger == "mail" and context.window_type == "mail":
                    score += boost
                elif trigger == "editor" and context.window_type in ["editor", "ide"]:
                    score += boost
                elif trigger == "terminal" and context.window_type == "terminal":
                    score += boost
                elif trigger == "error_content":
                    error_kws = ["error", "exception", "failed", "错误", "异常"]
                    if any(kw in context.screen_text.lower() for kw in error_kws):
                        score += boost
                elif trigger == "clipboard_has_at":
                    if "@" in context.clipboard_text:
                        score += boost

            scores[intent_type] = min(score, 1.0)

        # 选择最高分
        if not scores or max(scores.values()) < 0.1:
            best_intent = "other"
            confidence = 0.1
        else:
            best_intent = max(scores.items(), key=lambda x: x[1])
            best_intent, confidence = best_intent

        # 提取实体
        entities = self._extract_entities(user_input or "", context)

        # 生成推理
        reasoning = self._generate_reasoning(best_intent, confidence, user_input, context)

        return IntentResult(
            intent_type=best_intent,
            confidence=confidence,
            key_entities=entities,
            reasoning=reasoning,
            trigger_context=self._summarize_context(context)
        )

    def _extract_entities(self, text: str, context: UserContext) -> Dict:
        """提取关键实体"""
        import re

        entities = {}

        # 邮件实体
        if any(kw in text.lower() for kw in ["邮件", "发给", "email"]):
            # 收件人
            patterns = [r"给([^\s,，]+)发", r"发给([^\s,，]+)"]
            for p in patterns:
                m = re.search(p, text)
                if m:
                    entities["recipient"] = m.group(1)
                    break

        # 系统问题实体
        system_keywords = {
            "audio": ["声音", "音频", "声卡"],
            "network": ["网络", "wifi", "网"],
            "printer": ["打印", "打印机"],
            "bluetooth": ["蓝牙"],
        }
        for comp, kws in system_keywords.items():
            if any(kw in text for kw in kws):
                entities["component"] = comp
                break

        return entities

    def _generate_reasoning(self, intent: str, confidence: float,
                           text: str, context: UserContext) -> str:
        """生成意图推理说明"""
        parts = []

        if confidence > 0.7:
            parts.append("高置信度识别")
        elif confidence > 0.4:
            parts.append("中等置信度")
        else:
            parts.append("低置信度，需要更多信息")

        if text:
            parts.append(f"用户输入包含意图关键词")

        if context.window_type and context.window_type != "other":
            parts.append(f"当前窗口为{context.window_type}类型")

        if context.clipboard_text:
            parts.append(f"剪贴板有内容（{len(context.clipboard_text)}字）")

        return "，".join(parts)

    def _summarize_context(self, context: UserContext) -> str:
        """总结上下文"""
        parts = []

        if context.window_title:
            parts.append(f"窗口: {context.window_title[:30]}")

        if context.window_type and context.window_type != "other":
            parts.append(f"类型: {context.window_type}")

        if context.clipboard_text:
            parts.append(f"剪贴板: {context.clipboard_text[:50]}...")

        if context.screen_text:
            parts.append(f"屏幕: {context.screen_text[:50]}...")

        return " | ".join(parts) if parts else "无上下文"

    def get_full_context(self) -> Dict:
        """获取完整上下文字典（含行为追踪+跨应用关联）"""
        ctx = self.gather_context()

        # 记录行为
        tracker = self._get_behavior_tracker()
        if ctx.window_title:
            tracker.check_and_record_window(ctx.window_title, ctx.active_app)
        if ctx.clipboard_text:
            tracker.check_and_record_clipboard(ctx.clipboard_text)

        # 行为预测
        prediction = tracker.predict_next_action()

        # 跨应用上下文关联
        cross_app = self._analyze_cross_app_context(ctx, tracker)

        return {
            "window": {
                "title": ctx.window_title,
                "type": ctx.window_type,
                "app": ctx.active_app,
            },
            "clipboard": {
                "text": ctx.clipboard_text,
                "length": len(ctx.clipboard_text),
            },
            "screen": {
                "text": ctx.screen_text[:500] if ctx.screen_text else "",
                "length": len(ctx.screen_text) if ctx.screen_text else 0,
            },
            "behavior": {
                "recent_events": tracker.get_event_sequence(5),
                "prediction": prediction,
            },
            "cross_app_context": cross_app,
            "timestamp": ctx.timestamp,
        }

    def _get_behavior_tracker(self):
        """获取行为追踪器单例"""
        if self._behavior_tracker is None:
            try:
                from perception.behavior_tracker import get_tracker
                self._behavior_tracker = get_tracker()
            except ImportError:
                # 降级：无行为追踪
                class DummyTracker:
                    def check_and_record_window(self, *a, **kw): pass
                    def check_and_record_clipboard(self, *a, **kw): pass
                    def predict_next_action(self): return {"prediction": None, "confidence": 0}
                    def get_event_sequence(self, n=5): return []
                self._behavior_tracker = DummyTracker()
        return self._behavior_tracker

    def _analyze_cross_app_context(self, ctx: UserContext, tracker) -> Dict:
        """
        跨应用上下文关联分析

        例如：用户在浏览器搜索"Python排序" → 切换到编辑器 →
        智能体应关联"用户可能在查资料写代码"
        """
        recent = tracker.get_recent_events(10)  # 最近10分钟
        if len(recent) < 2:
            return {"has_context": False}

        # 找到最近的窗口切换序列
        window_switches = [e for e in recent if e.event_type == "window_switch"]
        if len(window_switches) < 2:
            return {"has_context": False}

        # 分析应用类型序列
        app_types = []
        for e in recent[-5:]:
            app = e.app.lower() if e.app else ""
            if any(k in app for k in ["browser", "firefox", "chrome", "webkit"]):
                app_types.append("browser")
            elif any(k in app for k in ["code", "editor", "vim", "vscode"]):
                app_types.append("editor")
            elif any(k in app for k in ["terminal", "konsole", "deepin-terminal"]):
                app_types.append("terminal")
            elif any(k in app for k in ["mail", "thunderbird", "outlook"]):
                app_types.append("mail")
            else:
                app_types.append("other")

        # 检测跨应用模式
        patterns = []

        # 模式：浏览器→编辑器（查资料写代码）
        if "browser" in app_types and "editor" in app_types:
            browser_idx = app_types.index("browser")
            editor_idx = app_types.index("editor")
            if browser_idx < editor_idx:
                patterns.append({
                    "pattern": "research_to_code",
                    "description": "用户在浏览器查资料后切换到编辑器，可能需要代码帮助",
                    "confidence": 0.6,
                })

        # 模式：编辑器→终端（运行代码）
        if "editor" in app_types and "terminal" in app_types:
            patterns.append({
                "pattern": "code_to_run",
                "description": "用户在编辑器写代码后切换到终端，可能在运行/调试",
                "confidence": 0.5,
            })

        # 模式：剪贴板内容包含代码/错误信息
        if ctx.clipboard_text:
            clip_lower = ctx.clipboard_text.lower()
            if any(k in clip_lower for k in ["error", "exception", "traceback", "failed"]):
                patterns.append({
                    "pattern": "error_in_clipboard",
                    "description": "剪贴板包含错误信息，用户可能需要调试帮助",
                    "confidence": 0.7,
                })
            elif any(k in clip_lower for k in ["def ", "class ", "import ", "function"]):
                patterns.append({
                    "pattern": "code_in_clipboard",
                    "description": "剪贴板包含代码片段",
                    "confidence": 0.5,
                })

        return {
            "has_context": len(patterns) > 0,
            "patterns": patterns,
            "app_sequence": app_types[-5:],
        }


def test():
    """测试上下文引擎"""
    engine = ContextEngine()

    print("=== ContextEngine 测试 ===\n")

    # 收集上下文
    print("[1] 收集上下文...")
    ctx = engine.gather_context()
    print(f"   窗口: {ctx.window_title[:40] if ctx.window_title else '(无)'}")
    print(f"   类型: {ctx.window_type or '(无)'}")
    print(f"   剪贴板: {ctx.clipboard_text[:50] if ctx.clipboard_text else '(空)'}...")
    print(f"   屏幕OCR: {'成功' if ctx.screen_text else '无'}")

    # 意图识别
    print("\n[2] 意图识别测试...")

    test_inputs = [
        "给张三发邮件说项目进度",
        "打印机连不上了",
        "帮我查一下这个代码哪里有bug",
        "看看系统有没有问题",
    ]

    for inp in test_inputs:
        result = engine.recognize_intent(inp)
        print(f"\n   输入: {inp}")
        print(f"   → 意图: {result.intent_type} (置信度: {result.confidence:.0%})")
        print(f"   → 实体: {result.key_entities}")
        print(f"   → 推理: {result.reasoning}")


if __name__ == "__main__":
    test()
