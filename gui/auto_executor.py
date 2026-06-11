#!/usr/bin/env python3
"""
自主执行器
接收 Decision，低风险操作自动执行，结果推送到 GUI

执行策略：
- auto_execute=True + risk=low → 静默执行，结果推送到对话窗口
- auto_execute=False → 不执行，生成建议让用户确认
- risk=high → 不执行，只告警
"""
import os
import sys
import subprocess
from typing import Optional, Callable
from dataclasses import dataclass

from PyQt5.QtCore import QObject, QThread, pyqtSignal

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from gui.decision_engine import Decision


class ExecutionResult:
    """执行结果"""
    def __init__(self, success: bool, output: str, action: str, auto: bool):
        self.success = success
        self.output = output
        self.action = action
        self.auto = auto  # 是否是自动执行的


class WorkerThread(QThread):
    """后台执行线程"""
    finished = pyqtSignal(object)  # ExecutionResult
    status = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(ExecutionResult(
                success=False, output=f"执行异常：{str(e)}",
                action="error", auto=True
            ))


class AutoExecutor(QObject):
    """
    自主执行器

    接收 Decision → 判断是否自动执行 → 执行 → 返回结果
    """

    # 信号：执行完成，结果推送到 GUI
    result_ready = pyqtSignal(object)  # ExecutionResult
    # 信号：需要用户确认（非自动执行）
    confirmation_needed = pyqtSignal(str, object)  # (提示文本, Decision)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None

    def execute(self, decision: Decision) -> Optional[ExecutionResult]:
        """
        执行决策

        返回：
        - ExecutionResult（自动执行完成）
        - None（需要用户确认，通过 confirmation_needed 信号通知）
        """
        if decision.action == "ignore":
            return None

        # 需要用户确认
        if not decision.auto_execute:
            hint = self._build_confirmation_hint(decision)
            self.confirmation_needed.emit(hint, decision)
            return None

        # 自动执行
        if decision.action == "translate":
            return self._auto_translate(decision)
        elif decision.action == "summarize":
            return self._auto_summarize(decision)
        elif decision.action == "analyze_code":
            return self._auto_analyze_code(decision)
        elif decision.action == "diagnose":
            return self._auto_diagnose(decision)
        else:
            return None

    def execute_async(self, decision: Decision):
        """异步执行（不阻塞 GUI 线程）"""
        if decision.action == "ignore":
            return

        if not decision.auto_execute:
            hint = self._build_confirmation_hint(decision)
            self.confirmation_needed.emit(hint, decision)
            return

        # 选择执行函数
        func_map = {
            "translate": self._auto_translate,
            "summarize": self._auto_summarize,
            "analyze_code": self._auto_analyze_code,
            "diagnose": self._auto_diagnose,
        }
        func = func_map.get(decision.action)
        if not func:
            return

        # 后台线程执行
        self._worker = WorkerThread(func, decision)
        self._worker.finished.connect(self.result_ready.emit)
        self._worker.start()

    # ---- 自动执行实现 ----

    def _auto_translate(self, decision: Decision) -> ExecutionResult:
        """自动翻译（调用系统翻译工具或本地翻译）"""
        text = decision.context.get("text", "")
        if not text:
            return ExecutionResult(False, "无内容可翻译", "translate", True)

        # 尝试用本地翻译（先检查有没有翻译工具）
        try:
            # 方案1：调用翻译 API（如果配置了）
            from scenarios.email_assistant import EmailAssistant
            # 用 LLM 做翻译（复用现有模型能力）
            prompt = f"请将以下英文翻译为中文，只输出翻译结果，不要解释：\n\n{text[:1000]}"
            # 这里简化处理，实际应调用 model_router
            result = self._call_llm(prompt)
            if result:
                # 把翻译结果写入剪贴板
                self._set_clipboard(result)
                return ExecutionResult(
                    True, f"✅ 已翻译并复制到剪贴板：\n\n{result[:500]}",
                    "translate", True
                )
        except Exception as e:
            pass

        return ExecutionResult(
            False, "翻译失败，请手动处理",
            "translate", True
        )

    def _auto_summarize(self, decision: Decision) -> ExecutionResult:
        """自动总结"""
        text = decision.context.get("text", "")
        if not text:
            return ExecutionResult(False, "无内容可总结", "summarize", True)

        try:
            prompt = f"请用3-5个要点总结以下内容：\n\n{text[:1500]}"
            result = self._call_llm(prompt)
            if result:
                return ExecutionResult(
                    True, f"📝 内容要点：\n\n{result}",
                    "summarize", True
                )
        except Exception:
            pass

        return ExecutionResult(False, "总结失败", "summarize", True)

    def _auto_analyze_code(self, decision: Decision) -> ExecutionResult:
        """自动代码分析"""
        code = decision.context.get("code", "")
        file_path = decision.context.get("file", "")
        language = decision.context.get("language", "unknown")

        # 如果是文件路径，尝试读取
        if file_path and not code:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read(3000)
            except Exception:
                return ExecutionResult(False, f"无法读取文件：{file_path}", "analyze_code", True)

        if not code:
            return ExecutionResult(False, "无代码可分析", "analyze_code", True)

        try:
            prompt = f"请分析以下{language}代码的功能、潜在问题和优化建议（简洁版）：\n\n```\n{code[:2000]}\n```"
            result = self._call_llm(prompt)
            if result:
                return ExecutionResult(
                    True, f"💻 代码分析：\n\n{result}",
                    "analyze_code", True
                )
        except Exception:
            pass

        return ExecutionResult(False, "代码分析失败", "analyze_code", True)

    def _auto_diagnose(self, decision: Decision) -> ExecutionResult:
        """自动系统诊断"""
        service = decision.context.get("service", "")
        description = decision.context.get("description", "")

        try:
            # 获取服务状态
            status_cmd = f"systemctl status {service} 2>&1 | head -20"
            status_output = subprocess.getoutput(status_cmd)

            prompt = f"系统服务 {service} 异常。状态信息：\n{status_output}\n\n请诊断问题并给出修复建议。"
            result = self._call_llm(prompt)
            if result:
                return ExecutionResult(
                    True, f"⚠️ 系统诊断：\n\n{result}",
                    "diagnose", True
                )
        except Exception:
            pass

        return ExecutionResult(False, "诊断失败", "diagnose", True)

    # ---- 工具方法 ----

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM（复用项目现有的模型路由）"""
        try:
            from agents.model_router import ModelRouter
            router = ModelRouter()
            response = router.generate(prompt, max_tokens=500)
            return response.get("text", "") if isinstance(response, dict) else str(response)
        except Exception:
            # 降级：用 erniebot 直接调
            try:
                import erniebot
                erniebot.api_type = "aistudio"
                erniebot.access_token = os.environ.get("ERNIEBOT_ACCESS_TOKEN", "")
                resp = erniebot.ChatCompletion.create(
                    model="ernie-lite",
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.get("result", "")
            except Exception:
                return None

    def _set_clipboard(self, text: str):
        """写入剪贴板"""
        try:
            from perception.clipboard_monitor import set_clipboard_text
            set_clipboard_text(text)
        except Exception:
            # 降级：直接用 xclip
            try:
                process = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE
                )
                process.communicate(text.encode("utf-8"))
            except Exception:
                pass

    def _build_confirmation_hint(self, decision: Decision) -> str:
        """生成用户确认提示"""
        hints = {
            "translate": "🔍 检测到英文内容，需要翻译吗？",
            "summarize": "📝 检测到长文本，需要总结要点吗？",
            "analyze_code": "💻 检测到代码，需要分析吗？",
            "open_url": "🔗 检测到链接，需要打开吗？",
            "suggest_reply": "📧 检测到邮件，需要帮忙回复吗？",
            "diagnose": f"⚠️ 检测到服务异常（{decision.context.get('service', '')}），需要诊断吗？",
        }
        return hints.get(decision.action, f"🔍 {decision.reasoning}")
