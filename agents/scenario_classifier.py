#!/usr/bin/env python3
"""
agents/scenario_classifier.py - 场景识别器

核心设计原则(来自 W6 Agent 评估课程):
1. 三道筛子判断是否适合 Agent 化
2. 不适合 Agent 的场景 → 直接走 LLM 对话,不进状态机
3. 场景复杂度决定模型选择(简单→lite,复杂→strong)

三道筛子:
  筛子 1:输入是否有模糊性?(非结构化→结构化)
  筛子 2:是否需要跨系统协调?(跨系统胶水)
  筛子 3:是否需要多步骤推理?(长链路任务)

三道都不过 → 直接 LLM 对话
任一道过了 → 进入 Agent 状态机

使用方式:
    classifier = ScenarioClassifier()
    result = classifier.classify("帮我分析项目代码结构")
    print(result.scenario_type)    # "code"
    print(result.agent_suitable)   # True
    print(result.complexity)       # "complex"
    print(result.recommended_model)  # "strong"
"""

import json
import os
import re
import sys
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AGENT_DIR)


# ============================================================
# 场景类型
# ============================================================

class ScenarioType(Enum):
    """场景类型"""
    EMAIL = "email"                  # 邮件撰写
    SYSTEM_FIX = "system_fix"       # 系统诊断修复
    CODE = "code"                    # 代码分析/生成
    SEARCH = "search"                # 信息检索
    FILE_OP = "file_op"             # 文件操作
    CHAT = "chat"                    # 闲聊/简单问答
    CONTENT = "content"              # 内容创作(报告/文档)
    UNKNOWN = "unknown"


class Complexity(Enum):
    """任务复杂度"""
    SIMPLE = "simple"      # 1 步可完成,lite 模型
    MODERATE = "moderate"  # 2-3 步,lite 或 strong
    COMPLEX = "complex"    # 4+ 步,strong 模型


# ============================================================
# 分类结果
# ============================================================

@dataclass
class ClassificationResult:
    """场景分类结果"""
    scenario_type: ScenarioType = ScenarioType.UNKNOWN
    agent_suitable: bool = False       # 是否适合 Agent 化
    complexity: Complexity = Complexity.SIMPLE
    recommended_model: str = "lite"    # "lite" / "strong"
    confidence: float = 0.0
    reasoning: str = ""                # 推理过程
    sieve_results: Dict[str, bool] = field(default_factory=dict)  # 三道筛子结果

    def to_dict(self) -> dict:
        return {
            "scenario_type": self.scenario_type.value,
            "agent_suitable": self.agent_suitable,
            "complexity": self.complexity.value,
            "recommended_model": self.recommended_model,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "sieve_results": self.sieve_results,
        }


# ============================================================
# 场景识别器
# ============================================================

# 关键词→场景映射
SCENARIO_KEYWORDS: Dict[ScenarioType, Dict] = {
    ScenarioType.EMAIL: {
        "keywords": ["发邮件", "写邮件", "发给", "email", "邮件", "告知", "通知", "写信",
                     "send email", "write email", "draft", "compose", "mail to", "send to"],
        "weight": 0.9,
    },
    ScenarioType.SYSTEM_FIX: {
        "keywords": ["连不上", "没声音", "坏了", "不行", "错误", "故障", "修复",
                     "can't", "not working", "error", "broken", "fix", "系统", "诊断",
                     "crash", "fail", "bug", "issue", "problem", "troubleshoot",
                     "debug", "repair", "diagnose", "service", "daemon"],
        "weight": 0.8,
    },
    ScenarioType.CODE: {
        "keywords": ["代码", "报错", "debug", "怎么写", "帮我改", "分析代码", "代码结构",
                     "error", "exception", "bug", "function", "函数", "类", "import",
                     "git", "commit", "分支", "merge",
                     "code", "analyze", "refactor", "implement", "class", "method",
                     "variable", "loop", "api", "endpoint", "database", "query",
                     "python", "java", "javascript", "typescript", "rust", "golang",
                     "compile", "build", "test", "run", "script", "algorithm"],
        "weight": 0.85,
    },
    ScenarioType.SEARCH: {
        "keywords": ["搜", "找", "查", "搜索", "search", "find", "look up",
                     "文献", "资料", "论文",
                     "research", "investigate", "lookup", "google", "browse"],
        "weight": 0.7,
    },
    ScenarioType.FILE_OP: {
        "keywords": ["文件", "目录", "读取", "写入", "创建", "删除", "移动", "复制",
                     "file", "directory", "read", "write", "create", "delete",
                     "move", "copy", "rename", "folder", "path", "open", "save"],
        "weight": 0.6,
    },
    ScenarioType.CONTENT: {
        "keywords": ["报告", "文档", "总结", "摘要", "写一篇", "生成", "撰写",
                     "report", "document", "summary", "write", "generate",
                     "draft", "article", "blog", "post", "presentation", "outline",
                     "summarize", "review", "translate"],
        "weight": 0.75,
    },
    ScenarioType.CHAT: {
        "keywords": ["你好", "谢谢", "帮个忙", "请问", "hi", "hello", "hey",
                     "thanks", "thank you", "please", "help", "what is",
                     "how to", "can you", "tell me", "explain"],
        "weight": 0.3,
    },
}

