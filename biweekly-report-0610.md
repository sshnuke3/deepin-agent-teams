# 文心伙伴赛道-进阶双周报（第3期 / 终期）

**邮件标题格式：** 文心伙伴赛道-【统信】-进阶双周报-【sshnuke3】-0610

---

### 认领者 GitHub ID
sshnuke3

### 赛题信息
- **进阶任务序号**：#27
- **赛题名称**：基于统信操作系统与文心大模型的多智能体协作系统
- **关联厂商**：统信软件

### 本期工作（2026.05.28 ~ 2026.06.10）

本期基于 Agent Workshop W1-W6 课程知识，对项目进行了 8 项系统性架构改进，全面提升工程质量与学术规范性。

---

#### 1. Plan-and-Solve 规划阶段（6月7日）✅

**对应 Workshop**：W3 — Plan-and-Solve Prompting

- 新增 `agents/planner.py`（约 280 行），实现结构化任务规划
- 状态机从 7 状态扩展为 **8 状态**，新增 PLANNING 状态
  - PLANNING 插入 CLAIMED 和 RUNNING 之间
  - 工具白名单为空（纯推理），Token 预算 800
  - 超时 30 秒自动降级
- Planner 核心能力：
  - `create_plan()` — 生成 TodoManager 格式的步骤计划
  - `update_step()` — 标记步骤状态（pending → in_progress → done）
  - `get_progress()` — 返回完成百分比
  - nag reminder — 步骤超时自动提醒
- Verifier 新增 Check 8（plan_completeness）+ Check 9（plan_coherence）
  - 验证所有步骤标记完成
  - DFS 检测循环依赖
- 相关提交：`c99a05f`

#### 2. 上下文管理 + 子Agent摘要回传（6月7日）✅

**对应 Workshop**：W4 — Context Window Management

- 新增 `agents/context_manager.py`（约 320 行），解决多轮对话上下文膨胀问题
- **滑动窗口策略**：保留最近 K 轮完整对话（默认 10 轮），早期压缩为摘要
- **子Agent摘要回传**：Worker 执行完毕后只回传压缩摘要，不注入原始对话
  - 摘要格式：结论 + 关键发现 + 未完成项 + 耗时
  - 避免父 Agent 上下文被子 Agent 对话撑爆
- **动态 Token 预算**：`budget = base_budget + per_step_budget * remaining_steps`
- Verifier 新增 Check 10（context_overflow）+ Check 11（summary_quality）
- 相关提交：`c99a05f`

#### 3. 独立 Prompt 模板管理（6月7日）✅

**对应 Workshop**：W5 — Prompt Engineering Best Practices

- 新增 `agents/prompt_loader.py`（约 200 行）+ `prompts/` 目录（10 个 .md 模板）
- **热加载**：修改 `.md` 文件后下次调用自动生效（mtime 检测），无需重启
- **A/B 测试**：`loader.register_ab_test(path, ["v1", "v2"], weights=[0.7, 0.3])`
  - 按权重随机选择模板版本
  - 记录每个版本的得分，用于后续优化
- **向后兼容**：PromptLoader 不可用时降级到硬编码 prompt
- 迁移的 prompt：
  - `prompts/planner/plan_generation.md`
  - `prompts/orchestrator/decompose.md` / `integrate.md` / `system.md`
  - `prompts/content_creator/email.md` / `summary.md`
  - `prompts/information_collector/summarize.md`
  - `prompts/agents/researcher.md` / `coder.md` / `general.md`
- 相关提交：`c99a05f`

#### 4. 并行扇出模式 + 辩论模式（6月8日）✅

**对应 Workshop**：W4 — Multi-Agent Orchestration Patterns

- **fan_out()**：ThreadPoolExecutor 并行执行多个子任务
  - `orchestrator.fan_out(tasks, max_workers=4)`
  - 自动收集每个子任务的结果
- **aggregate()**：4 种聚合策略
  - `concat` — 拼接所有结果
  - `vote` — 多数投票
  - `best` — 取最高置信度
  - `merge` — 深度合并
- **辩论模式** (`agents/debate.py`, 约 340 行)
  - Pro（正方）→ Con（反方）→ Pro 回应 → Con 再反驳 → Judge 裁决
  - 用于技术方案选型等需要正反论证的决策场景
  - Judge 输出：winner / decision / confidence / reasoning
- 相关提交：`45ceb85`

#### 5. A2A 协议 + Agent Card（6月8日）✅

**对应 Workshop**：W6 — Agent Interoperability

