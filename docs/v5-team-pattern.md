# v5 Team Pattern — 团队模式与 Advisor 协议

> 最后更新：2026-07-22  
> 状态：M5 已落地（4 个新包 + RunComplex 入口）  
> 设计依据：awesome-llm-apps 的 `advisor-orchestrator-worker` skill  
> （Anthropic Skills 范式下的"三层模型团队"模式）

---

## 为什么写这份文档

v4 M2/M3 把"三段 Lambda Chain"打通（Intent → Plan → Execute → Verify）后，master
项目在 `5dbdbc0 docs: rewrite README for GitHub visitors` 已经具备生产可用度。

但有几件事一直没人挂：

1. **没有 Advisor** — 任一阶段只能靠 Planner 自己审自己，没有更贵的判断介入
2. **没有并行 Workers** — Chain 串行，多目录 / 多任务并发只能干等
3. **没有失败账本** — 重派了多少次、什么时候 ESCALATE、过没过，看日志只能猜
4. **没有 budget 概念** — LLM 烧 token 没有上限，静默跑光

这四个问题在 `awesome-llm-apps/agent_skills/advisor-orchestrator-worker/SKILL.md`
里早就有答案了。v5 M5（这次）就是把这个 skill 的精髓落进 Go 仓。

---

## 团队角色（v5 M5 落地版）

```
                 ┌──────────────────────┐
                 │     Orchestrator     │  ← 复用 v4 现有 Orchestrator
                 │   (chatModel + run)  │
                 └──────────┬───────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
        ┌───────▼────────┐      ┌───────▼────────┐
        │   Advisor      │      │   Workers      │
        │ (独立 ChatModel│      │ (workerpool 并 │
        │  可换贵模型)   │      │  发调工具)      │
        └────────────────┘      └────────────────┘
```

| 角色 | 实现 | 文件 | 默认模型 |
|------|------|------|----------|
| **Orchestrator** | `internal/orchestrator/orchestrator.go` + `run_complex.go` | RunComplex 入口 | 同 v4 现有 |
| **Advisor** | `internal/advisor/advisor_agent.go` | 贵/独立 ChatModel | 可接 Claude Fable 5 / GPT-5.6 |
| **Workers** | `internal/workerpool/pool.go` | errgroup 并发 | 调用方决定 |
| **Ledger** | `internal/ledger/ledger.go` | JSONL 账本 | N/A |

---

## 7 步 Loop 与 v5 落地的对应

参考 advisor-orchestrator-worker skill 的 7 步 loop，v5 M5 落地是"最小可裁剪版"——

| # | Skill 步骤 | v5 落地 |
|---|------------|---------|
| 1 | Frame（声明成功标准 + 预算 + 工具检查） | `RunComplexOpts.SuccessCriteria` / `Budget` |
| 2 | Plan（拆解成可独立 subtasks） | 复用 `Orchestrator.stagePlan` |
| 3 | **Plan Review**（Advisor consult #1） | `Orchestrator.advisorPlanReview` → ledger `EventPlanReview` |
| 4 | Delegate（并行 dispatch workers） | `internal/workerpool.Run`（本次未挂） |
| 5 | Verify（每个 worker PASS/FIX/ESCALATE） | `agents.VerifierAgent` 改三态 |
| 6 | Synthesize | `formatOutput` |
| 6.5 | **Escalation consult**（若 ESCALATE） | `Orchestrator.advisorEscalation` → ledger `EventEscalation` |
| 7 | Taste Pass（Advisor consult #2 收尾） | 本次未实现（v5+ 后续） |

> **未来扩展点**：Taste Pass 在 RunComplex 里接入只多一个 hook；
> Worker pool 并行把 stageExecute 内部 swap 成 workerpool.Run；
> Budget 跟踪的 token 数从 advisor.TokensOut 加进 ledger。

---

## 三态 Verdict 协议

任何 verifier（包括未来新增的）必须遵守的 4 字段契约：

```go
type Verification struct {
    Passed         bool    // 兼容字段：true=PASS / 旧版 PASS；false=FIX 或 ESCALATE
    Reason         string  // 人类可读
    Verdict        Verdict // "PASS" | "FIX" | "ESCALATE"
    RedispatchHint string  // FIX 时给 executor 的重派指令
}
```

判定原则：

| 错误类型 | 判定 | 理由 |
|---------|------|------|
| 数据自洽类（MovePlan≠TotalFiles、body 空、count 不一致） | **FIX** | Planner/Executor 改一行 prompt 就能修 |
| 表达含糊类（nil report、未识别 mode、用户没说 title） | **ESCALATE** | 需要更贵模型理解意图 |
| 物理失败类（apply 后实地校验失败） | **FIX** | 重派 Executor 重新执行即可 |
| 边界冲突类（两 worker 结果矛盾、计划要结构改） | **ESCALATE** | 触发 Advisor consult |

向后兼容：所有 `&Verification{Passed: true, Reason: "ok"}` 老调用点，调用
`backwardCompatVerdict()` 自动补算 Verdict（不会因为升级炸掉现有 195 个测试）。

---

## Advisor Consult 协议

```go
type ConsultRequest struct {
    Type     ConsultType // "plan_review" | "escalation" | "taste_pass"
    Task     string      // 任务描述 + 成功标准
    Question string      // 一个具体的问题
    Material Material    // map[string]any — 计划 / 冲突 / 草稿
}

type ConsultResponse struct {
    Verdict       string   // 1 行判断
    TopRisks      []string // 1-3 个最大风险
    SpecificFixes []string // 具体改法（quoted / 编号）
    WhatToIgnore  []string // orchestrator 过度看重的内容
    Raw           string   // LLM 原始响应（解析失败时 fallback）
    TokensOut     int      // 进 ledger 用
}
```