# 复杂度关键词
COMPLEXITY_SIGNALS = {
    "simple": {
        "patterns": [
            r"^(你好|谢谢|hi|hello|hey)",
            r"^(帮我|请).{0,10}(查|找|搜|看)",
            r"^(help me|can you|please).{0,15}(check|find|look|search)",
        ],
        "max_length": 20,
    },
    "moderate": {
        "patterns": [
            r"(分析|检查|诊断).{0,20}(代码|系统|文件)",
            r"(写|生成|撰写).{0,10}(邮件|报告|文档)",
            r"(analyze|check|diagnose).{0,20}(code|system|file)",
            r"(write|generate|create).{0,15}(email|report|document)",
            r"(explain|describe|tell me about)",
        ],
        "min_length": 15,
        "max_length": 100,
    },
    "complex": {
        "patterns": [
            r"(全面|完整|详细).{0,10}(分析|评估|审查)",
            r"(重构|优化|改进|升级).{0,20}(架构|系统|代码)",
            r"(对比|比较|选型).{0,15}(方案|技术|框架)",
            r"多.{0,5}(步骤|阶段|模块)",
            r"(comprehensive|full|detailed).{0,15}(analysis|review|audit)",
            r"(refactor|optimize|improve|upgrade).{0,20}(architecture|system|code)",
            r"(compare|contrast|evaluate).{0,15}(options|approaches|frameworks)",
            r"(multi.?step|end.?to.?end|full.?stack)",
        ],
        "min_length": 30,
    },
}


