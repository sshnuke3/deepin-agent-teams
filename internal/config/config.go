// Package config 提供配置加载
package config

import (
	"fmt"
	"os"
)

// Config 全局配置
type Config struct {
	// LLM 配置
	LLMProvider string // agnes / qwen / openai / doubao / deepseek / ollama
	APIKey      string
	BaseURL     string
	Model       string

	// 日志
	LogLevel string
}

// 预设 provider 配置
//
// 优点：用户只设 LLM_PROVIDER 就能用，BaseURL/Model 自动填默认
var providerPresets = map[string]struct {
	BaseURL string
	Model   string
}{
	"agnes": {
		BaseURL: "https://apihub.agnes-ai.com/v1",
		Model:   "agnes-1.5-flash",
	},
	"qwen": {
		BaseURL: "https://ai.tdp.fan/api/v1",
		Model:   "qwen3.6-35b-a3b",
	},
}

// Load 从环境变量加载配置
func Load() (*Config, error) {
	provider := getEnv("LLM_PROVIDER", "agnes")

	// 解析预设
	baseURL := getEnv("LLM_BASE_URL", "")
	modelName := getEnv("LLM_MODEL", "")
	if preset, ok := providerPresets[provider]; ok {
		if baseURL == "" {
			baseURL = preset.BaseURL
		}
		if modelName == "" {
			modelName = preset.Model
		}
	}

	// API Key 按 provider 选
	apiKey := getEnv("AGNES_API_KEY", "")
	if apiKey == "" {
		apiKey = getEnv("QWEN_API_KEY", "")
	}
	if apiKey == "" {
		apiKey = getEnv("OPENAI_API_KEY", "")
	}

	cfg := &Config{
		LLMProvider: provider,
		APIKey:      apiKey,
		BaseURL:     baseURL,
		Model:       modelName,
		LogLevel:    getEnv("LOG_LEVEL", "info"),
	}

	if cfg.APIKey == "" {
		return nil, fmt.Errorf("API key not set (AGNES_API_KEY / QWEN_API_KEY / OPENAI_API_KEY)")
	}
	if cfg.BaseURL == "" || cfg.Model == "" {
		return nil, fmt.Errorf("provider %s: BASE_URL and MODEL required", provider)
	}

	return cfg, nil
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
