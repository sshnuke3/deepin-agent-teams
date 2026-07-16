package agents

import (
	"context"
	"fmt"

	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/internal/model"
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
	Directory string   `json:"directory"`
	Mode      string   `json:"mode"` // "preview" | "apply"
	Categories []string `json:"categories"` // 要整理的分类，空 = 全部
	Rationale  string   `json:"rationale"`  // LLM 解释为什么这样规划
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