class ScenarioClassifier:
    """
    场景识别器

    三道筛子判断是否适合 Agent 化:
    1. 输入是否有模糊性?
    2. 是否需要跨系统协调?
    3. 是否需要多步骤推理?
    """

    def __init__(self, model_router: Any = None) -> None:
        self.model_router = model_router

    def classify(self, user_input: str, context: Dict = None) -> ClassificationResult:
        """
        分类用户输入

        Args:
            user_input: 用户输入文本
            context: 额外上下文(window_title, active_app 等)

        Returns:
            ClassificationResult
        """
        # Step 1: 场景类型识别
        scenario_type, scenario_confidence = self._identify_scenario(user_input)

        # Step 2: 三道筛子
        sieve_results = self._apply_sieves(user_input, scenario_type, context)
        agent_suitable = any(sieve_results.values())

        # Step 3: 复杂度评估
        complexity = self._assess_complexity(user_input, scenario_type)

        # Step 4: 模型推荐
        recommended_model = self._recommend_model(complexity, scenario_type)

        # 构建推理过程
        reasoning_parts = [
            f"场景: {scenario_type.value} (置信度 {scenario_confidence:.0%})",
            f"筛子: {sieve_results}",
            f"复杂度: {complexity.value}",
            f"推荐模型: {recommended_model}",
        ]

        result = ClassificationResult(
            scenario_type=scenario_type,
            agent_suitable=agent_suitable,
            complexity=complexity,
            recommended_model=recommended_model,
            confidence=scenario_confidence,
            reasoning=" | ".join(reasoning_parts),
            sieve_results=sieve_results,
        )

        return result

    def _identify_scenario(self, text: str) -> tuple:
        """
        识别场景类型

        Returns:
            (ScenarioType, confidence)
        """
        text_lower = text.lower()
        scores: Dict[ScenarioType, float] = {}

        for scenario, config in SCENARIO_KEYWORDS.items():
            score = 0
            matched = 0
            for kw in config["keywords"]:
                if kw in text_lower:
                    score += config["weight"]
                    matched += 1
            if matched > 0:
                # 多个关键词命中时取平均,再乘以基础权重
                scores[scenario] = min(score / matched, 1.0)

        if not scores:
            return ScenarioType.CHAT, 0.3  # 默认为闲聊

        best = max(scores, key=scores.get)
        return best, scores[best]

    def _apply_sieves(
        self, text: str, scenario: ScenarioType, context: Dict = None
    ) -> Dict[str, bool]:
        """
        三道筛子

        筛子 1:输入是否有模糊性?(非结构化→结构化)
        筛子 2:是否需要跨系统协调?(跨系统胶水)
        筛子 3:是否需要多步骤推理?(长链路任务)
        """
        context = context or {}
        results = {}
        text_lower = text.lower()

        # 筛子 1：模糊性检测
        ambiguity_signals = [
            len(text) > 30,
            "帮我" in text or "help me" in text_lower,
            any(c in text for c in ["?", "?"]),
            scenario in (ScenarioType.CODE, ScenarioType.SYSTEM_FIX, ScenarioType.CONTENT),
        ]
        results["ambiguity"] = sum(ambiguity_signals) >= 2

        # 筛子 2：跨系统需求
        cross_system_signals = [
            scenario == ScenarioType.CODE,
            scenario == ScenarioType.SYSTEM_FIX,
            scenario == ScenarioType.EMAIL,
            ("和" in text and "然后" in text) or ("and" in text_lower and "then" in text_lower),
            "同时" in text or "simultaneously" in text_lower or "at the same time" in text_lower,
        ]
        results["cross_system"] = sum(cross_system_signals) >= 1

        # 筛子 3：多步骤推理
        zh_step_words = [kw for kw in ["然后", "接着", "最后", "首先"] if kw in text]
        en_step_words = [kw for kw in ["then", "next", "finally", "first"] if kw in text_lower]
        multistep_signals = [
            len(text) > 50,
            any(kw in text for kw in ["全面", "完整", "详细", "深入"]),
            any(kw in text_lower for kw in ["comprehensive", "full", "detailed", "thorough", "in-depth"]),
            len(zh_step_words) >= 2 or len(en_step_words) >= 2,
            scenario in (ScenarioType.CODE, ScenarioType.CONTENT),
            context.get("complexity_hint") == "high",
        ]
        results["multistep"] = sum(multistep_signals) >= 1

        return results

    def _assess_complexity(self, text: str, scenario: ScenarioType) -> Complexity:
        """评估任务复杂度"""
        # 模式匹配(检查复杂→中等→简单,返回最高的匹配)
        for level in ["complex", "moderate", "simple"]:
            config = COMPLEXITY_SIGNALS.get(level, {})
            for pattern in config.get("patterns", []):
                if re.search(pattern, text):
                    return Complexity(level)

        # 基于长度的启发式
        text_len = len(text)
        if text_len < 20:
            return Complexity.SIMPLE
        elif text_len < 80:
            return Complexity.MODERATE
        else:
            return Complexity.COMPLEX

    def _recommend_model(self, complexity: Complexity, scenario: ScenarioType) -> str:
        """推荐模型"""
        # 复杂任务用 strong
        if complexity == Complexity.COMPLEX:
            return "strong"
        # 代码和系统诊断倾向 strong
        if scenario in (ScenarioType.CODE, ScenarioType.SYSTEM_FIX):
            return "strong"
        # 其他用 lite
        return "lite"

    def is_agent_suitable(self, user_input: str, context: Dict = None) -> bool:
        """
        快速判断是否适合 Agent 化

        比 classify() 更轻量,只返回 bool。
        """
        result = self.classify(user_input, context)
        return result.agent_suitable

    def get_model_for_task(self, user_input: str, context: Dict = None) -> str:
        """
        快速获取推荐模型

        Returns:
            "lite" 或 "strong"
        """
        result = self.classify(user_input, context)
        return result.recommended_model


# ============================================================
# 动态模型路由器
# ============================================================

