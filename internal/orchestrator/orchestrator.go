// Package orchestrator 提供 Eino 编排逻辑
//
// 核心思想：v3 的 Python 状态机 → v4 的 Eino Lambda Chain
// 状态流转（识别 → 工具 → 格式化）压在一个 Lambda 里，类型安全
package orchestrator

import (
	"context"
	"fmt"

	"github.com/cloudwego/eino/compose"

	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
	intentpkg "github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// Orchestrator 编排器
type Orchestrator struct {
	intentAgent *agents.IntentAgent
}

// New 创建编排器
func New(intentAgent *agents.IntentAgent) *Orchestrator {
	return &Orchestrator{intentAgent: intentAgent}
}

// Run 处理用户输入，返回响应
func (o *Orchestrator) Run(ctx context.Context, userInput string) (string, error) {
	chain := compose.NewChain[string, string]().
		AppendLambda(compose.InvokableLambda(func(ctx context.Context, input string) (string, error) {
			// Step 1: 意图识别
			it, err := o.intentAgent.Recognize(ctx, input)
			if err != nil {
				return "", fmt.Errorf("recognize intent: %w", err)
			}

			// Step 2: 根据意图调工具
			var result *tools.Result
			switch it.Action {
			case intentpkg.ActionChangeTheme:
				theme := it.Theme
				if theme == "" {
					theme = intentpkg.ThemeAuto
				}
				result = tools.ChangeTheme(ctx, theme)
			case intentpkg.ActionGetSystemInfo:
				result = tools.GetSystemInfo(ctx)
			default:
				return "🤔 我没理解您的意思，请尝试：'切到深色模式' 或 '查看系统信息'", nil
			}

			// Step 3: 格式化输出
			return fmt.Sprintf("✅ 操作完成：%s", result.Message), nil
		}))

	runnable, err := chain.Compile(ctx)
	if err != nil {
		return "", fmt.Errorf("compile chain: %w", err)
	}

	return runnable.Invoke(ctx, userInput)
}