- 新增 7 个 Agent Card（JSON 格式）：system_operator / content_creator / information_collector / coder / researcher / lead / general_worker
- 每个 Card 包含：name / version / description / capabilities / agent_type / security_level / model_preference
- `AgentRegistry.auto_discover()` 扫描 `agent_cards/` 目录自动注册
- 支持按类型查找：`find_agent_by_type("coder")`
- 相关提交：`45ceb85`

#### 6. OpenTelemetry 标准化（6月8日）✅

**对应 Workshop**：W5 — Observability & Tracing

- 新增 `agents/otel_tracer.py`（约 350 行），封装 OpenTelemetry SDK
- **降级策略**：OTel SDK 不可用时自动回退到 `metrics_collector.py`，API 签名一致
- **5 种关键 Span**：
  - `task_execution` — 整个任务执行（agent.task.id, agent.task.type）
  - `llm_call` — LLM 调用（gen_ai.system, gen_ai.request.model）
  - `tool_call` — 工具调用（agent.tool.name, agent.tool.params）
  - `state_transition` — 状态机跳转（agent.state.from, agent.state.to）
  - `agent_loop` — Agent Loop 迭代（agent.loop.iteration）
- **GenAI 语义约定**：使用 `gen_ai.*` 属性名（OpenLLMetry 兼容）
- orchestrator.py 集成：每个 task 执行和 LLM 调用自动创建 Span
- 相关提交：`45ceb85`

#### 7. 场景识别 + 动态模型路由（6月8日）✅

**对应 Workshop**：W2 — Intent Recognition & Routing

- 新增 `agents/scenario_classifier.py`（约 280 行）
- **三道筛子**判断是否适合 Agent 化：
  1. **模糊性筛**：输入是否有多种理解方式？
  2. **跨系统筛**：是否需要多个工具/系统配合？
  3. **多步骤筛**：是否需要分解为多个子步骤？
- 三道都不过 → 直接 LLM 对话，不进状态机（节省资源）
- **DynamicModelRouter**：基于场景分类结果动态选择 lite/strong
  - 复杂度匹配：complex → moderate → simple（从高到低返回首个匹配）
  - `router.route("全面分析代码架构")` → `"strong"`
  - `router.route("帮我查天气")` → `"lite"`
- 相关提交：`45ceb85`

#### 8. 文档全面更新 + 测试完善（6月8-10日）✅

**文档更新：**
- `docs/ARCHITECTURE.md` — 从 10 章扩展到 **14 章**，新增 PLANNING 状态、上下文管理、Prompt 模板、可观测性、Agent Card 等章节
- `docs/QUALITY.md` — 验证检查从 7 项扩展到 **11 项**
- `docs/TECH_DECISIONS.md` — 新增 8 个技术选型条目
- `README.md` — 目录结构、状态机、Verifier、测试、赛题完成度表全面更新
- `TECHNICAL_REPORT.md` — 统计数据更新 + 新增第 10 章 Workshop 改进
- `PLAN.md` — 标记归档，指向 plan.md（最终状态）

**测试完善：**
- 修复 `test_decompose_fallback`：mock `_call_llm` 返回 None，避免环境中有 LLM 时走错路径
- 集成测试从 40/41 提升到 **41/41 全部通过**
- 新增 `tests/benchmark.py`：8 模块性能基准测试

**代码统计（更新）：**

| 指标 | 数值 |
|------|------|
| Python 文件 | 77 个 |
| Python 代码行数 | ~25,800 行 |
| JSON 文件 | 8 个（Agent Card） |
| Prompt 模板 | 10 个 .md 文件 |

**相关提交：** `c99a05f` `45ceb85` `1222d4b` `3325cf3`

---

### 性能基准测试结果

| 模块 | ops/s | 平均延迟 | P99 延迟 |
|------|-------|---------|---------|
| DebateJudge.judge | 152,986 | 0.007ms | 0.013ms |
| Tracer.span | 112,498 | 0.009ms | 0.020ms |
| PromptLoader.render | 104,205 | 0.010ms | 0.022ms |
| Planner.create_plan | 97,952 | 0.010ms | 0.019ms |
| ScenarioClassifier | ~52,000 | 0.019ms | 0.032ms |
| Verifier.verify (11项) | 51,787 | 0.019ms | 0.050ms |
| ContextWindow.add+get | 21,632 | 0.046ms | 0.305ms |
| StateMachine.lifecycle | 4,146 | 0.241ms | 0.476ms |

> 以上为纯 CPU 基准，零 LLM 调用。所有模块均在万级 ops/s 以上。

---

### 本期代码变更统计

