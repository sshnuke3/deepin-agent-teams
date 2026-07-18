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

// Verification 验证结果
type Verification struct {
	Passed bool
	Reason string
}

// VerifyOrganizeReport 验证文件整理报告
//
// 检查项：
//  1. preview 模式：MovePlan 非空且数量一致
//  2. apply 模式：分类目录存在 + 文件数与报告一致
func (v *VerifierAgent) VerifyOrganizeReport(ctx context.Context, report *tools.OrganizeReport) *Verification {
	if report == nil {
		return &Verification{Passed: false, Reason: "报告为空"}
	}

	// 通用：分类计数加总要等于 TotalFiles
	sum := 0
	for _, n := range report.Categories {
		sum += n
	}
	if sum != report.TotalFiles {
		return &Verification{
			Passed: false,
			Reason: fmt.Sprintf("分类计数不一致: 分类和=%d, TotalFiles=%d", sum, report.TotalFiles),
		}
	}

	// preview 模式：必须生成 MovePlan
	if report.Mode == "preview" {
		if len(report.MovePlan) == 0 {
			return &Verification{Passed: false, Reason: "preview 模式但 MovePlan 为空"}
		}
		if len(report.MovePlan) != report.TotalFiles {
			return &Verification{
				Passed: false,
				Reason: fmt.Sprintf("MovePlan(%d) 与 TotalFiles(%d) 不一致", len(report.MovePlan), report.TotalFiles),
			}
		}
		return &Verification{Passed: true, Reason: fmt.Sprintf("preview 报告自洽: %d 个文件", report.TotalFiles)}
	}

	// apply 模式：实地验证分类目录
	if report.Mode == "apply" {
		ok, msg := tools.VerifyOrganize(ctx, report.Directory, report.Categories)
		return &Verification{Passed: ok, Reason: msg}
	}

	return &Verification{Passed: false, Reason: fmt.Sprintf("未知 mode: %s", report.Mode)}
}

// VerifyReminderReport 验证日程提醒报告（v4 M2 新增）
//
// 检查项：
//  1. preview 模式：标题非空 + 报告自洽
//  2. apply 模式：StoragePath 存在 + JSON 可解析 + title 一致
func (v *VerifierAgent) VerifyReminderReport(ctx context.Context, report *tools.ReminderReport) *Verification {
	if report == nil {
		return &Verification{Passed: false, Reason: "报告为空"}
	}
	if report.Title == "" {
		return &Verification{Passed: false, Reason: "title 为空"}
	}

	// preview 模式：只校验报告自洽
	if report.Mode != "apply" {
		return &Verification{Passed: true, Reason: fmt.Sprintf("preview 报告自洽: '%s' 计划于 %s", report.Title, report.DueAt)}
	}

	// apply 模式：实地验证文件
	if report.StoragePath == "" {
		return &Verification{Passed: false, Reason: "apply 模式但 StoragePath 为空"}
	}
	ok, msg := tools.VerifyReminder(ctx, report.StoragePath, report.Title)
	return &Verification{Passed: ok, Reason: msg}
}

// VerifyEmailReport 验证邮件草稿报告（v4 M2 新增）
//
// 检查项：
//  1. preview 模式：subject 或 purpose 至少一个非空 + body 长度合理
//  2. apply 模式：StoragePath 存在 + .eml 含 To/Subject 头部
func (v *VerifierAgent) VerifyEmailReport(ctx context.Context, report *tools.EmailDraftReport) *Verification {
	if report == nil {
		return &Verification{Passed: false, Reason: "报告为空"}
	}
	if report.Subject == "" && report.Purpose == "" {
		return &Verification{Passed: false, Reason: "subject 和 purpose 都为空"}
	}
	if len(strings.TrimSpace(report.Body)) == 0 {
		return &Verification{Passed: false, Reason: "body 为空，Planner 未生成正文"}
	}

	// preview 模式：只校验报告自洽
	if report.Mode != "apply" {
		return &Verification{
			Passed: true,
			Reason: fmt.Sprintf("preview 报告自洽: 主题=%q, 正文长度=%d", report.Subject, len(report.Body)),
		}
	}

	// apply 模式：实地验证 .eml 文件
	if report.StoragePath == "" {
		return &Verification{Passed: false, Reason: "apply 模式但 StoragePath 为空"}
	}
	ok, msg := tools.VerifyEmailDraft(ctx, report.StoragePath, report.Subject)
	return &Verification{Passed: ok, Reason: msg}
}
