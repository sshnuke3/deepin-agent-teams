// Package tools - dbus.go
//
// v4 M3: D-Bus 通用调用层
//
// 设计目标：把所有 deepin 工具（D-Bus 调用、pactl 等）封装成一个可注入的命令执行层。
// - 默认：真调 gdbus 命令
// - 测试：通过 Executor interface 注入 mock
// - 环境变量 DEEPIN_DBUS=mock 时强制走 mock（demo / CI 用）
//
// 为什么不直接用 github.com/godbus/dbus：
// - godbus/dbus 是 CGO 依赖，跨平台编译麻烦
// - deepin 系统自带 gdbus 命令，依赖更轻
// - 跟 deepin 官方文档示例一致（CSDN/博客都这么写）
package tools

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// CommandExecutor 抽象 exec.Command 行为，方便测试 mock
//
// 默认实现是 realExecutor（真调 exec.Command）。
// 测试时用 fakeExecutor 预设 stdout / stderr / err。
type CommandExecutor interface {
	// Run 执行命令，返回 stdout（去掉尾换行）、stderr、退出错误
	Run(ctx context.Context, name string, args ...string) (stdout string, stderr string, err error)
}

// realExecutor 真的调用 os/exec
type realExecutor struct{}

func (realExecutor) Run(ctx context.Context, name string, args ...string) (string, string, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	var stdoutBuf, stderrBuf strings.Builder
	cmd.Stdout = &stdoutBuf
	cmd.Stderr = &stderrBuf
	err := cmd.Run()
	return strings.TrimRight(stdoutBuf.String(), "\n"),
		strings.TrimRight(stderrBuf.String(), "\n"),
		err
}

// defaultExecutor 是全局默认执行器（可被 setExecutor 替换）
var defaultExecutor CommandExecutor = realExecutor{}

// SetExecutor 设置全局命令执行器（测试用）
//
// 调用方负责恢复（生产代码不要调用）。
func SetExecutor(e CommandExecutor) {
	defaultExecutor = e
}

// ResetExecutor 恢复默认执行器（测试清理用）
func ResetExecutor() {
	defaultExecutor = realExecutor{}
}

// dbusMode 当前 D-Bus 运行模式
//   - "auto"：默认，调用时由环境变量决定（DEEPIN_DBUS=mock → mock，否则 real）
//   - "mock"：强制走 mock（CI 用）
//   - "real"：强制走 real（生产用）
type dbusModeT int

const (
	modeAuto dbusModeT = iota
	modeMock
	modeReal
)

func (m dbusModeT) effective() dbusModeT {
	if m != modeAuto {
		return m
	}
	if os.Getenv("DEEPIN_DBUS") == "mock" {
		return modeMock
	}
	return modeReal
}

func (m dbusModeT) String() string {
	switch m.effective() {
	case modeMock:
		return "mock"
	case modeReal:
		return "real"
	default:
		return "auto(real)"
	}
}

// dbusCall 调用 D-Bus 方法（通过 gdbus 命令）
//
// 参数：
//   - dest: bus name（如 "com.deepin.daemon.Appearance"）
//   - objectPath: 对象路径（如 "/com/deepin/daemon/Appearance"）
//   - method: 方法全名（如 "com.deepin.daemon.Appearance.SetCurrentTheme"）
//   - args: 方法参数（字符串）
//
// 返回：gdbus 的 stdout（去掉尾换行）和错误。
//
// 实现：
//   - mock 模式（DEEPIN_DBUS=mock）：返回假成功 + 占位 stdout（让上层逻辑跑通）
//   - real 模式：调 `gdbus call --session -d <dest> -o <path> -m <method> <args>`
//
// 注意：gdbus 返回的 stdout 形如 `(<'deepin-dark',>,)` —— 调用方自行解析。
func dbusCall(ctx context.Context, dest, objectPath, method string, args ...string) (string, error) {
	mode := dbusModeT(0).effective()
	if mode == modeMock {
		return mockDBusResponse(dest, method, args), nil
	}
	allArgs := []string{"call", "--session", "-d", dest, "-o", objectPath, "-m", method}
	allArgs = append(allArgs, args...)
	stdout, stderr, err := defaultExecutor.Run(ctx, "gdbus", allArgs...)
	if err != nil {
		return stdout, fmt.Errorf("dbus call %s.%s failed: %w (stderr: %s)", dest, method, err, stderr)
	}
	return stdout, nil
}

// dbusCallSystem 系统总线（--system）版本
// （少用，deepin 25 大部分服务走 session bus）
func dbusCallSystem(ctx context.Context, dest, objectPath, method string, args ...string) (string, error) {
	mode := dbusModeT(0).effective()
	if mode == modeMock {
		return mockDBusResponse(dest, method, args), nil
	}
	allArgs := []string{"call", "--system", "-d", dest, "-o", objectPath, "-m", method}
	allArgs = append(allArgs, args...)
	stdout, stderr, err := defaultExecutor.Run(ctx, "gdbus", allArgs...)
	if err != nil {
		return stdout, fmt.Errorf("system dbus call %s.%s failed: %w (stderr: %s)", dest, method, err, stderr)
	}
	return stdout, nil
}

// mockDBusResponse 假 D-Bus 响应（让上层逻辑跑通、演示 demo 可用）
//
// 不同方法返回合理的占位：
//   - SetXxx → ()  (空返回值)
//   - GetXxx → (<'mock-value',>) (单字符串返回值)
//   - 其他 → ()
func mockDBusResponse(dest, method string, args []string) string {
	parts := strings.Split(method, ".")
	name := parts[len(parts)-1]
	switch {
	case strings.HasPrefix(name, "Set"):
		return "()"
	case strings.HasPrefix(name, "Get"):
		return "(<'mock-value',>)"
	case strings.HasPrefix(name, "Enable"), strings.HasPrefix(name, "Disable"):
		return "()"
	default:
		return "()"
	}
}

// errDBusUnavailable 在没有 deepin 服务时返回的错误
var errDBusUnavailable = errors.New("D-Bus service unavailable (likely not running on deepin 25)")

// IsMockMode 报告当前是否在 mock 模式（让上层决定要不要在输出里提示"演示模式"）
func IsMockMode() bool {
	return dbusModeT(0).effective() == modeMock
}