class DynamicModelRouter:
    """
    动态模型路由器

    根据任务复杂度自动选择模型:
    - 简单任务(1步计划)→ ernie-lite
    - 复杂任务(3+步计划)→ ernie-3.5
    - 路由决策写入 trace

    使用方式:
        router = DynamicModelRouter(model_router=router)
        model = router.route("分析项目代码结构")
        # → "strong"

        # 或基于计划步数
        model = router.route_from_plan(steps_count=5)
        # → "strong"
    """

    def __init__(self, model_router: Any = None, classifier: ScenarioClassifier = None) -> None:
        self.model_router = model_router
        self.classifier = classifier or ScenarioClassifier()
        self._routing_log: List[Dict] = []

    def route(self, user_input: str, context: Dict = None) -> str:
        """
        根据用户输入路由到合适的模型

        Args:
            user_input: 用户输入
            context: 额外上下文

        Returns:
            "lite" 或 "strong"
        """
        result = self.classifier.classify(user_input, context)
        model = result.recommended_model

        self._log_routing(user_input[:50], model, result.complexity.value, result.scenario_type.value)
        return model

    def route_from_plan(self, steps_count: int) -> str:
        """
        根据计划步数路由

        Args:
            steps_count: 计划中的步骤数

        Returns:
            "lite" 或 "strong"
        """
        if steps_count <= 1:
            model = "lite"
        elif steps_count <= 3:
            model = "lite"  # 中等复杂度也用 lite,省成本
        else:
            model = "strong"  # 4+ 步用 strong

        self._log_routing(f"plan({steps_count}steps)", model, "plan_based", "")
        return model

    def route_from_task_type(self, task_type: str) -> str:
        """
        根据任务类型路由(兼容现有 MODEL_ROUTING 表)

        Args:
            task_type: 任务类型

        Returns:
            "lite" 或 "strong"
        """
        try:
            from config import MODEL_ROUTING
            level = MODEL_ROUTING.get(task_type, "lite")
            model = "strong" if level == "strong" else "lite"
        except ImportError:
            # 降级:基于场景类型推断
            scenario_map = {
                "code": "strong",
                "diagnosis": "strong",
                "email": "strong",
                "literature": "strong",
                "task_plan": "strong",
                "report": "strong",
                "intent": "lite",
                "summary": "lite",
                "classify": "lite",
                "general": "lite",
            }
            model = scenario_map.get(task_type, "lite")

        self._log_routing(f"type:{task_type}", model, "task_type", task_type)
        return model

    def _log_routing(self, input_summary: str, model: str, complexity: str, scenario: str):
        """记录路由决策"""
        entry = {
            "timestamp": time.time(),
            "input": input_summary,
            "model": model,
            "complexity": complexity,
            "scenario": scenario,
        }
        self._routing_log.append(entry)

    def get_routing_log(self) -> List[Dict]:
        """获取路由日志"""
        return list(self._routing_log)

    def get_stats(self) -> Dict[str, Any]:
        """获取路由统计"""
        total = len(self._routing_log)
        by_model = {}
        for entry in self._routing_log:
            m = entry["model"]
            by_model[m] = by_model.get(m, 0) + 1
        return {
            "total_routes": total,
            "by_model": by_model,
        }


# ============================================================
# 便捷工厂
# ============================================================

_global_classifier: Optional[ScenarioClassifier] = None


def get_classifier(model_router: Any = None) -> ScenarioClassifier:
    """获取全局场景分类器"""
    global _global_classifier
    if _global_classifier is None:
        _global_classifier = ScenarioClassifier(model_router=model_router)
    return _global_classifier


# ========== 单元测试 ==========

