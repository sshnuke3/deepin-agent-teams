package agents

import (
	"context"
	"testing"

	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
)

func TestVerifier_VerifyOrganizeReport_Preview(t *testing.T) {
	v := NewVerifierAgent()

	// 正常 preview 报告
	report := &tools.OrganizeReport{
		Mode:       "preview",
		TotalFiles: 3,
		Categories: map[string]int{"images": 2, "docs": 1},
		MovePlan: []tools.MoveEntry{
			{Src: "/a", Dst: "/b", Kind: "images"},
			{Src: "/c", Dst: "/d", Kind: "images"},
			{Src: "/e", Dst: "/f", Kind: "docs"},
		},
	}
	res := v.VerifyOrganizeReport(context.Background(), report)
	if !res.Passed {
		t.Errorf("preview 报告应通过: %s", res.Reason)
	}
	if res.Verdict != VerdictPass {
		t.Errorf("preview 通过时应为 VerdictPass，实际=%q", res.Verdict)
	}

	// MovePlan 与 TotalFiles 不一致 → 应失败
	bad := &tools.OrganizeReport{
		Mode:       "preview",
		TotalFiles: 5, // 虚报
		Categories: map[string]int{"images": 3, "docs": 2},
		MovePlan: []tools.MoveEntry{
			{Src: "/a", Dst: "/b", Kind: "images"},
		},
	}
	res = v.VerifyOrganizeReport(context.Background(), bad)
	if res.Passed {
		t.Error("MovePlan 与 TotalFiles 不一致时应失败")
	}
	if res.Verdict != VerdictFix {
		t.Errorf("数据自洽类问题应走本地重派 VerdictFix，实际=%q", res.Verdict)
	}
	if res.RedispatchHint == "" {
		t.Error("FIX verdict 必须有 RedispatchHint")
	}
}

func TestVerifier_VerifyOrganizeReport_UnknownMode(t *testing.T) {
	v := NewVerifierAgent()
	report := &tools.OrganizeReport{
		Mode:       "weird-mode",
		TotalFiles: 1,
		Categories: map[string]int{"images": 1},
		MovePlan:   []tools.MoveEntry{{Src: "/a", Dst: "/b"}},
	}
	res := v.VerifyOrganizeReport(context.Background(), report)
	if res.Passed {
		t.Error("未知 mode 应失败")
	}
	// 未知 mode 是 Planner 表达含糊 → 需要 Advisor 介入解释意图
	if res.Verdict != VerdictEscalate {
		t.Errorf("未知 mode 应走 ESCALATE，实际=%q", res.Verdict)
	}
}

func TestVerifier_VerifyOrganizeReport_NilReport(t *testing.T) {
	v := NewVerifierAgent()
	res := v.VerifyOrganizeReport(context.Background(), nil)
	if res == nil {
		t.Fatal("nil 报告也应返回判断结果")
	}
	if res.Verdict != VerdictEscalate {
		t.Errorf("nil 报告应 ESCALATE（Planner 根本没生成），实际=%q", res.Verdict)
	}
}

// ===== 三态 Verdict 全行为测试（v5 M5 团队模式新增）=====

func TestVerification_BackwardCompat(t *testing.T) {
	// 旧调用点只填 Passed/Reason → backwardCompatVerdict 应补算 Verdict
	passOld := &Verification{Passed: true, Reason: "ok"}
	backwardCompatVerdict(passOld)
	if passOld.Verdict != VerdictPass {
		t.Errorf("Passed=true 应补算 VerdictPass，实际=%q", passOld.Verdict)
	}

	failOld := &Verification{Passed: false, Reason: "fail"}
	backwardCompatVerdict(failOld)
	if failOld.Verdict != VerdictFix {
		t.Errorf("Passed=false 应默认补算 VerdictFix（本地可重派），实际=%q", failOld.Verdict)
	}

	// 已显式设置的不应被覆盖
	explicit := &Verification{Passed: false, Verdict: VerdictEscalate, Reason: "需要 Advisor"}
	backwardCompatVerdict(explicit)
	if explicit.Verdict != VerdictEscalate {
		t.Errorf("显式 Verdict 不应被覆盖，实际=%q", explicit.Verdict)
	}
}

func TestVerifier_VerifyReminderReport_TitleEmpty(t *testing.T) {
	v := NewVerifierAgent()
	report := &tools.ReminderReport{
		Mode:  "preview",
		Title: "",
		DueAt: "明天 3 点",
	}
	res := v.VerifyReminderReport(context.Background(), report)
	if res.Verdict != VerdictFix {
		t.Errorf("空 title 应走 FIX（可本地重派让 Planner 补），实际=%q", res.Verdict)
	}
	if res.RedispatchHint == "" {
		t.Error("FIX 必须有重派 hint")
	}
}

func TestVerifier_VerifyReminderReport_Preview_Pass(t *testing.T) {
	v := NewVerifierAgent()
	report := &tools.ReminderReport{
		Mode:  "preview",
		Title: "买菜",
		DueAt: "今晚 6 点",
	}
	res := v.VerifyReminderReport(context.Background(), report)
	if res.Verdict != VerdictPass {
		t.Errorf("preview 自洽应 PASS，实际=%q reason=%s", res.Verdict, res.Reason)
	}
}

func TestVerifier_VerifyEmailReport_BodyEmpty(t *testing.T) {
	v := NewVerifierAgent()
	report := &tools.EmailDraftReport{
		Mode:    "preview",
		Subject: "项目同步",
		Purpose: "周报",
		Body:    "", // Planner 未生成
	}
	res := v.VerifyEmailReport(context.Background(), report)
	if res.Verdict != VerdictFix {
		t.Errorf("空 body 应走 FIX，实际=%q", res.Verdict)
	}
	if res.RedispatchHint == "" {
		t.Error("FIX 必须有重派 hint（要求 Planner 撰写正文）")
	}
}

func TestVerifier_VerifySettingsReport_NoChanges(t *testing.T) {
	v := NewVerifierAgent()
	report := &tools.SettingsReport{
		Mode:    "preview",
		Changes: nil,
	}
	res := v.VerifySettingsReport(context.Background(), report)
	if res.Verdict != VerdictFix {
		t.Errorf("空 changes 应走 FIX，实际=%q", res.Verdict)
	}
}
