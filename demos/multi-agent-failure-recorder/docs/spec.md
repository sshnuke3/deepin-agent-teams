# spec.md — demos/multi-agent-failure-recorder

> 本文件按 ai-ops-sop §6 / §"上下文工程" 模板写
> 立项动机：bojieli《AI Agent》ch10 多 Agent 协作 + 主人 RFC D3 启动多 agent demo 采集失败样本

## §0 项目定位

**单一目的**：记录 deepin-agent-teams 在多 Agent 场景下的失败样本，让"3+ 次同类规律"门槛可被验证。

**不是**：
- ❌ 多 Agent 框架本身（v4-plan.md 已规划）
- ❌ 多 Agent SOP（立项前不能写）
- ❌ AI Agent 教程（ch10 已有）

## §1 调用链

```
跑实际任务 (deepin-agent-teams / 其他项目)
       │
       ├─ 跑挂 → bash scripts/capture-failure.sh
       │              │
       │              ├─ 写 runs/<date>-failure-<n>.json
       │              └─ 追加 runs/timeline.txt
       │
       └─ 跑通 → 不记录
       
跨 3 个 mode 各有样本 → 立项升级门槛达成
```

## §2 数据模型（runs/<date>-failure-<n>.json）

```json
{
  "id": "2026-07-22-failure-1",
  "captured_at": "2026-07-22T14:30:00+08:00",
  "mode": "F1" | "F2" | "F3" | "F4" | "F5",
  "scene": "deepin-agent-teams v4 GUI 多意图并发 / claude-code subagent / 自研多 agent ...",
  "agents_involved": [
    {"role": "intent_agent", "model": "qwen-max"},
    {"role": "planner_agent", "model": "qwen-max"}
  ],
  "task": "用户问：'整理文件 + 设置提醒' (并发多意图)",
  "expected": "两个意图都完成",
  "actual": "planner 等 intent 输出，intent 等 planner 反馈，死锁 5 分钟超时",
  "root_cause_hypothesis": "单 pipeline 设计误用为并发场景，agent 间没明确交接协议",
  "severity": "high" | "medium" | "low",
  "reproducibility": "100%" | "intermittent" | "unique",
  "tags": ["deadlock", "timeout", "v4-plan-revisit"]
}
```

**字段说明**：
- `mode` = 5 大失败模式之一
- `scene` = 跑挂时的项目/场景（可多个）
- `agents_involved` = 涉及的 agent 列表（仅记录，不修改）
- `expected` / `actual` = 一句话描述预期 vs 实际
- `root_cause_hypothesis` = 我的猜测（不一定对，仅作日后分析入口）
- `severity` = 影响范围
- `reproducibility` = 是否可复现
- `tags` = 自定义标签，便于跨样本检索

## §3 5 大失败模式详解

### F1 互相等待（deadlock）

**典型场景**：agent A 等 B 输出，B 等 A 反馈，形成环。

**检测信号**：
- 主循环超时（> 30s）
- 日志里互相 polling 同一个 lock/resource
- 涉及 N≥2 agent，且每个 agent 都在"等待 X 的回应"

**采集判断**：看到 deadlock / 互相等待字样 → F1

### F2 信息冲突（conflict）

**典型场景**：多 agent 对同一上下文理解不同。

**检测信号**：
- 同一问题多个 agent 给出**矛盾**答案
- 群决策超过单 agent 分数（说明冲突未解决）
- 用户反馈"agent 自相矛盾"

**采集判断**：看到矛盾 / 冲突 / self-contradict → F2

### F3 角色漂移（role drift）

**典型场景**：agent 做了不该做的事（破坏 role 边界）。

**检测信号**：
- agent 调用了"不属于该 role"的工具
- agent 输出越界（reply 超出 prompt 限定的 response format）
- 系统提示词被覆盖

**采集判断**：看到越界 / role drift / 工具越权 → F3

### F4 资源死锁（resource contention）

**典型场景**：agent 同时争抢同资源。

**检测信号**：
- LLM 调用达到 rate limit
- 文件锁 / 数据库锁报错
- 进程间死锁（os 层面 mutex）

**采集判断**：看到 rate limit / lock conflict / 429 / "resource busy" → F4

### F5 涌现失序（emergent chaos）

**典型场景**：群体行为不可预测，整体混乱。

**检测信号**：
- 群体决策分数 < 单 agent 分数
- 没有明显 F1-F4 但"明显不对"
- 反复重跑结果差异巨大

**采集判断**：没明确信号但"群体效果不如单 agent" → F5

## §4 采集流程（scripts/capture-failure.sh 工作流）

```bash
# 1. 看到失败
$ <跑多 agent 任务>
$ <任务挂掉>

# 2. 立即采集
$ bash scripts/capture-failure.sh
# 脚本交互式问：
# - mode? (F1-F5)
# - scene? (项目/场景名)
# - task? (用户请求)
# - expected? (一句话)
# - actual? (一句话)
# - agents_involved? (json array)
# - root_cause_hypothesis? (一句话)

# 3. 自动落盘
$ ls runs/2026-07-22-failure-1.json

# 4. 确认 timeline 更新
$ tail -3 runs/timeline.txt
```

## §5 立项升级门槛

**门槛达成条件**：
- F1-F5 中至少 3 个 mode 各有 1+ 样本
- 跨 2 个不同项目/场景（不只是 deepin-agent-teams）
- 至少 1 个 high severity 样本

**达成后**：
- 写 `~/.openclaw/workspace/methodology/multi-agent-pipeline.md`
- 升级到 ai-ops-sop 配套 SOP
- 进入 drafts/multi-agent-sop/ 主流版本（不再是 RFC）

**未达时**：
- 继续采集
- 半年没新样本 = 项目归档

## §6 链接

- 立项 RFC：`~/.openclaw/workspace/drafts/multi-agent-sop/RFC.md`
- 参考：bojieli/ai-agent-book chapter 10（已 clone 到 `~/.openclaw/workspace-public/ai-agent-book/book/chapter10.md`）
- 项目主体：`/root/.openclaw/workspace/deepin-agent-teams/`（v4-plan.md）
- 方法论：`~/.openclaw/workspace/methodology/ai-coding-pipeline-methodology.md`

---

# 2026-07-21 创建 · spec 骨架 ✓
# 主人定的两条规则: 加注释 ✓ / 完全剥离 ✓ (本 demo 是内部, 不对外)