def _test():
    """ScenarioClassifier 模块测试"""
    print("\n=== ScenarioClassifier 单元测试 ===\n")

    classifier = ScenarioClassifier()

    # Test 1: 邮件场景
    print("Test 1: 邮件场景")
    r = classifier.classify("帮我写一封邮件给张三,通知他明天开会")
    assert r.scenario_type == ScenarioType.EMAIL
    assert r.agent_suitable == True
    print(f"  类型: {r.scenario_type.value}, 适合Agent: {r.agent_suitable}, 复杂度: {r.complexity.value}")
    print("  ✅ PASS\n")

    # Test 2: 代码场景
    print("Test 2: 代码场景")
    r = classifier.classify("帮我分析这个项目的代码结构,找出潜在的 bug")
    assert r.scenario_type == ScenarioType.CODE
    assert r.agent_suitable == True
    assert r.recommended_model == "strong"
    print(f"  类型: {r.scenario_type.value}, 模型: {r.recommended_model}")
    print("  ✅ PASS\n")

    # Test 3: 系统诊断场景
    print("Test 3: 系统诊断场景")
    r = classifier.classify("我的系统连不上网了,帮我诊断一下")
    assert r.scenario_type == ScenarioType.SYSTEM_FIX
    assert r.agent_suitable == True
    print(f"  类型: {r.scenario_type.value}, 适合Agent: {r.agent_suitable}")
    print("  ✅ PASS\n")

    # Test 4: 搜索场景
    print("Test 4: 搜索场景")
    r = classifier.classify("帮我搜一下 Python asyncio 的用法")
    assert r.scenario_type == ScenarioType.SEARCH
    print(f"  类型: {r.scenario_type.value}")
    print("  ✅ PASS\n")

    # Test 5: 闲聊场景
    print("Test 5: 闲聊场景")
    r = classifier.classify("你好")
    assert r.scenario_type == ScenarioType.CHAT
    # 闲聊的三道筛子应该都没过
    print(f"  类型: {r.scenario_type.value}, 适合Agent: {r.agent_suitable}, 筛子: {r.sieve_results}")
    print("  ✅ PASS\n")

    # Test 6: 复杂任务
    print("Test 6: 复杂任务")
    r = classifier.classify("请全面分析这个项目的代码架构,评估性能瓶颈,然后给出详细的优化方案和实施步骤")
    assert r.complexity == Complexity.COMPLEX
    assert r.recommended_model == "strong"
    print(f"  复杂度: {r.complexity.value}, 模型: {r.recommended_model}")
    print("  ✅ PASS\n")

    # Test 7: 简单任务
    print("Test 7: 简单任务")
    r = classifier.classify("帮我查一下天气")
    assert r.complexity == Complexity.SIMPLE
    assert r.recommended_model == "lite"
    print(f"  复杂度: {r.complexity.value}, 模型: {r.recommended_model}")
    print("  ✅ PASS\n")

    # Test 8: 三道筛子验证
    print("Test 8: 三道筛子")
    r = classifier.classify("帮我全面分析项目代码,然后生成详细的优化报告")
    assert r.sieve_results.get("ambiguity") == True  # 有模糊性
    assert r.sieve_results.get("multistep") == True  # 多步骤
    print(f"  筛子: {r.sieve_results}")
    print("  ✅ PASS\n")

    # Test 9: is_agent_suitable 快速判断
    print("Test 9: is_agent_suitable")
    assert classifier.is_agent_suitable("帮我分析代码") == True
    assert classifier.is_agent_suitable("你好") == False
    print("  ✅ PASS\n")

    # Test 10: get_model_for_task
    print("Test 10: get_model_for_task")
    assert classifier.get_model_for_task("全面分析代码架构和性能瓶颈") == "strong"
    assert classifier.get_model_for_task("帮我查一下天气") == "lite"
    print("  ✅ PASS\n")

    # Test 11: ClassificationResult 序列化
    print("Test 11: 序列化")
    r = classifier.classify("帮我写邮件通知大家明天开会")
    d = r.to_dict()
    assert "scenario_type" in d
    assert "agent_suitable" in d
    assert "sieve_results" in d
    print("  ✅ PASS\n")

    # Test 12: DynamicModelRouter
    print("Test 12: DynamicModelRouter")
    router = DynamicModelRouter(classifier=classifier)
    model = router.route("分析项目代码结构")
    assert model in ("lite", "strong")
    # 基于计划步数
    assert router.route_from_plan(1) == "lite"
    assert router.route_from_plan(5) == "strong"
    stats = router.get_stats()
    assert stats["total_routes"] == 3
    print(f"  路由统计: {stats}")
    print("  ✅ PASS\n")

    # Test 13: route_from_task_type
    print("Test 13: route_from_task_type")
    router2 = DynamicModelRouter()
    assert router2.route_from_task_type("code") == "strong"
    assert router2.route_from_task_type("intent") == "lite"
    assert router2.route_from_task_type("general") == "lite"
    print("  ✅ PASS\n")

    # Test 14: 内容创作场景
    print("Test 14: 内容创作场景")
    r = classifier.classify("帮我写一篇关于 AI 的技术报告")
    assert r.scenario_type == ScenarioType.CONTENT
    assert r.agent_suitable == True
    print(f"  类型: {r.scenario_type.value}, 适合Agent: {r.agent_suitable}")
    print("  ✅ PASS\n")

    # Test 15: 多步骤描述
    print("Test 15: 多步骤描述")
    r = classifier.classify("首先读取配置文件,然后修改数据库连接参数,最后重启服务")
    assert r.sieve_results.get("multistep") == True
    print(f"  筛子: {r.sieve_results}")
    print("  ✅ PASS\n")

    print("=== 所有 ScenarioClassifier 测试通过 ===\n")


if __name__ == "__main__":
    _test()
