package agents

import (
	"context"
	"errors"
	"testing"

	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
	"github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

func TestPlanner_PlanOrganize_HappyPath(t *testing.T) {
	f := &fakeChatModel{
		response: `{"directory":"/tmp/docs","mode":"preview","categories":["docs","images"],"rationale":"用户指定目录"}`,
	}
	p := NewPlannerAgent(f)
	it := &intent.Intent{
		Action:    intent.ActionOrganizeFiles,
		Directory: "~/Downloads",
		Mode:      "preview",
	}
	got, err := p.PlanOrganize(context.Background(), "整理 ~/Downloads", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Directory != "/tmp/docs" {
		t.Errorf("got directory %q want %q", got.Directory, "/tmp/docs")
	}
	if got.Mode != "preview" {
		t.Errorf("got mode %q want %q", got.Mode, "preview")
	}
	if len(got.Categories) != 2 {
		t.Errorf("got categories len %d want 2", len(got.Categories))
	}
}

func TestPlanner_PlanOrganize_LLMReturnsMarkdownFence(t *testing.T) {
	f := &fakeChatModel{
		response: "```json\n{\"directory\":\"/tmp\",\"mode\":\"apply\",\"rationale\":\"用户要求执行\"}\n```",
	}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionOrganizeFiles, Directory: "/tmp", Mode: "apply"}
	got, err := p.PlanOrganize(context.Background(), "真的整理 /tmp", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Directory != "/tmp" {
		t.Errorf("got directory %q want %q", got.Directory, "/tmp")
	}
	if got.Mode != "apply" {
		t.Errorf("got mode %q want %q", got.Mode, "apply")
	}
}

func TestPlanner_PlanOrganize_BadJSONFallsBackToIntent(t *testing.T) {
	f := &fakeChatModel{response: "not json at all"}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionOrganizeFiles, Directory: "~/Downloads", Mode: "preview"}
	got, err := p.PlanOrganize(context.Background(), "anything", it)
	if err != nil {
		t.Fatalf("should not error on bad JSON, got %v", err)
	}
	if got.Directory != "~/Downloads" {
		t.Errorf("fallback directory should be Intent.Directory, got %q", got.Directory)
	}
	if got.Mode != "preview" {
		t.Errorf("fallback mode should be Intent.Mode, got %q", got.Mode)
	}
}

func TestPlanner_PlanOrganize_LLMError(t *testing.T) {
	f := &fakeChatModel{err: errors.New("network down")}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionOrganizeFiles, Directory: "~/Downloads", Mode: "preview"}
	_, err := p.PlanOrganize(context.Background(), "anything", it)
	if err == nil {
		t.Fatal("expected error when LLM call fails")
	}
}

func TestPlanner_PlanOrganize_EmptyFieldsGetDefaults(t *testing.T) {
	// LLM 返回空字段，应该兜底到 Intent 的值；Intent 也没的话用默认
	f := &fakeChatModel{response: `{"rationale":"only rationale"}`}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionOrganizeFiles, Directory: "", Mode: ""}
	got, err := p.PlanOrganize(context.Background(), "anything", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Directory != "~/Downloads" {
		t.Errorf("empty directory should default to ~/Downloads, got %q", got.Directory)
	}
	if got.Mode != "preview" {
		t.Errorf("empty mode should default to preview, got %q", got.Mode)
	}
}

func TestPlanner_PlanReminder_HappyPath(t *testing.T) {
	f := &fakeChatModel{
		response: `{"title":"开会","due_at":"2026-07-20T15:00:00+08:00","priority":"normal","mode":"preview","rationale":"明天下午 3 点"}`,
	}
	p := NewPlannerAgent(f)
	it := &intent.Intent{
		Action:   intent.ActionScheduleReminder,
		Title:    "开会",
		Priority: "normal",
		Mode:     "preview",
	}
	got, err := p.PlanReminder(context.Background(), "提醒我明天下午 3 点开会", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Title != "开会" {
		t.Errorf("got title %q want %q", got.Title, "开会")
	}
	if got.DueAt != "2026-07-20T15:00:00+08:00" {
		t.Errorf("got due_at %q want ISO8601", got.DueAt)
	}
}

func TestPlanner_PlanReminder_BadJSONFallsBack(t *testing.T) {
	f := &fakeChatModel{response: "garbage"}
	p := NewPlannerAgent(f)
	it := &intent.Intent{
		Action:   intent.ActionScheduleReminder,
		Title:    "提交周报",
		Priority: "high",
		Mode:     "apply",
	}
	got, err := p.PlanReminder(context.Background(), "存一下提醒", it)
	if err != nil {
		t.Fatalf("should not error, got %v", err)
	}
	if got.Title != "提交周报" {
		t.Errorf("fallback title should be Intent.Title, got %q", got.Title)
	}
	if got.Priority != "high" {
		t.Errorf("fallback priority should be Intent.Priority, got %q", got.Priority)
	}
	if got.Mode != "apply" {
		t.Errorf("fallback mode should be Intent.Mode, got %q", got.Mode)
	}
}

func TestPlanner_PlanReminder_LLMError(t *testing.T) {
	f := &fakeChatModel{err: errors.New("timeout")}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionScheduleReminder, Title: "x"}
	_, err := p.PlanReminder(context.Background(), "anything", it)
	if err == nil {
		t.Fatal("expected error when LLM call fails")
	}
}

