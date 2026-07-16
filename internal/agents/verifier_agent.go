package agents

import (
	"context"
	"fmt"

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