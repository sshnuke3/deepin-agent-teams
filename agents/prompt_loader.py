#!/usr/bin/env python3
"""
agents/prompt_loader.py — Prompt 模板管理模块

核心设计原则：
1. 从文件加载 prompt，变量替换用 {variable} 语法
2. 支持版本管理：prompts/v2/system_operator/base.md
3. 热加载：修改 prompt 文件后无需重启，下次调用自动加载最新版
4. A/B 测试：支持同时加载多个版本，按权重选择

使用方式：
    loader = PromptLoader("prompts/")

    # 加载并渲染
    prompt = loader.render("planner/plan_generation", task_description="分析代码")

    # 多版本 A/B 测试
    loader.register_ab_test("planner/plan_generation", ["v1", "v2"], weights=[0.7, 0.3])
    version, prompt = loader.render_ab("planner/plan_generation", task_description="分析代码")

    # 获取原始模板（不渲染）
    template = loader.get_template("orchestrator/decompose")
"""

import os
import sys
import re
import json
import time
import hashlib
import random
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_DIR)
DEFAULT_PROMPTS_DIR = os.path.join(PROJECT_ROOT, "prompts")


# ============================================================
# PromptTemplate — 单个模板
# ============================================================

@dataclass
class PromptTemplate:
    """单个 prompt 模板"""
    path: str               # 相对路径（如 "planner/plan_generation"）
    content: str            # 模板内容
    file_path: str          # 绝对文件路径
    last_modified: float    # 文件最后修改时间
    version: str = "v1"     # 版本号

    @property
    def variables(self) -> List[str]:
        """提取模板中的变量名（{name} 格式）"""
        return list(set(re.findall(r'\{(\w+)\}', self.content)))

    def render(self, **kwargs) -> str:
        """
        渲染模板

        替换所有 {variable} 占位符。缺失的变量保留原样。
        """
        result = self.content
        for var in self.variables:
            placeholder = "{" + var + "}"
            value = kwargs.get(var, placeholder)
            result = result.replace(placeholder, str(value))
        return result


# ============================================================
# A/B 测试配置
# ============================================================

@dataclass
class ABTestConfig:
    """A/B 测试配置"""
    prompt_path: str                # 基础 prompt 路径
    versions: List[str]             # 版本列表（["v1", "v2"]）
    weights: List[float] = field(default_factory=lambda: [0.5, 0.5])  # 权重
    call_count: int = 0             # 调用计数
    results: Dict[str, List[float]] = field(default_factory=dict)  # 各版本得分

    def pick_version(self) -> str:
        """按权重随机选择版本"""
        self.call_count += 1
        return random.choices(self.versions, weights=self.weights, k=1)[0]

    def record_score(self, version: str, score: float) -> None:
        """记录某版本的得分"""
        if version not in self.results:
            self.results[version] = []
        self.results[version].append(score)

    def get_summary(self) -> Dict[str, Any]:
        """获取 A/B 测试摘要"""
        summary = {}
        for v in self.versions:
            scores = self.results.get(v, [])
            summary[v] = {
                "count": len(scores),
                "avg_score": sum(scores) / len(scores) if scores else 0,
                "max_score": max(scores) if scores else 0,
                "min_score": min(scores) if scores else 0,
            }
        return summary


# ============================================================
# PromptLoader — 核心加载器
# ============================================================

