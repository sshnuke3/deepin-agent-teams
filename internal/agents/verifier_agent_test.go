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
}
