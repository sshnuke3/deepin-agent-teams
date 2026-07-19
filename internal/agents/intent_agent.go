// Package agents 包含各 Agent 实现
package agents

import (
	"context"
	"fmt"

	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// IntentAgent 负责意图识别
type IntentAgent struct {
	chatModel ChatModel
}

// NewIntentAgent 创建意图识别 Agent
func NewIntentAgent(cm ChatModel) *IntentAgent {
	return &IntentAgent{chatModel: cm}
}

const systemPrompt = `你是 deepin 系统设置 Agent 的意图识别器。

用户输入一句话，你必须返回严格的 JSON（不要解释、不要 markdown 包裹）：

格式 1（切主题，保留兼容旧用法）:
{"action": "change_theme", "theme": "deepin-dark" 或 "deepin-light" 或 "deepin-auto"}

格式 2（查信息）:
{"action": "get_system_info"}

格式 3（整理文件）:
{"action": "organize_files", "directory": "目标目录", "mode": "preview 或 apply"}

格式 4（日程提醒）:
{"action": "schedule_reminder", "title": "提醒标题", "due_at": "ISO8601 时间", "priority": "low|normal|high", "mode": "preview 或 apply"}

格式 5（邮件草稿）:
{"action": "draft_email", "recipient": "收件人邮箱（可空）", "subject": "邮件主题（可空）", "purpose": "邮件目的/要点", "mode": "preview 或 apply"}

格式 6（系统设置，v4 M2 新增）:
{"action": "apply_settings", "settings_category": "theme|volume|brightness|network", "settings_value": "对应值（deepin-dark/deepin-light/0-100 数字/on/off）", "mode": "preview 或 apply"}

格式 7（无法识别）:
{"action": "unknown"}

判断示例：
- "帮我切到深色模式" → {"action": "apply_settings", "settings_category": "theme", "settings_value": "deepin-dark", "mode": "preview"}
- "看一下系统信息" → {"action": "get_system_info"}
- "整理一下 Downloads 文件" → {"action": "organize_files", "directory": "~/Downloads", "mode": "preview"}
- "把 Downloads 文件真的整理一下" → {"action": "organize_files", "directory": "~/Downloads", "mode": "apply"}
- "提醒我明天下午 3 点开会" → {"action": "schedule_reminder", "title": "开会", "due_at": "2026-07-18T15:00:00+08:00", "priority": "normal", "mode": "preview"}
- "真的设个提醒：明天下午 3 点开会" → {"action": "schedule_reminder", "title": "开会", "due_at": "2026-07-18T15:00:00+08:00", "priority": "normal", "mode": "apply"}
- "帮 Alice 起草一封项目进度邮件" → {"action": "draft_email", "recipient": "alice@example.com", "subject": "项目进度", "purpose": "同步本周项目进度", "mode": "preview"}
- "写封邮件给 bob 说会议改时间" → {"action": "draft_email", "recipient": "bob@example.com", "subject": "会议改期通知", "purpose": "通知 Bob 会议改期", "mode": "preview"}
- "音量调到 80" → {"action": "apply_settings", "settings_category": "volume", "settings_value": "80", "mode": "preview"}
- "关掉 WiFi" → {"action": "apply_settings", "settings_category": "network", "settings_value": "off", "mode": "preview"}
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
