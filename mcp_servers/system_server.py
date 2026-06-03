#!/usr/bin/env python3
"""
mcp_servers/system_server.py - 系统操作 MCP Server

封装 Shell 命令执行、进程管理、系统信息查询等操作。
独立运行，不依赖 orchestrator。

启动方式：
    python system_server.py         # stdio 模式
    python system_server.py --test  # 自测模式
"""
import sys
import os
import json
import subprocess
import platform

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.mcp_protocol import MCPServer

server = MCPServer("system-service", version="1.0.0")


# ========== 工具定义 ==========

@server.tool(
    name="exec_command",
    description="执行 Shell 命令。返回 stdout、stderr、exit_code。危险操作需谨慎。",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 Shell 命令"},
            "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
            "cwd": {"type": "string", "description": "工作目录"}
        },
        "required": ["command"]
    }
)
def exec_command(command, timeout=30, cwd=None):
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
        return {
            "command": command,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "error": f"命令超时 ({timeout}s)",
            "exit_code": -1,
        }
    except Exception as e:
        return {
            "command": command,
            "error": str(e),
            "exit_code": -1,
        }


@server.tool(
    name="system_info",
    description="获取系统信息（OS、CPU、内存、磁盘）。",
    input_schema={"type": "object", "properties": {}}
)
def system_info():
    import shutil
    mem = shutil.disk_usage("/")
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "hostname": platform.node(),
        "disk_total_gb": round(mem.total / (1024**3), 1),
        "disk_free_gb": round(mem.free / (1024**3), 1),
    }


@server.tool(
    name="check_process",
    description="检查进程是否在运行。",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "进程名或关键词"}
        },
        "required": ["name"]
    }
)
def check_process(name):
    result = subprocess.run(
        f"ps aux | grep '{name}' | grep -v grep",
        shell=True, capture_output=True, text=True, timeout=10,
    )
    lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
    return {
        "keyword": name,
        "running": len(lines) > 0,
        "count": len(lines),
        "processes": lines[:10],
    }


@server.tool(
    name="git_status",
    description="获取 Git 仓库状态。",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "仓库路径", "default": "."}
        }
    }
)
def git_status(path="."):
    try:
        r = subprocess.run(
            "git status --porcelain && echo '---' && git log --oneline -5",
            shell=True, capture_output=True, text=True, timeout=10, cwd=path,
        )
        return {
            "path": path,
            "output": r.stdout[:3000],
            "exit_code": r.returncode,
        }
    except Exception as e:
        return {"path": path, "error": str(e)}


@server.tool(
    name="install_package",
    description="安装 Python 包（pip install）。注意：需要确认。",
    input_schema={
        "type": "object",
        "properties": {
            "package": {"type": "string", "description": "包名"},
            "upgrade": {"type": "boolean", "description": "是否升级", "default": False}
        },
        "required": ["package"]
    }
)
def install_package(package, upgrade=False):
    cmd = f"pip install {package}"
    if upgrade:
        cmd += " --upgrade"
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=120,
    )
    return {
        "package": package,
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-500:],
        "exit_code": result.returncode,
    }


# ========== 启动 ==========

if __name__ == "__main__":
    if "--test" in sys.argv:
        print(f"[{server.name}] 工具列表:")
        for t in server.tools.values():
            print(f"  - {t.name}: {t.description}")

        result = system_info()
        print(f"\n系统信息: {result['os']} {result['arch']}, Python {result['python']}")
        print("✅ 自测通过")
    else:
        server.run()
