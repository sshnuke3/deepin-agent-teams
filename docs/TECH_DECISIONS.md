# 技术选型决策

## 文心大模型 API（erniebot SDK）

**选型原因：** 赛题要求使用飞桨文心大模型 API
**API 类型：** aistudio（AI Studio 平台 token 认证）
**已知限制：**
- 不支持 system role，需用 user role 替代
- 有调用频率限制和 token 配额
- 模型名称：`ernie-lite`（轻量）、`ernie-3.5`（强力）

**双模型路由策略：**
- 轻量任务（意图识别/摘要/分类）→ ernie-lite（快/便宜）
- 复杂任务（邮件生成/诊断/代码分析）→ ernie-3.5（强/贵）
- 强模型失败自动降级到 lite

**更新（2026-05-22）：** 当前 token 已耗尽，ERNIE 仅作降级备选。

## PyQt5

**选型原因：** 赛题要求提供 GUI 交互界面，deepin 25 预装 Qt 库
**替代方案对比：**
- tkinter：功能太弱，不支持深色主题
- Electron：太重，打包后 100MB+
- GTK：Python 绑定文档少
**已知限制：** 截图功能在部分 Wayland 环境下不兼容

## PaddleOCR

**选型原因：** 飞桨生态，中文识别准确率高，离线可用
**替代方案对比：**
- Tesseract：中文识别率低
- 百度 OCR API：需要网络，有调用费用
**已知限制：** 首次加载模型较慢（约 3-5 秒）

## deepin D-Bus

**选型原因：** deepin 25 的系统管理都通过 D-Bus 接口暴露
**实现方式：** 使用 `dbus-send` 命令行工具（不依赖 dbus-python 库）
**已知限制：** D-Bus 接口可能随 deepin 版本变化

## 文件锁（fcntl）

**选型原因：** 多 Agent 并行执行时需要进程级互斥
**实现方式：** fcntl.flock() 文件锁 + 进程内 dict 锁
**已知限制：** 仅 Linux 可用，Windows 不兼容

## 多模型路由（ModelRouter）

**选型原因：** MiniMax 为主力模型，ERNIE 作降级备选。避免单点故障。
**实现方式：** 按优先级尝试调用，失败自动切换。
**路由链：** MiniMax → ERNIE-lite → ERNIE-3.5 → Fallback（返回错误信息）
**响应格式：** 统一 ModelResponse（content/success/error/latency_ms/token_used）
**环境变量：** `MINIMAX_API_KEY` / `ERNIE_TOKEN`

## 状态机引擎（TaskStateMachine）

**选型原因：** 替代轮询+模型主观判断，所有停止条件代码写死。
**核心原则：**
- 状态跳转条件写死在代码，不靠模型主观判断
- 每次跳转写 trace（/tmp/deepin_traces/{task_id}.jsonl）
- 状态机本身无状态，所有状态存在 Registry 层

**8 种状态：** PENDING / CLAIMED / PLANNING / RUNNING / VERIFIED / COMPLETED / FAILED / RETRY
**跳转规则：** 见 ARCHITECTURE.md 状态转换表
**超时检测：** RUNNING 状态超过 DEFAULT_TIMEOUT（60s）自动标记 FAILED
**重试策略：** RETRY → RUNNING，最多 MAX_RETRY（3）次，超时耗尽跳 FAILED

## 独立 Verifier

**选型原因：** VERIFIER ≠ 执行者，不能是同一个认知主体。
**设计原则：**
- 不读 Worker 上下文，完全独立的世界观
- 验收标准是清单（checklist），不是模型主观判断
- 决策只有三种：PASS / FAIL(reasons) / RETRY(cause)

**11 项检查：** deliverable_exists / functional_correctness / trace_integrity / error_free / tool_compliance / token_budget / dangerous_ops_confirmed / plan_completeness / plan_coherence / context_overflow / summary_quality
**类型分叉：** 不同 task type 有不同验收标准：
- `code_analysis` → 需 `lines` 字段
- `shell_executor` → 需 `command` + `exit_code`
- `file_reader` → 需 `content` 或 `size`
- `web_search` → 需 `results` 列表
- `ast_parser` → 需 `ast` 字段
**可接受错误：** E_TIMEOUT / E_BLOCKED 不算 FAIL（用户可重试），其他算 FAIL