class PromptLoader:
    """
    Prompt 模板加载器

    功能：
    1. 从文件加载 prompt 模板
    2. 变量替换（{variable} 语法）
    3. 版本管理（prompts/v2/...）
    4. 热加载（文件修改后自动重新加载）
    5. A/B 测试（多版本按权重选择）
    """

    def __init__(self, prompts_dir: str = None) -> None:
        """
        Args:
            prompts_dir: prompts 目录路径，默认 PROJECT_ROOT/prompts
        """
        self.prompts_dir = prompts_dir or DEFAULT_PROMPTS_DIR
        self._cache: Dict[str, PromptTemplate] = {}
        self._ab_tests: Dict[str, ABTestConfig] = {}

    def get_template(self, prompt_path: str, version: str = None) -> Optional[PromptTemplate]:
        """
        获取 prompt 模板（带缓存和热加载）

        Args:
            prompt_path: 相对路径，如 "planner/plan_generation"
            version: 版本号（如 "v2"），None 表示默认版本

        Returns:
            PromptTemplate 实例，文件不存在返回 None
        """
        # 构建实际文件路径
        if version:
            # 版本化路径：prompts/v2/planner/plan_generation.md
            file_name = f"{prompt_path}.md"
            file_path = os.path.join(self.prompts_dir, version, file_name)
            cache_key = f"{version}/{prompt_path}"
        else:
            # 默认路径：prompts/planner/plan_generation.md
            file_path = os.path.join(self.prompts_dir, f"{prompt_path}.md")
            cache_key = prompt_path

        # 检查文件是否存在
        if not os.path.isfile(file_path):
            # 降级：尝试不带 version
            if version:
                return self.get_template(prompt_path, version=None)
            print(f"[PromptLoader] 模板不存在: {file_path}")
            return None

        # 获取文件修改时间
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            return None

        # 缓存命中 + 热加载检查
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached.last_modified >= mtime:
                return cached  # 缓存有效
            # 文件已修改，重新加载
            print(f"[PromptLoader] 热加载: {cache_key}")

        # 从文件加载
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
        except Exception as e:
            print(f"[PromptLoader] 加载失败: {file_path}: {e}")
            return None

        template = PromptTemplate(
            path=prompt_path,
            content=content,
            file_path=file_path,
            last_modified=mtime,
            version=version or "v1",
        )
        self._cache[cache_key] = template
        return template

    def render(self, prompt_path: str, version: str = None, **kwargs) -> str:
        """
        加载并渲染 prompt 模板

        Args:
            prompt_path: 相对路径
            version: 版本号
            **kwargs: 模板变量

        Returns:
            渲染后的 prompt 字符串
        """
        template = self.get_template(prompt_path, version=version)
        if template is None:
            return f"(模板不存在: {prompt_path})"

        return template.render(**kwargs)

    def render_system_user(
        self,
        system_path: str,
        user_path: str = None,
        system_version: str = None,
        user_version: str = None,
        **kwargs,
    ) -> List[Dict[str, str]]:
        """
        加载 system + user prompt 模板，返回 messages 格式

        Args:
            system_path: system prompt 路径
            user_path: user prompt 路径（可选）
            **kwargs: 模板变量

        Returns:
            [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        """
        messages = []

        system_content = self.render(system_path, version=system_version, **kwargs)
        if system_content:
            messages.append({"role": "system", "content": system_content})

        if user_path:
            user_content = self.render(user_path, version=user_version, **kwargs)
            if user_content:
                messages.append({"role": "user", "content": user_content})

        return messages

    # ==================== A/B 测试 ====================

    def register_ab_test(
        self,
        prompt_path: str,
        versions: List[str],
        weights: List[float] = None,
    ) -> None:
        """
        注册 A/B 测试

        Args:
            prompt_path: 基础 prompt 路径
            versions: 版本列表
            weights: 权重（默认均匀分布）
        """
        if weights is None:
            weights = [1.0 / len(versions)] * len(versions)

        assert len(versions) == len(weights), "versions 和 weights 长度必须一致"
        assert abs(sum(weights) - 1.0) < 0.01, "weights 之和必须为 1.0"

        self._ab_tests[prompt_path] = ABTestConfig(
            prompt_path=prompt_path,
            versions=versions,
            weights=weights,
        )
        print(f"[PromptLoader] A/B 测试注册: {prompt_path} → {versions} (weights={weights})")

    def render_ab(self, prompt_path: str, **kwargs) -> Tuple[str, str]:
        """
        A/B 测试渲染

        按权重随机选择版本，返回 (version, rendered_prompt)。

        Args:
            prompt_path: prompt 路径
            **kwargs: 模板变量

        Returns:
            (version, rendered_prompt)
        """
        config = self._ab_tests.get(prompt_path)
        if config is None:
            # 未注册 A/B 测试，使用默认版本
            return ("default", self.render(prompt_path, **kwargs))

        version = config.pick_version()
        rendered = self.render(prompt_path, version=version, **kwargs)
        return (version, rendered)

    def record_ab_score(self, prompt_path: str, version: str, score: float) -> None:
        """记录 A/B 测试得分"""
        config = self._ab_tests.get(prompt_path)
        if config:
            config.record_score(version, score)

    def get_ab_summary(self, prompt_path: str) -> Optional[Dict]:
        """获取 A/B 测试摘要"""
        config = self._ab_tests.get(prompt_path)
        if config:
            return config.get_summary()
        return None

    def list_ab_tests(self) -> Dict[str, Dict]:
        """列出所有 A/B 测试"""
        return {
            path: {
                "versions": config.versions,
                "weights": config.weights,
                "call_count": config.call_count,
            }
            for path, config in self._ab_tests.items()
        }

    # ==================== 工具方法 ====================

    def list_templates(self) -> List[str]:
        """列出所有可用的模板"""
        templates = []
        prompts_dir = Path(self.prompts_dir)

        for md_file in prompts_dir.rglob("*.md"):
            # 跳过版本目录
            rel = md_file.relative_to(prompts_dir)
            parts = rel.parts
            if parts[0].startswith("v") and parts[0][1:].isdigit():
                # 版本目录下的文件，跳过（以默认版本为准）
                continue
            # 去掉 .md 后缀
            template_path = str(rel.with_suffix(""))
            templates.append(template_path)

        return sorted(templates)

    def invalidate_cache(self, prompt_path: str = None) -> None:
        """
        清除缓存

        Args:
            prompt_path: 指定路径清除，None 表示全部清除
        """
        if prompt_path is None:
            self._cache.clear()
            print("[PromptLoader] 缓存全部清除")
        elif prompt_path in self._cache:
            del self._cache[prompt_path]
            print(f"[PromptLoader] 缓存清除: {prompt_path}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "cached_templates": len(self._cache),
            "templates": list(self._cache.keys()),
            "ab_tests": len(self._ab_tests),
        }


