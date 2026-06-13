"""
MCP 工具适配器
Model Context Protocol 工具注册、发现与调用框架
"""
import os
import json
import subprocess
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class ToolParam:
    """工具参数定义"""
    name: str
    type: str  # string, int, float, bool, list, dict
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolResult:
    """工具调用结果"""
    success: bool
    output: Any = None
    error: str = ""
    duration_ms: int = 0
    tool_name: str = ""


@dataclass
class ToolDef:
    """工具定义"""
    name: str
    description: str
    category: str  # system, file, network, perception, custom
    parameters: List[ToolParam] = field(default_factory=list)
    handler: Optional[Callable] = None
    requires_confirm: bool = False  # 危险操作需确认


class MCPAdapter:
    """
    MCP 工具适配器

    提供工具注册、发现、调用能力
    兼容 MCP 协议规范
    """

    def __init__(self):
        self.tools: Dict[str, ToolDef] = {}
        self.call_history: List[Dict] = []
        self._register_builtin_tools()

    def register(self, tool: ToolDef):
        """注册工具"""
        self.tools[tool.name] = tool

    def unregister(self, name: str):
        """注销工具"""
        self.tools.pop(name, None)

    def list_tools(self, category: str = None) -> List[Dict]:
        """列出所有工具"""
        tools = list(self.tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return [{
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "parameters": [asdict(p) for p in t.parameters],
            "requires_confirm": t.requires_confirm,
        } for t in tools]

    def get_tool(self, name: str) -> Optional[ToolDef]:
        """获取工具定义"""
        return self.tools.get(name)

    def call(self, name: str, params: Dict = None, auto_confirm: bool = False) -> ToolResult:
        """
        调用工具

        Args:
            name: 工具名
            params: 参数
            auto_confirm: 是否自动确认（跳过危险操作确认）

        Returns:
            ToolResult
        """
        tool = self.tools.get(name)
        if not tool:
            return ToolResult(success=False, error=f"工具不存在: {name}")

        if tool.requires_confirm and not auto_confirm:
            return ToolResult(
                success=False,
                error=f"需要确认: {tool.description}（设置 auto_confirm=True 跳过）",
                tool_name=name,
            )

        params = params or {}
        start_time = datetime.now()

        try:
            if tool.handler:
                result = tool.handler(**params)
            else:
                result = self._default_handler(name, params)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            tool_result = ToolResult(
                success=True,
                output=result,
                duration_ms=duration,
                tool_name=name,
            )

            self.call_history.append({
                "tool": name,
                "params": params,
                "success": True,
                "duration_ms": duration,
                "timestamp": datetime.now().isoformat(),
            })

            return tool_result

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            self.call_history.append({
                "tool": name,
                "params": params,
                "success": False,
                "error": str(e),
                "duration_ms": duration,
                "timestamp": datetime.now().isoformat(),
            })
            return ToolResult(success=False, error=str(e), duration_ms=duration, tool_name=name)

    def _default_handler(self, name: str, params: Dict) -> Any:
        """默认处理器（执行 shell 命令）"""
        cmd = params.get("command", "")
        if not cmd:
            raise ValueError("缺少 command 参数")
        timeout = params.get("timeout", 30)
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=timeout)
        return {
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
        }

    def _register_builtin_tools(self):
        """注册内置工具集"""

        # === 系统工具 ===
        self.register(ToolDef(
            name="exec_command",
            description="执行 Shell 命令",
            category="system",
            parameters=[
                ToolParam("command", "string", "要执行的命令"),
                ToolParam("timeout", "int", "超时秒数", required=False, default=30),
            ],
        ))

        self.register(ToolDef(
            name="read_file",
            description="读取文件内容",
            category="file",
            parameters=[
                ToolParam("path", "string", "文件路径"),
                ToolParam("max_lines", "int", "最大行数", required=False, default=200),
            ],
            handler=self._handle_read_file,
        ))

        self.register(ToolDef(
            name="search_files",
            description="在文件系统中搜索关键词",
            category="file",
            parameters=[
                ToolParam("keyword", "string", "搜索关键词"),
                ToolParam("path", "string", "搜索路径", required=False, default="."),
                ToolParam("extensions", "list", "文件扩展名过滤", required=False, default=[]),
            ],
            handler=self._handle_search_files,
        ))

        self.register(ToolDef(
            name="list_directory",
            description="列出目录内容",
            category="file",
            parameters=[
                ToolParam("path", "string", "目录路径", required=False, default="."),
            ],
            handler=self._handle_list_dir,
        ))

        # === 感知工具 ===
        self.register(ToolDef(
            name="get_clipboard",
            description="获取剪贴板内容",
            category="perception",
            parameters=[],
            handler=self._handle_clipboard,
        ))

        self.register(ToolDef(
            name="get_active_window",
            description="获取当前活动窗口信息",
            category="perception",
            parameters=[],
            handler=self._handle_active_window,
        ))

        self.register(ToolDef(
            name="screenshot_ocr",
            description="截取屏幕并 OCR 识别文字",
            category="perception",
            parameters=[],
            handler=self._handle_screenshot_ocr,
        ))

        # === 网络工具 ===
        self.register(ToolDef(
            name="http_get",
            description="HTTP GET 请求",
            category="network",
            parameters=[
                ToolParam("url", "string", "请求地址"),
                ToolParam("max_chars", "int", "最大返回字符数", required=False, default=5000),
            ],
            handler=self._handle_http_get,
        ))

        # === 系统管理（需确认）===
        self.register(ToolDef(
            name="install_package",
            description="安装软件包（apt）",
            category="system",
            parameters=[
                ToolParam("package", "string", "软件包名"),
            ],
            handler=self._handle_install,
            requires_confirm=True,
        ))

        self.register(ToolDef(
            name="manage_service",
            description="管理系统服务（systemctl）",
            category="system",
            parameters=[
                ToolParam("service", "string", "服务名"),
                ToolParam("action", "string", "操作: start/stop/restart/enable/disable"),
            ],
            handler=self._handle_service,
            requires_confirm=True,
        ))

    # === 内置处理器 ===

    def _handle_read_file(self, path: str, max_lines: int = 200) -> Dict:
        if not os.path.exists(path):
            return {"error": f"文件不存在: {path}"}
        with open(path, "r", errors="ignore") as f:
            lines = f.readlines()[:max_lines]
        return {"content": "".join(lines), "lines": len(lines), "path": path}

    def _handle_search_files(self, keyword: str, path: str = ".", extensions: list = None) -> Dict:
        results = []
        try:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for fname in files:
                    if extensions and not any(fname.endswith(e) for e in extensions):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", errors="ignore") as f:
                            content = f.read(50000)
                            if keyword.lower() in content.lower():
                                count = content.lower().count(keyword.lower())
                                idx = content.lower().find(keyword.lower())
                                preview = content[max(0, idx-50):idx+100]
                                results.append({
                                    "path": fpath,
                                    "matches": count,
                                    "preview": preview.strip(),
                                })
                    except Exception:
                        continue
                if len(results) >= 20:
                    break
        except Exception as e:
            return {"error": str(e)}
        results.sort(key=lambda x: x["matches"], reverse=True)
        return {"results": results[:20], "total": len(results)}

    def _handle_list_dir(self, path: str = ".") -> Dict:
        if not os.path.isdir(path):
            return {"error": f"目录不存在: {path}"}
        entries = []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            entries.append({
                "name": name,
                "type": "dir" if os.path.isdir(full) else "file",
                "size": os.path.getsize(full) if os.path.isfile(full) else 0,
            })
        return {"path": path, "entries": entries[:100]}

    def _handle_clipboard(self) -> Dict:
        try:
            from perception.clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor()
            text = monitor.get_text()
            return {"text": text[:2000] if text else "", "has_text": bool(text)}
        except Exception:
            return {"text": "", "has_text": False, "error": "剪贴板不可用"}

    def _handle_active_window(self) -> Dict:
        try:
            from perception.window_manager import get_active_window, get_window_classification
            win = get_active_window()
            if win:
                return {
                    "title": win.title,
                    "class": win.class_name,
                    "type": get_window_classification(win.title, win.class_name),
                }
            return {"title": "", "class": "", "type": "unknown"}
        except Exception:
            return {"error": "窗口信息不可用"}

    def _handle_screenshot_ocr(self) -> Dict:
        try:
            from perception.screen_ocr import ocr_screen
            result = ocr_screen()
            return result
        except Exception:
            return {"error": "OCR 不可用", "success": False}

    def _handle_http_get(self, url: str, max_chars: int = 5000) -> Dict:
        import urllib.request
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "deepin-agent-teams/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read(max_chars).decode("utf-8", errors="ignore")
            return {"content": content, "url": url}
        except Exception as e:
            return {"error": str(e), "url": url}

    def _handle_install(self, package: str) -> Dict:
        result = subprocess.run(
            ["apt-get", "install", "-y", package],
            capture_output=True, text=True, timeout=120,
        )
        return {"stdout": result.stdout[-1000:], "stderr": result.stderr[-500:], "returncode": result.returncode}

    def _handle_service(self, service: str, action: str) -> Dict:
        allowed = {"start", "stop", "restart", "enable", "disable", "status"}
        if action not in allowed:
            return {"error": f"不允许的操作: {action}，支持: {allowed}"}
        import shlex
        if not shlex.split(service) == [service]:
            return {"error": f"非法的服务名: {service}"}
        result = subprocess.run(
            ["systemctl", action, service],
            capture_output=True, text=True, timeout=30,
        )
        return {"stdout": result.stdout[:1000], "stderr": result.stderr[:500], "returncode": result.returncode}

    def get_stats(self) -> Dict:
        """获取调用统计"""
        total = len(self.call_history)
        success = sum(1 for c in self.call_history if c.get("success"))
        return {
            "total_calls": total,
            "success": success,
            "failed": total - success,
            "tools_registered": len(self.tools),
            "categories": list(set(t.category for t in self.tools.values())),
        }


# 全局单例
_adapter: Optional[MCPAdapter] = None


def get_adapter() -> MCPAdapter:
    global _adapter
    if _adapter is None:
        _adapter = MCPAdapter()
    return _adapter


def call_tool(name: str, params: Dict = None, auto_confirm: bool = False) -> ToolResult:
    """快捷调用工具"""
    return get_adapter().call(name, params, auto_confirm)
