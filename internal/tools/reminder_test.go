package tools

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestScheduleReminder_Preview(t *testing.T) {
	ctx := context.Background()
	r := ScheduleReminder(ctx, "开会", "2026-07-18T15:00:00+08:00", "normal", "preview")

	if !r.VerifPassed {
		t.Fatalf("preview 应通过，实际: %s", r.VerifMsg)
	}
	if r.Title != "开会" {
		t.Errorf("title 失配: got %s", r.Title)
	}
	if r.DueAtParsed.IsZero() {
		t.Errorf("DueAtParsed 应非空")
	}
	if r.ReminderID != "" {
		t.Errorf("preview 模式不应生成 ReminderID, got %s", r.ReminderID)
	}
}

func TestScheduleReminder_Apply(t *testing.T) {
	ctx := context.Background()
	// 用临时 HOME 隔离
	tmp := t.TempDir()
	t.Setenv("HOME", tmp)

	title := "测试提醒"
	r := ScheduleReminder(ctx, title, "2026-07-18 15:00:00", "high", "apply")

	if !r.VerifPassed {
		t.Fatalf("apply 应通过，实际: %s", r.VerifMsg)
	}
	if r.ReminderID == "" {
		t.Errorf("apply 应生成 ReminderID")
	}
	if r.StoragePath == "" {
		t.Fatal("apply 应生成 StoragePath")
	}
	// 验证文件真的写入了
	if _, err := os.Stat(r.StoragePath); err != nil {
		t.Fatalf("文件应存在: %v", err)
	}

	// 验证文件路径在临时 HOME 下
	expectedDir := filepath.Join(tmp, ".local", "share", "deepin-agent", "reminders")
	if !strings.HasPrefix(r.StoragePath, expectedDir) {
		t.Errorf("文件路径应在临时 HOME 下, got %s, want prefix %s", r.StoragePath, expectedDir)
	}
}

func TestScheduleReminder_Apply_VerifyRoundtrip(t *testing.T) {
	ctx := context.Background()
	tmp := t.TempDir()
	t.Setenv("HOME", tmp)

	title := "完整往返测试"
	r := ScheduleReminder(ctx, title, "2026-07-18T15:00:00+08:00", "normal", "apply")
	if !r.VerifPassed {
		t.Fatalf("apply 失败: %s", r.VerifMsg)
	}

	// 调 Verifier 验证
	ok, msg := VerifyReminder(ctx, r.StoragePath, title)
	if !ok {
		t.Fatalf("VerifyReminder 失败: %s", msg)
	}
}

func TestScheduleReminder_BadTime(t *testing.T) {
	ctx := context.Background()
	// 不支持的自然语言
	r := ScheduleReminder(ctx, "测试", "某年某月某日", "normal", "preview")
	// preview 模式允许原值展示
	if !r.VerifPassed {
		t.Fatalf("preview 应允许原值, got: %s", r.VerifMsg)
	}

	// apply 模式应拒绝
	r2 := ScheduleReminder(ctx, "测试", "某年某月某日", "normal", "apply")
	if r2.VerifPassed {
		t.Fatalf("apply 不应通过坏时间, got: %s", r2.VerifMsg)
	}
}

func TestParseReminderTime(t *testing.T) {
	cases := []struct {
		input   string
		wantErr bool
	}{
		{"2026-07-18T15:00:00+08:00", false},
		{"2026-07-18 15:00:00", false},
		{"2026-07-18 15:04", false},
		{"2026-07-18", false},
		{"", true},
		{"某年某月某日", true},
		{"明天下午 3 点", true}, // 自然语言不在支持的格式里
	}
	for _, c := range cases {
		_, err := parseReminderTime(c.input)
		if (err != nil) != c.wantErr {
			t.Errorf("parseReminderTime(%q): err=%v, wantErr=%v", c.input, err, c.wantErr)
		}
	}
}

func TestSlugify(t *testing.T) {
	cases := []struct {
		input string
		want  string
	}{
		{"Hello World", "hello-world"},
		{"测试中文", ""}, // 中文会被过滤
		{"open_ai_meeting", "open-ai-meeting"},
		{"---", ""},
	}
	for _, c := range cases {
		got := slugify(c.input)
		if c.want == "" && got != "reminder" {
			t.Errorf("slugify(%q): got %q, want 'reminder' (default)", c.input, got)
		} else if c.want != "" && got != c.want {
			t.Errorf("slugify(%q): got %q, want %q", c.input, got, c.want)
		}
	}
}

// 验证 DueAtParsed 在正确时区
func TestScheduleReminder_DueAtParsed(t *testing.T) {
	ctx := context.Background()
	r := ScheduleReminder(ctx, "时区测试", "2026-07-18T15:00:00+08:00", "normal", "preview")
	if r.DueAtParsed.IsZero() {
		t.Fatal("DueAtParsed 不应为零")
	}
	// 验证 hour 是 15
	if r.DueAtParsed.Hour() != 15 {
		t.Errorf("小时应为 15, got %d", r.DueAtParsed.Hour())
	}
	// 验证时间在合理范围
	if r.DueAtParsed.Year() != 2026 || r.DueAtParsed.Month() != time.July || r.DueAtParsed.Day() != 18 {
		t.Errorf("日期失配: %v", r.DueAtParsed)
	}
}