// Package tools - settings.go
//
// v4 M2: 系统设置 demo
// 把原本零散的 ChangeTheme/GetSystemInfo 扩展为统一的 settings 系统
//
// 4 类设置：
//   - theme:      deepin-dark | deepin-light | deepin-auto
//   - volume:     0-100
//   - brightness: 0-100
//   - network:    on | off (wifi)
//
// 状态保存：apply 模式写到 ~/.local/share/deepin-agent/settings.json
// preview 模式不写，只展示计划
//
// v4 M3 替换成真 D-Bus 调用（com.deepin.daemon.{Appearance,Audio,Power,Network}）
package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// SettingsCategory 设置分类
const (
	CategoryTheme      = "theme"
	CategoryVolume     = "volume"
	CategoryBrightness = "brightness"
	CategoryNetwork    = "network"
)

// SettingsReport 系统设置报告
type SettingsReport struct {
	Categories  []string        `json:"categories"` // 涉及的分类列表
	Mode        string          `json:"mode"`       // preview | applied
	Changes     []SettingChange `json:"changes"`
	VerifPassed bool            `json:"verified"`
	VerifMsg    string          `json:"verify_msg,omitempty"`
}

// SettingChange 单次设置变更
type SettingChange struct {
	Category string `json:"category"` // theme/volume/brightness/network
	Key      string `json:"key"`      // gtk_theme / volume_level / brightness_level / wifi_enabled
	OldValue string `json:"old_value,omitempty"`
	NewValue string `json:"new_value"`
	Status   string `json:"status"` // planned | applied | failed
	Message  string `json:"message,omitempty"`
}

// ApplySettings 应用系统设置（preview/apply 双模式）
//
// changes 是 Planner 生成的变更列表，按顺序应用
// mode="preview": 只校验 + 返回报告，不写盘
// mode="apply":   调工具 + 写 settings.json
func ApplySettings(ctx context.Context, changes []SettingChange, mode string) *SettingsReport {
	report := &SettingsReport{
		Mode:    mode,
		Changes: []SettingChange{},
	}

	// 1. 校验 + 模拟执行
	categoriesSet := make(map[string]bool)
	for i := range changes {
		c := &changes[i]
		// 校验
		if err := validateChange(c); err != nil {
			c.Status = "failed"
			c.Message = err.Error()
			report.Changes = append(report.Changes, *c)
			report.VerifPassed = false
			report.VerifMsg = fmt.Sprintf("%s 校验失败: %v", c.Category, err)
			return report
		}

		// preview 模式：只标记 planned
		if mode != "apply" {
			c.Status = "planned"
			c.Message = fmt.Sprintf("计划将 %s.%s 改为 %s", c.Category, c.Key, c.NewValue)
			report.Changes = append(report.Changes, *c)
			categoriesSet[c.Category] = true
			continue
		}

		// apply 模式：真接 D-Bus（或 mock fallback）
		if err := applyChange(ctx, c); err != nil {
			c.Status = "failed"
			c.Message = err.Error()
			report.Changes = append(report.Changes, *c)
			report.VerifPassed = false
			report.VerifMsg = fmt.Sprintf("%s 应用失败: %v", c.Category, err)
			return report
		}

		modeNote := ""
		if IsMockMode() {
			modeNote = "（演示模式）"
		} else {
			modeNote = "（D-Bus 真调用）"
		}
		c.Status = "applied"
		c.Message = fmt.Sprintf("已应用 %s.%s = %s%s", c.Category, c.Key, c.NewValue, modeNote)
		report.Changes = append(report.Changes, *c)
		categoriesSet[c.Category] = true
	}

	// 提取分类列表（按字母序）
	for cat := range categoriesSet {
		report.Categories = append(report.Categories, cat)
	}
	// 简化：直接保留迭代顺序即可，这里不强求排序

	// 2. apply 模式：落盘 settings.json
	if mode == "apply" {
		if err := saveSettings(report.Changes); err != nil {
			report.VerifPassed = false
			report.VerifMsg = fmt.Sprintf("保存失败: %v", err)
			return report
		}
		report.VerifPassed = true
		report.VerifMsg = fmt.Sprintf("已应用 %d 项设置并持久化", len(report.Changes))
		return report
	}

	// preview 模式
	report.VerifPassed = true
	report.VerifMsg = fmt.Sprintf("预览: %d 项设置待应用", len(report.Changes))
	return report
}

// validateChange 校验设置项的合法性
//
// 接收指针，确保 c.Key / c.NewValue 归一化能写入原对象
func validateChange(c *SettingChange) error {
	if c.Category == "" {
		return fmt.Errorf("category 为空")
	}
	switch c.Category {
	case CategoryTheme:
		switch c.NewValue {
		case "deepin-dark", "deepin-light", "deepin-auto":
			c.Key = "gtk_theme"
			return nil
		default:
			return fmt.Errorf("未知主题: %s", c.NewValue)
		}
	case CategoryVolume, CategoryBrightness:
		v, err := strconv.Atoi(c.NewValue)
		if err != nil {
			return fmt.Errorf("数值非法: %s", c.NewValue)
		}
		if v < 0 || v > 100 {
			return fmt.Errorf("数值越界 (0-100): %d", v)
		}
		if c.Category == CategoryVolume {
			c.Key = "volume_level"
		} else {
			c.Key = "brightness_level"
		}
		return nil
	case CategoryNetwork:
		switch c.NewValue {
		case "on", "off":
			c.Key = "wifi_enabled"
			if c.NewValue == "on" {
				c.NewValue = "true"
			} else {
				c.NewValue = "false"
			}
			return nil
		default:
			return fmt.Errorf("网络状态必须是 on/off: %s", c.NewValue)
		}
	default:
		return fmt.Errorf("不支持的分类: %s", c.Category)
	}
}

