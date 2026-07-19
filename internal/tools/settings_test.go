package tools

import (
	"context"
	"errors"
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

	// 这个测试原本是 mock 路径验证（v4 M2 时代代码里就是 mock）
	// v4 M3 改了 applyChange 真接 D-Bus；这里显式设 mock 以保留原测试意图
	t.Setenv("DEEPIN_DBUS", "mock")

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

// === applyChange 真 D-Bus 路径测试 (v4 M3) ===

func TestApplyChange_Theme_RealDBus_CallsSetGtkTheme(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	c := &SettingChange{Category: CategoryTheme, Key: "gtk_theme", NewValue: "deepin-dark"}
	if err := applyChange(context.Background(), c); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(fake.calls) != 1 {
		t.Fatalf("expected 1 gdbus call, got %d", len(fake.calls))
	}
	call := fake.calls[0]
	// 验证调到了 SetGtkTheme
	hasSetGtkTheme := false
	for _, a := range call.args {
		if a == "com.deepin.daemon.Appearance.SetGtkTheme" {
			hasSetGtkTheme = true
		}
	}
	if !hasSetGtkTheme {
		t.Errorf("should call Appearance.SetGtkTheme, got args: %v", call.args)
	}
	// 验证参数是 deepin-dark
	hasValue := false
	for _, a := range call.args {
		if a == "deepin-dark" {
			hasValue = true
		}
	}
	if !hasValue {
		t.Errorf("should pass 'deepin-dark' as arg, got: %v", call.args)
	}
}

func TestApplyChange_Volume_RealDBus_ConvertsToRatio(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	c := &SettingChange{Category: CategoryVolume, Key: "volume_level", NewValue: "50"}
	if err := applyChange(context.Background(), c); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(fake.calls) != 1 {
		t.Fatalf("expected 1 gdbus call, got %d", len(fake.calls))
	}
	// 50% → 0.500000
	hasRatio := false
	for _, a := range fake.calls[0].args {
		if a == "0.500000" {
			hasRatio = true
		}
	}
	if !hasRatio {
		t.Errorf("volume 50 should convert to 0.500000, got args: %v", fake.calls[0].args)
	}
}

func TestApplyChange_Volume_EdgeValues(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	// 0 → 0.000000
	c := &SettingChange{Category: CategoryVolume, Key: "volume_level", NewValue: "0"}
	_ = applyChange(context.Background(), c)
	hasZero := false
	for _, a := range fake.calls[0].args {
		if a == "0.000000" {
			hasZero = true
		}
	}
	if !hasZero {
		t.Errorf("volume 0 should convert to 0.000000, got: %v", fake.calls[0].args)
	}

	// 100 → 1.000000
	fake.calls = nil
	c2 := &SettingChange{Category: CategoryVolume, Key: "volume_level", NewValue: "100"}
	_ = applyChange(context.Background(), c2)
	hasOne := false
	for _, a := range fake.calls[0].args {
		if a == "1.000000" {
			hasOne = true
		}
	}
	if !hasOne {
		t.Errorf("volume 100 should convert to 1.000000, got: %v", fake.calls[0].args)
	}
}

func TestApplyChange_Brightness_RealDBus_ConvertsToRatio(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	c := &SettingChange{Category: CategoryBrightness, Key: "brightness_level", NewValue: "80"}
	if err := applyChange(context.Background(), c); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	hasMethod := false
	hasRatio := false
	for _, a := range fake.calls[0].args {
		if a == "com.deepin.daemon.Display.Brightness.SetBrightness" {
			hasMethod = true
		}
		if a == "0.800000" {
			hasRatio = true
		}
	}
	if !hasMethod {
		t.Errorf("should call Display.Brightness.SetBrightness, got: %v", fake.calls[0].args)
	}
	if !hasRatio {
		t.Errorf("brightness 80 should convert to 0.800000, got: %v", fake.calls[0].args)
	}
}

func TestApplyChange_Network_RealDBus_ChoosesCorrectMethod(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	// on → EnableWifi
	c := &SettingChange{Category: CategoryNetwork, Key: "wifi_enabled", NewValue: "true"}
	_ = applyChange(context.Background(), c)
	hasEnable := false
	for _, a := range fake.calls[0].args {
		if a == "com.deepin.daemon.Network.EnableWifi" {
			hasEnable = true
		}
	}
	if !hasEnable {
		t.Errorf("network on should call EnableWifi, got: %v", fake.calls[0].args)
	}

	// off → DisableWifi
	fake.calls = nil
	c2 := &SettingChange{Category: CategoryNetwork, Key: "wifi_enabled", NewValue: "false"}
	_ = applyChange(context.Background(), c2)
	hasDisable := false
	for _, a := range fake.calls[0].args {
		if a == "com.deepin.daemon.Network.DisableWifi" {
			hasDisable = true
		}
	}
	if !hasDisable {
		t.Errorf("network off should call DisableWifi, got: %v", fake.calls[0].args)
	}
}

func TestApplyChange_UnknownCategory_ReturnsError(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	c := &SettingChange{Category: "invalid", NewValue: "x"}
	err := applyChange(context.Background(), c)
	if err == nil {
		t.Error("unknown category should return error")
	}
	if len(fake.calls) != 0 {
		t.Errorf("unknown category should not invoke gdbus, got %d calls", len(fake.calls))
	}
}

func TestApplyChange_DBusError_Propagates(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{err: errors.New("connection refused")}
	SetExecutor(fake)
	defer ResetExecutor()

	c := &SettingChange{Category: CategoryTheme, Key: "gtk_theme", NewValue: "deepin-dark"}
	err := applyChange(context.Background(), c)
	if err == nil {
		t.Fatal("expected error when gdbus fails")
	}
}

func TestApplyChange_MockMode_SkipsDBus(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "mock")
	fake := &fakeExecutor{stdout: "(ignored)"}
	SetExecutor(fake)
	defer ResetExecutor()

	c := &SettingChange{Category: CategoryTheme, Key: "gtk_theme", NewValue: "deepin-light"}
	if err := applyChange(context.Background(), c); err != nil {
		t.Errorf("mock mode should not error, got %v", err)
	}
	if len(fake.calls) != 0 {
		t.Errorf("mock mode should not invoke gdbus, got %d calls", len(fake.calls))
	}
}

