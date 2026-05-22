#!/usr/bin/env python3
"""
tools/analyze_capabilities.py - Worker 能力正交化分析工具

分析项目中的 capability 分布，找出：
1. 重叠能力（多个 Worker 都实现了）
2. 缺失能力（被调用但未实现）
3. 孤立能力（实现了但从未被调用）
4. 能力签名冲突（同名能力实现不一致）
"""
import os
import sys
import json
import re
import glob
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_capability_definitions(base_dir: str) -> dict:
    """
    扫描所有 Worker 实现，找到 capability 定义和实现

    Returns:
        {
            "file_reader": {
                "file": "agents/worker_base.py",
                "method": "_read_file",
                "line": 103,
                "error_handling": True,  # 是否有 try/except
                "timeout": True,          # 是否有 timeout
            },
            ...
        }
    """
    capabilities = {}
    patterns = [
        # lambda 形式注册
        r'"(\w+)"\s*:\s*lambda\s+p[^:]*:\s*self\.(_[\w]+)\s*\(',
        # 方法定义
        r'def\s+(_[\w]+)\s*\(',
    ]

    for py_file in glob.glob(os.path.join(base_dir, "agents", "*.py")):
        if "__init__" in py_file:
            continue

        with open(py_file) as f:
            content = f.read()
            lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # lambda 注册: "cap_name": lambda p: self._cap_method
            m = re.match(r'\s+"(\w+)"\s*:\s*lambda\s+[^:]+:\s*self\.(_[\w]+)\s*\(', line)
            if m:
                cap_name = m.group(1)
                method_name = m.group(2)
                cap_info = {
                    "file": os.path.basename(py_file),
                    "line": i,
                    "method": method_name,
                    "style": "lambda_register",
                    "error_handling": _has_try_except(content, method_name),
                    "timeout": _has_timeout(content, method_name),
                }
                if cap_name in capabilities:
                    capabilities[cap_name]["overlaps"].append(cap_info)
                else:
                    capabilities[cap_name] = {"implementations": [cap_info], "overlaps": []}

            # 方法定义 def _cap_name
            m = re.match(r'\s+def\s+(_[\w]+)\s*\(', line)
            if m:
                method_name = m.group(1)
                cap_name = method_name  # 推断 capability 名
                # 检查是否有 error handling
                has_error = _has_try_except(content, method_name)
                has_timeout = _has_timeout(content, method_name)

    return capabilities


def _has_try_except(content: str, method_name: str) -> bool:
    """检查方法是否有 try/except"""
    pattern = rf'def\s+{re.escape(method_name)}\b[^:]+:(.*?)(?=\n    def |\nclass |\Z)'
    m = re.search(pattern, content, re.DOTALL)
    if m:
        return "except" in m.group(1)
    return False


def _has_timeout(content: str, method_name: str) -> bool:
    """检查方法是否有 timeout 处理"""
    pattern = rf'def\s+{re.escape(method_name)}\b[^:]+:(.*?)(?=\n    def |\nclass |\Z)'
    m = re.search(pattern, content, re.DOTALL)
    if m:
        method_body = m.group(1)
        return any(kw in method_body for kw in ["timeout", "Timeout", "TIMEOUT"])
    return False


def find_capability_usage(base_dir: str) -> dict:
    """
    扫描所有文件，找到 capability 的调用点

    Returns:
        {
            "file_reader": [{"file": "...", "line": N, "context": "..."}],
            ...
        }
    """
    usage = defaultdict(list)

    patterns = [
        r'capabilities_needed["\']?\s*:\s*\[(.*?)\]',  # capabilities_needed: [...]
        r'capabilities\s*=\s*\[(.*?)\]',                 # capabilities = [...]
        r'"(\w+)"\s*(?:in|,)\s*(?:caps|needed)',        # "web_search" in caps
        r'"(\w+)"\s*(?:in|,)\s*(?:capabilities)',        # "web_search" in capabilities
    ]

    for py_file in glob.glob(os.path.join(base_dir, "**/*.py"), recursive=True):
        if "__pycache__" in py_file:
            continue

        with open(py_file) as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            for pattern in patterns:
                matches = re.findall(pattern, line)
                for m in matches:
                    cap_name = m if isinstance(m, str) else m[0] if isinstance(m, tuple) else None
                    if cap_name and cap_name.isidentifier():
                        usage[cap_name].append({
                            "file": os.path.relpath(py_file, base_dir),
                            "line": i,
                            "context": line.strip()[:80],
                        })

    return usage


