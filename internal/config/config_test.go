package config

import (
	"os"
	"path/filepath"
	"testing"
)

// TestLoadDotEnv_Basic 测试基础 .env 加载
func TestLoadDotEnv_Basic(t *testing.T) {
	tmpDir := t.TempDir()
	envFile := filepath.Join(tmpDir, ".env")
	content := `# 注释行
LLM_PROVIDER=qwen
QWEN_API_KEY=test-key-12345
LLM_BASE_URL=https://example.com/v1

# 空行 + 引号值
LLM_MODEL="qwen-test"
`
	if err := os.WriteFile(envFile, []byte(content), 0644); err != nil {
		t.Fatalf("write .env: %v", err)
	}

	// 清掉测试用的 env
	os.Unsetenv("LLM_PROVIDER")
	os.Unsetenv("QWEN_API_KEY")
	os.Unsetenv("LLM_BASE_URL")
	os.Unsetenv("LLM_MODEL")
	t.Cleanup(func() {
		os.Unsetenv("LLM_PROVIDER")
		os.Unsetenv("QWEN_API_KEY")
		os.Unsetenv("LLM_BASE_URL")
		os.Unsetenv("LLM_MODEL")
	})

	if err := loadDotEnv(envFile); err != nil {
		t.Fatalf("loadDotEnv: %v", err)
	}

	if got := os.Getenv("LLM_PROVIDER"); got != "qwen" {
		t.Errorf("LLM_PROVIDER: got %q, want qwen", got)
	}
	if got := os.Getenv("QWEN_API_KEY"); got != "test-key-12345" {
		t.Errorf("QWEN_API_KEY: got %q", got)
	}
	if got := os.Getenv("LLM_BASE_URL"); got != "https://example.com/v1" {
		t.Errorf("LLM_BASE_URL: got %q", got)
	}
	// 引号应被去掉
	if got := os.Getenv("LLM_MODEL"); got != "qwen-test" {
		t.Errorf("LLM_MODEL: got %q, want qwen-test (引号应被去掉)", got)
	}
}

// TestLoadDotEnv_EnvPriority 测试已有 env 不被 .env 覆盖
func TestLoadDotEnv_EnvPriority(t *testing.T) {
	tmpDir := t.TempDir()
	envFile := filepath.Join(tmpDir, ".env")
	os.WriteFile(envFile, []byte("QWEN_API_KEY=from-file\n"), 0644)

	os.Setenv("QWEN_API_KEY", "from-shell")
	t.Cleanup(func() { os.Unsetenv("QWEN_API_KEY") })

	if err := loadDotEnv(envFile); err != nil {
		t.Fatalf("loadDotEnv: %v", err)
	}

	// shell 环境变量应优先
	if got := os.Getenv("QWEN_API_KEY"); got != "from-shell" {
		t.Errorf("env 应优先于 .env: got %q, want from-shell", got)
	}
}

// TestLoadDotEnv_MissingFile 测试文件不存在不报错
func TestLoadDotEnv_MissingFile(t *testing.T) {
	err := loadDotEnv("/tmp/nonexistent-env-file-12345")
	if err == nil {
		t.Error("不存在的文件应返回 error")
	}
}

// TestLoad 测试完整 Load 流程（用临时 .env）
func TestLoad(t *testing.T) {
	tmpDir := t.TempDir()
	envFile := filepath.Join(tmpDir, ".env")
	content := `LLM_PROVIDER=qwen
QWEN_API_KEY=test-load-key
`
	os.WriteFile(envFile, []byte(content), 0644)

	// 清掉相关 env
	for _, k := range []string{"LLM_PROVIDER", "QWEN_API_KEY", "AGNES_API_KEY", "OPENAI_API_KEY"} {
		os.Unsetenv(k)
	}
	// 切到临时目录让 .env 加载生效
	origDir, _ := os.Getwd()
	os.Chdir(tmpDir)
	t.Cleanup(func() {
		os.Chdir(origDir)
		for _, k := range []string{"LLM_PROVIDER", "QWEN_API_KEY", "AGNES_API_KEY", "OPENAI_API_KEY"} {
			os.Unsetenv(k)
		}
	})

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.LLMProvider != "qwen" {
		t.Errorf("LLMProvider: got %q, want qwen", cfg.LLMProvider)
	}
	if cfg.APIKey != "test-load-key" {
		t.Errorf("APIKey: got %q", cfg.APIKey)
	}
	if cfg.BaseURL == "" || cfg.Model == "" {
		t.Errorf("预设应自动填 BaseURL/Model: got BaseURL=%q Model=%q", cfg.BaseURL, cfg.Model)
	}
}

// TestLoad_MissingKey 测试无 key 时返回清晰错误
func TestLoad_MissingKey(t *testing.T) {
	tmpDir := t.TempDir()
	envFile := filepath.Join(tmpDir, ".env")
	os.WriteFile(envFile, []byte("LLM_PROVIDER=qwen\n"), 0644) // 不设 KEY

	for _, k := range []string{"LLM_PROVIDER", "QWEN_API_KEY", "AGNES_API_KEY", "OPENAI_API_KEY"} {
		os.Unsetenv(k)
	}
	origDir, _ := os.Getwd()
	os.Chdir(tmpDir)
	t.Cleanup(func() {
		os.Chdir(origDir)
		for _, k := range []string{"LLM_PROVIDER", "QWEN_API_KEY", "AGNES_API_KEY", "OPENAI_API_KEY"} {
			os.Unsetenv(k)
		}
	})

	_, err := Load()
	if err == nil {
		t.Fatal("无 key 应返回 error")
	}
	// 错误信息应提示 .env
	if !contains(err.Error(), ".env") {
		t.Errorf("错误应提示 .env: %v", err)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
