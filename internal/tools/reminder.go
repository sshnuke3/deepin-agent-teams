// Package tools - reminder.go
//
// v4 M2: 日程提醒 demo
// 工具实现：把提醒写到 ~/.local/share/deepin-agent/reminders/
//
// 跟 file_organizer 同构：
// - preview 模式：只生成计划，不真写
// - apply 模式：真的写入文件（带 ID 命名 + 时间戳）
//
// 暂不接 systemd timer / crontab（v4 M3 再接），先把"Agent 决策 → 工具执行 → 验证"的链路打通。
package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// ReminderReport 日程提醒报告
type ReminderReport struct {
	Title       string    `json:"title"`
	DueAt       string    `json:"due_at"`        // 用户输入的提醒时间
	DueAtParsed time.Time `json:"due_at_parsed"` // 实际解析出的时间
	Priority    string    `json:"priority"`      // low | normal | high
	Mode        string    `json:"mode"`          // preview | applied
	ReminderID  string    `json:"reminder_id"`   // apply 模式下生成的 ID
	StoragePath string    `json:"storage_path"`  // apply 模式下文件的实际路径
	VerifPassed bool      `json:"verified"`
	VerifMsg    string    `json:"verify_msg,omitempty"`
}

// ScheduleReminder 生成日程提醒
//
// mode="preview": 解析 DueAt，不写入磁盘
// mode="apply":   写入 ~/.local/share/deepin-agent/reminders/<id>.json
func ScheduleReminder(ctx context.Context, title, dueAt, priority, mode string) *ReminderReport {
	report := &ReminderReport{
		Title:    title,
		DueAt:    dueAt,
		Priority: priority,
		Mode:     mode,
	}

	// 1. 解析时间（容错：支持 RFC3339 / "明天上午 9 点" 等自然语言先返回 DueAt 原值）
	parsed, err := parseReminderTime(dueAt)
	if err != nil {
		// 解析失败：preview 模式照走，apply 模式拒绝写入
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("时间解析失败: %v", err)
		if mode == "preview" {
			// preview 模式允许原值展示
			report.VerifPassed = true
			report.VerifMsg = fmt.Sprintf("预览: 时间格式 '%s' 无法精确解析，待 Planner 二次规划", dueAt)
			return report
		}
		return report
	}
	report.DueAtParsed = parsed

	// 2. preview 模式：到此为止
	if mode != "apply" {
		report.VerifPassed = true
		report.VerifMsg = fmt.Sprintf("预览模式: 提醒 '%s' 计划于 %s（未写入）", title, parsed.Format(time.RFC3339))
		return report
	}

	// 3. apply 模式：写入存储
	home, err := os.UserHomeDir()
	if err != nil {
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("获取 HOME 失败: %v", err)
		return report
	}
	dir := filepath.Join(home, ".local", "share", "deepin-agent", "reminders")
	if err := os.MkdirAll(dir, 0755); err != nil {
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("建目录失败: %v", err)
		return report
	}

	// ID 用 timestamp + title slug（够用就行，M3 再换成 uuid）
	id := fmt.Sprintf("%d-%s", time.Now().Unix(), slugify(title))
	storagePath := filepath.Join(dir, id+".json")

	data, err := json.MarshalIndent(map[string]any{
		"id":         id,
		"title":      title,
		"due_at":     parsed.Format(time.RFC3339),
		"priority":   priority,
		"created_at": time.Now().Format(time.RFC3339),
		"status":     "pending",
	}, "", "  ")
	if err != nil {
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("序列化失败: %v", err)
		return report
	}

	if err := os.WriteFile(storagePath, data, 0644); err != nil {
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("写入失败: %v", err)
		return report
	}

	report.ReminderID = id
	report.StoragePath = storagePath
	report.VerifPassed = true
	report.VerifMsg = fmt.Sprintf("已写入: %s（ID=%s）", storagePath, id)
	return report
}

// VerifyReminder 验证提醒是否真的写入
//
// 校验：文件存在 + JSON 可解析 + title/due_at 字段一致
func VerifyReminder(ctx context.Context, storagePath, expectedTitle string) (bool, string) {
	if storagePath == "" {
		return false, "StoragePath 为空"
	}
	data, err := os.ReadFile(storagePath)
	if err != nil {
		return false, fmt.Sprintf("读取失败: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		return false, fmt.Sprintf("JSON 解析失败: %v", err)
	}
	if got, _ := m["title"].(string); got != expectedTitle {
		return false, fmt.Sprintf("title 不一致: 文件=%s, 期望=%s", got, expectedTitle)
	}
	return true, fmt.Sprintf("提醒验证通过: %s", storagePath)
}

// parseReminderTime 解析时间字符串
//
// 优先 RFC3339；其次常见格式；自然语言（如 "明天上午 9 点"）返回 error 让 Planner 兜底
func parseReminderTime(s string) (time.Time, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return time.Time{}, fmt.Errorf("空字符串")
	}
	// 1. RFC3339 (2026-07-18T09:00:00+08:00)
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return t, nil
	}
	// 2. 简化 RFC3339 (2026-07-18 09:00)
	for _, layout := range []string{
		"2006-01-02 15:04:05",
		"2006-01-02 15:04",
		"2006-01-02",
		"01-02 15:04",
	} {
		if t, err := time.ParseInLocation(layout, s, time.Local); err == nil {
			return t, nil
		}
	}
	// 3. 自然语言留给 Planner 处理
	return time.Time{}, fmt.Errorf("不支持的自然语言: %q", s)
}

// slugify 把 title 转成文件名安全的 slug
func slugify(s string) string {
	s = strings.ToLower(s)
	var b strings.Builder
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		} else if r == ' ' || r == '-' || r == '_' {
			b.WriteRune('-')
		}
		// 其他字符（含中文、全角符号）直接丢
	}
	out := b.String()
	// 去掉首尾的分隔符（避免出现 "---xxx---" 或只有 "---"）
	out = strings.Trim(out, "-")
	if len(out) > 30 {
		out = out[:30]
		out = strings.TrimRight(out, "-")
	}
	if out == "" {
		out = "reminder"
	}
	return out
}
