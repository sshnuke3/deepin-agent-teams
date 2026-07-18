// Package config 提供配置加载
//
// 支持两路加载（优先顺序）：
//  1. 环境变量（容器/CI 场景）
//  2. .env 文件（本地开发场景）—— 不覆盖已设置的 env
//
// .env 文件必须加入 .gitignore（项目里已经 ignore）
package config

import (
	"bufio"
	"fmt"
	"os"
	"strings"
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

// Load 从环境变量 + .env 文件加载配置
func Load() (*Config, error) {
	// .env 加载失败不致命（CI 环境可能没文件）—— 只 log
	_ = loadDotEnv(".env")

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
		return nil, fmt.Errorf("API key not set (AGNES_API_KEY / QWEN_API_KEY / OPENAI_API_KEY) — try creating a .env file")
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

// loadDotEnv 从 .env 文件加载变量（不覆盖已设置的 env）
//
// 支持格式：
//
//	KEY=value
//	KEY="quoted value"
//	# 注释行
//	空行
//
// 限制：不展开变量引用 ($VAR / ${VAR})，仅做字面赋值
func loadDotEnv(path string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		idx := strings.Index(line, "=")
		if idx <= 0 {
			continue
		}
		key := strings.TrimSpace(line[:idx])
		val := strings.TrimSpace(line[idx+1:])
		// 去掉可选的引号
		if len(val) >= 2 && (val[0] == '"' && val[len(val)-1] == '"' || val[0] == '\'' && val[len(val)-1] == '\'') {
			val = val[1 : len(val)-1]
		}
		// 不覆盖已设置的 env（保持 export 优先级）
		if os.Getenv(key) == "" {
			os.Setenv(key, val)
		}
	}
	return scanner.Err()
}