## CheckpointManager

**选型原因：** 失败恢复时不让 Worker 整体重来，跳过已完成的 capability。
**目录结构：** /tmp/deepin_checkpoints/{task_id}/
**关键方法：**
- `save(capability, result)` — 每步能力执行完写 checkpoint
- `is_completed(capability)` — 检查是否已完成
- `last_checkpoint()` — 重试时从最近 checkpoint 恢复
- `verify(capability, result)` — hash 验证防篡改
- `cleanup()` — 成功后清理所有 checkpoint 文件

## 网页搜索（duckduckgo html）

**选型原因：** 无需 API key，直接 curl duckduckgo html 端即可。
**限制：** 可能被 CAPTCHA/cloudflare 拦截（标记为 E_BLOCKED，不算 FAIL）
**解析方式：** 正则提取 `<a class="result__a">` 标题和链接
**备选：** 如果 duckduckgo 也被拦，考虑 Bing 搜索 API 或 SearXNG

## MCP 工具协议（mcp_protocol.py）

**选型原因：** 解耦工具层，实现「加工具不改 Agent」。
**决策时间：** 2026-06-03

**方案对比：**

| 方案 | 优点 | 缺点 |
|------|------|------|
| 硬编码（v3） | 简单直接 | 工具和 Agent 强耦合 |
| 官方 MCP SDK | 协议完整 | PEP 668 限制，无法 pip install |
| **纯 Python 实现（选用）** | 零依赖、协议兼容、深信适配 | 需自行实现 JSON-RPC |

**实现要点：**
- JSON-RPC over stdio，与官方 MCP 协议一致
- MCPServer：装饰器注册工具，自动处理 initialize/list/call
- MCPClient：连接子进程，自动发现和调用工具
- ToolRegistry：统一工具注册表，支持本地 + MCP 两种来源

**核心收益：**
- 加新工具 = 写 MCP Server + `connect_server()` 一行代码
- 每个 Server 可独立运行、独立测试
- 工具列表自动生成 LLM Function Calling 格式

**相关文件：** `mcp_servers/mcp_protocol.py`、`tools/tool_registry.py`、`agents/orchestrator_v4.py`

## 安全增强（P0）

**选型原因：** 参考 Agent 生产级架构与质量保障实践 + OpenVibeCoding 架构分析
**决策时间：** 2026-06-04

### 工具白名单隔离

**方案：** 每状态/阶段独立白名单，RUNNING 内部分 4 阶段（plan/gather/analyze/execute）
**核心函数：** `is_tool_allowed(tool, state, phase)` — 大小写不敏感
**关键设计：**
- PENDING/CLAIMED/FAILED/COMPLETED 不允许任何工具
- plan 阶段纯思考（无工具）
- gather 阶段只读工具
- analyze 阶段分析工具
- execute 阶段所有工具（含写操作）
**相关文件：** `agents/security_config.py`

### Token 预算

**方案：** 每状态/阶段独立上限 + 全局上限 15000
**核心类：** `TokenTracker` — 大小写不敏感，支持 record/check_budget/summary
**超限处理：** `check_and_enforce_token_budget()` → 自动触发 FAILED
**相关文件：** `agents/security_config.py`、`agents/task_state_machine.py`

### 危险操作确认（Confirming 守卫）

**方案：** 正则匹配危险模式 → 四值确认（allow/always/deny/exit）
**危险模式分级：** critical（rm -rf/mkfs/dd）→ high（kill -9/curl|bash）→ medium（sudo）
**关键设计：** `always` 将 pattern_id 加入白名单，后续同类操作自动放行
**相关文件：** `agents/security_config.py`、`agents/worker_base.py`

## 离线评测框架（P1）

