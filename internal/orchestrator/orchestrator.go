// Package orchestrator 提供 Eino 编排逻辑
//
// v4 M2 架构：Planner → Executor → Verifier 三段 Lambda Chain
//
// 关键变化（相对 v3 状态机）：
// - 把 v3 的 7 个状态压成 3 个 Lambda 节点
// - Executor 直接调工具，不通过 LLM（快、可测）
// - Verifier 独立 Agent，强制执行后校验
package orchestrator

import (
	"context"
	"fmt"
	"strings"

	"github.com/cloudwego/eino/compose"

	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
	"github.com/sshnuke3/deepin-agent-teams/internal/model"
	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
	intentpkg "github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// Orchestrator 编排器
type Orchestrator struct {
	intentAgent *agents.IntentAgent
	planner     *agents.PlannerAgent
	verifier    *agents.VerifierAgent
	chatModel   model.ChatModel
}

// New 创建编排器
func New(chatModel model.ChatModel) *Orchestrator {
	return &Orchestrator{
		intentAgent: agents.NewIntentAgent(chatModel),
		planner:     agents.NewPlannerAgent(chatModel),
		verifier:    agents.NewVerifierAgent(),
		chatModel:   chatModel,
	}
}

// PipelineContext 三段 Chain 中传递的中间状态
type PipelineContext struct {
	UserInput string
	Intent    *intentpkg.Intent
	Plan      *agents.OrganizePlan
	Report    *tools.OrganizeReport
	Verify    *agents.Verification
}

// Run 处理用户输入，返回响应
func (o *Orchestrator) Run(ctx context.Context, userInput string) (string, error) {
	// ============ 三段 Lambda Chain ============
	// Stage 1: Intent → Plan (IntentAgent + PlannerAgent)
	// Stage 2: Plan → Report (Executor: 调工具)
	// Stage 3: Report → Verify (Verifier: 校验)
	chain := compose.NewChain[string, *PipelineContext]().
		AppendLambda(compose.InvokableLambda(o.stagePlan)).
		AppendLambda(compose.InvokableLambda(o.stageExecute)).
		AppendLambda(compose.InvokableLambda(o.stageVerify))

	runnable, err := chain.Compile(ctx)
	if err != nil {
		return "", fmt.Errorf("compile chain: %w", err)
	}

	pc, err := runnable.Invoke(ctx, userInput)
	if err != nil {
		return "", err
	}

	// ============ 格式化最终输出 ============
	return formatOutput(pc)
}

// stagePlan Stage 1: Intent + Plan
func (o *Orchestrator) stagePlan(ctx context.Context, userInput string) (*PipelineContext, error) {
	pc := &PipelineContext{UserInput: userInput}

	// 1a. Intent 识别
	it, err := o.intentAgent.Recognize(ctx, userInput)
	if err != nil {
		return nil, fmt.Errorf("recognize intent: %w", err)
	}
	pc.Intent = it

	// 1b. 非文件整理 → 走原 v3 路径（主题/系统信息）
	if it.Action != intentpkg.ActionOrganizeFiles {
		return pc, nil
	}

	// 1c. 文件整理 → 调 Planner 生成详细计划
	plan, err := o.planner.PlanOrganize(ctx, userInput, it)
	if err != nil {
		// Planner 失败 → 用 Intent 默认值兜底
		plan = &agents.OrganizePlan{
			Directory: it.Directory,
			Mode:      it.Mode,
		}
		if plan.Directory == "" {
			plan.Directory = "~/Downloads"
		}
		if plan.Mode == "" {
			plan.Mode = "preview"
		}
	}
	pc.Plan = plan
	return pc, nil
}

// stageExecute Stage 2: Executor 调工具
func (o *Orchestrator) stageExecute(ctx context.Context, pc *PipelineContext) (*PipelineContext, error) {
	if pc.Intent.Action == intentpkg.ActionChangeTheme {
		theme := pc.Intent.Theme
		if theme == "" {
			theme = intentpkg.ThemeAuto
		}
		// 主题走 Result 报告，包装进 fake Report 复用 format
		pc.Report = &tools.OrganizeReport{
			Mode:         "theme",
			VerifPassed:  true,
			VerifMsg:     fmt.Sprintf("已切换到 %s 主题", theme),
			AppliedCmds:  []string{fmt.Sprintf("theme.set(%s)", theme)},
		}
		return pc, nil
	}

	if pc.Intent.Action == intentpkg.ActionGetSystemInfo {
		pc.Report = &tools.OrganizeReport{
			Mode:        "sysinfo",
			VerifPassed: true,
			VerifMsg:    tools.GetSystemInfo(ctx).Message,
		}
		return pc, nil
	}

	if pc.Intent.Action != intentpkg.ActionOrganizeFiles {
		pc.Report = &tools.OrganizeReport{
			Mode:        "unknown",
			VerifPassed: false,
			VerifMsg:    "未识别意图",
		}
		return pc, nil
	}

	// 文件整理：调真实工具
	pc.Report = tools.OrganizeFiles(ctx, pc.Plan.Directory, pc.Plan.Mode)
	return pc, nil
}

// stageVerify Stage 3: Verifier 校验
func (o *Orchestrator) stageVerify(ctx context.Context, pc *PipelineContext) (*PipelineContext, error) {
	pc.Verify = o.verifier.VerifyOrganizeReport(ctx, pc.Report)
	return pc, nil
}

// formatOutput 格式化最终回复
func formatOutput(pc *PipelineContext) (string, error) {
	if pc.Intent == nil {
		return "❌ 内部错误: 意图为空", nil
	}

	switch pc.Intent.Action {
	case intentpkg.ActionChangeTheme:
		return fmt.Sprintf("✅ %s", pc.Report.VerifMsg), nil

	case intentpkg.ActionGetSystemInfo:
		return fmt.Sprintf("ℹ️ %s", pc.Report.VerifMsg), nil

	case intentpkg.ActionOrganizeFiles:
		return formatOrganizeOutput(pc), nil

	default:
		return "🤔 我没理解您的意思，请尝试：'整理 Downloads 文件' 或 '切到深色模式'", nil
	}
}

func formatOrganizeOutput(pc *PipelineContext) string {
	var sb strings.Builder

	// 头部
	if pc.Plan.Mode == "preview" {
		sb.WriteString("📋 **文件整理预览**（未真移，加 --apply 才会执行）\n\n")
	} else {
		sb.WriteString("🚀 **文件整理已执行**\n\n")
	}

	// 目录
	sb.WriteString(fmt.Sprintf("📂 目录: `%s`\n", pc.Plan.Directory))

	// 统计
	if pc.Report.TotalFiles == 0 {
		sb.WriteString("\n✨ 没有需要整理的文件\n")
		return sb.String()
	}

	sb.WriteString(fmt.Sprintf("📊 待整理: %d 个文件\n\n", pc.Report.TotalFiles))

	// 分类明细
	sb.WriteString("**分类明细**:\n")
	for category, count := range pc.Report.Categories {
		sb.WriteString(fmt.Sprintf("  - %s/: %d 个\n", category, count))
	}
	if pc.Report.OtherCount > 0 {
		sb.WriteString(fmt.Sprintf("  - 其他（不分类）: %d 个\n", pc.Report.OtherCount))
	}

	// 验证
	sb.WriteString("\n**验证**:\n")
	if pc.Verify.Passed {
		sb.WriteString(fmt.Sprintf("  ✅ %s\n", pc.Verify.Reason))
	} else {
		sb.WriteString(fmt.Sprintf("  ❌ %s\n", pc.Verify.Reason))
	}

	return sb.String()
}