def analyze_orthogonality(capabilities: dict, usage: dict) -> dict:
    """
    正交化分析：
    - 重叠能力（多个 Worker 实现了）
    - 缺失能力（被调用但未实现）
    - 孤立能力（实现了但从未被调用）
    - 能力签名冲突
    """
    results = {
        "overlaps": [],       # 多个 Worker 实现了同一个 capability
        "missing": [],        # 被调用但没有实现
        "orphaned": [],       # 实现了但从未被调用
        "well_defined": [],   # 恰好有一个实现且被使用
    }

    # 找重叠（capabilities 中 overlaps 非空）
    for cap_name, cap_data in capabilities.items():
        impls = cap_data.get("implementations", [])
        if len(impls) > 1:
            results["overlaps"].append({
                "capability": cap_name,
                "implementations": impls,
                "used_by": usage.get(cap_name, []),
            })

    # 找缺失（被使用但没有实现）
    for cap_name, use_list in usage.items():
        if cap_name not in capabilities:
            results["missing"].append({
                "capability": cap_name,
                "usage": use_list,
            })

    # 找孤立（实现了但从未被使用）
    for cap_name, cap_data in capabilities.items():
        impls = cap_data.get("implementations", [])
        if cap_name not in usage or not usage[cap_name]:
            results["orphaned"].append({
                "capability": cap_name,
                "implementations": impls,
            })

    # 定义良好（有实现且被使用，且不重叠）
    for cap_name in capabilities:
        if cap_name in usage and cap_name not in [o["capability"] for o in results["overlaps"]]:
            impls = capabilities[cap_name].get("implementations", [])
            if impls:
                results["well_defined"].append({
                    "capability": cap_name,
                    "implementations": impls,
                })

    return results


def print_report(results: dict):
    print(f"\n{'='*50}")
    print("Worker 能力正交化分析报告")
    print(f"{'='*50}\n")

    # Overlaps
    if results["overlaps"]:
        print(f"⚠️  重叠能力（{len(results['overlaps'])} 个）：多个 Worker 实现了同一个 capability")
        for item in results["overlaps"]:
            print(f"\n  {item['capability']}:")
            for impl in item["implementations"]:
                print(f"    - {impl['file']}::{impl['method']} (line {impl['line']})")
            if item["used_by"]:
                print(f"    被调用于: {item['used_by'][0]['file']}:{item['used_by'][0]['line']}")
    else:
        print("✅ 无重叠能力")

    # Missing
    if results["missing"]:
        print(f"\n\n❌ 缺失能力（{len(results['missing'])} 个）：被调用但未实现")
        for item in results["missing"]:
            print(f"\n  {item['capability']}:")
            for u in item["usage"][:3]:
                print(f"    - {u['file']}:{u['line']} → {u['context'][:60]}")
    else:
        print("\n\n✅ 无缺失能力")

    # Orphaned
    if results["orphaned"]:
        print(f"\n\n🔵 孤立能力（{len(results['orphaned'])} 个）：实现了但从未被调用")
        for item in results["orphaned"]:
            impl = item["implementations"][0]
            print(f"  {item['capability']} → {impl['file']}::{impl['method']}")
    else:
        print("\n\n✅ 无孤立能力（所有实现的能力都被使用）")

    # Well-defined
    print(f"\n\n✅ 定义良好的能力（{len(results['well_defined'])} 个）：唯一实现 + 正在使用")
    for item in results["well_defined"]:
        impl = item["implementations"][0]
        print(f"  {item['capability']} → {impl['file']}::{impl['method']}")

    print(f"\n{'='*50}\n")


def main():
    print("\n=== Worker 能力正交化分析 ===\n")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("扫描 capability 定义...")
    capabilities = find_capability_definitions(base_dir)
    print(f"找到 {len(capabilities)} 个能力定义")

    print("扫描 capability 使用...")
    usage = find_capability_usage(base_dir)
    print(f"找到 {len(usage)} 种能力被调用")

    results = analyze_orthogonality(capabilities, usage)
    print_report(results)

    # 输出 JSON 摘要
    summary = {
        "total_defined": len(capabilities),
        "total_used": len(usage),
        "overlap_count": len(results["overlaps"]),
        "missing_count": len(results["missing"]),
        "orphaned_count": len(results["orphaned"]),
        "health_score": f"{len(results['well_defined'])}/{len(capabilities)} capabilities well-defined",
    }
    print("摘要:", json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()