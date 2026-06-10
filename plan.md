# Plan: deepin-agent-teams 全面改进计划 — 最终状态

> 基于 Agent Workshop W1-W6 课程知识的 Gap 分析，按 P0→P1→P2 四阶段 8 步执行
> 最后更新：2026-06-10

## 进度总览

- [x] Step 1: Plan-and-Solve 规划阶段 ✅
- [x] Step 2: 上下文管理 + 子Agent摘要回传 ✅
- [x] Step 3: 独立 Prompt 模板管理 ✅
- [x] Step 4: 并行扇出模式 ✅
- [x] Step 5: A2A 协议 + Agent Card ✅
- [x] Step 6: OpenTelemetry 标准化 ✅
- [x] Step 7: 场景识别 + 模型路由优化 ✅
- [x] Step 8: 文档更新 + 全量测试 ✅

## 测试结果

| 模块 | 测试结果 |
|------|---------|
| planner.py | 全部通过 |
| task_state_machine.py | 全部通过 |
| verifier.py | 全部通过（11 项检查） |
| context_manager.py | 全部通过（11 个测试） |
| prompt_loader.py | 全部通过（12 个测试） |
| debate.py | 全部通过（10 个测试） |
| scenario_classifier.py | 全部通过（15 个测试） |
| otel_tracer.py | 全部通过（15 个测试） |
| e2e 集成测试 | 40/41 通过（1 个是之前就有的降级逻辑问题） |

## 新增文件汇总

| 文件 | 说明 |
|------|------|
| agents/planner.py | Plan-and-Solve 规划模块 |
| agents/context_manager.py | 上下文窗口管理 |
| agents/prompt_loader.py | Prompt 模板管理 |
| agents/debate.py | 辩论模式 |
| agents/scenario_classifier.py | 场景识别器 |
| agents/otel_tracer.py | OpenTelemetry 封装 |
| agents/agent_cards/*.json | 7 个 Agent Card |
| prompts/**/*.md | 10 个 Prompt 模板 |

## 修改文件汇总

| 文件 | 改动 |
|------|------|
| agents/task_state_machine.py | 新增 PLANNING 状态 |
| agents/security_config.py | 新增 PLANNING 工具白名单 + 动态预算 |
| agents/verifier.py | 新增 Check 8-11 |
| agents/orchestrator.py | 集成 Planner + ContextWindow + PromptLoader + OTel Tracer + fan_out/aggregate |
| agents/content_creator.py | 迁移到 PromptLoader |
| agents/information_collector.py | 迁移到 PromptLoader |
| agents/registry.py | 新增 Agent Card 自动发现 |
| docs/ARCHITECTURE.md | 更新架构文档 |
| docs/QUALITY.md | 更新质量标准 |