**选型原因：** 参考 promptfoo 架构，纯 Python 实现
**决策时间：** 2026-06-04

**方案对比：**

| 方案 | 优点 | 缺点 |
|------|------|------|
| promptfoo（外部工具） | 功能完整 | Node.js 依赖，CI 配置复杂 |
| **eval_runner.py（选用）** | 零依赖，Python 原生 | 需自行实现断言 |

**核心组件：**
- AIMock — 确定性 Fixture，CI 零 API 消耗
- EvalRunner — 评测管道（定义用例 → 执行 → 对比 → 报告）
- EvalAssert — 评测断言工具集

**相关文件：** `agents/eval_runner.py`

## 可观测性（P1）

**选型原因：** 轻量方案够用，后续可平滑迁移到 OpenTelemetry SDK
**决策时间：** 2026-06-04

**方案：** OpenTelemetry 封装（`otel_tracer.py`）+ 降级回退（`metrics_collector.py`）
**存储：** JSONL 格式，`tests/metrics/` 目录
**降级策略：** OTel SDK 不可用时自动回退到 metrics_collector，API 签名一致
**关键埋点：** task_execution / llm_call / tool_call / state_transition / agent_loop
**GenAI 语义约定：** 使用 `gen_ai.*` 属性名（OpenLLMetry 兼容）

**相关文件：** `agents/otel_tracer.py`、`agents/metrics_collector.py`

## Red Teaming（P1）

**选型原因：** 主动攻击验证安全机制，而非被动等待线上事故
**决策时间：** 2026-06-04

**5 类攻击向量（19 个）：**
- Prompt 注入（3 个）— 直接覆盖、间接注入、角色扮演
- 工具白名单绕过（5 个）— 各状态/阶段尝试违规调用
- Token 预算绕过（3 个）— 单阶段超限、全局超限、跨阶段累计
- 状态机非法跳转（4 个）— 跳过中间状态、状态回退
- 确认机制绕过（4 个）— 不确认执行、编码绕过

**修复记录：** base64 编码绕过（`echo xxx | base64 -d | bash`）→ 新增通用管道到解释器模式

**相关文件：** `agents/red_team_tests.py`

## Brain/Hands 分离（P2）

**选型原因：** 学自 OpenVibeCoding，解耦编排层与执行层
**决策时间：** 2026-06-04

**核心设计：**
- `HandsInterface` — 抽象接口（execute/health_check/get_capabilities）
- `LocalHands` — 本地执行实现（向后兼容）
- `DockerHands` — Docker 容器执行（预留接口）
- `MockHands` — 测试用 Mock（确定性输出）
- `HandsFactory` — 工厂模式创建实例

**核心收益：**
- 换执行后端不影响编排逻辑（Docker → CloudBase → 本地进程）
- 编排层可独立测试（Mock Hands）
- 多种执行后端可并存

**相关文件：** `agents/hands_interface.py`

## 三级环境隔离（P2）

**选型原因：** 学自 OpenVibeCoding 的 shared/isolated/task 三级设计
**决策时间：** 2026-06-04

| 级别 | 说明 | 适用场景 |
|------|------|----------|
| shared | 所有人共用一个环境 | 个人项目 |
| isolated | 每 Worker 独立环境 | 团队项目 |
| task | 每任务独立环境 + 独立配额 | 多租户 SaaS |

**核心组件：**
- `EnvironmentManager` — 环境生命周期管理
- `ResourceQuota` — 资源配额限制（文件数/大小/进程数/CPU/内存/超时）
- `IsolationPolicy` — 按场景预设策略

**相关文件：** `agents/environment_isolation.py`


## Plan-and-Solve 规划模块（P0）

**选型原因：** W3 课程核心方法——先规划再执行，减少幻觉和遗漏步骤
**决策时间：** 2026-06-10

**核心设计：**
- PLANNING 状态插入 CLAIMED 和 RUNNING 之间（八状态机）
- PLANNING 阶段工具白名单为空（纯推理），Token 预算 800
- 超时 30 秒，超时自动降级为通用任务
- Planner 模块：生成结构化计划（TodoManager）+ nag reminder 提醒更新进度