# ============================================================
# 全局单例
# ============================================================

_global_loader: Optional[PromptLoader] = None


def get_loader(prompts_dir: str = None) -> PromptLoader:
    """获取全局 PromptLoader 实例（单例模式）"""
    global _global_loader
    if _global_loader is None:
        _global_loader = PromptLoader(prompts_dir)
    return _global_loader


# ========== 单元测试 ==========

def _test():
    """PromptLoader 模块测试"""
    print("\n=== PromptLoader 单元测试 ===\n")

    # 使用实际的 prompts 目录
    loader = PromptLoader()

    # Test 1: 列出所有模板
    print("Test 1: 列出模板")
    templates = loader.list_templates()
    assert len(templates) > 0, f"应至少有 1 个模板，实际 {len(templates)}"
    print(f"  找到 {len(templates)} 个模板: {templates}")
    print("  ✅ PASS\n")

    # Test 2: 加载 planner 模板
    print("Test 2: 加载 planner 模板")
    template = loader.get_template("planner/plan_generation")
    assert template is not None
    assert "任务规划专家" in template.content
    assert "steps" in template.content
    print(f"  变量: {template.variables}")
    print("  ✅ PASS\n")

    # Test 3: 渲染 orchestrator/decompose 模板
    print("Test 3: 渲染 decompose 模板")
    rendered = loader.render(
        "orchestrator/decompose",
        user_request="分析项目代码",
        tools_section="可用工具列表...",
    )
    assert "分析项目代码" in rendered
    assert "可用工具列表..." in rendered
    assert "{user_request}" not in rendered  # 变量应被替换
    print("  ✅ PASS\n")

    # Test 4: 渲染 content_creator/email 模板
    print("Test 4: 渲染 email 模板")
    rendered = loader.render(
        "content_creator/email",
        context_text="项目进度：已完成 80%",
    )
    assert "项目进度：已完成 80%" in rendered
    assert "收件人" in rendered
    print("  ✅ PASS\n")

    # Test 5: 渲染 information_collector/summarize 模板
    print("Test 5: 渲染 summarize 模板")
    rendered = loader.render(
        "information_collector/summarize",
        max_length=200,
        content="这是一段很长的内容...",
    )
    assert "200" in rendered
    assert "这是一段很长的内容..." in rendered
    print("  ✅ PASS\n")

    # Test 6: 渲染 agents/researcher 模板
    print("Test 6: 渲染 agent 模板")
    rendered = loader.render("agents/researcher")
    assert "Researcher Agent" in rendered
    assert "信息检索" in rendered
    print("  ✅ PASS\n")

    # Test 7: render_system_user
    print("Test 7: render_system_user")
    messages = loader.render_system_user(
        system_path="orchestrator/system",
        user_path="orchestrator/integrate",
        user_request="测试需求",
        plan_json='{"tasks": []}',
        results_text="结果文本",
    )
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "测试需求" in messages[1]["content"]
    print("  ✅ PASS\n")

    # Test 8: 不存在的模板
    print("Test 8: 不存在的模板")
    result = loader.render("nonexistent/template")
    assert "不存在" in result
    print("  ✅ PASS\n")

    # Test 9: A/B 测试
    print("Test 9: A/B 测试")
    # 创建临时 v2 版本
    v2_dir = os.path.join(loader.prompts_dir, "v2", "planner")
    os.makedirs(v2_dir, exist_ok=True)
    v2_path = os.path.join(v2_dir, "plan_generation.md")
    with open(v2_path, 'w') as f:
        f.write("你是高级任务规划专家 V2。给定任务描述，拆解为步骤。\n输出严格 JSON。")

    loader.register_ab_test(
        "planner/plan_generation",
        versions=["v1", "v2"],
        weights=[0.7, 0.3],
    )

    # 多次调用，统计版本分布
    version_counts = {"v1": 0, "v2": 0}
    for _ in range(100):
        version, rendered = loader.render_ab(
            "planner/plan_generation",
            task_description="测试",
        )
        version_counts[version] = version_counts.get(version, 0) + 1

    # v1 应该比 v2 多（权重 0.7 vs 0.3）
    assert version_counts["v1"] > version_counts["v2"], f"v1={version_counts['v1']}, v2={version_counts['v2']}"
    print(f"  版本分布: v1={version_counts['v1']}, v2={version_counts['v2']}")

    # 记录分数
    loader.record_ab_score("planner/plan_generation", "v1", 0.8)
    loader.record_ab_score("planner/plan_generation", "v2", 0.9)
    summary = loader.get_ab_summary("planner/plan_generation")
    assert summary is not None
    assert "v1" in summary
    assert "v2" in summary
    print(f"  A/B 摘要: {summary}")

    # 清理
    os.remove(v2_path)
    os.rmdir(v2_dir)
    # 确保上级目录也被清理
    try:
        parent = os.path.dirname(v2_dir)
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    except OSError:
        pass

    print("  ✅ PASS\n")

    # Test 10: 热加载
    print("Test 10: 热加载")
    # 创建临时模板
    test_path = os.path.join(loader.prompts_dir, "test_hot_reload.md")
    with open(test_path, 'w') as f:
        f.write("版本1: {var}")

    t1 = loader.get_template("test_hot_reload")
    assert t1 is not None
    assert "版本1" in t1.content
    v1_rendered = loader.render("test_hot_reload", var="测试")
    assert "版本1" in v1_rendered

    # 修改文件
    time.sleep(0.1)  # 确保 mtime 不同
    with open(test_path, 'w') as f:
        f.write("版本2: {var}")

    loader.invalidate_cache("test_hot_reload")
    t2 = loader.get_template("test_hot_reload")
    assert t2 is not None
    assert "版本2" in t2.content
    v2_rendered = loader.render("test_hot_reload", var="测试")
    assert "版本2" in v2_rendered

    # 清理
    os.remove(test_path)
    print("  ✅ PASS\n")

    # Test 11: 缓存统计
    print("Test 11: 缓存统计")
    stats = loader.get_cache_stats()
    assert stats["cached_templates"] > 0
    print(f"  缓存: {stats}")
    print("  ✅ PASS\n")

    # Test 12: list_ab_tests
    print("Test 12: A/B 测试列表")
    ab_list = loader.list_ab_tests()
    # 已经在 Test 9 中清理了，所以应该是空的
    # 但我们之前注册过，检查一下
    print(f"  A/B 测试: {ab_list}")
    print("  ✅ PASS\n")

    print("=== 所有 PromptLoader 测试通过 ===\n")


if __name__ == "__main__":
    _test()
