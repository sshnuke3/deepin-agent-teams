# Plan: deepin-agent-teams 全面改进计划

> 基于 Agent Workshop W1-W6 课程知识的 Gap 分析，按 P0→P1→P2 分四阶段执行
> 预估总工期：15-20 个工作日

---

## 阶段一：P0 核心硬伤修复（5-7天）

### Step 1: Plan-and-Solve 规划阶段 ⭐ 最高优先级

- [ ] 1.1 `task_state_machine.py` 新增 `PLANNING` 状态
  - 状态流：PENDING → CLAIMED → **PLANNING** → RUNNING → VERIFIED → COMPLETED
  - PLANNING 超时：30秒，超时自动降级为 RUNNING（不阻塞）
  - 跳转条件：Worker 认领后必须先输出结构化计划才能进入 RUNNING

- [ ] 1.2 新增 `planner.py` 模块
  - PlanManager：接收任务描述 → 输出步骤列表
  - TodoItem 数据结构：`{id, description, status: pending|in_progress|done, started_at, completed_at}`
  - 约束：同一时间只能有一个 `in_progress`
  - nag reminder：连续 3 轮未更新 todo → 注入提醒 prompt
  - 计划格式：JSON 结构化输出（方便状态机解析）

- [ ] 1.3 `orchestrator.py` 集成 Planner
  - CLAIMED 后调用 `planner.create_plan(task)`
  - 每轮 RUNNING 开始前检查 `todo_manager.get_progress()`
  - 所有 todo 完成才允许进入 VERIFIED
  - 计划变更记录（plan revision trace）

- [ ] 1.4 `verifier.py` 新增 planning 检查项
  - 检查项 8：`plan_completeness` — 所有 todo 是否都标记 done
  - 检查项 9：`plan_coherence` — 计划步骤是否逻辑自洽

- [ ] 1.5 测试
  - 正常场景：简单任务 1 步计划，复杂任务 3-5 步
  - 异常场景：计划为空、计划超时、计划在执行中被推翻
  - nag 场景：模拟 3 轮无进展，验证提醒注入

---

### Step 2: 上下文管理 + 子 Agent 摘要回传 ⭐ 最高优先级

- [ ] 2.1 新增 `context_manager.py` 模块
  - ContextWindow：滑动窗口管理
    - 保留最近 K 轮（默认 10 轮）完整对话
    - 早期对话压缩为摘要
    - 重要信息提取到结构化字段（entities, decisions, constraints）
  - 上下文压缩策略：
    - 超过 N 轮（默认 20）→ 自动触发摘要
    - 摘要由 LLM 生成（用 ernie-lite，成本低）
    - 摘要格式：{段落摘要 + 关键实体列表}
  - Token 计数器：实时跟踪上下文 token 量

- [ ] 2.2 子 Agent 摘要回传
  - Worker 执行完毕后，输出经过压缩的 `summary` 字段
  - Orchestrator 只把 summary 注入父上下文，不是原始对话
  - summary 格式：`{结论, 关键发现, 未完成项, 耗时}`
  - 摘要长度上限：500 tokens

- [ ] 2.3 `security_config.py` 更新 Token 预算
  - 全局 Token 预算从固定值改为动态计算
  - `budget = base_budget + per_step_budget * remaining_steps`
  - 超预算时的降级策略：切换到 ernie-lite（低成本模型）

- [ ] 2.4 `verifier.py` 新增上下文检查
  - 检查项 10：`context_overflow` — 上下文是否超出窗口
  - 检查项 11：`summary_quality` — 摘要是否包含关键信息

- [ ] 2.5 测试
  - 长对话场景：50 轮对话，验证压缩触发和摘要质量
  - Token 爆炸场景：模拟无限循环，验证预算熔断
  - 摘要质量：人工评估摘要是否保留关键信息

---

## 阶段二：P1 工程化能力提升（4-5天）

### Step 3: 独立 Prompt 模板管理

