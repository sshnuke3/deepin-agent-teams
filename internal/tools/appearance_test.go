package tools

import (
	"context"
	"errors"
	"strings"
	"testing"
)

// === ChangeTheme 测试 ===

func TestChangeTheme_ValidTheme_MockMode(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "mock")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	res := ChangeTheme(context.Background(), "deepin-dark")
	if !res.Success {
		t.Errorf("expected success in mock mode, got error: %s", res.Message)
	}
	if !strings.Contains(res.Message, "deepin-dark") {
		t.Errorf("message should mention theme, got %q", res.Message)
	}
	if !strings.Contains(res.Message, "演示模式") {
		t.Errorf("mock mode should show (演示模式), got %q", res.Message)
	}
}

func TestChangeTheme_InvalidTheme_Rejected(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "mock")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	for _, bad := range []string{"", "ubuntu-dark", "hack", "DEEPIN-DARK"} {
		res := ChangeTheme(context.Background(), bad)
		if res.Success {
			t.Errorf("theme %q should be rejected", bad)
		}
		if !strings.Contains(res.Message, "无效主题名") {
			t.Errorf("error message should mention invalid, got %q", res.Message)
		}
	}
	// 非法输入不应该调 gdbus
	if len(fake.calls) != 0 {
		t.Errorf("invalid theme should not invoke gdbus, got %d calls", len(fake.calls))
	}
}

func TestChangeTheme_RealMode_DBusErrorPropagates(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{
		err:    errors.New("connection refused"),
		stderr: "Cannot autolaunch D-Bus",
	}
	SetExecutor(fake)
	defer ResetExecutor()

	res := ChangeTheme(context.Background(), "deepin-light")
	if res.Success {
		t.Error("expected failure when dbus errors")
	}
	if !strings.Contains(res.Message, "切换主题失败") {
		t.Errorf("message should describe failure, got %q", res.Message)
	}
	if !strings.Contains(res.Message, "connection refused") {
		t.Errorf("message should include underlying error, got %q", res.Message)
	}
}

func TestChangeTheme_RealMode_NoMockNote(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	res := ChangeTheme(context.Background(), "deepin-auto")
	if !res.Success {
		t.Errorf("expected success, got %s", res.Message)
	}
	if strings.Contains(res.Message, "演示模式") {
		t.Errorf("real mode should NOT show mock note, got %q", res.Message)
	}
}

// === GetCurrentTheme 测试 ===

func TestGetCurrentTheme_MockMode(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "mock")
	fake := &fakeExecutor{}
	SetExecutor(fake)
	defer ResetExecutor()

	theme, err := GetCurrentTheme(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if theme != "mock-value" {
		t.Errorf("mock Get should return mock-value, got %q", theme)
	}
}

func TestGetCurrentTheme_RealMode_ParsesGVariant(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{stdout: "(<'deepin-dark',>)"}
	SetExecutor(fake)
	defer ResetExecutor()

	theme, err := GetCurrentTheme(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if theme != "deepin-dark" {
		t.Errorf("got %q want %q", theme, "deepin-dark")
	}
}

func TestGetCurrentTheme_RealMode_DBusError(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{err: errors.New("not running")}
	SetExecutor(fake)
	defer ResetExecutor()

	_, err := GetCurrentTheme(context.Background())
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "query current theme") {
		t.Errorf("error should describe operation, got %q", err)
	}
}

// === GetSystemInfo 测试 ===

func TestGetSystemInfo_MockMode(t *testing.T) {
	t.Setenv("DEEPIN_DBUS", "mock")
	fake := &fakeExecutor{}
	SetExecutor(fake)
	defer ResetExecutor()

	res := GetSystemInfo(context.Background())
	if !res.Success {
		t.Errorf("expected success, got %s", res.Message)
	}
	// 应该包含主机名、当前主题
	if !strings.Contains(res.Message, "主机名") {
		t.Errorf("message should include hostname, got %q", res.Message)
	}
	if !strings.Contains(res.Message, "当前主题") {
		t.Errorf("message should include current theme, got %q", res.Message)
	}
	// 当前主题是 mock-value（mock 模式 GetCurrentTheme 返回）
	if !strings.Contains(res.Message, "mock-value") {
		t.Errorf("mock mode should show mock theme, got %q", res.Message)
	}
}

func TestGetSystemInfo_RealMode_DBusErrorStillSucceeds(t *testing.T) {
	// 即使 D-Bus 不可用，GetSystemInfo 也不应该整体失败
	// （只是无法显示当前主题）
	t.Setenv("DEEPIN_DBUS", "")
	fake := &fakeExecutor{err: errors.New("not available")}
	SetExecutor(fake)
	defer ResetExecutor()

	res := GetSystemInfo(context.Background())
	if !res.Success {
		t.Errorf("GetSystemInfo should be resilient to dbus failures, got %s", res.Message)
	}
	if !strings.Contains(res.Message, "当前主题: 未知") {
		t.Errorf("theme should be '未知' when dbus fails, got %q", res.Message)
	}
}

// === readOSRelease 测试 ===

func TestReadOSRelease_ReturnsPRETTYNAME(t *testing.T) {
	// /etc/os-release 真实存在于 Linux 上（这里是 Ubuntu 24.04）
	got := readOSRelease()
	if got == "" {
		t.Skip("/etc/os-release not available")
	}
	if got == "unknown" {
		t.Skip("PRETTY_NAME not in /etc/os-release")
	}
	// 应该是 "Ubuntu 24.04 ..." 这种形式
	if !strings.Contains(got, "Ubuntu") && !strings.Contains(got, "Deepin") {
		t.Logf("unexpected OS: %q (test still passes — just logs)", got)
	}
}

// === isValidTheme 测试 ===

func TestIsValidTheme(t *testing.T) {
	valid := []string{"deepin-dark", "deepin-light", "deepin-auto"}
	invalid := []string{"", "ubuntu-dark", "Dark", "deepin_DARK", "deepinblack"}
	for _, v := range valid {
		if !isValidTheme(v) {
			t.Errorf("%q should be valid", v)
		}
	}
	for _, v := range invalid {
		if isValidTheme(v) {
			t.Errorf("%q should be invalid", v)
		}
	}
}