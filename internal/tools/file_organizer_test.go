package tools

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestOrganizeFiles_Preview 测试 preview 模式（不真移）
func TestOrganizeFiles_Preview(t *testing.T) {
	dir := t.TempDir()
	// 创建测试文件
	files := map[string]string{
		"a.jpg":  "image",
		"b.png":  "image",
		"c.pdf":  "docs",
		"d.mp4":  "videos",
		"e.zip":  "archives",
		"f.go":   "code",
		"rand":   "other", // 无扩展名 → other
	}
	for name := range files {
		path := filepath.Join(dir, name)
		if err := os.WriteFile(path, []byte("test"), 0644); err != nil {
			t.Fatalf("create file: %v", err)
		}
	}

	report := OrganizeFiles(context.Background(), dir, "preview")

	// 验证：6 个有扩展名的应该被分类
	if report.TotalFiles != 6 {
		t.Errorf("TotalFiles: got %d, want 6", report.TotalFiles)
	}
	if report.OtherCount != 1 {
		t.Errorf("OtherCount: got %d, want 1", report.OtherCount)
	}

	// 验证：每个分类计数正确
	expected := map[string]int{
		"images":   2,
		"docs":     1,
		"videos":   1,
		"archives": 1,
		"code":     1,
	}
	for cat, want := range expected {
		if got := report.Categories[cat]; got != want {
			t.Errorf("Categories[%s]: got %d, want %d", cat, got, want)
		}
	}

	// 验证：preview 模式下文件没被移动
	for name := range files {
		path := filepath.Join(dir, name)
		if _, err := os.Stat(path); err != nil {
			t.Errorf("preview 模式不应移动文件 %s: %v", name, err)
		}
	}

	// 验证：MovePlan 与 TotalFiles 一致
	if len(report.MovePlan) != report.TotalFiles {
		t.Errorf("MovePlan(%d) != TotalFiles(%d)", len(report.MovePlan), report.TotalFiles)
	}
}

// TestOrganizeFiles_Apply 测试 apply 模式（真移）
func TestOrganizeFiles_Apply(t *testing.T) {
	dir := t.TempDir()
	files := []string{"a.jpg", "b.png", "c.pdf"}
	for _, name := range files {
		path := filepath.Join(dir, name)
		if err := os.WriteFile(path, []byte("test"), 0644); err != nil {
			t.Fatalf("create file: %v", err)
		}
	}

	report := OrganizeFiles(context.Background(), dir, "apply")

	// 验证：原文件已移走
	for _, name := range files {
		path := filepath.Join(dir, name)
		if _, err := os.Stat(path); err == nil {
			t.Errorf("apply 后原文件应已移动: %s", path)
		}
	}

	// 验证：分类目录有文件
	imagesDir := filepath.Join(dir, "images")
	entries, err := os.ReadDir(imagesDir)
	if err != nil {
		t.Fatalf("read images dir: %v", err)
	}
	if len(entries) != 2 {
		t.Errorf("images 目录文件数: got %d, want 2", len(entries))
	}

	docsDir := filepath.Join(dir, "docs")
	entries, err = os.ReadDir(docsDir)
	if err != nil {
		t.Fatalf("read docs dir: %v", err)
	}
	if len(entries) != 1 {
		t.Errorf("docs 目录文件数: got %d, want 1", len(entries))
	}

	// 验证：AppliedCmds 记录数等于 MovePlan
	if len(report.AppliedCmds) != len(report.MovePlan) {
		t.Errorf("AppliedCmds(%d) != MovePlan(%d)", len(report.AppliedCmds), len(report.MovePlan))
	}
}

// TestVerifyOrganize 测试验证逻辑
func TestVerifyOrganize(t *testing.T) {
	dir := t.TempDir()
	// 手动建分类目录
	for _, cat := range []string{"images", "docs"} {
		if err := os.MkdirAll(filepath.Join(dir, cat), 0755); err != nil {
			t.Fatalf("mkdir: %v", err)
		}
	}
	// images 放 2 个，docs 放 1 个
	for _, name := range []string{"a.jpg", "b.png"} {
		os.WriteFile(filepath.Join(dir, "images", name), []byte("x"), 0644)
	}
	os.WriteFile(filepath.Join(dir, "docs", "c.pdf"), []byte("x"), 0644)

	expected := map[string]int{
		"images": 2,
		"docs":   1,
	}
	ok, msg := VerifyOrganize(context.Background(), dir, expected)
	if !ok {
		t.Errorf("VerifyOrganize 失败: %s", msg)
	}

	// 错误用例：期望数量不对
	wrongExpected := map[string]int{
		"images": 5,
		"docs":   1,
	}
	ok, _ = VerifyOrganize(context.Background(), dir, wrongExpected)
	if ok {
		t.Error("期望数量错误时应返回失败，但返回了成功")
	}
}

// TestOrganizeFiles_TildeExpansion 测试 ~ 展开
func TestOrganizeFiles_TildeExpansion(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "test.jpg"), []byte("x"), 0644)

	report := OrganizeFiles(context.Background(), "~/nonexistent-fake-path-12345", "preview")

	// 不存在的路径应返回错误标记
	if report.VerifPassed {
		t.Errorf("不存在路径的 VerifPassed 应为 false，实际: %s", report.VerifMsg)
	}
	if !strings.Contains(report.VerifMsg, "扫描失败") {
		t.Errorf("错误信息应包含'扫描失败'，实际: %s", report.VerifMsg)
	}
}