package tools

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestDraftEmail_Preview 测试 preview 模式（不落盘）
func TestDraftEmail_Preview(t *testing.T) {
	report := DraftEmail(context.Background(),
		"alice@example.com",
		"项目进度同步",
		"想跟 Alice 同步本周项目进度",
		"Hi Alice,\n\n本周项目进度如下：\n- M2 完成\n- M3 启动中\n\nBest,\n龙虾",
		"formal", "preview")

	if !report.VerifPassed {
		t.Errorf("preview 应通过: %s", report.VerifMsg)
	}
	if report.Mode != "preview" {
		t.Errorf("Mode: got %q, want preview", report.Mode)
	}
	if report.StoragePath != "" {
		t.Errorf("preview 模式不应有 StoragePath, got %q", report.StoragePath)
	}
	if report.Subject != "项目进度同步" {
		t.Errorf("Subject: got %q, want 项目进度同步", report.Subject)
	}
}

// TestDraftEmail_Apply 测试 apply 模式（落盘 + .eml 格式）
func TestDraftEmail_Apply(t *testing.T) {
	// 临时把 HOME 切到 t.TempDir（避免污染真实 ~/.local/share）
	origHome := os.Getenv("HOME")
	t.Cleanup(func() { os.Setenv("HOME", origHome) })
	tmpHome := t.TempDir()
	os.Setenv("HOME", tmpHome)

	report := DraftEmail(context.Background(),
		"bob@example.com",
		"会议邀请",
		"邀请 Bob 周三开会",
		"Hi Bob,\n\n想约你周三下午 3 点聊一下 v4 进度。\n\nBest,\n龙虾",
		"formal", "apply")

	if !report.VerifPassed {
		t.Fatalf("apply 应通过: %s", report.VerifMsg)
	}
	if report.StoragePath == "" {
		t.Fatal("apply 模式必须有 StoragePath")
	}

	// 验证文件真的写了
	data, err := os.ReadFile(report.StoragePath)
	if err != nil {
		t.Fatalf("read draft: %v", err)
	}
	content := string(data)

	// 必须包含必要头部
	if !strings.Contains(content, "To: bob@example.com") {
		t.Errorf(".eml 缺少 To: 头, content:\n%s", content)
	}
	if !strings.Contains(content, "Subject: 会议邀请") {
		t.Errorf(".eml 缺少 Subject: 头, content:\n%s", content)
	}
	if !strings.Contains(content, "Hi Bob") {
		t.Errorf(".eml 缺少正文, content:\n%s", content)
	}

	// 验证 ID 命名格式
	if !strings.Contains(report.DraftID, "-") {
		t.Errorf("DraftID 应是 <timestamp>-<slug>, got %q", report.DraftID)
	}
}

// TestDraftEmail_EmptySubjectAndPurpose 测试空主题+空目的 → 拒绝
func TestDraftEmail_EmptySubjectAndPurpose(t *testing.T) {
	report := DraftEmail(context.Background(),
		"x@y.com",
		"",
		"",
		"body",
		"formal", "preview")

	if report.VerifPassed {
		t.Error("空主题+空目的应失败")
	}
	if !strings.Contains(report.VerifMsg, "主题和目的") {
		t.Errorf("错误信息应提到'主题和目的', got: %s", report.VerifMsg)
	}
}

// TestVerifyEmailDraft 测试验证逻辑
func TestVerifyEmailDraft(t *testing.T) {
	tmpDir := t.TempDir()
	storagePath := filepath.Join(tmpDir, "test.eml")

	content := "To: alice@example.com\r\n" +
		"Subject: 测试主题\r\n" +
		"Date: Mon, 18 Jul 2026 09:00:00 +0800\r\n" +
		"\r\n" +
		"正文内容"
	if err := os.WriteFile(storagePath, []byte(content), 0644); err != nil {
		t.Fatalf("write test eml: %v", err)
	}

	// 正常：主题匹配
	ok, msg := VerifyEmailDraft(context.Background(), storagePath, "测试主题")
	if !ok {
		t.Errorf("应通过, got: %s", msg)
	}

	// 异常：主题不匹配
	ok, msg = VerifyEmailDraft(context.Background(), storagePath, "期望错误的主题")
	if ok {
		t.Errorf("主题不匹配应失败, got: %s", msg)
	}
}

// TestVerifyEmailDraft_MissingHeader 测试缺头部
func TestVerifyEmailDraft_MissingHeader(t *testing.T) {
	tmpDir := t.TempDir()
	storagePath := filepath.Join(tmpDir, "bad.eml")
	os.WriteFile(storagePath, []byte("just a plain text without email headers"), 0644)

	ok, msg := VerifyEmailDraft(context.Background(), storagePath, "")
	if ok {
		t.Errorf("缺头部应失败, got: %s", msg)
	}
	if !strings.Contains(msg, "缺少") {
		t.Errorf("错误信息应提到'缺少', got: %s", msg)
	}
}

// TestDraftEmail_NoRecipient 测试无收件人 → 用占位符
func TestDraftEmail_NoRecipient(t *testing.T) {
	origHome := os.Getenv("HOME")
	t.Cleanup(func() { os.Setenv("HOME", origHome) })
	os.Setenv("HOME", t.TempDir())

	report := DraftEmail(context.Background(),
		"", // 没填收件人
		"无收件人测试",
		"测试占位符",
		"body",
		"formal", "apply")

	if !report.VerifPassed {
		t.Fatalf("apply 应通过（占位符不算错）: %s", report.VerifMsg)
	}

	data, _ := os.ReadFile(report.StoragePath)
	if !strings.Contains(string(data), "<收件人待填>") {
		t.Errorf(".eml 应包含占位符, content:\n%s", string(data))
	}
}
