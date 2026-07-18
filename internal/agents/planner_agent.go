package agents

import (
	"context"
	"fmt"
	"time"

	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/internal/model"
	"github.com/sshnuke3/deepin-agent-teams/internal/tools"
	"github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// PlannerAgent 任务规划器
//
// v4 M2 新增：v3 状态机的"Planner"角色
// 职责：拿到 Intent 后，结合用户上下文，生成执行计划
type PlannerAgent struct {
	chatModel model.ChatModel
}

// NewPlannerAgent 创建 Planner
func NewPlannerAgent(cm model.ChatModel) *PlannerAgent {
	return &PlannerAgent{chatModel: cm}
}

// OrganizePlan 文件整理的执行计划
type OrganizePlan struct {
	Directory  string   `json:"directory"`
	Mode       string   `json:"mode"`       // "preview" | "apply"
	Categories []string `json:"categories"` // 要整理的分类，空 = 全部
	Rationale  string   `json:"rationale"`  // LLM 解释为什么这样规划
}

// ReminderPlan 日程提醒的执行计划（v4 M2 新增）
//
// Planner 负责把 Intent 里的"明天下午 3 点"翻译成 ISO8601 + 设定 priority + mode
type ReminderPlan struct {
	Title     string `json:"title"`
	DueAt     string `json:"due_at"`    // 必须是 ISO8601 或可解析格式
	Priority  string `json:"priority"`  // low | normal | high
	Mode      string `json:"mode"`      // preview | apply
	Rationale string `json:"rationale"` // LLM 解释
}

// EmailPlan 邮件草稿的执行计划（v4 M2 新增）
//
// Planner 负责根据 Purpose 撰写邮件正文 + 选择 tone + 决定 mode
type EmailPlan struct {
	Recipient string `json:"recipient"` // 收件人邮箱（用户没填就空字符串）
	Subject   string `json:"subject"`   // 主题
	Purpose   string `json:"purpose"`   // 邮件目的（用户原始描述）
	Body      string `json:"body"`      // Planner 生成的正文
	Tone      string `json:"tone"`      // formal | casual | urgent
	Mode      string `json:"mode"`      // preview | apply
	Rationale string `json:"rationale"` // LLM 解释
}

// SettingsPlan 系统设置的执行计划（v4 M2 新增）
//
// Planner 负责根据用户口语化描述提取 category + value
type SettingsPlan struct {
	Changes   []tools.SettingChange `json:"changes"`   // Planner 生成的变更列表
	Mode      string                `json:"mode"`      // preview | apply
	Rationale string                `json:"rationale"` // LLM 解释
}

const plannerSystemPrompt = `你是 deepin-agent 的 Planner Agent。

用户给出了文件整理意图，请你判断执行参数，只输出 JSON（不要 markdown）：

格式：
{
  "directory": "目标目录（默认 ~/Downloads）",
  "mode": "preview 或 apply",
  "categories": ["分类列表，空数组表示全部"],
  "rationale": "你的判断理由（一句话）"
}

判断规则：
1. 默认 mode="preview"（只看不摸，安全第一）
2. 只有用户明确说"执行""真的整理""动手"才用 mode="apply"
3. 如果用户指定目录就用指定的，否则默认 ~/Downloads
4. rationale 用中文，简短说明

只输出 JSON。`

// PlanOrganize 为文件整理生成执行计划
func (p *PlannerAgent) PlanOrganize(ctx context.Context, userInput string, it *intent.Intent) (*OrganizePlan, error) {
	userMsg := fmt.Sprintf("用户输入: %s\n识别意图: directory=%s, mode=%s",
		userInput, it.Directory, it.Mode)

	resp, err := p.chatModel.Generate(ctx, []*schema.Message{
		{Role: schema.System, Content: plannerSystemPrompt},
		{Role: schema.User, Content: userMsg},
	})
	if err != nil {
		return nil, fmt.Errorf("planner LLM call failed: %w", err)
	}

	plan := &OrganizePlan{
		Directory: it.Directory,
		Mode:      it.Mode,
	}
	// 简单解析 LLM 返回的 JSON（实际应复用 pkg/intent.Parse 的容错逻辑）
	if err := jsonUnmarshal(resp.Content, plan); err != nil {
		// 解析失败 → 用 Intent 的默认值兜底
		return plan, nil
	}
	// Intent 没指定 directory 时，用 Planner 的判断
	if plan.Directory == "" {
		plan.Directory = it.Directory
	}
	if plan.Mode == "" {
		plan.Mode = it.Mode
	}
	if plan.Mode == "" {
		plan.Mode = "preview"
	}
	if plan.Directory == "" {
		plan.Directory = "~/Downloads"
	}
	return plan, nil
}

const reminderPlannerPrompt = `你是 deepin-agent 的 Planner Agent。

用户给出了日程提醒意图，请你判断执行参数，只输出 JSON（不要 markdown）：

格式：
{
  "title": "提醒标题（必填）",
  "due_at": "ISO8601 时间（必填，例如 2026-07-18T15:00:00+08:00）",
  "priority": "low | normal | high（默认 normal）",
  "mode": "preview 或 apply（默认 preview）",
  "rationale": "你的判断理由（一句话）"
}

判断规则：
1. 当前时间以 %s 为准
2. "明天上午 9 点" → 明天 09:00:00（本地时区）
3. "下周三下午 3 点" → 下个周三 15:00:00
4. 默认 mode="preview"（只看不存，安全第一）
5. 只有用户明确说"存起来""真的设""提醒我"才用 mode="apply"
6. priority: 用户说"重要""紧急" → high；说"有空再看" → low；其他 normal
7. rationale 用中文，简短说明

只输出 JSON。`

// PlanReminder 为日程提醒生成执行计划
func (p *PlannerAgent) PlanReminder(ctx context.Context, userInput string, it *intent.Intent) (*ReminderPlan, error) {
	now := time.Now().Format(time.RFC3339)
	prompt := fmt.Sprintf(reminderPlannerPrompt, now)

	userMsg := fmt.Sprintf("用户输入: %s\n识别意图: title=%s, due_at=%s, priority=%s, mode=%s",
		userInput, it.Title, it.DueAt, it.Priority, it.Mode)

	resp, err := p.chatModel.Generate(ctx, []*schema.Message{
		{Role: schema.System, Content: prompt},
		{Role: schema.User, Content: userMsg},
	})
	if err != nil {
		return nil, fmt.Errorf("planner LLM call failed: %w", err)
	}

	plan := &ReminderPlan{
		Title:    it.Title,
		DueAt:    it.DueAt,
		Priority: it.Priority,
		Mode:     it.Mode,
	}
	if err := jsonUnmarshal(resp.Content, plan); err != nil {
		// 解析失败 → 用 Intent 默认值兜底
		return plan, nil
	}
	// 兜底逻辑
	if plan.Title == "" {
		plan.Title = it.Title
	}
	if plan.DueAt == "" {
		plan.DueAt = it.DueAt
	}
	if plan.Priority == "" {
		plan.Priority = it.Priority
		if plan.Priority == "" {
			plan.Priority = "normal"
		}
	}
	if plan.Mode == "" {
		plan.Mode = it.Mode
		if plan.Mode == "" {
			plan.Mode = "preview"
		}
	}
	return plan, nil
}

const emailPlannerPrompt = `你是 deepin-agent 的 Planner Agent，负责根据用户意图撰写邮件草稿。

用户给出了邮件草稿意图，请你判断执行参数 + 撰写正文，只输出 JSON（不要 markdown）：

格式：
{
  "recipient": "收件人邮箱（用户没填就空字符串）",
  "subject": "邮件主题",
  "purpose": "邮件目的（保留用户原始描述）",
  "body": "你撰写的邮件正文（中文为主，正式得体）",
  "tone": "formal | casual | urgent",
  "mode": "preview 或 apply（默认 preview）",
  "rationale": "你的判断理由（一句话）"
}

判断规则：
1. 默认 mode="preview"（只看不存，安全第一）
2. 只有用户明确说"保存""存为草稿""写下来"才用 mode="apply"
3. tone: 默认 formal（商务/工作场景）；用户说"随便""轻松点" → casual；说"紧急""马上" → urgent
4. body 必须有称呼 + 正文 + 落款（称呼"Hi <名>,"或"您好,"；落款"Best,\n龙虾"）
5. 如果 subject 为空，根据 purpose 提炼一个简明主题
6. rationale 用中文，简短说明

只输出 JSON。`

// PlanEmail 为邮件草稿生成执行计划
func (p *PlannerAgent) PlanEmail(ctx context.Context, userInput string, it *intent.Intent) (*EmailPlan, error) {
	userMsg := fmt.Sprintf("用户输入: %s\n识别意图: recipient=%s, subject=%s, purpose=%s, mode=%s",
		userInput, it.Recipient, it.Subject, it.Purpose, it.Mode)

	resp, err := p.chatModel.Generate(ctx, []*schema.Message{
		{Role: schema.System, Content: emailPlannerPrompt},
		{Role: schema.User, Content: userMsg},
	})
	if err != nil {
		return nil, fmt.Errorf("planner LLM call failed: %w", err)
	}

	plan := &EmailPlan{
		Recipient: it.Recipient,
		Subject:   it.Subject,
		Purpose:   it.Purpose,
		Tone:      "formal",
		Mode:      it.Mode,
	}
	if err := jsonUnmarshal(resp.Content, plan); err != nil {
		// 解析失败 → 用 Intent 默认值兜底（body 留空让用户在 preview 里看到）
		return plan, nil
	}
	// 兜底逻辑
	if plan.Recipient == "" {
		plan.Recipient = it.Recipient
	}
	if plan.Subject == "" {
		plan.Subject = it.Subject
	}
	if plan.Purpose == "" {
		plan.Purpose = it.Purpose
	}
	if plan.Tone == "" {
		plan.Tone = "formal"
	}
	if plan.Mode == "" {
		plan.Mode = it.Mode
		if plan.Mode == "" {
			plan.Mode = "preview"
		}
	}
	return plan, nil
}

const settingsPlannerPrompt = `你是 deepin-agent 的 Planner Agent，负责根据用户口语化描述生成系统设置变更。

用户说了设置需求，请你提取 category + value，输出 JSON：

格式：
{
  "changes": [
    {"category": "theme|volume|brightness|network", "new_value": "对应值"}
  ],
  "mode": "preview 或 apply（默认 preview）",
  "rationale": "你的判断理由（一句话）"
}

判断规则：
1. 默认 mode="preview"（只看不改，安全第一）
2. 用户明确说"设置""改成""调""真的改" → mode="apply"
3. category 映射：
   - 主题/色系 → "theme"，new_value: "deepin-dark"（暗/黑/深）或 "deepin-light"（浅/亮/白）或 "deepin-auto"（自动/跟随）
   - 音量/声音大小 → "volume"，new_value: 0-100 的数字
   - 亮度/背光 → "brightness"，new_value: 0-100 的数字
   - 网络/WiFi → "network"，new_value: "on"（开）或 "off"（关）
4. 数字必须字符串化（"50" 不是 50）
5. rationale 用中文，简短说明

只输出 JSON。`

// PlanSettings 为系统设置生成执行计划
func (p *PlannerAgent) PlanSettings(ctx context.Context, userInput string, it *intent.Intent) (*SettingsPlan, error) {
	userMsg := fmt.Sprintf("用户输入: %s\n识别意图: category=%s, value=%s, mode=%s",
		userInput, it.SettingsCategory, it.SettingsValue, it.Mode)

	resp, err := p.chatModel.Generate(ctx, []*schema.Message{
		{Role: schema.System, Content: settingsPlannerPrompt},
		{Role: schema.User, Content: userMsg},
	})
	if err != nil {
		return nil, fmt.Errorf("planner LLM call failed: %w", err)
	}

	plan := &SettingsPlan{
		Mode: it.Mode,
	}
	if it.Mode == "" {
		plan.Mode = "preview"
	}

	// 解析 LLM 返回
	if err := jsonUnmarshal(resp.Content, plan); err != nil {
		// 解析失败 → 用 Intent 默认值兜底（生成单个 change）
		plan.Changes = []tools.SettingChange{{
			Category: it.SettingsCategory,
			NewValue: it.SettingsValue,
		}}
		return plan, nil
	}

	// 兜底：如果 Planner 没生成 changes，用 Intent 的字段造一个
	if len(plan.Changes) == 0 {
		plan.Changes = []tools.SettingChange{{
			Category: it.SettingsCategory,
			NewValue: it.SettingsValue,
		}}
	}
	return plan, nil
}
