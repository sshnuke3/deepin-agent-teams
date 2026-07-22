package orchestrator

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/sshnuke3/deepin-agent-teams/internal/advisor"
	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
	"github.com/sshnuke3/deepin-agent-teams/internal/ledger"
	intentpkg "github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// RunComplexOpts RunComplex 的可选配置
//
// 全部字段可选——不传就走默认值（向后兼容）。
type RunComplexOpts struct {
	// Ledger 账本（nil = 不记账；tests 注入 buffer-backed ledger）
	Ledger *ledger.Ledger

	// AdvisorAgent 贵模型顾问（nil = 跳过所有 consult，跳过 ESCALATE 处理）
	// 实际部署可以接 Claude Fable 5 / GPT-5.6 等更强模型。
	AdvisorAgent *advisor.AdvisorAgent

	// SuccessCriteria 用户在 frame 阶段声明的 3-5 条可测成功标准
	// （原 advisor-orchestrator-worker skill frame step 的产物）
	SuccessCriteria []string

	// Budget 整次 Run 的 dispatches/consults 总上限
	// 超出后 stop + report，不静默烧 token。
	Budget int

	// RunID 自定义（默认自动生成）
	RunID string

	// Now 注入时间源（测试用）
	Now func() time.Time
}

// RunComplex 团队模式（v5 M5）：走 advisor-orchestrator-worker 7 步 loop 的最小可裁剪版本
//
// 与 Run 的关系：
//   - Run 还在，三段串行 chain 不动
//   - RunComplex 是新入口，包了：
//     1. Frame：声明成功标准 + ledger 开账
//     2. Plan：复用 Run.stagePlan
//     3. Plan Review：(可选) advisor consult #1
//     4. Execute：复用 Run.stageExecute
//     5. Verify：复用 Run.stageVerify；如果 Verdict==ESCALATE 触发 advisor consult #2
//     6. Taste Pass：(可选) advisor consult #3  整体审查
//     7. Finish：ledger 收尾 + 报告
//
// 失败处理：
//   - 任一 advisor 报错 → 退化为不挂 advisor 继续 Run（非致命）
//   - Budget 超 → 立刻 stop + 报告（不静默烧）
func (o *Orchestrator) RunComplex(ctx context.Context, userInput string, opts RunComplexOpts) (string, error) {
	runID := opts.RunID
	if runID == "" {
		runID = ledger.NewRunID()
	}
	ldg := opts.Ledger

	nowFn := opts.Now
	if nowFn == nil {
		nowFn = time.Now
	}

	// 1. Frame
	ldg.Emit(ledger.Event{
		RunID: runID, Type: ledger.EventRunStart,
		Extra: map[string]any{"user_input_length": len(userInput)},
	})
	ldg.Emit(ledger.Event{
		RunID: runID, Type: ledger.EventFrame,
		Extra: map[string]any{
			"success_criteria": opts.SuccessCriteria,
			"budget":           opts.Budget,
		},
	})

	if opts.Budget <= 0 {
		opts.Budget = 20 // 默认预算
	}

	budget := &budgetTracker{remaining: opts.Budget}

	// 2. Plan（用现有 stagePlan 来补齐 Plan）
	pc, err := o.runPrePlan(ctx, userInput)
	if err != nil {
		ldg.Emit(ledger.Event{RunID: runID, Type: ledger.EventRunEnd, Reason: "plan failed: " + err.Error()})
		return "", err
	}
	ldg.Emit(ledger.Event{
		RunID: runID, Type: ledger.EventPlan,
		Extra: map[string]any{"intent": pc.Intent.Action},
	})

	// 3. Plan Review（advisor consult #1，可选）
	if opts.AdvisorAgent != nil && budget.tryConsume(1) {
		reviewResp, err := o.advisorPlanReview(ctx, opts.AdvisorAgent, runID, pc, opts.SuccessCriteria)
		if err != nil {
			ldg.Emit(ledger.Event{
				RunID: runID, Type: ledger.EventPlanReview,
				Reason: "advisor error: " + err.Error(),
			})
		} else if reviewResp != nil {
			ldg.Emit(ledger.Event{
				RunID: runID, Type: ledger.EventPlanReview,
				Verdict: reviewResp.Verdict,
				Reason:  strings.Join(reviewResp.SpecificFixes, "; "),
				Extra: map[string]any{
					"top_risks":     reviewResp.TopRisks,
					"what_to_ignore": reviewResp.WhatToIgnore,
					"tokens_out":    reviewResp.TokensOut,
				},
			})
			// 主流程不阻塞，只在报告里展示 advisor 意见
		}
	}

	// 4. Execute（用现有 stageExecute）
	start := nowFn()
	pc, err = o.stageExecute(ctx, pc)
	if err != nil {
		ldg.Emit(ledger.Event{RunID: runID, Type: ledger.EventRunEnd, Reason: "execute failed: " + err.Error()})
		return "", err
	}
	ldg.Emit(ledger.Event{
		RunID: runID, Type: ledger.EventDispatch,
		DurationMs: nowFn().Sub(start).Milliseconds(),
	})

	// 5. Verify
	pc, err = o.stageVerify(ctx, pc)
	if err != nil {
		ldg.Emit(ledger.Event{RunID: runID, Type: ledger.EventRunEnd, Reason: "verify failed: " + err.Error()})
		return "", err
	}
	ldg.Emit(ledger.Event{
		RunID: runID, Type: ledger.EventVerify,
		Verdict: string(pc.Verify.Verdict),
		Reason:  pc.Verify.Reason,
	})
	if pc.Verify.Verdict != "" {
		// ledger 留 subtask-style 记录
		ldg.Subtask(runID, fmt.Sprintf("stageVerify_%s", pc.Intent.Action),
			string(pc.Verify.Verdict), pc.Verify.Reason, 0, 1)
	}

	// 6. ESCALATE → advisor consult #2（commitment boundary）
	if pc.Verify.Verdict == agents.VerdictEscalate && opts.AdvisorAgent != nil && budget.tryConsume(1) {
		escResp, err := o.advisorEscalation(ctx, opts.AdvisorAgent, runID, pc)
		if err != nil {
			ldg.Emit(ledger.Event{
				RunID: runID, Type: ledger.EventEscalation,
				Reason: "advisor error: " + err.Error(),
			})
		} else if escResp != nil {
			ldg.Emit(ledger.Event{
				RunID: runID, Type: ledger.EventEscalation,
				Verdict: escResp.Verdict,
				Reason:  strings.Join(escResp.SpecificFixes, "; "),
			})
		}
	}

	// 7. Finish
	finalOut, err := formatOutput(pc)
	if err != nil {
		ldg.Emit(ledger.Event{RunID: runID, Type: ledger.EventRunEnd, Reason: "format failed: " + err.Error()})
		return "", err
	}

	if budget.exhausted() {
		finalOut += fmt.Sprintf("\n\n⚠️ Budget exhausted (%d)", opts.Budget)
	}

	ldg.Emit(ledger.Event{
		RunID: runID, Type: ledger.EventRunEnd,
		Extra: map[string]any{"budget_remaining": budget.remaining},
	})
	return finalOut, nil
}

