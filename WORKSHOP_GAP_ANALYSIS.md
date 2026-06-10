# deepin-agent-teams 改进分析

> 基于 Agent Workshop W1-W6 课程知识 vs 项目现状的系统性 Gap 分析
> 2026-06-10

---

## 一、对照矩阵：W1-W6 知识点 vs 项目现状

| 课程知识点 | 项目现状 | 差距等级 |
|-----------|---------|---------|
| **W1** LLM API 调用、Temperature、Token 计费 | ✅ model_router.py 双模型路由（ernie-lite/ernie-3.5） | 已覆盖 |
| **W2** Few-shot、CoT、结构化输出 | ⚠️ system prompt 写在代码里，无模板管理 | 🔴 缺失 |
| **W3** Agent Loop (ReAct) | ✅ orchestrator.py 有完整循环 | 已覆盖 |
| **W3** Tool Use (dispatch map) | ✅ tools/ 目录 + ToolRegistry | 已覆盖 |
| **W3** Plan-and-Solve (先列计划再执行) | ❌ 无 Planning 阶段，直接 CLAIMED→RUNNING | 🔴 缺失 |
| **W3** Subagent 上下文隔离 | ⚠️ workers 是子进程，但无独立 messages[] + 摘要回传 | 🟡 部分 |
| **W4** MCP Server/Client | ✅ mcp_servers/mcp_protocol.py，orchestrator 有 tools 模式 | 已覆盖 |
| **W4** A2A 协议（Agent Card、Task 生命周期） | ❌ 无 A2A，Agent 间无标准化通信协议 | 🔴 缺失 |
| **W5** 顺序链式协作 | ✅ orchestrator 顺序调度 Worker | 已覆盖 |
| **W5** 主管分发模式 | ✅ orchestrator 作为 Supervisor 分发任务 | 已覆盖 |
| **W5** 并行扇出模式 | ❌ 无并行执行，所有任务串行 | 🔴 缺失 |
| **W5** 辩论模式（正反方→裁判） | ❌ 无辩论/投票机制 | 🔴 缺失 |
| **W5** JSONL 消息总线 | ❌ Agent 间无消息总线，靠 orchestrator 直接调度 | 🟡 缺失 |
| **W5** 请求-响应 FSM（审批流程） | ⚠️ conflict_resolver.py 有冲突解决，但无审批 FSM | 🟡 部分 |
| **W5** 自主任务板 | ❌ 无任务板，Agent 不能自主认领任务 | 🔴 缺失 |
| **W6** 场景识别（四类适合/五类不适合） | ❌ 无场景筛选机制 | 🟡 缺失 |
| **W6** promptfoo 离线评测 | ⚠️ eval_runner.py 有 AIMock 但无 promptfoo 集成 | 🟡 部分 |
| **W6** AIMock Record & Replay | ⚠️ 有 AIMock fixture，但无录制-重放能力 | 🟡 部分 |
| **W6** OpenTelemetry 可观测性 | ⚠️ metrics_collector.py 是自研轻量方案，非标准 OTel | 🟡 部分 |
| **W6** 成本控制（Token 预算+熔断） | ✅ security_config.py 有 TokenTracker + 预算 | 已覆盖 |
| **W6** 工具白名单+参数校验 | ✅ security_config.py 工具白名单 | 已覆盖 |
| **W6** Red Teaming | ✅ red_team_tests.py 19 个攻击向量 | 已覆盖 |

---

## 二、六大缺失项详解

### 缺失 1：Plan-and-Solve 规划阶段（W3）

**现状**：任务直接从 CLAIMED 跳到 RUNNING，Worker 拿到任务就开干。

**问题**：
- 复杂任务没有拆解步骤，容易"迷路"
- 没有 TodoManager 跟踪进度
- 没有 nag reminder（连续 N 轮无进展则提醒）

**建议**：
```
CLAIMED → PLANNING → RUNNING（带 TodoManager）
                      ↓
                   每轮检查进度，连续3轮无进展 → 注入提醒
```

- 在 TaskState 中增加 `PLANNING` 状态
- Worker 执行前先输出结构化计划（步骤列表）
- TodoManager 跟踪 `[ ]` → `[>]` → `[x]` 状态
- 超过 3 轮未更新 todo → 注入提醒 prompt

**工作量**：中等（2-3天）

---

### 缺失 2：并行扇出 + 辩论模式（W5）

**现状**：所有任务串行执行，只有主管分发模式。

**问题**：
- 需要多角度分析时（如代码审查 = 安全 + 性能 + 可维护性），只能串行跑三遍
- 关键技术决策缺乏正反论证，容易"一言堂"

**建议**：

1. **并行扇出**：orchestrator 支持 `fan_out` 模式
   ```python
   results = orch.fan_out([
       {"agent": "security_analyst", "task": "安全审查"},
       {"agent": "perf_analyst", "task": "性能分析"},
       {"agent": "maintainability_analyst", "task": "可维护性分析"},
   ])
   summary = orch.aggregate(results)
   ```