- [ ] 3.1 建立 `prompts/` 目录结构
  ```
  prompts/
  ├── system_operator/
  │   ├── base.md
  │   ├── few_shots.json
  │   └── cot_template.md
  ├── information_collector/
  │   ├── base.md
  │   ├── few_shots.json
  │   └── cot_template.md
  ├── content_creator/
  │   ├── base.md
  │   ├── few_shots.json
  │   └── cot_template.md
  ├── planner/
  │   └── plan_generation.md
  └── verifier/
      └── checklist_template.md
  ```

- [ ] 3.2 新增 `prompt_loader.py` 模块
  - PromptLoader：从文件加载 prompt + 变量替换（`{task_description}`, `{context}` 等）
  - 支持 Jinja2 模板语法
  - 支持版本管理：`prompts/v2/system_operator/base.md`
  - 热加载：修改 prompt 文件后无需重启

- [ ] 3.3 迁移现有硬编码 prompt
  - 从 `worker_base.py`、`system_operator.py`、`information_collector.py`、`content_creator.py` 提取 prompt
  - 移到对应目录
  - 验证迁移前后输出一致

- [ ] 3.4 A/B 测试支持
  - PromptLoader 支持加载多个版本
  - 评测时对比不同 prompt 版本的得分

- [ ] 3.5 测试
  - 加载测试：验证所有 prompt 文件可正确加载
  - 变量替换测试：验证模板变量正确替换
  - 回归测试：迁移前后同一输入输出一致

---

### Step 4: 并行扇出模式

- [ ] 4.1 `orchestrator.py` 新增 fan_out 方法
  ```python
  def fan_out(self, tasks: List[Dict]) -> List[Dict]:
      """并行分发多个子任务，等待全部完成"""
  ```
  - 使用 `concurrent.futures.ThreadPoolExecutor` 并行执行
  - 每个子任务独立的 TaskState 和 Token 预算
  - 超时处理：单个子任务超时不阻塞其他任务
  - 部分失败：收集已成功结果 + 失败原因

- [ ] 4.2 新增 aggregate 方法
  ```python
  def aggregate(self, results: List[Dict]) -> Dict:
      """汇总多个并行任务的结果"""
  ```
  - 汇总策略：拼接、投票、取最高置信度
  - 可配置：由任务描述指定汇总方式

- [ ] 4.3 辩论模式（Debate）
  - 新增 `debate.py` 模块
  - 流程：Pro Agent 论点 → Con Agent 反驳 → Judge（Verifier）决策
  - 适用场景：技术方案选型、架构决策
  - 辩论轮数：默认 2 轮

- [ ] 4.4 测试
  - fan_out 场景：3 个子任务并行执行
  - 部分失败：1 个超时，2 个成功
  - 辩论场景：正反方各 2 轮，裁判输出决策

---

## 阶段三：P2 协议标准化（3-4天）

### Step 5: A2A 协议 + Agent Card

- [ ] 5.1 每个 Agent 实现 `agent_card.json`
  ```json
  {
    "name": "system_operator",
    "version": "1.0",
    "description": "系统运维智能体",
    "capabilities": ["shell_executor", "file_reader", "package_tool"],
    "input_types": ["text", "system_command"],
    "output_types": ["text", "command_result"],
    "security_level": "elevated",
    "model_preference": "ernie-lite"
  }
  ```

- [ ] 5.2 AgentRegistry 从 agent_card.json 自动发现
  - 扫描 `agents/` 目录下的 `agent_card.json`
  - 自动注册到 Registry
  - 支持运行时动态加载新 Agent

- [ ] 5.3 Task 生命周期标准化
  - 统一 Task 状态：submitted → working → completed / failed
  - 每个状态转换写 trace（已有，统一格式）
  - Task 超时处理：全局超时 + 阶段超时

- [ ] 5.4 测试
  - 动态注册：新增一个 Agent，验证自动发现
  - 生命周期：完整走一遍 submitted → working → completed

---

### Step 6: 标准 OpenTelemetry 可观测性

- [ ] 6.1 引入 OpenLLMetry
  - 安装：`pip install traceloop-sdk opentelemetry-exporter-otlp`
  - 自动 instrument OpenAI SDK / erniebot 调用
  - 采集 GenAI 语义约定属性

- [ ] 6.2 在关键节点埋点
  - Agent Loop 每轮 → Span
  - LLM 调用 → Span + token usage（`gen_ai.usage.input_tokens` 等）
  - 工具调用 → Span + 输入输出
  - 状态机跳转 → Event