// runPrePlan 只跑 stagePlan，等价于 Run 第一步，但不立刻走 execute。
// 复用现有 stagePlan；不要重复走 Recognize（节省 token）。
func (o *Orchestrator) runPrePlan(ctx context.Context, userInput string) (*PipelineContext, error) {
	pc := &PipelineContext{UserInput: userInput}
	it, err := o.intentAgent.Recognize(ctx, userInput)
	if err != nil {
		return nil, fmt.Errorf("recognize intent: %w", err)
	}
	pc.Intent = it
	// 复用 stagePlan 的 Plan 填充逻辑
	if err := o.populatePlan(ctx, pc); err != nil {
		return nil, fmt.Errorf("populate plan: %w", err)
	}
	return pc, nil
}

// advisorPlanReview 调 advisor 做 plan review（loop step 3）
func (o *Orchestrator) advisorPlanReview(
	ctx context.Context,
	adv *advisor.AdvisorAgent,
	runID string,
	pc *PipelineContext,
	criteria []string,
) (*advisor.ConsultResponse, error) {
	task := pc.UserInput
	if len(criteria) > 0 {
		task += "\n\nSuccess criteria:\n- " + strings.Join(criteria, "\n- ")
	}

	mat := advisor.Material{
		"intent":  string(pc.Intent.Action),
		"plan":    planToMap(pc),
		"run_id":  runID,
	}
	resp, err := adv.Consult(ctx, advisor.ConsultRequest{
		Type:     advisor.TypePlanReview,
		Task:     task,
		Question: "Will this plan deliver against the success criteria, and what's the highest-risk thing to fix now?",
		Material: mat,
	})
	return resp, err
}