2. **辩论模式**：对于重大技术决策
   ```
   Pro Agent → 论点 → Con Agent → 反驳 → Judge（Verifier）→ 决策
   ```

**工作量**：中等（3-4天）

---

### 缺失 3：独立 Prompt 模板管理（W2）

**现状**：System prompt 硬编码在各 Agent 文件中，散布在 30+ 个 .py 文件里。

**问题**：
- 修改 prompt 需要改代码
- 无法 A/B 测试不同 prompt 效果
- 无法复用 prompt 模板（Few-shot、CoT 等）

**建议**：

1. 建立 `prompts/` 目录，按场景组织
   ```
   prompts/
   ├── system_operator/
   │   ├── base.md          # 基础 system prompt
   │   ├── few_shots.json   # few-shot 示例
   │   └── cot_template.md  # CoT 模板
   ├── information_collector/
   └── content_creator/
   ```

2. PromptLoader 类：从文件加载 + 变量替换
3. 支持版本管理：`prompts/v2/system_operator/base.md`

**工作量**：轻量（1-2天）

---

### 缺失 4：A2A 协议 + Agent Card（W4）

**现状**：Agent 间通过 orchestrator 直接函数调用，无标准化通信。

**问题**：
- 新增 Agent 需要修改 orchestrator 代码
- Agent 能力不透明（没有声明式描述）
- 无法动态发现和组合 Agent

**建议**：

1. 每个 Agent 实现 `agent_card.json`
   ```json
   {
     "name": "system_operator",
     "description": "系统运维智能体，负责系统配置、包管理、服务控制",
     "capabilities": ["shell_executor", "file_reader", "package_tool"],
     "input_types": ["text", "system_command"],
     "output_types": ["text", "command_result"]
   }
   ```

2. AgentRegistry 从 agent_card.json 自动发现 Agent
3. Task 生命周期标准化：submitted → working → completed/failed

**工作量**：中等（2-3天）

---

### 缺失 5：标准 OpenTelemetry 可观测性（W6）

**现状**：metrics_collector.py 是自研 JSONL 方案，不是标准 OpenTelemetry。

**问题**：
- 无法接入 Jaeger/Grafana 等标准工具
- 没有调用链追踪（Traces）
- 没有 GenAI 语义约定（`gen_ai.usage.input_tokens` 等）

**建议**：

1. 引入 OpenLLMetry（`traceloop-sdk`）
2. 在 orchestrator 的关键节点埋点：
   - Agent Loop 每轮 → Span
   - LLM 调用 → Span + token usage
   - 工具调用 → Span + 输入输出
3. 导出到 Console（开发）/ Jaeger（生产）
4. 保留现有 metrics_collector 作为降级方案

**工作量**：中等（2-3天）

---

### 缺失 6：并行执行 + 上下文压缩（W3/W6）

**现状**：Worker 是子进程但串行执行；无上下文窗口管理。

**问题**：
- 子 Agent 不返回摘要，原始输出直接塞入主上下文
- 长任务会撑爆上下文窗口
- 无滑动窗口 / 摘要压缩机制

**建议**：

1. **子 Agent 摘要回传**：
   ```python
   # 子 Agent 独立 messages[]，完成后只返回摘要
   sub_result = sub_agent.run(task)
   summary = sub_agent.get_summary()  # 压缩后的结论
   main_context.append(summary)       # 不是原始对话
   ```

2. **上下文压缩**：
   - 超过 N 轮 → 自动摘要历史
   - 滑动窗口：保留最近 K 轮 + 全局摘要
   - 重要信息提取到结构化字段

**工作量**：中等（3-4天）

---

## 三、优先级排序

| 优先级 | 改进项 | 理由 | 工作量 |
|--------|--------|------|--------|
| **P0** | Plan-and-Solve 规划阶段 | 直接影响复杂任务成功率 | 2-3天 |
| **P0** | 上下文压缩 + 子Agent摘要 | 长任务必崩，这是硬伤 | 3-4天 |
| **P1** | 独立 Prompt 模板管理 | 改 prompt 不用改代码，迭代效率 | 1-2天 |
| **P1** | 并行扇出模式 | 多维度分析场景需要 | 3-4天 |
| **P2** | A2A 协议 + Agent Card | 可扩展性，但当前 3 个 Agent 够用 | 2-3天 |
| **P2** | 标准 OpenTelemetry | 生产可观测性，当前轻量方案可接受 | 2-3天 |

---

## 四、一句话总结

**项目在安全（白名单/预算/Red Team）和质检（Verifier/状态机）方面做得很好，但在 Agent 工程化的"软能力"上存在明显短板——缺规划、缺并行、缺通信标准、缺上下文管理。**

最致命的两个问题：
1. 复杂任务没有规划阶段，直接开干 → 容易迷路
2. 上下文无压缩，长任务必然撑爆 → Token 爆炸

建议优先解决这两个 P0 问题。
