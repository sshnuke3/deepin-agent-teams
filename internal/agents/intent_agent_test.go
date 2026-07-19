package agents

import (
	"context"
	"errors"
	"testing"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// fakeChatModel 是一个可配置的 ChatModel mock，用来模拟 LLM 返回。
type fakeChatModel struct {
	// 预设的 LLM 返回内容（直接走 success 路径）
	response string
	// 预设的错误（设置后会返回 error）
	err error
	// 捕获调用参数，方便断言
	lastMessages []*schema.Message
}

func (f *fakeChatModel) Generate(_ context.Context, in []*schema.Message, _ ...model.Option) (*schema.Message, error) {
	f.lastMessages = in
	if f.err != nil {
		return nil, f.err
	}
	return &schema.Message{Role: schema.Assistant, Content: f.response}, nil
}

func TestIntentAgent_Recognize_ChangeTheme(t *testing.T) {
	f := &fakeChatModel{
		response: `{"action":"change_theme","theme":"deepin-dark"}`,
	}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "帮我切到深色模式")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Action != intent.ActionChangeTheme {
		t.Errorf("got action %q want %q", got.Action, intent.ActionChangeTheme)
	}
	if got.Theme != intent.ThemeDark {
		t.Errorf("got theme %q want %q", got.Theme, intent.ThemeDark)
	}
}

func TestIntentAgent_Recognize_GetSystemInfo(t *testing.T) {
	f := &fakeChatModel{response: `{"action":"get_system_info"}`}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "看下系统信息")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Action != intent.ActionGetSystemInfo {
		t.Errorf("got action %q want %q", got.Action, intent.ActionGetSystemInfo)
	}
}

func TestIntentAgent_Recognize_OrganizeFiles(t *testing.T) {
	f := &fakeChatModel{
		response: `{"action":"organize_files","directory":"~/Downloads","mode":"preview"}`,
	}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "整理一下 Downloads")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Action != intent.ActionOrganizeFiles {
		t.Errorf("got action %q want %q", got.Action, intent.ActionOrganizeFiles)
	}
	if got.Mode != "preview" {
		t.Errorf("got mode %q want %q", got.Mode, "preview")
	}
}

func TestIntentAgent_Recognize_ScheduleReminder(t *testing.T) {
	f := &fakeChatModel{
		response: `{"action":"schedule_reminder","title":"开会","due_at":"2026-07-20T15:00:00+08:00","priority":"normal","mode":"preview"}`,
	}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "提醒我明天下午 3 点开会")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Action != intent.ActionScheduleReminder {
		t.Errorf("got action %q want %q", got.Action, intent.ActionScheduleReminder)
	}
	if got.Title != "开会" {
		t.Errorf("got title %q want %q", got.Title, "开会")
	}
}

func TestIntentAgent_Recognize_DraftEmail(t *testing.T) {
	f := &fakeChatModel{
		response: `{"action":"draft_email","recipient":"alice@example.com","subject":"项目进度","purpose":"同步本周项目进度","mode":"preview"}`,
	}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "帮 Alice 起草一封项目进度邮件")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Action != intent.ActionDraftEmail {
		t.Errorf("got action %q want %q", got.Action, intent.ActionDraftEmail)
	}
	if got.Recipient != "alice@example.com" {
		t.Errorf("got recipient %q want %q", got.Recipient, "alice@example.com")
	}
}

func TestIntentAgent_Recognize_ApplySettings(t *testing.T) {
	f := &fakeChatModel{
		response: `{"action":"apply_settings","settings_category":"volume","settings_value":"80","mode":"preview"}`,
	}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "音量调到 80")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Action != intent.ActionApplySettings {
		t.Errorf("got action %q want %q", got.Action, intent.ActionApplySettings)
	}
	if got.SettingsCategory != "volume" {
		t.Errorf("got category %q want %q", got.SettingsCategory, "volume")
	}
	if got.SettingsValue != "80" {
		t.Errorf("got value %q want %q", got.SettingsValue, "80")
	}
}

func TestIntentAgent_Recognize_Unknown(t *testing.T) {
	f := &fakeChatModel{response: `{"action":"unknown"}`}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "你好")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Action != intent.ActionUnknown {
		t.Errorf("got action %q want %q", got.Action, intent.ActionUnknown)
	}
}

func TestIntentAgent_Recognize_LLMError(t *testing.T) {
	f := &fakeChatModel{err: errors.New("network down")}
	a := NewIntentAgent(f)
	_, err := a.Recognize(context.Background(), "anything")
	if err == nil {
		t.Fatal("expected error when LLM call fails")
	}
}

func TestIntentAgent_Recognize_BadJSONFromLLM(t *testing.T) {
	f := &fakeChatModel{response: "not json at all"}
	a := NewIntentAgent(f)
	_, err := a.Recognize(context.Background(), "anything")
	if err == nil {
		t.Fatal("expected error when LLM returns invalid JSON")
	}
}

func TestIntentAgent_Recognize_LLMReturnsMarkdownFence(t *testing.T) {
	// LLM 不听话，外面包了 ```json ... ```，应该被 Parse 容错处理
	f := &fakeChatModel{
		response: "```json\n{\"action\":\"get_system_info\"}\n```",
	}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "看下系统信息")
	if err != nil {
		t.Fatalf("fenced JSON should parse, got %v", err)
	}
	if got.Action != intent.ActionGetSystemInfo {
		t.Errorf("got action %q want %q", got.Action, intent.ActionGetSystemInfo)
	}
}

