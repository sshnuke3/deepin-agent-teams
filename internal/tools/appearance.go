// Package tools 提供 deepin 系统工具的实现
//
// 当前是 mock 实现（不真接 D-Bus），用于演示 Agent 编排
// v4 Week 5-6 会替换成真 DTK/DDE D-Bus 调用
package tools

import (
	"context"
	"fmt"
	"os"
)

// Result 工具调用结果
type Result struct {
	ToolName string
	Success  bool
	Message  string
}

// ChangeTheme 切换主题（mock 实现）
// 真实实现：D-Bus call com.deepin.daemon.Appearance
// org.deepin.daemon.Appearance.SetGtkTheme(theme)
func ChangeTheme(ctx context.Context, theme string) *Result {
	return &Result{
		ToolName: "change_theme",
		Success:  true,
		Message:  fmt.Sprintf("已切换到 %s 主题", theme),
	}
}

// GetSystemInfo 获取系统信息（mock 实现）
// 真实实现：调用 deepin 系统信息 API
func GetSystemInfo(ctx context.Context) *Result {
	hostname, _ := os.Hostname()
	return &Result{
		ToolName: "get_system_info",
		Success:  true,
		Message:  fmt.Sprintf("主机名: %s, 系统: deepin 25", hostname),
	}
}
