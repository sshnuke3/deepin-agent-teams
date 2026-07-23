package model

import (
	"context"
	"os"
	"testing"
)

// TestAdvisorConfigFromEnv_Defaults 默认值测试
func TestAdvisorConfigFromEnv_Defaults(t *testing.T) {
	// 清空所有 ADVISOR_* env
	for _, k := range []string{"ADVISOR_PROVIDER", "ADVISOR_API_KEY", "ADVISOR_BASE_URL", "ADVISOR_MODEL"} {
		old := os.Getenv(k)
		os.Unsetenv(k)
		defer func(k, v string) { os.Setenv(k, v) }(k, old)
	}

	cfg := AdvisorConfigFromEnv()

	// 默认 provider=mengyu, baseURL=mengyu.ltd, model=KAT-Coder
	if cfg.Provider != "mengyu" {
		t.Errorf("Provider default = %q, want %q", cfg.Provider, "mengyu")
	}
	if cfg.BaseURL != "https://ai-api.mengyu.ltd/v1" {
		t.Errorf("BaseURL default = %q, want mengyu.ltd", cfg.BaseURL)
	}
	if cfg.Model != "KAT-Coder-Exp-72B-1010" {
		t.Errorf("Model default = %q, want KAT-Coder", cfg.Model)
	}
	// 没有 ADVISOR_API_KEY → Enabled=false(降级路径)
	if cfg.Enabled {
		t.Errorf("Enabled should be false when no ADVISOR_API_KEY")
	}
}

// TestAdvisorConfigFromEnv_WithKey 启用路径
func TestAdvisorConfigFromEnv_WithKey(t *testing.T) {
	os.Setenv("ADVISOR_API_KEY", "sk-test-key-12345678901234567890")
	defer os.Unsetenv("ADVISOR_API_KEY")

	cfg := AdvisorConfigFromEnv()
	if !cfg.Enabled {
		t.Errorf("Enabled should be true when ADVISOR_API_KEY set")
	}
	if cfg.APIKey != "sk-test-key-12345678901234567890" {
		t.Errorf("APIKey not propagated")
	}
}

// TestAdvisorConfigFromEnv_Override 自定义 override
func TestAdvisorConfigFromEnv_Override(t *testing.T) {
	os.Setenv("ADVISOR_PROVIDER", "openai")
	os.Setenv("ADVISOR_API_KEY", "sk-test")
	os.Setenv("ADVISOR_BASE_URL", "https://api.openai.com/v1")
	os.Setenv("ADVISOR_MODEL", "gpt-4o")
	defer func() {
		os.Unsetenv("ADVISOR_PROVIDER")
		os.Unsetenv("ADVISOR_API_KEY")
		os.Unsetenv("ADVISOR_BASE_URL")
		os.Unsetenv("ADVISOR_MODEL")
	}()

	cfg := AdvisorConfigFromEnv()
	if cfg.Provider != "openai" || cfg.Model != "gpt-4o" || cfg.BaseURL != "https://api.openai.com/v1" {
		t.Errorf("Override failed: %+v", cfg)
	}
}

// TestNewAdvisorChatModel_Disabled 降级路径
func TestNewAdvisorChatModel_Disabled(t *testing.T) {
	_, err := NewAdvisorChatModel(context.Background(), AdvisorConfig{Enabled: false})
	if err == nil {
		t.Error("expected error when Enabled=false")
	}
}

// TestNewAdvisorChatModel_MissingFields 字段校验
func TestNewAdvisorChatModel_MissingFields(t *testing.T) {
	tests := []struct {
		name string
		cfg  AdvisorConfig
	}{
		{"no api key", AdvisorConfig{Enabled: true, BaseURL: "x", Model: "y"}},
		{"no base url", AdvisorConfig{Enabled: true, APIKey: "sk-test", Model: "y"}},
		{"no model", AdvisorConfig{Enabled: true, APIKey: "sk-test", BaseURL: "x"}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := NewAdvisorChatModel(context.Background(), tc.cfg)
			if err == nil {
				t.Errorf("expected error for %s", tc.name)
			}
		})
	}
}