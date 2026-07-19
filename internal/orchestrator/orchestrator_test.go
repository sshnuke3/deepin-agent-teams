package orchestrator

import (
	"strings"
	"testing"

	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
	intentpkg "github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

func TestFormatOutput_NilIntent(t *testing.T) {
	pc := &PipelineContext{}
	got, err := formatOutput(pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "内部错误") {
		t.Errorf("nil intent should return internal error, got %q", got)
	}
}

func TestFormatOutput_UnknownAction(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionUnknown},
	}
	got, err := formatOutput(pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "没理解") {
		t.Errorf("unknown action should return confused message, got %q", got)
	}
}

func TestFormatOutput_ChangeTheme(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionChangeTheme, Theme: intentpkg.ThemeDark},
		Report: &tools.OrganizeReport{VerifMsg: "已切换到 deepin-dark 主题"},
	}
	got, err := formatOutput(pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "deepin-dark") {
		t.Errorf("should contain theme name, got %q", got)
	}
}

func TestFormatOutput_GetSystemInfo(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionGetSystemInfo},
		Report: &tools.OrganizeReport{VerifMsg: "OS: deepin 25"},
	}
	got, err := formatOutput(pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "OS: deepin 25") {
		t.Errorf("should contain system info, got %q", got)
	}
}

func TestFormatOrganizeOutput_Preview(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionOrganizeFiles},
		Plan: &agents.OrganizePlan{
			Directory: "/home/user/Downloads",
			Mode:      "preview",
		},
		Report: &tools.OrganizeReport{
			Mode:       "preview",
			TotalFiles: 5,
			Categories: map[string]int{"images": 3, "docs": 2},
			OtherCount: 0,
		},
		Verify: &agents.Verification{Passed: true, Reason: "preview 报告自洽: 5 个文件"},
	}
	got := formatOrganizeOutput(pc)
	if !strings.Contains(got, "文件整理预览") {
		t.Errorf("should show preview header, got %q", got)
	}
	if !strings.Contains(got, "5 个文件") {
		t.Errorf("should show total files, got %q", got)
	}
	if !strings.Contains(got, "images/: 3 个") {
		t.Errorf("should show images category, got %q", got)
	}
}

func TestFormatOrganizeOutput_Apply(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionOrganizeFiles},
		Plan: &agents.OrganizePlan{
			Directory: "/tmp/test",
			Mode:      "apply",
		},
		Report: &tools.OrganizeReport{
			Mode:       "apply",
			TotalFiles: 2,
			Categories: map[string]int{"code": 2},
		},
		Verify: &agents.Verification{Passed: true, Reason: "文件已移动"},
	}
	got := formatOrganizeOutput(pc)
	if !strings.Contains(got, "已执行") {
		t.Errorf("should show applied header, got %q", got)
	}
}

func TestFormatOrganizeOutput_EmptyFiles(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionOrganizeFiles},
		Plan: &agents.OrganizePlan{
			Directory: "/tmp/empty",
			Mode:      "preview",
		},
		Report: &tools.OrganizeReport{
			Mode:       "preview",
			TotalFiles: 0,
			Categories: map[string]int{},
		},
		Verify: &agents.Verification{Passed: true, Reason: "无文件"},
	}
	got := formatOrganizeOutput(pc)
	if !strings.Contains(got, "没有需要整理的文件") {
		t.Errorf("should show no files message, got %q", got)
	}
}

func TestFormatOrganizeOutput_WithOtherCount(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionOrganizeFiles},
		Plan: &agents.OrganizePlan{
			Directory: "/tmp",
			Mode:      "preview",
		},
		Report: &tools.OrganizeReport{
			Mode:       "preview",
			TotalFiles: 4,
			Categories: map[string]int{"images": 2},
			OtherCount: 2,
		},
		Verify: &agents.Verification{Passed: true, Reason: "ok"},
	}
	got := formatOrganizeOutput(pc)
	if !strings.Contains(got, "其他（不分类）: 2 个") {
		t.Errorf("should show other count, got %q", got)
	}
}