硬约束：

- 300 字上限（skill discipline）
- JSON 字段名不可改（`verdict / top_risks / specific_fixes / what_to_ignore`）
  → `TestAdvisor_JSONFieldNamesLocked` 守住
- 解析失败不静默 —— `Verdict = "(parse-failed)"` + `Raw` 保留原文

---

## Failure Ledger 协议

JSONL，每行一条事件，落在 `~/.cache/deepin-agent-teams/ledger.jsonl`。

```jsonl
{"ts":"2026-07-22T07:30:00Z","run_id":"run_xxx","type":"run_start",...}
{"ts":"...","run_id":"...","type":"frame","extra":{"success_criteria":[...],...}}
{"ts":"...","run_id":"...","type":"plan","extra":{"intent":"organize_files"}}
{"ts":"...","run_id":"...","type":"plan_review","verdict":"Plan fine but..."}
{"ts":"...","run_id":"...","type":"dispatch","duration_ms":150}
{"ts":"...","run_id":"...","type":"verify","verdict":"FIX","reason":"..."}
{"ts":"...","run_id":"...","type":"subtask_fix","subtask_id":"...","attempt":1}
{"ts":"...","run_id":"...","type":"run_end","extra":{"budget_remaining":12}}
```

EventType 常量表：

| EventType | 触发点 |
|-----------|--------|
| `run_start` / `run_end` | RunComplex 入口/出口 |
| `frame` | 写入 opts |
| `plan` | stagePlan 完成 |
| `plan_review` | Advisor consult #1 |
| `dispatch` | stageExecute 完成 |
| `verify` | stageVerify 完成 |
| `subtask_pass` / `subtask_fix` / `subtask_escalate` | verifier 三态 |
| `escalation` | Advisor consult #2 (commitment boundary) |
| `redispatch` | FIX 触发重派（待 Worker pool 接入时启用） |
| `taste_pass` | Advisor consult #3（v5+ 后续） |

---

## 使用方法

### CLI（未来要做的）

```bash
./bin/team run \
  --user-input "整理 ~/Downloads" \
  --budget 10 \
  --criteria "分类计数自洽" "preview 报告 MovePlan 非空" \
  --llm qwen  # Planner 模型
  --advisor claude-fable-5  # 贵 Advisor
```

### Go API（现在能用）

```go
o := orchestrator.New(chatModel)
adv := advisor.NewAdvisorAgent(advisorModel)
ldg, _ := ledger.New()

out, err := o.RunComplex(ctx, "整理 ~/Downloads", RunComplexOpts{
    Ledger:          ldg,
    AdvisorAgent:    adv,
    SuccessCriteria: []string{"分类计数自洽", "preview MovePlan 非空"},
    Budget:          10,
})
```

### 测试/调试用法

```go
var buf bytes.Buffer
ldg := ledger.OpenWriter(&buf)  // 注入 buffer，不写盘

o.RunComplex(ctx, "...", RunComplexOpts{
    Ledger: ldg,
    AdvisorAgent: adv,
})
// 然后 parseEvents(t, &buf) 校验事件流
```

---

## 与 advisor-orchestrator-worker skill 的对位关系

v5 落地是 skill 的**最小可裁剪版**，未来扩展点：

| Skill 要求 | v5 落地 | 待办 |
|------------|--------|------|
| Frame step 工具检查（agy/claude CLI 等） | 部分（opts 声明） | v5+ 把工具检查放到 frame 里 |
| Stateless briefs（每个 worker 独立 input） | ❌ | 等 workerpool 接入 |
| 7 步循环完整 | 6 步（缺 Taste Pass） | v5+ |
| Worker 批大小（Antigravity 3 上限） | ❌ | workerpool.Run 加 batchSize 参数 |
| Commit boundary 完整覆盖 | 部分（仅 ESCALATE） | v5+ 加上"两 worker 矛盾"检测 |
| 退出格式（deliverable + 计划 + ledger + advisor 备注 + 风险） | 部分 | RunComplex 最后输出格式化 |
| 退化模式（model missing） | ❌ | advisor 包加 Degraded 标志 |

> **注意**：skill 强调"经济账算得清"——v5 落地的 Budget 只是次数上限，
> token 计量在 advisor.TokensOut + ledger.Extra 落地，方便事后算成本。

---

## 落地清单（4 个 commit）

```
e4a3711 feat(verifier): add PASS/FIX/ESCALATE three-state verdict (v5 M5 team pattern)
a294988 feat(workerpool): add concurrent worker pool with per-worker timeout
8496c2e feat(ledger): add JSONL failure ledger for team-mode audit
7d1ceca feat(orchestrator): add RunComplex entry point wiring Advisor + Worker pool + Ledger
```

测试：226/226 PASS（含 -race）；pre-commit hook 守住 secrets 风险。

---

## 接下来（M5 之后）

- **Worker pool 挂上 Execute**：把 stageExecute 内部按 multi-directory 拆成 workers 并发
- **Taste Pass consult**：在 RunComplex 末尾多发一次 Advisor consult
- **Wails GUI 接 RunComplex**：GUI 现有的是 Run，要新增 RunComplex 选项
- **真 deepin 25 上验证 Worker pool**：DI 模块并行跑 gdbus 时无 head-of-line block
- **cost 仪表盘**：从 ledger.jsonl 渲染一段时间内的 budget 占用 + Advisor 介入率

---

## 引用

- Skill 源码：`awesome-llm-apps/agent_skills/advisor-orchestrator-worker/SKILL.md`
- Skill 协议：`references/advisor-consult.md`（4 段响应式）
- Skill 失败账本格式：SKILL.md 的 Finish 段
- v4 plan：`v4-plan.md`，v5 不动 v4 plan 的破坏性承诺
