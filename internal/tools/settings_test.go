package tools

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestValidateChange_Theme 测试主题校验
func TestValidateChange_Theme(t *testing.T) {
	tests := []struct {
		name    string
		val     string
		wantErr bool
	}{
		{"dark", "deepin-dark", false},
		{"light", "deepin-light", false},
		{"auto", "deepin-auto", false},
		{"invalid", "windows", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := SettingChange{Category: CategoryTheme, NewValue: tt.val}
			err := validateChange(&c)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateChange(%q): err=%v, wantErr=%v", tt.val, err, tt.wantErr)
			}
			if !tt.wantErr && c.Key != "gtk_theme" {
				t.Errorf("Key 应自动填 gtk_theme, got %q", c.Key)
			}
		})
	}
}

// TestValidateChange_Volume 测试音量校验
func TestValidateChange_Volume(t *testing.T) {
	tests := []struct {
		val     string
		wantErr bool
	}{
		{"0", false}, {"50", false}, {"100", false},
		{"-1", true}, {"101", true}, {"abc", true}, {"", true},
	}
	for _, tt := range tests {
		t.Run(tt.val, func(t *testing.T) {
			c := SettingChange{Category: CategoryVolume, NewValue: tt.val}
			err := validateChange(&c)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateChange(%q): err=%v, wantErr=%v", tt.val, err, tt.wantErr)
			}
			if !tt.wantErr && c.Key != "volume_level" {
				t.Errorf("Key 应为 volume_level, got %q", c.Key)
			}
		})
	}
}

// TestValidateChange_Brightness 测试亮度校验
func TestValidateChange_Brightness(t *testing.T) {
	c := SettingChange{Category: CategoryBrightness, NewValue: "75"}
	if err := validateChange(&c); err != nil {
		t.Fatalf("75 应通过: %v", err)
	}
	if c.Key != "brightness_level" {
		t.Errorf("Key 应为 brightness_level, got %q", c.Key)
	}

	// 越界
	bad := SettingChange{Category: CategoryBrightness, NewValue: "150"}
	if err := validateChange(&bad); err == nil {
		t.Error("150 应被拒")
	}
}

// TestValidateChange_Network 测试网络开关校验
func TestValidateChange_Network(t *testing.T) {
	for _, val := range []string{"on", "off"} {
		c := SettingChange{Category: CategoryNetwork, NewValue: val}
		if err := validateChange(&c); err != nil {
			t.Errorf("%q 应通过: %v", val, err)
		}
		if c.Key != "wifi_enabled" {
			t.Errorf("Key 应为 wifi_enabled, got %q", c.Key)
		}
		// on/off 应被归一化成 true/false
		want := "true"
		if val == "off" {
			want = "false"
		}
		if c.NewValue != want {
			t.Errorf("on/off 应归一化成 %s, got %s", want, c.NewValue)
		}
	}

	// 非法值
	bad := SettingChange{Category: CategoryNetwork, NewValue: "maybe"}
	if err := validateChange(&bad); err == nil {
		t.Error("'maybe' 应被拒")
	}
}

// TestValidateChange_Unknown 测试未知分类
func TestValidateChange_Unknown(t *testing.T) {
	c := SettingChange{Category: "wallpaper", NewValue: "blue"}
	if err := validateChange(&c); err == nil {
		t.Error("未知分类应被拒")
	}
}

// TestApplySettings_Preview 测试 preview 模式
func TestApplySettings_Preview(t *testing.T) {
	changes := []SettingChange{
		{Category: CategoryTheme, NewValue: "deepin-dark"},
		{Category: CategoryVolume, NewValue: "80"},
	}
	report := ApplySettings(context.Background(), changes, "preview")

	if !report.VerifPassed {
		t.Errorf("preview 应通过: %s", report.VerifMsg)
	}
	if report.Mode != "preview" {
		t.Errorf("Mode: got %q, want preview", report.Mode)
	}
	if len(report.Changes) != 2 {
		t.Errorf("Changes 数量: got %d, want 2", len(report.Changes))
	}
	for _, c := range report.Changes {
		if c.Status != "planned" {
			t.Errorf("preview 模式 Status 应为 planned, got %s", c.Status)
		}
	}
}

// TestApplySettings_Apply 测试 apply 模式 + 落盘
func TestApplySettings_Apply(t *testing.T) {
	// 切到临时 HOME
	origHome := os.Getenv("HOME")
	t.Cleanup(func() { os.Setenv("HOME", origHome) })
	tmpHome := t.TempDir()
	os.Setenv("HOME", tmpHome)

	changes := []SettingChange{
		{Category: CategoryTheme, NewValue: "deepin-light"},
		{Category: CategoryBrightness, NewValue: "60"},
	}
	report := ApplySettings(context.Background(), changes, "apply")

	if !report.VerifPassed {
		t.Fatalf("apply 应通过: %s", report.VerifMsg)
	}
	if len(report.Changes) != 2 {
		t.Fatalf("Changes 数量: got %d, want 2", len(report.Changes))
	}

	// 验证 settings.json 真的写了
	settingsPath := filepath.Join(tmpHome, ".local", "share", "deepin-agent", "settings.json")
	if _, err := os.Stat(settingsPath); err != nil {
		t.Fatalf("settings.json 未生成: %v", err)
	}

	// 验证内容
	ok, msg := VerifySettings(context.Background(), changes)
	if !ok {
		t.Errorf("VerifySettings 应通过: %s", msg)
	}
}

// TestApplySettings_ValidationFailure 测试校验失败立即返回
func TestApplySettings_ValidationFailure(t *testing.T) {
	changes := []SettingChange{
		{Category: CategoryTheme, NewValue: "deepin-dark"},
		{Category: CategoryVolume, NewValue: "999"}, // 越界
	}
	report := ApplySettings(context.Background(), changes, "preview")

	if report.VerifPassed {
		t.Error("校验失败应让 VerifPassed = false")
	}
	if !strings.Contains(report.VerifMsg, "校验失败") {
		t.Errorf("错误信息应提到'校验失败', got: %s", report.VerifMsg)
	}
}

// TestNormalizeSettingInput 测试归一化
func TestNormalizeSettingInput(t *testing.T) {
	tests := []struct {
		raw  string
		want string
	}{
		{"暗色", "deepin-dark"},
		{"深色", "deepin-dark"},
		{"黑色", "deepin-dark"},
		{"dark", "deepin-dark"},
		{"浅色", "deepin-light"},
		{"白色", "deepin-light"},
		{"自动", "deepin-auto"},
		{"跟随", "deepin-auto"},
		{"auto", "deepin-auto"},
		{"unknown", "unknown"}, // 不识别就原样返回
	}
	for _, tt := range tests {
		got := NormalizeSettingInput(CategoryTheme, tt.raw)
		if got != tt.want {
			t.Errorf("NormalizeSettingInput(%q): got %q, want %q", tt.raw, got, tt.want)
		}
	}
}