| 指标 | 数值 |
|------|------|
| 新增文件 | 28 个（8 个 Python 模块 + 7 个 Agent Card + 10 个 Prompt 模板 + 1 个 benchmark + 2 个文档） |
| 修改文件 | 14 个（orchestrator / verifier / security_config / registry / content_creator / information_collector / planner / task_state_machine / e2e test / 4 个文档） |
| 新增行数 | +5,329 行 |
| Git 提交 | 4 个（`c99a05f` → `45ceb85` → `1222d4b` → `3325cf3`） |

### 测试覆盖

| 测试套件 | 结果 |
|---------|------|
| test_e2e.py（集成测试） | **41/41 通过** |
| planner.py（单元测试） | **9/9 通过** |
| task_state_machine.py | **12/12 通过** |
| verifier.py（11项检查） | **19/19 通过** |
| context_manager.py | **11/11 通过** |
| prompt_loader.py | **12/12 通过** |
| debate.py | **10/10 通过** |
| scenario_classifier.py | **15/15 通过** |
| otel_tracer.py | **15/15 通过** |
| benchmark.py（性能基准） | **8/8 模块通过** |

### 当前阻塞

无。

### 赛题完成度自查（终版更新于 2026-06-10）

| 阶段 | 要求 | 状态 |
|------|------|:----:|
| 一、多模态环境感知 | 屏幕截图+OCR+窗口+剪贴板+D-Bus+系统监控+行为追踪+意图置信度 | ✅ |
| 一、复杂意图识别 | 多轮对话+跨应用上下文+意图置信度+场景识别三道筛子 | ✅ |
| 二、状态机引擎 | **8 状态**+代码写死跳转+trace 可追溯+PLANNING 规划阶段 | ✅ |
| 二、独立 Verifier | **11 项检查**+独立世界观+PASS/FAIL/RETRY | ✅ |
| 二、Checkpoint 恢复 | 中断后从 checkpoint 恢复，不整体重来 | ✅ |
| 二、智能体团队 | Lead+Researcher+Coder+Operator+Collector+Creator + 7 种 Agent Card | ✅ |
| 二、动态编排 | 任务拆解+分配+交接+冲突解决+结果汇总+**并行扇出**+**辩论模式** | ✅ |
| 二、工具使用 | Bash+文件搜索+网页搜索+网页获取+MCP+多模型路由 | ✅ |
| 二、上下文管理 | 滑动窗口+子Agent摘要回传+动态 Token 预算 | ✅ |
| 二、Prompt 模板 | 文件管理+热加载+A/B 测试+10 个模板 | ✅ |
| 二、可观测性 | OpenTelemetry 封装+GenAI 语义约定+降级回退 | ✅ |
| 三、四大场景 | 邮件助手+系统诊断+代码分析+文献阅读 | ✅ |
| 四、GUI 界面 | 悬浮球+对话窗口+系统托盘（PyQt5） | ✅ |
| 四、deepin 25 适配 | 34/34 测试通过 | ✅ |
| 五、技术报告 | RFC.md + ARCHITECTURE.md(14章) + TECH_DECISIONS.md(16节) + QUALITY.md(11项检查) | ✅ |
| 五、演示视频 | deepin_demo.mp4（157秒） | ✅ |

### 关键时间线

| 日期 | 里程碑 | 状态 |
|------|--------|:----:|
| 5/16 | deepin 25 实体机验证 34/34 通过 | ✅ |
| 5/16 | 演示视频录制 + 技术报告完成 | ✅ |
| 5/22 | P0/P1/P2 工程优化全部完成 | ✅ |
| 5/22 | 文档全面同步 + GitHub push | ✅ |
| 6/7 | Workshop 改进 Step 1-3（Plan-and-Solve + 上下文管理 + Prompt 模板） | ✅ |
| 6/8 | Workshop 改进 Step 4-8（并行扇出 + A2A + OTel + 场景识别 + 文档） | ✅ |
| 6/10 | e2e 41/41 + benchmark + 文档终版同步 | ✅ |

### Git 提交记录

| Commit | 日期 | 说明 |
|--------|------|------|
| `c99a05f` | 6/7 | Step 1-3: Plan-and-Solve + 上下文管理 + Prompt 模板 |
| `45ceb85` | 6/8 | Step 4-7: 并行扇出 + 辩论 + A2A + OTel + 场景识别 |
| `1222d4b` | 6/10 | 修复 e2e 41/41 + benchmark + 代码统计 |
| `3325cf3` | 6/10 | 文档终版更新（README/TECHNICAL_REPORT/TECH_DECISIONS/PLAN） |

### GitHub 仓库

- **地址**：https://github.com/sshnuke3/deepin-agent-teams
- **分支**：main
- **最新 commit**：`3325cf3`
