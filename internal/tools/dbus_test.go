package tools

import (
	"context"
	"errors"
	"strings"
	"testing"
)

// fakeExecutor 测试用 mock —— 预设 stdout / stderr / err，并捕获调用参数
type fakeExecutor struct {
	stdout string
	stderr string
	err    error
	// 捕获
	calls []fakeCall
}

type fakeCall struct {
	name string
	args []string
}

func (f *fakeExecutor) Run(_ context.Context, name string, args ...string) (string, string, error) {
	f.calls = append(f.calls, fakeCall{name: name, args: args})
	return f.stdout, f.stderr, f.err
}

// 用 env 子测试隔离 DEEPIN_DBUS
func setDBusEnv(t *testing.T, value string) {
	t.Helper()
	if value == "" {
		t.Setenv("DEEPIN_DBUS", "")
	} else {
		t.Setenv("DEEPIN_DBUS", value)
	}
}

// === mockDBusResponse 测试 ===

func TestMockDBusResponse_SetReturnsEmptyTuple(t *testing.T) {
	got := mockDBusResponse("com.deepin.daemon.Appearance", "com.deepin.daemon.Appearance.SetCurrentTheme", []string{"deepin-dark"})
	if got != "()" {
		t.Errorf("Set* should return (), got %q", got)
	}
}

func TestMockDBusResponse_GetReturnsMockValue(t *testing.T) {
	got := mockDBusResponse("com.deepin.daemon.Appearance", "com.deepin.daemon.Appearance.GetCurrentTheme", nil)
	if got != "(<'mock-value',>)" {
		t.Errorf("Get* should return (<'mock-value',>), got %q", got)
	}
}

func TestMockDBusResponse_UnknownMethodReturnsEmptyTuple(t *testing.T) {
	got := mockDBusResponse("com.deepin.daemon.X", "com.deepin.daemon.X.Whatever", nil)
	if got != "()" {
		t.Errorf("unknown method should return (), got %q", got)
	}
}

// === dbusCall (real) 测试 ===

func TestDBusCall_RealMode_InvokesGdbus(t *testing.T) {
	setDBusEnv(t, "") // 默认（real 模式）
	fake := &fakeExecutor{stdout: "(<'deepin-dark',>)", stderr: ""}
	SetExecutor(fake)
	defer ResetExecutor()

	out, err := dbusCall(context.Background(),
		"com.deepin.daemon.Appearance",
		"/com/deepin/daemon/Appearance",
		"com.deepin.daemon.Appearance.SetCurrentTheme",
		"deepin-dark",
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out != "(<'deepin-dark',>)" {
		t.Errorf("got stdout %q", out)
	}
	if len(fake.calls) != 1 {
		t.Fatalf("expected 1 call, got %d", len(fake.calls))
	}
	call := fake.calls[0]
	if call.name != "gdbus" {
		t.Errorf("expected gdbus, got %q", call.name)
	}
	// 验证关键参数存在
	expectedArgs := []string{
		"call", "--session",
		"-d", "com.deepin.daemon.Appearance",
		"-o", "/com/deepin/daemon/Appearance",
		"-m", "com.deepin.daemon.Appearance.SetCurrentTheme",
		"deepin-dark",
	}
	if !equalSlices(call.args, expectedArgs) {
		t.Errorf("gdbus args mismatch:\n  got:  %v\n  want: %v", call.args, expectedArgs)
	}
}

func TestDBusCall_RealMode_BubblesUpExecutorError(t *testing.T) {
	setDBusEnv(t, "")
	fake := &fakeExecutor{err: errors.New("gdbus not found"), stderr: "command not found"}
	SetExecutor(fake)
	defer ResetExecutor()

	_, err := dbusCall(context.Background(), "com.deepin.daemon.X", "/x", "com.deepin.daemon.X.Y")
	if err == nil {
		t.Fatal("expected error when executor fails")
	}
	if !strings.Contains(err.Error(), "gdbus not found") {
		t.Errorf("error should wrap underlying err, got %q", err)
	}
	if !strings.Contains(err.Error(), "stderr") {
		t.Errorf("error should mention stderr, got %q", err)
	}
}

func TestDBusCall_MockMode_DoesNotInvokeGdbus(t *testing.T) {
	setDBusEnv(t, "mock")
	fake := &fakeExecutor{stdout: "should-not-be-used"}
	SetExecutor(fake)
	defer ResetExecutor()

	out, err := dbusCall(context.Background(), "com.deepin.daemon.Appearance", "/x", "com.deepin.daemon.Appearance.GetCurrentTheme")
	if err != nil {
		t.Fatalf("mock mode should not error, got %v", err)
	}
	if out != "(<'mock-value',>)" {
		t.Errorf("mock Get should return (<'mock-value',>), got %q", out)
	}
	if len(fake.calls) != 0 {
		t.Errorf("mock mode should NOT invoke gdbus, got %d calls", len(fake.calls))
	}
}

func TestDBusCallSystem_UsesSystemBus(t *testing.T) {
	setDBusEnv(t, "")
	fake := &fakeExecutor{stdout: "()"}
	SetExecutor(fake)
	defer ResetExecutor()

	_, err := dbusCallSystem(context.Background(), "com.deepin.daemon.Network", "/com/deepin/daemon/Network", "com.deepin.daemon.Network.Enable", "false")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(fake.calls) != 1 {
		t.Fatalf("expected 1 call, got %d", len(fake.calls))
	}
	hasSystem := false
	for _, a := range fake.calls[0].args {
		if a == "--system" {
			hasSystem = true
		}
		if a == "--session" {
			t.Errorf("system call should not use --session")
		}
	}
	if !hasSystem {
		t.Errorf("system bus call should use --system flag, args: %v", fake.calls[0].args)
	}
}

func TestIsMockMode_RespectsEnv(t *testing.T) {
	setDBusEnv(t, "mock")
	if !IsMockMode() {
		t.Error("DEEPIN_DBUS=mock should set mock mode")
	}
	setDBusEnv(t, "")
	if IsMockMode() {
		t.Error("DEEPIN_DBUS=empty should NOT be mock mode")
	}
}

// === parseGVariantString 测试 ===

func TestParseGVariantString_SingleQuote(t *testing.T) {
	got := parseGVariantString("(<'deepin-dark',>)")
	if got != "deepin-dark" {
		t.Errorf("got %q want %q", got, "deepin-dark")
	}
}

func TestParseGVariantString_DoubleQuote(t *testing.T) {
	got := parseGVariantString(`(<'has "quotes"',>)`)
	if got != `has "quotes"` {
		t.Errorf("got %q", got)
	}
}

func TestParseGVariantString_Empty(t *testing.T) {
	got := parseGVariantString("(,)")
	if got != "(,)" {
		t.Errorf("empty tuple should be returned as-is, got %q", got)
	}
}

func TestParseGVariantString_NotTuple(t *testing.T) {
	got := parseGVariantString("just a string")
	if got != "just a string" {
		t.Errorf("non-tuple should be returned as-is, got %q", got)
	}
}

func TestParseGVariantString_WithWhitespace(t *testing.T) {
	got := parseGVariantString("  (<'deepin-dark',>)  ")
	if got != "deepin-dark" {
		t.Errorf("should trim whitespace, got %q", got)
	}
}

// === equalSlices helper ===
func equalSlices(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}