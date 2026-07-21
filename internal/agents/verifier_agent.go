package agents

import (
	"context"
	"fmt"
	"strings"

	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
)

// VerifierAgent 验证 Agent
//
// v4 M2 新增：v3 状态机的精华 - "执行后必须验证"
// 职责：拿到执行报告后，独立校验（不信任 Executor 的自我汇报）
type VerifierAgent struct{}

// NewVerifierAgent 创建 Verifier
func NewVerifierAgent() *VerifierAgent {
	return &VerifierAgent{}
}

// Verdict 验证三态（v5/v5 M5 团队模式新增）
//
// 对应 advisor-orchestrator-worker skill 的三态 verdict：
//   - PASS      通过（保留原 Passed=true 的语义）
//   - FIX       本地可重派：保留 Verification 信息，并给出重派指令
//   - ESCALATE  需要更贵模型/Advisor 介入判断
//
// 旧调用方只用 Passed/Reason 判断，行为零变化；
// 新调用方（worker_pool / orchestrator.RunComplex）会读 Verdict + RedispatchHint。
type Verdict string

const (
	VerdictPass      Verdict = "PASS"
	VerdictFix       Verdict = "FIX"
	VerdictEscalate  Verdict = "ESCALATE"
)

// Verification 验证结果
type Verification struct {
	Passed bool   // 兼容字段：true=PASS/部分 FIX/ESCALATE 前的中间态；false=FIX 或 ESCALATE
	Reason string // 人类可读的失败/通过原因

	// v5 团队模式字段（默认零值，等价于旧行为）
	Verdict        Verdict // PASS / FIX / ESCALATE（建议字段，不再依赖 Passed 推断）
	RedispatchHint string  // FIX 时：给 executor 的重派指令（命名失败，advisor-orchestrator-worker 的 brief 约定）
}

// pass 内部助手：构造 PASS verdict，同时保留兼容 Passed=true
func pass(reason string) *Verification {
	return &Verification{Passed: true, Verdict: VerdictPass, Reason: reason}
}

// fail 内部助手：旧版默认 FIX（保留 Passed=false 兼容行为），若需 ESCALATE 用 failEscalate
func fail(reason string) *Verification {
	return &Verification{Passed: false, Verdict: VerdictFix, Reason: reason}
}

// failWithHint FIX 且带重派指令
func failWithHint(reason, hint string) *Verification {
	return &Verification{
		Passed:         false,
		Verdict:        VerdictFix,
		Reason:         reason,
		RedispatchHint: hint,
	}
}

// failEscalate ESCALATE（需要 Advisor 介入）
func failEscalate(reason string) *Verification {
	return &Verification{Passed: false, Verdict: VerdictEscalate, Reason: reason}
}

// backwardCompatVerdict 兼容层：从旧结构补算 Verdict（仅用作过渡期反向补全）
//
// 如果某个旧测试或旧调用点构造了只填 Passed/Reason 的 Verification，
// 调用本函数会基于 Passed 给出默认 verdict：
//   - Passed=true  → VerdictPass
//   - Passed=false → VerdictFix（默认走本地重派，不假定需要 Advisor）
func backwardCompatVerdict(v *Verification) *Verification {
	if v == nil {
		return nil
	}
	if v.Verdict != "" {
		return v // 已显式设置，不再覆盖
	}
	if v.Passed {
		v.Verdict = VerdictPass
	} else {
		v.Verdict = VerdictFix
	}
	return v
}

// VerifyOrganizeReport 验证文件整理报告
//
// 检查项：
//  1. preview 模式：MovePlan 非空且数量一致
//  2. apply 模式：分类目录存在 + 文件数与报告一致
func (v *VerifierAgent) VerifyOrganizeReport(ctx context.Context, report *tools.OrganizeReport) *Verification {
	if report == nil {
		return failEscalate("报告为空（需要 Planner 重新生成）")
	}

	// 通用：分类计数加总要等于 TotalFiles
	sum := 0
	for _, n := range report.Categories {
		sum += n
	}
	if sum != report.TotalFiles {
		return failWithHint(
			fmt.Sprintf("分类计数不一致: 分类和=%d, TotalFiles=%d", sum, report.TotalFiles),
			"重新扫描目录，按真实扩展名分类，确保每类计数加总等于 TotalFiles",
		)
	}

	// preview 模式：必须生成 MovePlan
	if report.Mode == "preview" {
		if len(report.MovePlan) == 0 {
			return failWithHint("preview 模式但 MovePlan 为空", "重新生成 preview，对每个文件给出 (Src, Dst, Kind) 三元组")
		}
		if len(report.MovePlan) != report.TotalFiles {
			return failWithHint(
				fmt.Sprintf("MovePlan(%d) 与 TotalFiles(%d) 不一致", len(report.MovePlan), report.TotalFiles),
				fmt.Sprintf("重派：要求 MovePlan 长度=%d", report.TotalFiles),
			)
		}
		return pass(fmt.Sprintf("preview 报告自洽: %d 个文件", report.TotalFiles))
	}

	// apply 模式：实地验证分类目录
	if report.Mode == "apply" {
		ok, msg := tools.VerifyOrganize(ctx, report.Directory, report.Categories)
		if !ok {
			return failWithHint("apply 模式实地验证失败: "+msg, "重新执行文件移动，逐个文件 fsync 后再验证")
		}
		return pass(msg)
	}

	return failEscalate(fmt.Sprintf("未知 mode: %s（需要 Planner 显式声明 preview/apply）", report.Mode))
}