func TestFormatOrganizeOutput_FailedVerification(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionOrganizeFiles},
		Plan: &agents.OrganizePlan{
			Directory: "/tmp",
			Mode:      "preview",
		},
		Report: &tools.OrganizeReport{
			Mode:       "preview",
			TotalFiles: 1,
			Categories: map[string]int{"docs": 1},
			MovePlan:   []tools.MoveEntry{{Src: "/a", Dst: "/b"}},
		},
		Verify: &agents.Verification{Passed: false, Reason: "分类计数不一致"},
	}
	got := formatOrganizeOutput(pc)
	if !strings.Contains(got, "分类计数不一致") {
		t.Errorf("should show verification failure reason, got %q", got)
	}
}

func TestFormatReminderOutput_Preview(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionScheduleReminder},
		ReminderPlan: &agents.ReminderPlan{
			Title:    "开会",
			DueAt:    "2026-07-20T10:00:00+08:00",
			Priority: "high",
			Mode:     "preview",
		},
		ReminderReport: &tools.ReminderReport{
			Title:    "开会",
			DueAt:    "2026-07-20T10:00:00+08:00",
			Priority: "high",
			Mode:     "preview",
		},
		Verify: &agents.Verification{Passed: true, Reason: "preview 报告自洽"},
	}
	got := formatReminderOutput(pc)
	if !strings.Contains(got, "日程提醒预览") {
		t.Errorf("should show preview header, got %q", got)
	}
	if !strings.Contains(got, "开会") {
		t.Errorf("should show title, got %q", got)
	}
	if !strings.Contains(got, "high") {
		t.Errorf("should show priority, got %q", got)
	}
}

func TestFormatReminderOutput_Apply(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionScheduleReminder},
		ReminderPlan: &agents.ReminderPlan{
			Title:    "提交报告",
			DueAt:    "2026-07-21T17:00:00+08:00",
			Priority: "normal",
			Mode:     "apply",
			Rationale: "用户说很重要",
		},
		ReminderReport: &tools.ReminderReport{
			Title:       "提交报告",
			DueAt:       "2026-07-21T17:00:00+08:00",
			Priority:    "normal",
			Mode:        "apply",
			ReminderID:  "rem-123",
			StoragePath: "/home/user/.local/share/deepin-agent/reminders/rem-123.json",
		},
		Verify: &agents.Verification{Passed: true, Reason: "文件已存储"},
	}
	got := formatReminderOutput(pc)
	if !strings.Contains(got, "已存储") {
		t.Errorf("should show apply header, got %q", got)
	}
	if !strings.Contains(got, "rem-123") {
		t.Errorf("should show reminder ID, got %q", got)
	}
	if !strings.Contains(got, "用户说很重要") {
		t.Errorf("should show rationale, got %q", got)
	}
}

func TestFormatEmailOutput_Preview(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionDraftEmail},
		EmailPlan: &agents.EmailPlan{
			Recipient: "boss@example.com",
			Subject:   "周报",
			Purpose:   "汇报本周进展",
			Tone:      "formal",
			Mode:      "preview",
		},
		EmailReport: &tools.EmailDraftReport{
			Subject: "周报",
			Purpose: "汇报本周进展",
			Body:    "Hi Boss,\n本周完成 x,y,z.\nBest,\n龙虾",
			Tone:    "formal",
			Mode:    "preview",
		},
		Verify: &agents.Verification{Passed: true, Reason: "preview 报告自洽"},
	}
	got := formatEmailOutput(pc)
	if !strings.Contains(got, "邮件草稿预览") {
		t.Errorf("should show preview header, got %q", got)
	}
	if !strings.Contains(got, "boss@example.com") {
		t.Errorf("should show recipient, got %q", got)
	}
	if !strings.Contains(got, "正文预览") {
		t.Errorf("should show body preview, got %q", got)
	}
}

