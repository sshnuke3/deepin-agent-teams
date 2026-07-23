// Package model 提供 ChatModel 抽象层
//
// 设计目标：把 LLM 调用封装成统一接口，业务层不关心底层用哪家模型
// 实现：当前用 eino-ext 的 openai adapter，可切 Agnes/OpenAI/豆包/DeepSeek/Ollama
package model

import (
	"context"
	"fmt"

	"github.com/cloudwego/eino-ext/components/model/openai"
)

// ChatModel 是统一的对话模型接口（type alias 转发 eino-ext openai 类型）
type ChatModel = *openai.ChatModel

// NewChatModel 根据配置创建 ChatModel
func NewChatModel(ctx context.Context, provider, apiKey, baseURL, modelName string) (ChatModel, error) {
	// 不同 provider 需要不同 max_tokens：
	//   - Agnes: 100 够用（普通 chat）
	//   - Qwen (reasoning): 需 2000+（思考会吃掉 ~500 token）
	maxTokens := 100
	if provider == "qwen" {
		maxTokens = 2000
	}
	// 通用校验:openai / agnes / qwen / doubao / deepseek / ollama / mengyu 都通过 adapter
	switch provider {
	case "agnes", "qwen", "openai", "doubao", "deepseek", "ollama", "mengyu":
		return newOpenAIChatModel(ctx, apiKey, modelName, baseURL, maxTokens)
	default:
		return nil, fmt.Errorf("unsupported LLM provider: %s", provider)
	}
}

// newOpenAIChatModel 内部 helper:所有 OpenAI 兼容服务都用同一个 adapter
//
// 包括:Agnes / Qwen (TDP) / OpenAI / 豆包 / DeepSeek / Ollama / mengyu.ltd 中转
func newOpenAIChatModel(ctx context.Context, apiKey, modelName, baseURL string, maxTokens int) (ChatModel, error) {
	mt := maxTokens
	return openai.NewChatModel(ctx, &openai.ChatModelConfig{
		APIKey:    apiKey,
		Model:     modelName,
		BaseURL:   baseURL,
		MaxTokens: &mt,
	})
}