**计划格式：**
```json
{
  "summary": "分析代码质量",
  "steps": [
    {"id": 1, "action": "读取代码文件", "capability": "file_reader", "depends_on": [], "status": "pending"}
  ]
}
```

**相关文件：** `agents/planner.py`、`agents/task_state_machine.py`、`prompts/planner/plan_generation.md`

## 上下文管理（P1）

**选型原因：** 解决多轮对话中上下文膨胀导致 token 超限的问题
**决策时间：** 2026-06-10

**核心设计：**
- 滑动窗口策略：保留最近 K 轮完整对话（默认 10 轮），早期压缩为摘要
- 子Agent摘要回传：只回传压缩摘要到父上下文，不注入原始对话
- 动态 Token 预算：`budget = base_budget + per_step_budget * remaining_steps`

**子Agent摘要格式：**
```python
SubagentSummary(
    task_id="task-001",
    conclusion="发现 3 个潜在问题",
    key_findings=["函数 A 缺少异常处理"],
    duration_ms=1500,
)
```

**相关文件：** `agents/context_manager.py`

## Prompt 模板管理（P1）

**选型原因：** 硬编码 prompt 难以迭代，文件管理 + 热加载支持快速实验
**决策时间：** 2026-06-10

**核心设计：**
- 热加载：修改 `.md` 文件后下次调用自动生效（mtime 检测）
- A/B 测试：`loader.register_ab_test(path, ["v1", "v2"], weights=[0.7, 0.3])`
- 版本管理：支持 v2/v3 等多版本模板
- 向后兼容：PromptLoader 不可用时降级到硬编码 prompt

**相关文件：** `agents/prompt_loader.py`、`prompts/` 目录

## 并行扇出模式（P1）

**选型原因：** 多个独立子任务可并行执行，减少总耗时
**决策时间：** 2026-06-10

**方案对比：**

| 方案 | 优点 | 缺点 |
|------|------|------|
| asyncio | 原生异步 | 需要 async 全链路改造 |
| **ThreadPoolExecutor（选用）** | 同步代码兼容、实现简单 | 线程开销 |

**聚合策略：** concat（拼接）、vote（投票）、best（取最高置信度）、merge（深度合并）

**相关文件：** `agents/orchestrator.py`（`fan_out()` + `aggregate()`）

## 辩论模式（P1）

**选型原因：** 技术方案选型等决策场景需要正反论证，避免单一视角偏差
**决策时间：** 2026-06-10

**核心设计：**
- Pro（正方）→ Con（反方）→ Pro 回应 → Con 再反驳 → Judge 裁决
- 最多 N 轮（默认 2 轮），超过直接交 Judge
- Judge 输出：winner / decision / confidence / reasoning

**相关文件：** `agents/debate.py`

## A2A 协议 + Agent Card（P2）

**选型原因：** 标准化 Agent 描述，支持自动发现和动态注册
**决策时间：** 2026-06-10

**核心设计：**
- 每个 Agent 实现 `agent_card.json`（name/version/capabilities/agent_type）
- `AgentRegistry.auto_discover()` 扫描 `agent_cards/` 目录自动注册
- 支持按类型查找：`find_agent_by_type("coder")`

**相关文件：** `agents/registry.py`、`agents/agent_cards/*.json`

## 场景识别 + 动态模型路由（P2）

**选型原因：** 不同场景需要不同复杂度的模型，动态路由比静态规则更灵活
**决策时间：** 2026-06-10

**核心设计：**
- 三道筛子判断是否适合 Agent 化：模糊性筛 → 跨系统筛 → 多步骤筛
- 三道都不过 → 直接 LLM 对话，不进状态机
- 动态路由：`DynamicModelRouter` 基于场景分类结果选择 lite/strong
- 复杂度匹配：complex → moderate → simple（从高到低返回首个匹配）

**相关文件：** `agents/scenario_classifier.py`
