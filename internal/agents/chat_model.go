package agents

import (
	"context"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/schema"
)

// ChatModel 是 agent 所需的最小 LLM 抽象
//
// 定义在 agents 包内部，*openai.ChatModel（model.ChatModel）自动满足这个 interface，
// 所以外部调用者（orchestrator）传 model.ChatModel 进来不需要任何改动。
//
// 拆出这个 interface 的目的是让单元测试可以注入 mock LLM。
type ChatModel interface {
	Generate(ctx context.Context, in []*schema.Message, opts ...model.Option) (*schema.Message, error)
}