// VerifyReminderReport 验证日程提醒报告（v4 M2 新增）
//
// 检查项：
//  1. preview 模式：标题非空 + 报告自洽
//  2. apply 模式：StoragePath 存在 + JSON 可解析 + title 一致
func (v *VerifierAgent) VerifyReminderReport(ctx context.Context, report *tools.ReminderReport) *Verification {
	if report == nil {
		return failEscalate("报告为空（Planner 未生成）")
	}
	if report.Title == "" {
		return failWithHint("title 为空", "从用户输入提取标题；若用户没说 title，用主谓宾结构自动生成")
	}

	// preview 模式：只校验报告自洽
	if report.Mode != "apply" {
		return pass(fmt.Sprintf("preview 报告自洽: '%s' 计划于 %s", report.Title, report.DueAt))
	}

	// apply 模式：实地验证文件
	if report.StoragePath == "" {
		return failWithHint("apply 模式但 StoragePath 为空", "重派执行：append 到 reminders.json，返回 StoragePath")
	}
	ok, msg := tools.VerifyReminder(ctx, report.StoragePath, report.Title)
	if !ok {
		return failWithHint("apply 模式实地验证失败: "+msg, "重新写入 reminders.json，确认 title 字段匹配")
	}
	return pass(msg)
}

// VerifyEmailReport 验证邮件草稿报告（v4 M2 新增）
//
// 检查项：
//  1. preview 模式：subject 或 purpose 至少一个非空 + body 长度合理
//  2. apply 模式：StoragePath 存在 + .eml 含 To/Subject 头部
func (v *VerifierAgent) VerifyEmailReport(ctx context.Context, report *tools.EmailDraftReport) *Verification {
	if report == nil {
		return failEscalate("报告为空（Planner 未生成）")
	}
	if report.Subject == "" && report.Purpose == "" {
		return failWithHint("subject 和 purpose 都为空", "重派 Planner：必须给出 subject 或 purpose 至少一个")
	}
	if len(strings.TrimSpace(report.Body)) == 0 {
		return failWithHint("body 为空，Planner 未生成正文", "重派 Planner：根据 purpose 撰写 ≥50 字正文")
	}

	// preview 模式：只校验报告自洽
	if report.Mode != "apply" {
		return pass(fmt.Sprintf("preview 报告自洽: 主题=%q, 正文长度=%d", report.Subject, len(report.Body)))
	}

	// apply 模式：实地验证 .eml 文件
	if report.StoragePath == "" {
		return failWithHint("apply 模式但 StoragePath 为空", "重派 Executor：写入 .eml 并返回 StoragePath")
	}
	ok, msg := tools.VerifyEmailDraft(ctx, report.StoragePath, report.Subject)
	if !ok {
		return failWithHint("apply 模式实地验证失败: "+msg, "重新生成 .eml，确认 To/Subject 头完整")
	}
	return pass(msg)
}

// VerifySettingsReport 验证系统设置报告（v4 M2 新增）
//
// 检查项：
//  1. preview 模式：至少一个 change + 校验都通过
//  2. apply 模式：settings.json 存在 + 含本次所有变更的 (category, key, new_value)
func (v *VerifierAgent) VerifySettingsReport(ctx context.Context, report *tools.SettingsReport) *Verification {
	if report == nil {
		return failEscalate("报告为空（Planner 未生成）")
	}
	if len(report.Changes) == 0 {
		return failWithHint("changes 为空", "重派 Planner：至少给出一项 (category, key, new_value)")
	}

	// preview 模式：报告自洽检查（每项 status 应该是 planned）
	if report.Mode != "apply" {
		for _, c := range report.Changes {
			if c.Status != "planned" {
				return failWithHint(
					fmt.Sprintf("preview 模式下 change[%s] status=%s（应为 planned）", c.Category, c.Status),
					fmt.Sprintf("重派 Planner：所有变更 status 必须为 planned（category=%s）", c.Category),
				)
			}
		}
		return pass(fmt.Sprintf("preview 报告自洽: %d 项设置", len(report.Changes)))
	}

	// apply 模式：实地验证
	ok, msg := tools.VerifySettings(ctx, report.Changes)
	if !ok {
		return failWithHint("apply 模式实地验证失败: "+msg, "重派 Executor：把每项 change 写入 settings.json 后再次验证")
	}
	return pass(msg)
}
