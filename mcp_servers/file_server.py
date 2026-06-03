#!/usr/bin/env python3
"""
mcp_servers/file_server.py - 文件操作 MCP Server

封装文件读写、目录扫描、文件搜索等操作。
独立运行，不依赖 orchestrator。

启动方式：
    python file_server.py           # stdio 模式
    python file_server.py --test    # 自测模式
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.mcp_protocol import MCPServer

server = MCPServer("file-service", version="1.0.0")


# ========== 工具定义 ==========

@server.tool(
    name="read_file",
    description="读取文件内容。支持设置最大行数，避免读取过大文件。",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "max_lines": {"type": "integer", "description": "最大行数", "default": 200}
        },
        "required": ["path"]
    }
)
def read_file(path, max_lines=200):
    if not os.path.exists(path):
        return {"error": f"文件不存在: {path}"}
    if not os.path.isfile(path):
        return {"error": f"不是文件: {path}"}
    with open(path, "r", errors="ignore") as f:
        lines = f.readlines()[:max_lines]
    return {
        "path": path,
        "content": "".join(lines),
        "lines": len(lines),
        "truncated": len(lines) >= max_lines,
        "size": os.path.getsize(path),
    }


@server.tool(
    name="write_file",
    description="写入文件内容。自动创建父目录。",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "写入内容"}
        },
        "required": ["path", "content"]
    }
)
def write_file(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return {"path": path, "bytes_written": len(content)}


@server.tool(
    name="list_directory",
    description="列出目录内容，包括文件名、类型、大小。",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径", "default": "."},
            "max_entries": {"type": "integer", "description": "最大条目数", "default": 100}
        }
    }
)
def list_directory(path=".", max_entries=100):
    if not os.path.isdir(path):
        return {"error": f"目录不存在: {path}"}
    entries = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        entries.append({
            "name": name,
            "type": "dir" if os.path.isdir(full) else "file",
            "size": os.path.getsize(full) if os.path.isfile(full) else 0,
        })
        if len(entries) >= max_entries:
            break
    return {"path": path, "entries": entries, "count": len(entries)}


@server.tool(
    name="search_files",
    description="在文件中搜索关键词。返回匹配的文件列表及预览。",
    input_schema={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键词"},
            "path": {"type": "string", "description": "搜索路径", "default": "."},
            "extensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "文件扩展名过滤，如 ['.py', '.md']"
            },
            "max_results": {"type": "integer", "default": 20}
        },
        "required": ["keyword"]
    }
)
def search_files(keyword, path=".", extensions=None, max_results=20):
    results = []
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
                        preview = content[max(0, idx - 50):idx + 100]
                        results.append({
                            "path": fpath,
                            "matches": count,
                            "preview": preview.strip(),
                        })
            except Exception:
                continue
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break
    results.sort(key=lambda x: x["matches"], reverse=True)
    return {"results": results, "total": len(results), "keyword": keyword}


@server.tool(
    name="file_exists",
    description="检查文件或目录是否存在。",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "路径"}
        },
        "required": ["path"]
    }
)
def file_exists(path):
    return {
        "path": path,
        "exists": os.path.exists(path),
        "is_file": os.path.isfile(path),
        "is_dir": os.path.isdir(path),
    }


# ========== 启动 ==========

if __name__ == "__main__":
    if "--test" in sys.argv:
        print(f"[{server.name}] 工具列表:")
        for t in server.tools.values():
            print(f"  - {t.name}: {t.description}")

        # 测试读取当前文件
        result = read_file(__file__, max_lines=5)
        print(f"\n读取测试: {result['path']}, {result['lines']} lines")
        print("✅ 自测通过")
    else:
        server.run()