func TestFormatEmailOutput_NoRecipient(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionDraftEmail},
		EmailPlan: &agents.EmailPlan{
			Subject: "周报",
			Purpose: "汇报",
			Tone:    "formal",
			Mode:    "preview",
		},
		EmailReport: &tools.EmailDraftReport{
			Subject: "周报",
			Purpose: "汇报",
			Body:    "正文内容",
			Tone:    "formal",
			Mode:    "preview",
		},
		Verify: &agents.Verification{Passed: true, Reason: "ok"},
	}
	got := formatEmailOutput(pc)
	if !strings.Contains(got, "(未指定收件人)") {
		t.Errorf("should show placeholder for missing recipient, got %q", got)
	}
}

func TestFormatSettingsOutput_Preview(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionApplySettings},
		SettingsPlan: &agents.SettingsPlan{
			Mode: "preview",
			Changes: []tools.SettingChange{
				{Category: "theme", NewValue: "deepin-dark", Status: "planned"},
			},
		},
		SettingsReport: &tools.SettingsReport{
			Mode:       "preview",
			Categories: []string{"theme"},
			Changes: []tools.SettingChange{
				{Category: "theme", NewValue: "deepin-dark", Status: "planned"},
			},
		},
		Verify: &agents.Verification{Passed: true, Reason: "preview 报告自洽: 1 项设置"},
	}
	got := formatSettingsOutput(pc)
	if !strings.Contains(got, "系统设置预览") {
		t.Errorf("should show preview header, got %q", got)
	}
	if !strings.Contains(got, "theme") {
		t.Errorf("should show theme category, got %q", got)
	}
}

func TestFormatSettingsOutput_Apply(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionApplySettings},
		SettingsPlan: &agents.SettingsPlan{
			Mode: "apply",
			Changes: []tools.SettingChange{
				{Category: "volume", NewValue: "50", Status: "applied"},
			},
		},
		SettingsReport: &tools.SettingsReport{
			Mode:       "apply",
			Categories: []string{"volume"},
			Changes: []tools.SettingChange{
				{Category: "volume", NewValue: "50", Status: "applied", Message: "音量已设置"},
			},
		},
		Verify: &agents.Verification{Passed: true, Reason: "设置已应用"},
	}
	got := formatSettingsOutput(pc)
	if !strings.Contains(got, "已应用") {
		t.Errorf("should show applied header, got %q", got)
	}
	if !strings.Contains(got, "音量已设置") {
		t.Errorf("should show change message, got %q", got)
	}
}

func TestFormatSettingsOutput_FailedChange(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionApplySettings},
		SettingsPlan: &agents.SettingsPlan{
			Mode: "apply",
			Changes: []tools.SettingChange{
				{Category: "network", NewValue: "on", Status: "failed", Message: "权限不足"},
			},
		},
		SettingsReport: &tools.SettingsReport{
			Mode:       "apply",
			Categories: []string{"network"},
			Changes: []tools.SettingChange{
				{Category: "network", NewValue: "on", Status: "failed", Message: "权限不足"},
			},
		},
		Verify: &agents.Verification{Passed: false, Reason: "设置应用失败"},
	}
	got := formatSettingsOutput(pc)
	if !strings.Contains(got, "权限不足") {
		t.Errorf("should show failure message, got %q", got)
	}
	if !strings.Contains(got, "设置应用失败") {
		t.Errorf("should show verification failure, got %q", got)
	}
}

func TestFormatSettingsOutput_NoRationale(t *testing.T) {
	pc := &PipelineContext{
		Intent: &intentpkg.Intent{Action: intentpkg.ActionApplySettings},
		SettingsPlan: &agents.SettingsPlan{
			Mode: "preview",
			Changes: []tools.SettingChange{
				{Category: "brightness", NewValue: "80", Status: "planned"},
			},
		},
		SettingsReport: &tools.SettingsReport{
			Mode:       "preview",
			Categories: []string{"brightness"},
			Changes: []tools.SettingChange{
				{Category: "brightness", NewValue: "80", Status: "planned"},
			},
		},
		Verify: &agents.Verification{Passed: true, Reason: "ok"},
	}
	got := formatSettingsOutput(pc)
	if strings.Contains(got, "判断:") {
		t.Errorf("should not show rationale when empty, got %q", got)
	}
}