func TestIntentAgent_Recognize_SendsSystemPrompt(t *testing.T) {
	// 验证 Recognize 一定把 systemPrompt 放在第一条，user input 放在第二条
	f := &fakeChatModel{response: `{"action":"unknown"}`}
	a := NewIntentAgent(f)
	_, _ = a.Recognize(context.Background(), "测试输入")

	if len(f.lastMessages) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(f.lastMessages))
	}
	if f.lastMessages[0].Role != schema.System {
		t.Errorf("first message role should be system, got %q", f.lastMessages[0].Role)
	}
	if f.lastMessages[0].Content != systemPrompt {
		t.Errorf("first message content should be systemPrompt, got %q", f.lastMessages[0].Content)
	}
	if f.lastMessages[1].Role != schema.User {
		t.Errorf("second message role should be user, got %q", f.lastMessages[1].Role)
	}
	if f.lastMessages[1].Content != "测试输入" {
		t.Errorf("second message content should be user input, got %q", f.lastMessages[1].Content)
	}
}

func TestIntentAgent_Recognize_ReminderMissingTitleMapsToUnknown(t *testing.T) {
	// LLM 返回没 title 的 reminder，intent.Parse 应该把它降级为 unknown
	f := &fakeChatModel{
		response: `{"action":"schedule_reminder","priority":"normal","mode":"preview"}`,
	}
	a := NewIntentAgent(f)
	got, err := a.Recognize(context.Background(), "随便提醒一下")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Action != intent.ActionUnknown {
		t.Errorf("reminder without title should map to unknown, got %q", got.Action)
	}
}

// === RecognizeMulti 测试 (v4 M3 多意图) ===

func TestIntentAgent_RecognizeMulti_SingleIntentFromLLM(t *testing.T) {
	// LLM 返回单 intent（单需求场景），ParseMulti 包装为 [it]
	f := &fakeChatModel{response: `{"action":"get_system_info"}`}
	a := NewIntentAgent(f)
	got, err := a.RecognizeMulti(context.Background(), "看下系统信息")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("expected 1 intent, got %d", len(got))
	}
	if got[0].Action != intent.ActionGetSystemInfo {
		t.Errorf("got action %q want %q", got[0].Action, intent.ActionGetSystemInfo)
	}
}

func TestIntentAgent_RecognizeMulti_ArrayOfTwo(t *testing.T) {
	f := &fakeChatModel{
		response: `[{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark","mode":"preview"},{"action":"apply_settings","settings_category":"volume","settings_value":"30","mode":"preview"}]`,
	}
	a := NewIntentAgent(f)
	got, err := a.RecognizeMulti(context.Background(), "切深色 + 音量调到 30")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 intents, got %d", len(got))
	}
	if got[0].SettingsCategory != "theme" {
		t.Errorf("intent[0] category got %q", got[0].SettingsCategory)
	}
	if got[1].SettingsValue != "30" {
		t.Errorf("intent[1] value got %q", got[1].SettingsValue)
	}
}

func TestIntentAgent_RecognizeMulti_ArrayOfThreeHeterogeneous(t *testing.T) {
	f := &fakeChatModel{
		response: `[{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark","mode":"preview"},{"action":"schedule_reminder","title":"开会","due_at":"2026-07-20T09:00:00+08:00","priority":"normal","mode":"preview"},{"action":"draft_email","purpose":"请假","mode":"preview"}]`,
	}
	a := NewIntentAgent(f)
	got, err := a.RecognizeMulti(context.Background(), "切深色 + 提醒开会 + 请假邮件")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 3 {
		t.Fatalf("expected 3 intents, got %d", len(got))
	}
	if got[0].Action != intent.ActionApplySettings {
		t.Errorf("intent[0] got %q", got[0].Action)
	}
	if got[1].Action != intent.ActionScheduleReminder {
		t.Errorf("intent[1] got %q", got[1].Action)
	}
	if got[2].Action != intent.ActionDraftEmail {
		t.Errorf("intent[2] got %q", got[2].Action)
	}
}

func TestIntentAgent_RecognizeMulti_LLMError(t *testing.T) {
	f := &fakeChatModel{err: errors.New("network down")}
	a := NewIntentAgent(f)
	_, err := a.RecognizeMulti(context.Background(), "anything")
	if err == nil {
		t.Fatal("expected error when LLM call fails")
	}
}

func TestIntentAgent_RecognizeMulti_BadJSON(t *testing.T) {
	f := &fakeChatModel{response: "not json"}
	a := NewIntentAgent(f)
	_, err := a.RecognizeMulti(context.Background(), "anything")
	if err == nil {
		t.Fatal("expected error when LLM returns invalid JSON")
	}
}

func TestIntentAgent_RecognizeMulti_UsesMultiPrompt(t *testing.T) {
	// 验证 RecognizeMulti 用了多意图 system prompt（跟单意图的不同）
	f := &fakeChatModel{response: `[{"action":"get_system_info"}]`}
	a := NewIntentAgent(f)
	_, _ = a.RecognizeMulti(context.Background(), "anything")

	if len(f.lastMessages) < 2 {
		t.Fatalf("expected at least 2 messages, got %d", len(f.lastMessages))
	}
	if f.lastMessages[0].Content == systemPrompt {
		t.Error("RecognizeMulti should NOT use the single-intent systemPrompt")
	}
	if f.lastMessages[0].Content != multiIntentSystemPrompt {
		t.Error("RecognizeMulti should use multiIntentSystemPrompt")
	}
}

func TestIntentAgent_RecognizeMulti_EmptyArray(t *testing.T) {
	f := &fakeChatModel{response: `[]`}
	a := NewIntentAgent(f)
	_, err := a.RecognizeMulti(context.Background(), "anything")
	if err == nil {
		t.Error("empty array should return error")
	}
}