func TestPlanner_PlanReminder_PriorityDefaultsToNormal(t *testing.T) {
	f := &fakeChatModel{response: `{"title":"开会"}`} // 没 priority
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionScheduleReminder, Title: "开会", Priority: "", Mode: ""}
	got, err := p.PlanReminder(context.Background(), "提醒开会", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Priority != "normal" {
		t.Errorf("empty priority should default to normal, got %q", got.Priority)
	}
	if got.Mode != "preview" {
		t.Errorf("empty mode should default to preview, got %q", got.Mode)
	}
}

func TestPlanner_PlanEmail_HappyPath(t *testing.T) {
	f := &fakeChatModel{
		response: `{"recipient":"alice@example.com","subject":"项目进度","purpose":"同步本周进度","body":"Hi Alice,\n本周完成 x,y,z.\nBest,\n龙虾","tone":"formal","mode":"preview","rationale":"商务邮件"}`,
	}
	p := NewPlannerAgent(f)
	it := &intent.Intent{
		Action:    intent.ActionDraftEmail,
		Recipient: "alice@example.com",
		Subject:   "项目进度",
		Purpose:   "同步本周进度",
		Mode:      "preview",
	}
	got, err := p.PlanEmail(context.Background(), "帮 Alice 起草一封项目进度邮件", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Recipient != "alice@example.com" {
		t.Errorf("got recipient %q", got.Recipient)
	}
	if got.Subject != "项目进度" {
		t.Errorf("got subject %q", got.Subject)
	}
	if got.Body == "" {
		t.Error("body should not be empty")
	}
	if got.Tone != "formal" {
		t.Errorf("got tone %q want %q", got.Tone, "formal")
	}
}

func TestPlanner_PlanEmail_BadJSONFallsBack(t *testing.T) {
	f := &fakeChatModel{response: "not json"}
	p := NewPlannerAgent(f)
	it := &intent.Intent{
		Action:    intent.ActionDraftEmail,
		Recipient: "bob@example.com",
		Subject:   "会议改期",
		Purpose:   "通知改期",
	}
	got, err := p.PlanEmail(context.Background(), "写邮件", it)
	if err != nil {
		t.Fatalf("should not error, got %v", err)
	}
	if got.Recipient != "bob@example.com" {
		t.Errorf("fallback recipient should be Intent.Recipient, got %q", got.Recipient)
	}
	if got.Subject != "会议改期" {
		t.Errorf("fallback subject should be Intent.Subject, got %q", got.Subject)
	}
	if got.Tone != "formal" {
		t.Errorf("default tone should be formal, got %q", got.Tone)
	}
}

func TestPlanner_PlanEmail_LLMError(t *testing.T) {
	f := &fakeChatModel{err: errors.New("LLM down")}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionDraftEmail, Subject: "x"}
	_, err := p.PlanEmail(context.Background(), "anything", it)
	if err == nil {
		t.Fatal("expected error when LLM call fails")
	}
}

func TestPlanner_PlanEmail_EmptyToneDefaultsToFormal(t *testing.T) {
	f := &fakeChatModel{response: `{"recipient":"a@b.com","subject":"x","body":"body"}`}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionDraftEmail}
	got, err := p.PlanEmail(context.Background(), "anything", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Tone != "formal" {
		t.Errorf("empty tone should default to formal, got %q", got.Tone)
	}
}

