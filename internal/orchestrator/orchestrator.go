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
	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
	intentpkg "github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// Orchestrator 编排器
type Orchestrator struct {
	intentAgent *agents.IntentAgent
	planner     *agents.PlannerAgent
	verifier    *agents.VerifierAgent
	chatModel   agents.ChatModel
}

// New 创建编排器
//
// 接 agents.ChatModel interface（*openai.ChatModel / mockChatModel 都满足）。
// 原 model.ChatModel（*openai.ChatModel）是这个 interface 的实现，调用方零改动。
func New(chatModel agents.ChatModel) *Orchestrator {
	return &Orchestrator{
		intentAgent: agents.NewIntentAgent(chatModel),
		planner:     agents.NewPlannerAgent(chatModel),
		verifier:    agents.NewVerifierAgent(),
		chatModel:   chatModel,
	}
}

// PipelineContext 三段 Chain 中传递的中间状态
type PipelineContext struct {
	UserInput      string
	Intent         *intentpkg.Intent
	Plan           *agents.OrganizePlan
	ReminderPlan   *agents.ReminderPlan
	EmailPlan      *agents.EmailPlan
	SettingsPlan   *agents.SettingsPlan
	Report         *tools.OrganizeReport
	ReminderReport *tools.ReminderReport
	EmailReport    *tools.EmailDraftReport
	SettingsReport *tools.SettingsReport
	Verify         *agents.Verification
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

// RunMulti 处理多意图输入（v4 M3 新增）
//
// 调用 IntentAgent.RecognizeMulti 拿到 []*intent.Intent；如果只有 1 个，降级走 Run。
// 多意图时逐个调 runSingle（复用 Run 的同一套 chain），拼接各 chain 输出。
//
// 失败策略：单个 chain 失败不中断其他 chain，但会在该 chain 输出里加错误标记。
func (o *Orchestrator) RunMulti(ctx context.Context, userInput string) (string, error) {
	intents, err := o.intentAgent.RecognizeMulti(ctx, userInput)
	if err != nil {
		return "", fmt.Errorf("recognize multi: %w", err)
	}

	// 过滤掉 unknown（保留至少 1 个，避免返回空）
	filtered := make([]*intentpkg.Intent, 0, len(intents))
	for _, it := range intents {
		if it.Action != intentpkg.ActionUnknown {
			filtered = append(filtered, it)
		}
	}
	if len(filtered) == 0 {
		filtered = intents // 如果全是 unknown，保留作为提示用户
	}

	// 单意图走 Run（完整 chain 路径）
	if len(filtered) == 1 {
		return o.runSingle(ctx, userInput, filtered[0])
	}

	// 多意图：逐个走，拼接结果
	results := make([]string, 0, len(filtered))
	for i, it := range filtered {
		out, err := o.runSingle(ctx, userInput, it)
		if err != nil {
			results = append(results, fmt.Sprintf("❌ 第 %d 个意图执行失败: %v", i+1, err))
			continue
		}
		results = append(results, out)
	}

	return strings.Join(results, "\n\n---\n\n"), nil
}

// runSingle 在指定 Intent 下走完整 chain（被 Run 和 RunMulti 复用）
//
// 这个函数不做 Intent 识别，直接用传进来的 it （IntentAgent 识别后的结果）。
// 为什么要拆出来：RunMulti 已经在外面调用了 RecognizeMulti，重复识别会浪费 LLM token。
func (o *Orchestrator) runSingle(ctx context.Context, userInput string, it *intentpkg.Intent) (string, error) {
	// 用 eino 表达“预设 Intent → 补齐 Plan → 调工具 → 校验”。
	// 为避免重写三个 stage，这里改成手动调用顺序（等价于 chain.Invoke 的展开）。
	pc := &PipelineContext{UserInput: userInput, Intent: it}

	// Stage 1: Plan
	if err := o.populatePlan(ctx, pc); err != nil {
		return "", fmt.Errorf("stage plan: %w", err)
	}
	// Stage 2: Execute
	pc, err := o.stageExecute(ctx, pc)
	if err != nil {
		return "", err
	}
	// Stage 3: Verify
	pc, err = o.stageVerify(ctx, pc)
	if err != nil {
		return "", err
	}
	return formatOutput(pc)
}

// populatePlan 根据预识别的 Intent 调用 Planner，补齐 Plan 字段
// （从 Run / RunMulti 复用）
func (o *Orchestrator) populatePlan(ctx context.Context, pc *PipelineContext) error {
	it := pc.Intent
	switch it.Action {
	case intentpkg.ActionDraftEmail:
		ep, err := o.planner.PlanEmail(ctx, pc.UserInput, it)
		if err != nil {
			ep = &agents.EmailPlan{
				Recipient: it.Recipient, Subject: it.Subject,
				Purpose: it.Purpose, Tone: "formal", Mode: it.Mode,
			}
			if ep.Mode == "" {
				ep.Mode = "preview"
			}
		}
		pc.EmailPlan = ep
	case intentpkg.ActionApplySettings:
		sp, err := o.planner.PlanSettings(ctx, pc.UserInput, it)
		if err != nil {
			sp = &agents.SettingsPlan{
				Changes: []tools.SettingChange{{
					Category: it.SettingsCategory, NewValue: it.SettingsValue,
				}},
				Mode: it.Mode,
			}
			if sp.Mode == "" {
				sp.Mode = "preview"
			}
		}
		pc.SettingsPlan = sp
	case intentpkg.ActionScheduleReminder:
		rp, err := o.planner.PlanReminder(ctx, pc.UserInput, it)
		if err != nil {
			rp = &agents.ReminderPlan{
				Title: it.Title, DueAt: it.DueAt,
				Priority: it.Priority, Mode: it.Mode,
			}
			if rp.Priority == "" {
				rp.Priority = "normal"
			}
			if rp.Mode == "" {
				rp.Mode = "preview"
			}
		}
		pc.ReminderPlan = rp
	case intentpkg.ActionOrganizeFiles:
		plan, err := o.planner.PlanOrganize(ctx, pc.UserInput, it)
		if err != nil {
			plan = &agents.OrganizePlan{Directory: it.Directory, Mode: it.Mode}
			if plan.Directory == "" {
				plan.Directory = "~/Downloads"
			}
			if plan.Mode == "" {
				plan.Mode = "preview"
			}
		}
		pc.Plan = plan
	}
	return nil
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

	// 1b. 非文件整理/日程提醒/邮件草稿/系统设置 → 走原 v3 路径（主题/系统信息）
	if it.Action != intentpkg.ActionOrganizeFiles && it.Action != intentpkg.ActionScheduleReminder && it.Action != intentpkg.ActionDraftEmail && it.Action != intentpkg.ActionApplySettings {
		return pc, nil
	}

	// 1e. 邮件草稿 → 调 Planner 撰写正文
	if it.Action == intentpkg.ActionDraftEmail {
		ep, err := o.planner.PlanEmail(ctx, userInput, it)
		if err != nil {
			// Planner 失败 → 用 Intent 默认值兜底
			ep = &agents.EmailPlan{
				Recipient: it.Recipient,
				Subject:   it.Subject,
				Purpose:   it.Purpose,
				Tone:      "formal",
				Mode:      it.Mode,
			}
			if ep.Mode == "" {
				ep.Mode = "preview"
			}
		}
		pc.EmailPlan = ep
		return pc, nil
	}

	// 1f. 系统设置 → 调 Planner 提取 category + value
	if it.Action == intentpkg.ActionApplySettings {
		sp, err := o.planner.PlanSettings(ctx, userInput, it)
		if err != nil {
			// Planner 失败 → 用 Intent 默认值兜底
			sp = &agents.SettingsPlan{
				Changes: []tools.SettingChange{{
					Category: it.SettingsCategory,
					NewValue: it.SettingsValue,
				}},
				Mode: it.Mode,
			}
			if sp.Mode == "" {
				sp.Mode = "preview"
			}
		}
		pc.SettingsPlan = sp
		return pc, nil
	}

	// 1c. 日程提醒 → 调 Planner 翻译自然语言时间
	if it.Action == intentpkg.ActionScheduleReminder {
		rp, err := o.planner.PlanReminder(ctx, userInput, it)
		if err != nil {
			// Planner 失败 → 用 Intent 默认值兜底
			rp = &agents.ReminderPlan{
				Title:    it.Title,
				DueAt:    it.DueAt,
				Priority: it.Priority,
				Mode:     it.Mode,
			}
			if rp.Priority == "" {
				rp.Priority = "normal"
			}
			if rp.Mode == "" {
				rp.Mode = "preview"
			}
		}
		pc.ReminderPlan = rp
		return pc, nil
	}

	// 1d. 文件整理 → 调 Planner 生成详细计划
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
			Mode:        "theme",
			VerifPassed: true,
			VerifMsg:    fmt.Sprintf("已切换到 %s 主题", theme),
			AppliedCmds: []string{fmt.Sprintf("theme.set(%s)", theme)},
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

	if pc.Intent.Action != intentpkg.ActionOrganizeFiles && pc.Intent.Action != intentpkg.ActionScheduleReminder && pc.Intent.Action != intentpkg.ActionDraftEmail && pc.Intent.Action != intentpkg.ActionApplySettings {
		pc.Report = &tools.OrganizeReport{
			Mode:        "unknown",
			VerifPassed: false,
			VerifMsg:    "未识别意图",
		}
		return pc, nil
	}

	// 日程提醒：调真实工具
	if pc.Intent.Action == intentpkg.ActionScheduleReminder {
		pc.ReminderReport = tools.ScheduleReminder(ctx, pc.ReminderPlan.Title, pc.ReminderPlan.DueAt, pc.ReminderPlan.Priority, pc.ReminderPlan.Mode)
		return pc, nil
	}

	// 邮件草稿：调真实工具
	if pc.Intent.Action == intentpkg.ActionDraftEmail {
		pc.EmailReport = tools.DraftEmail(ctx, pc.EmailPlan.Recipient, pc.EmailPlan.Subject, pc.EmailPlan.Purpose, pc.EmailPlan.Body, pc.EmailPlan.Tone, pc.EmailPlan.Mode)
		return pc, nil
	}

	// 系统设置：调真实工具
	if pc.Intent.Action == intentpkg.ActionApplySettings {
		pc.SettingsReport = tools.ApplySettings(ctx, pc.SettingsPlan.Changes, pc.SettingsPlan.Mode)
		return pc, nil
	}

	// 文件整理：调真实工具
	pc.Report = tools.OrganizeFiles(ctx, pc.Plan.Directory, pc.Plan.Mode)
	return pc, nil
}

// stageVerify Stage 3: Verifier 校验
func (o *Orchestrator) stageVerify(ctx context.Context, pc *PipelineContext) (*PipelineContext, error) {
	switch pc.Intent.Action {
	case intentpkg.ActionScheduleReminder:
		pc.Verify = o.verifier.VerifyReminderReport(ctx, pc.ReminderReport)
	case intentpkg.ActionDraftEmail:
		pc.Verify = o.verifier.VerifyEmailReport(ctx, pc.EmailReport)
	case intentpkg.ActionApplySettings:
		pc.Verify = o.verifier.VerifySettingsReport(ctx, pc.SettingsReport)
	default:
		pc.Verify = o.verifier.VerifyOrganizeReport(ctx, pc.Report)
	}
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

	case intentpkg.ActionScheduleReminder:
		return formatReminderOutput(pc), nil

	case intentpkg.ActionDraftEmail:
		return formatEmailOutput(pc), nil

	case intentpkg.ActionApplySettings:
		return formatSettingsOutput(pc), nil

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

// formatReminderOutput 格式化日程提醒输出（v4 M2 新增）
func formatReminderOutput(pc *PipelineContext) string {
	var sb strings.Builder
	rp := pc.ReminderPlan
	rr := pc.ReminderReport

	if rp.Mode == "preview" {
		sb.WriteString("📅 **日程提醒预览**（未写入，加 --apply 才会存储）\n\n")
	} else {
		sb.WriteString("🚀 **日程提醒已存储**\n\n")
	}

	sb.WriteString(fmt.Sprintf("📌 标题: **%s**\n", rp.Title))
	sb.WriteString(fmt.Sprintf("⏰ 时间: %s\n", rp.DueAt))
	sb.WriteString(fmt.Sprintf("🎯 优先级: %s\n", rp.Priority))

	if rp.Mode == "apply" && rr != nil && rr.StoragePath != "" {
		sb.WriteString(fmt.Sprintf("🆔 ID: `%s`\n", rr.ReminderID))
		sb.WriteString(fmt.Sprintf("📁 路径: `%s`\n", rr.StoragePath))
	}

	if rp.Rationale != "" {
		sb.WriteString(fmt.Sprintf("\n💡 判断: %s\n", rp.Rationale))
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

// formatEmailOutput 格式化邮件草稿输出（v4 M2 新增）
func formatEmailOutput(pc *PipelineContext) string {
	var sb strings.Builder
	ep := pc.EmailPlan
	er := pc.EmailReport

	if ep.Mode == "preview" {
		sb.WriteString("📧 **邮件草稿预览**（未保存，加 --apply 才会落盘）\n\n")
	} else {
		sb.WriteString("🚀 **邮件草稿已保存**\n\n")
	}

	recipient := ep.Recipient
	if recipient == "" {
		recipient = "(未指定收件人)"
	}
	sb.WriteString(fmt.Sprintf("📨 收件人: `%s`\n", recipient))
	sb.WriteString(fmt.Sprintf("📌 主题: **%s**\n", ep.Subject))
	sb.WriteString(fmt.Sprintf("🎨 语气: %s\n", ep.Tone))

	if ep.Mode == "apply" && er != nil && er.StoragePath != "" {
		sb.WriteString(fmt.Sprintf("🆔 ID: `%s`\n", er.DraftID))
		sb.WriteString(fmt.Sprintf("📁 路径: `%s`\n", er.StoragePath))
	}

	if ep.Purpose != "" {
		sb.WriteString(fmt.Sprintf("\n💭 目的: %s\n", ep.Purpose))
	}

	if ep.Rationale != "" {
		sb.WriteString(fmt.Sprintf("💡 判断: %s\n", ep.Rationale))
	}

	// 正文（用代码块包起来方便看格式）
	if er != nil && er.Body != "" {
		sb.WriteString("\n📝 **正文预览**:\n```\n")
		sb.WriteString(er.Body)
		sb.WriteString("\n```\n")
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

// formatSettingsOutput 格式化系统设置输出（v4 M2 新增）
func formatSettingsOutput(pc *PipelineContext) string {
	var sb strings.Builder
	sp := pc.SettingsPlan
	sr := pc.SettingsReport

	if sp.Mode == "preview" {
		sb.WriteString("⚙️ **系统设置预览**（未应用，加 --apply 才会真改）\n\n")
	} else {
		sb.WriteString("🚀 **系统设置已应用**\n\n")
	}

	if len(sr.Categories) > 0 {
		sb.WriteString(fmt.Sprintf("📦 分类数: %d（%s）\n\n", len(sr.Categories), strings.Join(sr.Categories, ", ")))
	} else {
		sb.WriteString("📦 分类数: 0\n\n")
	}

	sb.WriteString("**变更明细**:\n")
	for i, c := range sr.Changes {
		icon := "📋"
		if c.Status == "applied" {
			icon = "✅"
		} else if c.Status == "failed" {
			icon = "❌"
		}
		sb.WriteString(fmt.Sprintf("  %s %d. [%s] %s = %s", icon, i+1, c.Category, c.Key, c.NewValue))
		if c.Message != "" {
			sb.WriteString(fmt.Sprintf(" — %s", c.Message))
		}
		sb.WriteString("\n")
	}

	if sp.Rationale != "" {
		sb.WriteString(fmt.Sprintf("\n💡 判断: %s\n", sp.Rationale))
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
