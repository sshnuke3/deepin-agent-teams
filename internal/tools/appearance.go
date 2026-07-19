// Package tools - appearance.go
//
// v4 M3: 主题切换 - 真 D-Bus + mock fallback
//
// 真接 D-Bus：
//   - dest: com.deepin.daemon.Appearance
//   - path: /com/deepin/daemon/Appearance
//   - method: com.deepin.daemon.Appearance.SetCurrentTheme(theme)
//   - method: com.deepin.daemon.Appearance.GetCurrentTheme() -> string
//
// 环境：
//   - 真 deepin 25：直接调 gdbus 命令
//   - 其他（Ubuntu / CI）：设 DEEPIN_DBUS=mock 自动走 mock，或代码检测后降级
//
// 历史：
//   - v4 M2 之前：纯 mock，硬编码 "系统: deepin 25" 字符串
//   - v4 M3 起：真接 D-Bus，mock 作为可执行 fallback
package tools

import (
	"context"
	"fmt"
	"os"
	"strings"
)

// Result 工具调用结果
type Result struct {
	ToolName string
	Success  bool
	Message  string
}

// ChangeTheme 切换主题
//
// theme 接受 deepin 标准主题名：
//   - "deepin-dark"（深色）
//   - "deepin-light"（浅色）
//   - "deepin-auto"（自动，跟随系统）
//
// 返回：
//   - 成功：Success=true，Message 含新主题名
//   - 失败：Success=false，Message 含错误信息
//   - mock 模式：Success=true，Message 加 "(演示模式)"
func ChangeTheme(ctx context.Context, theme string) *Result {
	res := &Result{ToolName: "change_theme"}

	// 校验主题名（防止无效值传进 D-Bus）
	if !isValidTheme(theme) {
		res.Success = false
		res.Message = fmt.Sprintf("无效主题名: %q (有效: deepin-dark / deepin-light / deepin-auto)", theme)
		return res
	}

	out, err := dbusCall(ctx,
		"com.deepin.daemon.Appearance",
		"/com/deepin/daemon/Appearance",
		"com.deepin.daemon.Appearance.SetCurrentTheme",
		theme,
	)
	if err != nil {
		res.Success = false
		res.Message = fmt.Sprintf("切换主题失败: %v", err)
		return res
	}

	res.Success = true
	modeNote := ""
	if IsMockMode() {
		modeNote = "（演示模式）"
	}
	res.Message = fmt.Sprintf("已切换到 %s 主题%s（gdbus 返回: %s）", theme, modeNote, out)
	return res
}

// GetCurrentTheme 查询当前主题
//
// 真接 D-Bus 返回值，mock 模式返回 "mock-value"。
func GetCurrentTheme(ctx context.Context) (string, error) {
	out, err := dbusCall(ctx,
		"com.deepin.daemon.Appearance",
		"/com/deepin/daemon/Appearance",
		"com.deepin.daemon.Appearance.GetCurrentTheme",
	)
	if err != nil {
		return "", fmt.Errorf("query current theme: %w", err)
	}
	return parseGVariantString(out), nil
}

// GetSystemInfo 获取系统信息
//
// 改进（v4 M3）：
//   - hostname 仍然用 os.Hostname()
//   - 系统名：DEEPIN_DBUS=mock 时用硬编码 "deepin 25"，否则用 GetCurrentTheme 推断（暗→deepin 25 dark）
//   - 真实 OS：读 /etc/os-release（不是硬编码）
func GetSystemInfo(ctx context.Context) *Result {
	hostname, _ := os.Hostname()

	osName := readOSRelease()
	if osName == "" {
		osName = "unknown"
	}

	theme, themeErr := GetCurrentTheme(ctx)
	themeStr := "未知"
	if themeErr == nil {
		themeStr = theme
	}

	return &Result{
		ToolName: "get_system_info",
		Success:  true,
		Message:  fmt.Sprintf("主机名: %s, 系统: %s, 当前主题: %s", hostname, osName, themeStr),
	}
}

// readOSRelease 从 /etc/os-release 读 PRETTY_NAME
// （替代 v4 M2 的硬编码 "deepin 25"）
func readOSRelease() string {
	data, err := os.ReadFile("/etc/os-release")
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "PRETTY_NAME=") {
			v := strings.TrimPrefix(line, "PRETTY_NAME=")
			v = strings.Trim(v, `"`)
			return v
		}
	}
	return ""
}

// isValidTheme 校验主题名是否合法
func isValidTheme(theme string) bool {
	switch theme {
	case "deepin-dark", "deepin-light", "deepin-auto":
		return true
	default:
		return false
	}
}

// parseGVariantString 从 gdbus 返回的 GVariant 字符串中提取 string 值
//
// gdbus 单字符串返回值格式：(<'value',>)
// 带特殊字符的：(<"with \"quotes\"",>)
// 空字符串：(,)
// 我们只关心最常见的单字符串情况，其他情况原样返回
func parseGVariantString(gvariant string) string {
	s := strings.TrimSpace(gvariant)
	// 找 <'...'> 或 <"..."> 包围
	if strings.HasPrefix(s, "(<'") && strings.HasSuffix(s, "',>)") {
		return s[3 : len(s)-4]
	}
	if strings.HasPrefix(s, "(<\"") && strings.HasSuffix(s, "\",>)") {
		return s[3 : len(s)-4]
	}
	// 不是单字符串 → 原样返回（让上层处理）
	return s
}