func TestPlanner_PlanSettings_HappyPath(t *testing.T) {
	f := &fakeChatModel{
		response: `{"changes":[{"category":"theme","new_value":"deepin-dark"}],"mode":"preview","rationale":"切到深色"}`,
	}
	p := NewPlannerAgent(f)
	it := &intent.Intent{
		Action:           intent.ActionApplySettings,
		SettingsCategory: "theme",
		SettingsValue:    "deepin-dark",
		Mode:             "preview",
	}
	got, err := p.PlanSettings(context.Background(), "切到深色模式", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got.Changes) != 1 {
		t.Fatalf("expected 1 change, got %d", len(got.Changes))
	}
	if got.Changes[0].Category != "theme" {
		t.Errorf("got category %q want %q", got.Changes[0].Category, "theme")
	}
	if got.Changes[0].NewValue != "deepin-dark" {
		t.Errorf("got value %q want %q", got.Changes[0].NewValue, "deepin-dark")
	}
	if got.Mode != "preview" {
		t.Errorf("got mode %q want %q", got.Mode, "preview")
	}
}

func TestPlanner_PlanSettings_BadJSONFallsBackToIntent(t *testing.T) {
	f := &fakeChatModel{response: "garbage"}
	p := NewPlannerAgent(f)
	it := &intent.Intent{
		Action:           intent.ActionApplySettings,
		SettingsCategory: "volume",
		SettingsValue:    "80",
		Mode:             "apply",
	}
	got, err := p.PlanSettings(context.Background(), "音量调到 80", it)
	if err != nil {
		t.Fatalf("should not error, got %v", err)
	}
	if len(got.Changes) != 1 {
		t.Fatalf("expected 1 fallback change, got %d", len(got.Changes))
	}
	if got.Changes[0].Category != "volume" {
		t.Errorf("fallback category should be Intent.SettingsCategory, got %q", got.Changes[0].Category)
	}
	if got.Changes[0].NewValue != "80" {
		t.Errorf("fallback value should be Intent.SettingsValue, got %q", got.Changes[0].NewValue)
	}
	if got.Mode != "apply" {
		t.Errorf("fallback mode should be Intent.Mode, got %q", got.Mode)
	}
}

func TestPlanner_PlanSettings_LLMError(t *testing.T) {
	f := &fakeChatModel{err: errors.New("network error")}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionApplySettings, SettingsCategory: "x", SettingsValue: "y"}
	_, err := p.PlanSettings(context.Background(), "anything", it)
	if err == nil {
		t.Fatal("expected error when LLM call fails")
	}
}

func TestPlanner_PlanSettings_EmptyChangesFallsBack(t *testing.T) {
	// LLM 返回空 changes 列表（合法 JSON 但 changes=[]），应该兜底到 Intent
	f := &fakeChatModel{response: `{"mode":"preview","rationale":"no changes"}`}
	p := NewPlannerAgent(f)
	it := &intent.Intent{
		Action:           intent.ActionApplySettings,
		SettingsCategory: "brightness",
		SettingsValue:    "60",
		Mode:             "preview",
	}
	got, err := p.PlanSettings(context.Background(), "亮度 60", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got.Changes) != 1 {
		t.Fatalf("expected 1 fallback change, got %d", len(got.Changes))
	}
	if got.Changes[0].Category != "brightness" {
		t.Errorf("fallback category should be Intent.SettingsCategory, got %q", got.Changes[0].Category)
	}
}

func TestPlanner_PlanSettings_EmptyIntentModeDefaultsToPreview(t *testing.T) {
	f := &fakeChatModel{response: `{"changes":[{"category":"volume","new_value":"50"}],"rationale":"音量"}`}
	p := NewPlannerAgent(f)
	it := &intent.Intent{Action: intent.ActionApplySettings, SettingsCategory: "volume", SettingsValue: "50", Mode: ""}
	got, err := p.PlanSettings(context.Background(), "音量 50", it)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Mode != "preview" {
		t.Errorf("empty Intent.Mode should default to preview, got %q", got.Mode)
	}
}

// sanity: 确认 fakeChatModel 能被 agents 包内部用（不是测试目的，但防止 mock 设计出问题）
func TestFakeChatModel_SatisfiesChatModelInterface(t *testing.T) {
	var _ ChatModel = (*fakeChatModel)(nil)
	var _ ChatModel = (*fakeChatModel)(nil)
	_ = tools.SettingChange{} // keep import alive
}