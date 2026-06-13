#!/usr/bin/env python3
"""
测试结果分析脚本
============================================================
把 deepin 25 实体机上生成的 test_results_TIMESTAMP.json
拷到本目录，然后运行：
  python3 tests/analyze_results.py test_results_20260429_xxxxx.json

输出汇总分析报告。
============================================================
"""
import json
import sys
import os
from datetime import datetime

if len(sys.argv) < 2:
    print("用法: python3 analyze_results.py <test_results_*.json>")
    sys.exit(1)

json_file = sys.argv[1]
if not os.path.exists(json_file):
    print(f"文件不存在: {json_file}")
    sys.exit(1)

with open(json_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 过滤出JSON行（跳过注释行）
results = []
for line in lines:
    line = line.strip()
    if line.startswith("#") or line.startswith("-" * 20) or not line:
        continue
    try:
        results.append(json.loads(line))
    except Exception:
        continue

if not results:
    print("未找到有效测试结果")
    sys.exit(1)

passed = [r for r in results if r["passed"]]
failed = [r for r in results if not r["passed"]]

print("=" * 60)
print("deepin-agent-teams 感知层测试结果分析")
print("=" * 60)
print(f"测试时间: {results[0]['timestamp'] if results else 'N/A'}")
print(f"总计: ✅ {len(passed)} 通过 / ❌ {len(failed)} 失败\n")

# 按类别统计
print("--- 按类别 ---")
by_category = {}
for r in results:
    cat = r["category"]
    if cat not in by_category:
        by_category[cat] = []
    by_category[cat].append(r)

for cat, items in sorted(by_category.items()):
    cat_passed = [r for r in items if r["passed"]]
    cat_failed = [r for r in items if not r["passed"]]
    status = f"✅ {len(cat_passed)}/{len(items)}"
    if cat_failed:
        status += f" ⚠️ {len(cat_failed)}失败"
    print(f"  [{cat}] {status}")

# 失败详情
if failed:
    print("\n--- 失败项详情 ---")
    for r in failed:
        details = r.get("details", {})
        tool_info = ""
        if details.get("error") == "tool_not_found":
            tool_info = f" (工具未安装)"
        elif "trace" in details:
            # 只显示最后一行错误
            trace_lines = details["trace"].strip().split("\n")
            error_line = next((l.strip() for l in reversed(trace_lines) if l.strip()), "")
            tool_info = f"\n    错误: {error_line}"
        print(f"  ❌ [{r['category']}] {r['test']}{tool_info}")
        print(f"     消息: {r['message']}")

# 感知层准备度评估
print("\n--- deepin 25 感知层准备度评估 ---")
perception_cats = ["screen", "clipboard", "window", "system", "dbus", "ocr", "context"]
score_map = {}
for cat in perception_cats:
    if cat in by_category:
        items = by_category[cat]
        passed_count = sum(1 for r in items if r["passed"])
        total = len(items)
        score = passed_count / total * 100 if total > 0 else 0
        score_map[cat] = (score, passed_count, total)

# 关键感知能力
key_caps = {
    "screen": "截图",
    "clipboard": "剪贴板",
    "window": "窗口管理",
    "dbus": "D-Bus控制",
    "ocr": "屏幕OCR",
    "context": "意图识别",
}

for cap, name in key_caps.items():
    if cap in score_map:
        score, p, t = score_map[cap]
        if score == 100:
            status = "✅ 完全可用"
        elif score >= 50:
            status = "⚠️ 部分可用"
        else:
            status = "❌ 需修复"
        print(f"  {name:10s}: {status} ({p}/{t})")

print("\n" + "=" * 60)
