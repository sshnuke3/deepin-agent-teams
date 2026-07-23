// Package model — advisor 子包
//
// Advisor ChatModel 独立 factory（v5 M5+）
//
// 设计目标：Advisor 用比 Orchestrator 更"判断力强"的模型（advisor-orchestrator-worker
// skill 的 commitment boundaries 哲学：贵模型只在 plan_review / escalation /
// taste_pass 三个 commitment 边界介入，不参与日常执行）。
//
// 默认接 mengyu.ltd 中转的 KAT-Coder-Exp-72B-1010（代码推理强、reasoning 充分，
// 适合做"判断代码计划是否合理 + 失败是否需升级"这种审查型任务）。
//
// 也可以通过 env 切回与 Orchestrator 同模型，或换别的中转站。
package model

import (
	"context"
	"fmt"
	"os"
)

// AdvisorConfig Advisor 的 LLM 配置
//
// 与主 Config 平行,独立 env 命名空间,避免污染主配置。
type AdvisorConfig struct {
	Provider string // "mengyu" / "openai" / "deepseek" / 与主 Config 共用
	APIKey   string
	BaseURL  string
	Model    string

	// Enabled 默认 true;--no-advisor flag 会强制 false(降级模式)
	Enabled bool
}

// AdvisorConfigFromEnv 从 env 加载 Advisor 配置(优先 ADVISOR_* 字段)
//
// 回退:若 ADVISOR_* 全空,返回 Enabled=false(降级到 no-advisor 模式,等价于老行为)
//
// 默认值:走 mengyu.ltd 中转的 KAT-Coder-Exp-72B-1010
func AdvisorConfigFromEnv() AdvisorConfig {
	provider := getEnvOr("ADVISOR_PROVIDER", "mengyu")
	apiKey := os.Getenv("ADVISOR_API_KEY")
	baseURL := getEnvOr("ADVISOR_BASE_URL", "https://ai-api.mengyu.ltd/v1")
	modelName := getEnvOr("ADVISOR_MODEL", "KAT-Coder-Exp-72B-1010")

	// 若 apiKey 为空且 baseURL/model 都是默认值,跳过 advisor(避免浪费启动时间)
	enabled := apiKey != ""
	return AdvisorConfig{
		Provider: provider,
		APIKey:   apiKey,
		BaseURL:  baseURL,
		Model:    modelName,
		Enabled:  enabled,
	}
}

func getEnvOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// NewAdvisorChatModel 根据 AdvisorConfig 构造独立的 ChatModel
//
// 关键纪律:AdvisorChatModel 与 Orchestrator ChatModel 必须分离
//
//   - Orchestrator:走 LLM_PROVIDER / AGNES_API_KEY 等主配置
//   - Advisor:走 ADVISOR_* 配置(独立命名空间,允许换不同的中转站/账号)
//
// 返回 (ChatModel, error):
//   - 成功:独立 ChatModel 实例,Advisor 可调用
//   - 失败:error 非 nil;调用方应降级到 nil AdvisorAgent(RunComplex 自动跳过 consult)
func NewAdvisorChatModel(ctx context.Context, cfg AdvisorConfig) (ChatModel, error) {
	if !cfg.Enabled {
		return nil, fmt.Errorf("advisor: disabled (no ADVISOR_API_KEY)")
	}
	if cfg.APIKey == "" {
		return nil, fmt.Errorf("advisor: APIKey empty")
	}
	if cfg.BaseURL == "" {
		return nil, fmt.Errorf("advisor: BaseURL empty")
	}
	if cfg.Model == "" {
		return nil, fmt.Errorf("advisor: Model empty")
	}

	// Advisor 专属 max_tokens:KAT-Coder 72B 是代码推理模型,reasoning 占比高
	// Plan review 场景下 1000 token 足够(verdict+top_risks+specific_fixes ≤ 300 字限制)
	mt := 1000

	chatModel, err := newOpenAIChatModel(ctx, cfg.APIKey, cfg.Model, cfg.BaseURL, mt)
	if err != nil {
		return nil, fmt.Errorf("advisor: ChatModel init: %w", err)
	}
	return chatModel, nil
}