// applyChange 真应用（v4 M3：真接 D-Bus）
//
// 按 category 调用对应 D-Bus 方法：
//   - theme:      com.deepin.daemon.Appearance.SetGtkTheme (string)
//   - volume:     com.deepin.daemon.Audio.SinkSetVolume (double 0.0-1.0)
//   - brightness: com.deepin.daemon.Display.Brightness.SetBrightness (double 0.0-1.0)
//   - network:    com.deepin.daemon.Network.EnableWifi / DisableWifi
//
// mock 模式（DEEPIN_DBUS=mock）：跳过 D-Bus，直接成功（返回 nil）。
func applyChange(ctx context.Context, c *SettingChange) error {
	if IsMockMode() {
		// mock 模式：不做 D-Bus 调用，假装成功
		return nil
	}

	switch c.Category {
	case CategoryTheme:
		_, err := dbusCall(ctx,
			"com.deepin.daemon.Appearance",
			"/com/deepin/daemon/Appearance",
			"com.deepin.daemon.Appearance.SetGtkTheme",
			c.NewValue,
		)
		return err

	case CategoryVolume:
		// 0-100 → 0.0-1.0
		v, _ := strconv.Atoi(c.NewValue)
		ratio := float64(v) / 100.0
		_, err := dbusCall(ctx,
			"com.deepin.daemon.Audio",
			"/com/deepin/daemon/Audio",
			"com.deepin.daemon.Audio.SinkSetVolume",
			fmt.Sprintf("%f", ratio),
		)
		return err

	case CategoryBrightness:
		// 0-100 → 0.0-1.0
		v, _ := strconv.Atoi(c.NewValue)
		ratio := float64(v) / 100.0
		_, err := dbusCall(ctx,
			"com.deepin.daemon.Display",
			"/com/deepin/daemon/Display",
			"com.deepin.daemon.Display.Brightness.SetBrightness",
			fmt.Sprintf("%f", ratio),
		)
		return err

	case CategoryNetwork:
		method := "com.deepin.daemon.Network.EnableWifi"
		if c.NewValue == "false" {
			method = "com.deepin.daemon.Network.DisableWifi"
		}
		_, err := dbusCall(ctx,
			"com.deepin.daemon.Network",
			"/com/deepin/daemon/Network",
			method,
		)
		return err

	default:
		return fmt.Errorf("未实现 category: %s", c.Category)
	}
}

// saveSettings 把变更列表写到 ~/.local/share/deepin-agent/settings.json
func saveSettings(changes []SettingChange) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	dir := filepath.Join(home, ".local", "share", "deepin-agent")
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}
	path := filepath.Join(dir, "settings.json")

	// 读取已有（如果有），merge 新变更
	existing := map[string]map[string]string{}
	if data, err := os.ReadFile(path); err == nil {
		json.Unmarshal(data, &existing)
	}
	for _, c := range changes {
		if existing[c.Category] == nil {
			existing[c.Category] = map[string]string{}
		}
		existing[c.Category][c.Key] = c.NewValue
	}

	data, err := json.MarshalIndent(map[string]any{
		"updated_at": time.Now().Format(time.RFC3339),
		"settings":   existing,
	}, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

// VerifySettings 验证设置是否真的应用（apply 模式专用）
//
// 校验：settings.json 存在 + 含本次变更的所有 (category, key, new_value)
func VerifySettings(ctx context.Context, changes []SettingChange) (bool, string) {
	home, err := os.UserHomeDir()
	if err != nil {
		return false, fmt.Sprintf("HOME 失败: %v", err)
	}
	path := filepath.Join(home, ".local", "share", "deepin-agent", "settings.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return false, fmt.Sprintf("读取 settings.json 失败: %v", err)
	}

	var stored struct {
		Settings map[string]map[string]string `json:"settings"`
	}
	if err := json.Unmarshal(data, &stored); err != nil {
		return false, fmt.Sprintf("JSON 解析失败: %v", err)
	}

	for _, c := range changes {
		cat, ok := stored.Settings[c.Category]
		if !ok {
			return false, fmt.Sprintf("分类 %s 未持久化", c.Category)
		}
		if got, ok := cat[c.Key]; !ok || got != c.NewValue {
			return false, fmt.Sprintf("%s.%s 不匹配: 期望=%s, 实际=%v", c.Category, c.Key, c.NewValue, cat[c.Key])
		}
	}
	return true, fmt.Sprintf("验证通过: %d 项设置已持久化", len(changes))
}

// NormalizeSettingInput 把 Planner 输出归一化（处理常见说法）
//
// 例：把"暗色""黑色""dark"映射成 "deepin-dark"
//
//	把"音量调到 50""声音 50" 提取出 "50"
func NormalizeSettingInput(category, rawValue string) string {
	rawValue = strings.TrimSpace(strings.ToLower(rawValue))
	switch category {
	case CategoryTheme:
		switch rawValue {
		case "暗色", "黑色", "深色", "dark":
			return "deepin-dark"
		case "浅色", "亮色", "白色", "light":
			return "deepin-light"
		case "自动", "跟随", "auto":
			return "deepin-auto"
		}
	}
	return rawValue
}