func TestApplySettings_Apply_RealDBus_ShowsModeNote(t *testing.T) {
	// 验证 apply 模式的输出信息里包含 "(D-Bus 真调用)" 或 "(演示模式)" 之一
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	// 临时重设 HOME 防止写盘污染真机
	tmpHome := t.TempDir()
	t.Setenv("HOME", tmpHome)

	changes := []SettingChange{
		{Category: CategoryTheme, Key: "gtk_theme", NewValue: "deepin-dark"},
	}
	report := ApplySettings(context.Background(), changes, "apply")
	if !report.VerifPassed {
		t.Errorf("expected success, got %+v", report)
	}
	foundNote := false
	for _, c := range report.Changes {
		if strings.Contains(c.Message, "D-Bus 真调用") || strings.Contains(c.Message, "演示模式") {
			foundNote = true
		}
	}
	if !foundNote {
		t.Errorf("apply result should mention mode (D-Bus/演示), got: %+v", report.Changes)
	}
}

func TestApplySettings_Apply_RealDBus_HandlesGdbusFailure(t *testing.T) {
	// gdbus 失败时，整条 chain 应该 fail（不让 settings.json 写入无效状态）
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{err: errors.New("dde-session not running")}
	SetExecutor(fake)
	defer ResetExecutor()

	tmpHome := t.TempDir()
	t.Setenv("HOME", tmpHome)

	changes := []SettingChange{
		{Category: CategoryTheme, Key: "gtk_theme", NewValue: "deepin-dark"},
	}
	report := ApplySettings(context.Background(), changes, "apply")
	if report.VerifPassed {
		t.Error("expected failure when gdbus errors")
	}
	// 失败时不应该写盘
	settingsPath := filepath.Join(tmpHome, ".local", "share", "deepin-agent", "settings.json")
	if _, err := os.Stat(settingsPath); err == nil {
		t.Error("settings.json should NOT be written when apply fails")
	}
}
