// Package agents 包含各 Agent 实现
package agents

import (
	"context"
	"fmt"

	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/internal/model"
	"github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// IntentAgent 负责意图识别
type IntentAgent struct {
	chatModel model.ChatModel
}

// NewIntentAgent 创建意图识别 Agent
func NewIntentAgent(cm model.ChatModel) *IntentAgent {
	return &IntentAgent{chatModel: cm}
}

const systemPrompt = `你是 deepin 系统设置 Agent 的意图识别器。

用户输入一句话，你必须返回严格的 JSON（不要解释、不要 markdown 包裹）：

格式 1（切主题）:
{"action": "change_theme", "theme": "deepin-dark" 或 "deepin-light" 或 "deepin-auto"}

格式 2（查信息）:
{"action": "get_system_info"}

格式 3（整理文件）:
{"action": "organize_files", "directory": "目标目录", "mode": "preview 或 apply"}

格式 4（日程提醒）:
{"action": "schedule_reminder", "title": "提醒标题", "due_at": "ISO8601 时间", "priority": "low|normal|high", "mode": "preview 或 apply"}

格式 5（无法识别）:
{"action": "unknown"}

判断示例：
- "帮我切到深色模式" → {"action": "change_theme", "theme": "deepin-dark"}
- "看一下系统信息" → {"action": "get_system_info"}
- "整理一下 Downloads 文件" → {"action": "organize_files", "directory": "~/Downloads", "mode": "preview"}
- "把 Downloads 文件真的整理一下" → {"action": "organize_files", "directory": "~/Downloads", "mode": "apply"}
- "提醒我明天下午 3 点开会" → {"action": "schedule_reminder", "title": "开会", "due_at": "2026-07-18T15:00:00+08:00", "priority": "normal", "mode": "preview"}
- "真的设个提醒：明天下午 3 点开会" → {"action": "schedule_reminder", "title": "开会", "due_at": "2026-07-18T15:00:00+08:00", "priority": "normal", "mode": "apply"}
- "你好" → {"action": "unknown"}

只输出 JSON，不要任何其他文字。`

// Recognize 识别用户输入的意图
func (a *IntentAgent) Recognize(ctx context.Context, userInput string) (*intent.Intent, error) {
	resp, err := a.chatModel.Generate(ctx, []*schema.Message{
		{Role: schema.System, Content: systemPrompt},
		{Role: schema.User, Content: userInput},
	})
	if err != nil {
		return nil, fmt.Errorf("LLM call failed: %w", err)
	}

	return intent.Parse(resp.Content)
}