- [ ] 6.3 导出配置
  - 开发环境：Console 导出（打印到终端）
  - 生产环境：OTLP 导出到 Jaeger / Grafana
  - 保留现有 metrics_collector 作为降级方案（OTel 不可用时回退）

- [ ] 6.4 Trace 可视化
  - Jaeger 部署：`docker run -d -p 16686:16686 jaegertracing/all-in-one`
  - 验证调用链可在 Jaeger UI 中查看

- [ ] 6.5 测试
  - 埋点验证：执行一个任务，检查 trace 是否完整
  - 导出验证：Jaeger UI 中能看到调用链

---

## 阶段四：P2.5 增强与收尾（2-3天）

### Step 7: 场景识别 + 模型路由优化

- [ ] 7.1 场景识别器（Scenario Classifier）
  - 输入：用户意图 + 上下文
  - 输出：场景类型（email / system_fix / code / search / chat）
  - 使用 W6 的"三道筛子"判断是否适合 Agent 化
  - 不适合 Agent 的场景 → 直接走 LLM 对话，不进状态机

- [ ] 7.2 模型路由优化
  - 当前：ernie-lite（轻量）/ ernie-3.5（复杂）
  - 优化：根据任务复杂度动态选择
    - 简单任务（1步计划）→ ernie-lite
    - 复杂任务（3+步计划）→ ernie-3.5
  - 路由决策写入 trace

- [ ] 7.3 测试
  - 场景分类：10 个测试用例，验证分类准确率
  - 模型切换：验证复杂任务自动升级模型

---

### Step 8: 文档 + 评测报告更新

- [ ] 8.1 更新 `docs/ARCHITECTURE.md`
  - 新增模块：planner.py, context_manager.py, prompt_loader.py, debate.py
  - 更新状态机图（增加 PLANNING 状态）
  - 更新工具白名单表（增加 plan 阶段）

- [ ] 8.2 更新 `docs/QUALITY.md`
  - 新增验证项：plan_completeness, plan_coherence, context_overflow, summary_quality
  - 更新 Red Team 测试用例

- [ ] 8.3 运行全量测试
  - 单元测试：所有新模块
  - 集成测试：端到端任务流
  - Red Team：19 个攻击向量 + 新增上下文溢出攻击
  - 生成测试报告

- [ ] 8.4 更新 `TECHNICAL_REPORT.md`
  - 新增改进章节
  - 更新架构图
  - 更新测试数据

---

## 依赖关系

```
Step 1 (Planning)  ←── Step 3 (Prompt)  ←── Step 7 (场景识别)
      ↓                    ↓
Step 2 (上下文)    ←── Step 4 (并行)   ←── Step 8 (文档)
      ↓                    ↓
Step 5 (A2A)       ←── Step 6 (OTel)
```

- Step 1 和 Step 2 可以并行开发（无依赖）
- Step 3 依赖 Step 1（planner 需要 prompt 模板）
- Step 4 依赖 Step 2（并行需要上下文隔离）
- Step 5、6、7 可以并行开发
- Step 8 最后执行

## 里程碑

| 里程碑 | 完成步骤 | 预计日期 | 交付物 |
|--------|---------|---------|--------|
| M1 核心修复 | Step 1 + 2 | +7天 | 规划能力 + 上下文管理 |
| M2 工程提升 | Step 3 + 4 | +12天 | Prompt 模板化 + 并行执行 |
| M3 协议标准 | Step 5 + 6 | +16天 | A2A + OpenTelemetry |
| M4 收尾 | Step 7 + 8 | +19天 | 全量测试 + 文档更新 |

## 风险项

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| ernie-lite 摘要质量差 | 上下文压缩效果不好 | 用规则压缩 |
| 并行执行 Token 爆炸 | fan_out 3个任务 = 3倍消耗 | 每个子任务独立预算，全局总预算 |
| Prompt 迁移回归 | 移动 prompt 后行为变化 | 先写对比测试，迁移前后 diff |
| OTel 依赖冲突 | pip 安装和 deepin 环境冲突 | 保留 metrics_collector 降级方案 |
