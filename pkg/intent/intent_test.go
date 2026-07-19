package intent

import (
	"testing"
)

func TestStripMarkdown(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"plain json", `{"action":"test"}`, `{"action":"test"}`},
		{"json fenced", "```json\n{\"action\":\"test\"}\n```", "\n{\"action\":\"test\"}\n"},
		{"generic fenced", "```\n{\"action\":\"test\"}\n```", "\n{\"action\":\"test\"}\n"},
		{"json no newline", "```json{\"action\":\"test\"}```", "{\"action\":\"test\"}"},
		{"no closing fence", "```json\n{\"action\":\"test\"}", "\n{\"action\":\"test\"}"},
		{"empty", "", ""},
		{"short string", "ab", "ab"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := stripMarkdown(tt.in)
			if got != tt.want {
				t.Errorf("stripMarkdown(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

func TestIndexOf(t *testing.T) {
	tests := []struct {
		s, sub string
		want   int
	}{
		{"hello", "ll", 2},
		{"hello", "xyz", -1},
		{"", "a", -1},
		{"abc", "", 0},
	}
	for _, tt := range tests {
		got := indexOf(tt.s, tt.sub)
		if got != tt.want {
			t.Errorf("indexOf(%q, %q) = %d, want %d", tt.s, tt.sub, got, tt.want)
		}
	}
}

func TestParse_InvalidJSON(t *testing.T) {
	_, err := Parse("not json at all")
	if err == nil {
		t.Error("invalid JSON should return error")
	}
}

func TestParse_UnknownAction(t *testing.T) {
	intent, err := Parse(`{"action":"bogus_action"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Action != ActionUnknown {
		t.Errorf("unknown action should map to ActionUnknown, got %q", intent.Action)
	}
}

func TestParse_ValidActions(t *testing.T) {
	tests := []struct {
		action string
		json   string
	}{
		{ActionChangeTheme, `{"action":"change_theme"}`},
		{ActionGetSystemInfo, `{"action":"get_system_info"}`},
		{ActionOrganizeFiles, `{"action":"organize_files"}`},
		{ActionScheduleReminder, `{"action":"schedule_reminder","title":"开会"}`},
		{ActionDraftEmail, `{"action":"draft_email","subject":"周报"}`},
		{ActionApplySettings, `{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark"}`},
		{ActionUnknown, `{"action":"unknown"}`},
	}
	for _, tt := range tests {
		intent, err := Parse(tt.json)
		if err != nil {
			t.Fatalf("action %q: unexpected error: %v", tt.action, err)
		}
		if intent.Action != tt.action {
			t.Errorf("action %q: got %q", tt.action, intent.Action)
		}
	}
}

func TestParse_OrganizeFiles_Defaults(t *testing.T) {
	intent, err := Parse(`{"action":"organize_files"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Directory != "~/Downloads" {
		t.Errorf("default directory should be ~/Downloads, got %q", intent.Directory)
	}
	if intent.Mode != "preview" {
		t.Errorf("default mode should be preview, got %q", intent.Mode)
	}
}

func TestParse_OrganizeFiles_CustomValues(t *testing.T) {
	intent, err := Parse(`{"action":"organize_files","directory":"/tmp/docs","mode":"apply"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Directory != "/tmp/docs" {
		t.Errorf("directory should be /tmp/docs, got %q", intent.Directory)
	}
	if intent.Mode != "apply" {
		t.Errorf("mode should be apply, got %q", intent.Mode)
	}
}

func TestParse_ScheduleReminder_Defaults(t *testing.T) {
	intent, err := Parse(`{"action":"schedule_reminder","title":"开会"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Priority != "normal" {
		t.Errorf("default priority should be normal, got %q", intent.Priority)
	}
	if intent.Mode != "preview" {
		t.Errorf("default mode should be preview, got %q", intent.Mode)
	}
}

func TestParse_ScheduleReminder_NoTitle_Unknown(t *testing.T) {
	intent, err := Parse(`{"action":"schedule_reminder"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Action != ActionUnknown {
		t.Errorf("reminder without title should be ActionUnknown, got %q", intent.Action)
	}
}

func TestParse_DraftEmail_Defaults(t *testing.T) {
	intent, err := Parse(`{"action":"draft_email","subject":"周报","purpose":"汇报本周进展"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Mode != "preview" {
		t.Errorf("default mode should be preview, got %q", intent.Mode)
	}
}

func TestParse_DraftEmail_NoSubjectNoPurpose_Unknown(t *testing.T) {
	intent, err := Parse(`{"action":"draft_email"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Action != ActionUnknown {
		t.Errorf("email without subject and purpose should be ActionUnknown, got %q", intent.Action)
	}
}

func TestParse_DraftEmail_HasPurposeOnly(t *testing.T) {
	intent, err := Parse(`{"action":"draft_email","purpose":"请假"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Action != ActionDraftEmail {
		t.Errorf("email with purpose should stay ActionDraftEmail, got %q", intent.Action)
	}
}

func TestParse_ApplySettings_ValidCategory(t *testing.T) {
	intent, err := Parse(`{"action":"apply_settings","settings_category":"volume","settings_value":"80"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Mode != "preview" {
		t.Errorf("default mode should be preview, got %q", intent.Mode)
	}
	if intent.SettingsCategory != "volume" {
		t.Errorf("category should be volume, got %q", intent.SettingsCategory)
	}
}

func TestParse_ApplySettings_InvalidCategory_Unknown(t *testing.T) {
	intent, err := Parse(`{"action":"apply_settings","settings_category":"font_size","settings_value":"14"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Action != ActionUnknown {
		t.Errorf("invalid settings category should be ActionUnknown, got %q", intent.Action)
	}
}

func TestParse_ApplySettings_MissingValue_Unknown(t *testing.T) {
	intent, err := Parse(`{"action":"apply_settings","settings_category":"theme"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Action != ActionUnknown {
		t.Errorf("missing settings value should be ActionUnknown, got %q", intent.Action)
	}
}

func TestParse_MarkdownWrappedJSON(t *testing.T) {
	input := "```json\n{\"action\":\"get_system_info\"}\n```"
	intent, err := Parse(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if intent.Action != ActionGetSystemInfo {
		t.Errorf("should parse markdown-wrapped JSON, got action %q", intent.Action)
	}
}

func TestParse_AllSettingsCategories(t *testing.T) {
	categories := []string{"theme", "volume", "brightness", "network"}
	for _, cat := range categories {
		intent, err := Parse(`{"action":"apply_settings","settings_category":"` + cat + `","settings_value":"test"}`)
		if err != nil {
			t.Fatalf("category %q: unexpected error: %v", cat, err)
		}
		if intent.Action != ActionApplySettings {
			t.Errorf("category %q: should stay ActionApplySettings, got %q", cat, intent.Action)
		}
	}
}

// === ParseMulti 测试 (v4 M3 多意图支持) ===

func TestParseMulti_SingleObject(t *testing.T) {
	got, err := ParseMulti(`{"action":"get_system_info"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("expected 1 intent, got %d", len(got))
	}
	if got[0].Action != ActionGetSystemInfo {
		t.Errorf("got %q want %q", got[0].Action, ActionGetSystemInfo)
	}
}

func TestParseMulti_ArrayOfTwo(t *testing.T) {
	input := `[
		{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark"},
		{"action":"apply_settings","settings_category":"volume","settings_value":"30"}
	]`
	got, err := ParseMulti(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 intents, got %d", len(got))
	}
	if got[0].SettingsCategory != "theme" {
		t.Errorf("intent[0] category got %q want %q", got[0].SettingsCategory, "theme")
	}
	if got[1].SettingsValue != "30" {
		t.Errorf("intent[1] value got %q want %q", got[1].SettingsValue, "30")
	}
}

func TestParseMulti_ArrayOfThreeHeterogeneous(t *testing.T) {
	input := `[
		{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark"},
		{"action":"schedule_reminder","title":"开会","due_at":"2026-07-20T09:00:00+08:00","priority":"normal","mode":"preview"},
		{"action":"draft_email","purpose":"请假","mode":"preview"}
	]`
	got, err := ParseMulti(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 3 {
		t.Fatalf("expected 3 intents, got %d", len(got))
	}
	if got[0].Action != ActionApplySettings || got[1].Action != ActionScheduleReminder || got[2].Action != ActionDraftEmail {
		t.Errorf("order mismatch: got [%q, %q, %q]", got[0].Action, got[1].Action, got[2].Action)
	}
}

func TestParseMulti_WrappedIntentsField(t *testing.T) {
	input := `{"intents":[{"action":"get_system_info"},{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark"}]}`
	got, err := ParseMulti(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 intents, got %d", len(got))
	}
	if got[0].Action != ActionGetSystemInfo {
		t.Errorf("intent[0] action got %q", got[0].Action)
	}
	if got[1].Action != ActionApplySettings {
		t.Errorf("intent[1] action got %q", got[1].Action)
	}
}

func TestParseMulti_EmptyArray(t *testing.T) {
	_, err := ParseMulti(`[]`)
	if err == nil {
		t.Error("empty array should return error")
	}
}

func TestParseMulti_EmptyInput(t *testing.T) {
	_, err := ParseMulti(``)
	if err == nil {
		t.Error("empty input should return error")
	}
}

func TestParseMulti_InvalidJSON(t *testing.T) {
	_, err := ParseMulti(`not json at all`)
	if err == nil {
		t.Error("invalid JSON should return error")
	}
}

func TestParseMulti_ArrayItemInvalid(t *testing.T) {
	// 数组里有一项是无效 JSON
	input := `[{"action":"get_system_info"}, "not an object"]`
	_, err := ParseMulti(input)
	if err == nil {
		t.Error("array with invalid item should return error")
	}
}

func TestParseMulti_MarkdownFenced(t *testing.T) {
	input := "```json\n[{\"action\":\"get_system_info\"}]\n```"
	got, err := ParseMulti(input)
	if err != nil {
		t.Fatalf("fenced array should parse, got %v", err)
	}
	if len(got) != 1 || got[0].Action != ActionGetSystemInfo {
		t.Errorf("fenced array parse failed: %v", got)
	}
}

func TestParseMulti_AppliesSingleIntentDefaults(t *testing.T) {
	// ParseMulti 内部复用 Parse，所以安全默认值（organize 默认目录、reminder 默认 priority 等）应该生效
	input := `[{"action":"schedule_reminder"}]` // 没 title，应被降级为 unknown
	got, err := ParseMulti(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("expected 1 intent, got %d", len(got))
	}
	if got[0].Action != ActionUnknown {
		t.Errorf("reminder without title should map to unknown, got %q", got[0].Action)
	}
}

func TestParseMulti_AppliesMultiSettingsDefaults(t *testing.T) {
	// 第二项 settings value 为空，应该被降级为 unknown；但第一项保留
	input := `[
		{"action":"apply_settings","settings_category":"theme","settings_value":"deepin-dark"},
		{"action":"apply_settings","settings_category":"theme"}
	]`
	got, err := ParseMulti(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 intents, got %d", len(got))
	}
	if got[0].Action != ActionApplySettings {
		t.Errorf("intent[0] should stay apply_settings, got %q", got[0].Action)
	}
	if got[1].Action != ActionUnknown {
		t.Errorf("intent[1] without value should map to unknown, got %q", got[1].Action)
	}
}
