package orchestrator

import (
	"context"
	"strings"
	"testing"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
	intentpkg "github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// fakeChatModel 是 orchestrator 测试专用的 LLM mock
// （与 internal/agents 包的同名 mock 重名但不冲突——跨包独立）
type fakeChatModel struct {
	// 预设的 LLM 返回内容
	response string
	// 调用计数（用于多意图场景验证）
	calls int
	// 记录每次调用的 prompt 内容（用于断言多意图 prompt 被使用）
	lastPrompts []string
}

func (f *fakeChatModel) Generate(_ context.Context, in []*schema.Message, _ ...model.Option) (*schema.Message, error) {
	f.calls++
	if len(in) > 0 {
		f.lastPrompts = append(f.lastPrompts, in[0].Content)
	}
	return &schema.Message{Role: schema.Assistant, Content: f.response}, nil
}

// 快速构造一个 Orchestrator + fakeChatModel 供测试使用
func newTestOrchestrator(response string) (*Orchestrator, *fakeChatModel) {
	f := &fakeChatModel{response: response}
	o := New(f)
	return o, f
}

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

// === RunMulti 测试 (v4 M3 多意图) ===

func TestRunMulti_SingleIntent_DelegatesToRunPath(t *testing.T) {
	// LLM 返回单意图（数组长度 1），应该走 Run 路径（不调 2 次 LLM）
	f := &fakeChatModel{
		response: `[{"action":"get_system_info"}]`,
	}
	o := New(f)
	got, err := o.RunMulti(context.Background(), "看下系统信息")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "系统") {
		t.Errorf("expected sysinfo output, got %q", got)
	}
}

func TestRunMulti_TwoIntents_OutputHasSeparator(t *testing.T) {
	// LLM 返回 2 个 apply_settings，输出应该用 --- 分隔
	f := &fakeChatModel{
		response: `[{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark","mode":"preview"},{"action":"apply_settings","settings_category":"volume","settings_value":"30","mode":"preview"}]`,
	}
	o := New(f)
	got, err := o.RunMulti(context.Background(), "切深色 + 音量 30")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "---") {
		t.Errorf("multi-intent output should have separator, got %q", got)
	}
	if !strings.Contains(got, "theme") {
		t.Errorf("output should mention theme, got %q", got)
	}
	if !strings.Contains(got, "volume") {
		t.Errorf("output should mention volume, got %q", got)
	}
}

func TestRunMulti_HeterogeneousIntents_AllRun(t *testing.T) {
	// settings + reminder + email 三意图，每个 chain 都跑
	f := &fakeChatModel{
		response: `[{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark","mode":"preview"},{"action":"schedule_reminder","title":"开会","due_at":"2026-07-20T09:00:00+08:00","priority":"normal","mode":"preview"},{"action":"draft_email","purpose":"请假","mode":"preview"}]`,
	}
	o := New(f)
	got, err := o.RunMulti(context.Background(), "切深色 + 提醒开会 + 请假邮件")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "deepin-dark") {
		t.Errorf("output should mention theme value, got %q", got)
	}
	if !strings.Contains(got, "开会") {
		t.Errorf("output should mention reminder title, got %q", got)
	}
	if !strings.Contains(got, "请假") {
		t.Errorf("output should mention email purpose, got %q", got)
	}
}

func TestRunMulti_LLMError_BubblesUp(t *testing.T) {
	// LLM 调用失败 → RunMulti 返回错误（不吞掉）
	f := &fakeChatModel{} // response 空，ParseMulti 会报错
	f.response = "not json"
	o := New(f)
	_, err := o.RunMulti(context.Background(), "anything")
	if err == nil {
		t.Fatal("expected error when LLM returns invalid JSON")
	}
}

func TestRunMulti_AllUnknown_FallsBackToConfusedMessage(t *testing.T) {
	// 所有意图都是 unknown（LLM 识别不出来）→ 各 chain 都走 unknown 路径
	f := &fakeChatModel{
		response: `[{"action":"unknown"},{"action":"unknown"}]`,
	}
	o := New(f)
	got, err := o.RunMulti(context.Background(), "火星语")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "没理解") {
		t.Errorf("unknown intents should show confused message, got %q", got)
	}
}

func TestRunMulti_FiltersOutUnknown_ButKeepsAtLeastOne(t *testing.T) {
	// 2 个 intent 里 1 个 unknown 1 个有效 → 只跑有效的 1 个
	f := &fakeChatModel{
		response: `[{"action":"unknown"},{"action":"get_system_info"}]`,
	}
	o := New(f)
	got, err := o.RunMulti(context.Background(), "火星语 + 看下系统信息")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// 只跑 1 个 → 不应该有 ---
	if strings.Contains(got, "---") {
		t.Errorf("should not have separator when only 1 valid intent, got %q", got)
	}
	if !strings.Contains(got, "系统") {
		t.Errorf("should show sysinfo, got %q", got)
	}
}

func TestRunMulti_EmptyArray_ReturnsError(t *testing.T) {
	f := &fakeChatModel{response: `[]`}
	o := New(f)
	_, err := o.RunMulti(context.Background(), "anything")
	if err == nil {
		t.Error("empty array should return error")
	}
}