// advisorEscalation 调 advisor 做 escalation consult（commitment boundary）
func (o *Orchestrator) advisorEscalation(
	ctx context.Context,
	adv *advisor.AdvisorAgent,
	runID string,
	pc *PipelineContext,
) (*advisor.ConsultResponse, error) {
	mat := advisor.Material{
		"run_id":          runID,
		"intent":          string(pc.Intent.Action),
		"verify_verdict":  string(pc.Verify.Verdict),
		"verify_reason":   pc.Verify.Reason,
		"redispatch_hint": pc.Verify.RedispatchHint,
	}
	resp, err := adv.Consult(ctx, advisor.ConsultRequest{
		Type:     advisor.TypeEscalation,
		Task:     pc.UserInput,
		Question: "The verifier escalated. Should we redispatch (FIX), accept the failure, or change strategy?",
		Material: mat,
	})
	return resp, err
}

// planToMap 把 PipelineContext 序列化成 Material（去掉 nil）
func planToMap(pc *PipelineContext) map[string]any {
	out := map[string]any{}
	if pc.Intent != nil {
		out["intent"] = pc.Intent.Action
		if pc.Intent.Recipient != "" {
			out["recipient"] = pc.Intent.Recipient
		}
		if pc.Intent.Subject != "" {
			out["subject"] = pc.Intent.Subject
		}
		if pc.Intent.Directory != "" {
			out["directory"] = pc.Intent.Directory
		}
		if pc.Intent.Title != "" {
			out["title"] = pc.Intent.Title
		}
		if pc.Intent.Mode != "" {
			out["mode"] = pc.Intent.Mode
		}
	}
	if pc.Plan != nil {
		out["plan_kind"] = "organize"
		out["plan"] = pc.Plan
	}
	if pc.ReminderPlan != nil {
		out["plan_kind"] = "reminder"
		out["plan"] = pc.ReminderPlan
	}
	if pc.EmailPlan != nil {
		out["plan_kind"] = "email"
		out["plan"] = pc.EmailPlan
	}
	if pc.SettingsPlan != nil {
		out["plan_kind"] = "settings"
		out["plan"] = pc.SettingsPlan
	}
	return out
}

// budgetTracker 简单的预算跟踪
type budgetTracker struct {
	remaining int
}

func (b *budgetTracker) tryConsume(n int) bool {
	if b.remaining < n {
		return false
	}
	b.remaining -= n
	return true
}

func (b *budgetTracker) exhausted() bool {
	return b.remaining <= 0
}

// 保留意图判别助手（被 runPrePlan 通过 populatePlan 间接调用）
//
// 不再重复引用 intent.Action 字符串，避免常量改动不一致
var _ = intentpkg.ActionOrganizeFiles
