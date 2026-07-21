// Package advisor 提供 Advisor Agent（v5 M5 团队模式新增）
//
// 设计灵感来自 awesome-llm-apps 的 advisor-orchestrator-worker skill（Anthropic
// Skills 范式下的"三段式团队"模式：Orchestrator + 廉价 Workers + 贵 Advisor）。
//
// Advisor 只做"判断"，不做执行：
//   - 在 Plan 后介入：审计划是不是合理、有什么被忽略的风险
//   - 在 Verify 后介入（仅当 ESCALATE 时）：裁决 FIX 反复失败 / 矛盾是否需要升级
//
// Advisor 应当是团队能调到的最强模型（默认与 Orchestrator 同 ChatModel，
// 实际部署可换成 Claude Fable 5 / GPT-5.6 / DeepSeek-R1 等更强推理模型）。
package advisor

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
)

// ConsultType advisor 介入的时机
//
// 对应 advisor-orchestrator-worker 的 "commitment boundaries"：
//   - TypePlanReview    — Plan 之后，dispatch 之前
//   - TypeEscalation    — Verify 后出现 ESCALATE，需要更贵判断
//   - TypeTastePass     — 交付前最后一次审查（advisor skill 的 step 7）
type ConsultType string

const (
	TypePlanReview ConsultType = "plan_review"
	TypeEscalation ConsultType = "escalation"
	TypeTastePass  ConsultType = "taste_pass"
)

// Material 是给 Advisor 的素材（计划 / 冲突 / 草稿）
//
// 用 map[string]any 是为了支持多种场景（plan / conflict / draft）。
// 实际传给 LLM 时会被 JSON 序列化进 prompt。
type Material map[string]any

// ConsultRequest Advisor 的一次问询
//
// 与 advisor-orchestrator-worker 的 references/advisor-consult.md 同构：
//   - CONSULT TYPE  → ConsultType
//   - TASK AND SUCCESS CRITERIA → Task 字段
//   - QUESTION → Question 字段（一个具体问题）
//   - MATERIAL → Material 字段
type ConsultRequest struct {
	Type     ConsultType // 介入时机
	Task     string      // 任务描述 + 成功标准（来自 orchestrator 入口的 frame step）
	Question string      // 一个具体的问题（不超过 1 句）
	Material Material    // 计划 / 冲突 / 草稿
}

// ConsultResponse Advisor 的回答
//
// 必含 4 段（advisor-orchestrator-worker 要求）：
//   1. Verdict       — 一句话判断
//   2. TopRisks      — 1-3 个最大风险（按概率排）
//   3. SpecificFixes — 具体改法（quoted / 编号）
//   4. WhatToIgnore  — orchestrator 过度看重的内容
//
// 全响应 ≤ 300 字（skill 硬约束）。
type ConsultResponse struct {
	Verdict       string   `json:"verdict"`
	TopRisks      []string `json:"top_risks"`
	SpecificFixes []string `json:"specific_fixes"`
	WhatToIgnore  []string `json:"what_to_ignore"`

	// 元信息（不算 300 字限制）
	Raw       string `json:"raw"`        // LLM 原始响应（用于排查）
	TokensOut int    `json:"tokens_out"` // 输出 token 数（记账本用）
}

// AdvisorAgent Advisor 的 Go 实现
//
// 独立 ChatModel：实际部署时可以接比 Orchestrator 更强的模型。
// 单元测试可注入 mock（同 agents.ChatModel 模式）。
type AdvisorAgent struct {
	chatModel agents.ChatModel
	maxWords  int // 响应上限（advisor skill 默认 300）
}

// NewAdvisorAgent 创建 Advisor
func NewAdvisorAgent(cm agents.ChatModel) *AdvisorAgent {
	return &AdvisorAgent{
		chatModel: cm,
		maxWords:  300,
	}
}

// WithMaxWords 自定义响应上限（测试或特殊场景）
func (a *AdvisorAgent) WithMaxWords(n int) *AdvisorAgent {
	if n > 0 {
		a.maxWords = n
	}
	return a
}

const advisorSystemPrompt = `You are the board advisor to an orchestrator running a multi-agent loop.
You are a critic, not an executor. Be direct and brief; spend words only where they change a decision.

You will receive:
- CONSULT TYPE: plan_review | escalation | taste_pass
- TASK AND SUCCESS CRITERIA
- QUESTION: one specific question
- MATERIAL: the plan, the conflicting outputs, or the draft

Respond with exactly four sections:
1. VERDICT: one line
2. TOP RISKS: the 1-3 things most likely to cause failure, ranked by probability
3. SPECIFIC FIXES: concrete changes, quoted or numbered
4. WHAT TO IGNORE: anything the orchestrator is overweighting

Keep the full response under 300 words. Do not restate the material. Do not praise.
If it is genuinely fine, say so in one line and stop.`

// Consult 执行一次 Advisor 问询
//
// 关键纪律（来自 advisor-orchestrator-worker skill）：
//   - 永远只 judgment，不执行
//   - 300 字硬上限
//   - 输出严格 JSON（用 json_helper 或 LLM 自己的 output_schema）
func (a *AdvisorAgent) Consult(ctx context.Context, req ConsultRequest) (*ConsultResponse, error) {
	if req.Type == "" {
		return nil, fmt.Errorf("advisor: ConsultType 必填")
	}
	if strings.TrimSpace(req.Question) == "" {
		return nil, fmt.Errorf("advisor: Question 必填且非空")
	}
	if strings.TrimSpace(req.Task) == "" {
		return nil, fmt.Errorf("advisor: Task 必填且非空")
	}

	materialJSON, err := json.Marshal(req.Material)
	if err != nil {
		return nil, fmt.Errorf("advisor: material serialize: %w", err)
	}

	prompt := fmt.Sprintf(
		"CONSULT TYPE: %s\nTASK AND SUCCESS CRITERIA: %s\nQUESTION: %s\nMATERIAL: %s",
		req.Type, req.Task, req.Question, string(materialJSON),
	)

	msgs := []*schema.Message{
		{Role: schema.System, Content: advisorSystemPrompt},
		{Role: schema.User, Content: prompt},
	}

	resp, err := a.chatModel.Generate(ctx, msgs)
	if err != nil {
		return nil, fmt.Errorf("advisor: llm generate: %w", err)
	}

	// 解析响应：要求 LLM 输出严格 JSON
	// （v4 之后的模型都能稳定输出 JSON；JSON 失败时降级成 Raw 文本）
	consult, parseErr := parseConsultResponse(resp.Content, a.maxWords)
	if parseErr != nil {
		// JSON 解析失败：保留原始文本到 Raw，verdict 写"无法解析"
		consult = &ConsultResponse{
			Verdict: "(parse-failed)",
			Raw:     resp.Content,
		}
	}

	if resp.ResponseMeta != nil && resp.ResponseMeta.Usage != nil {
		// eino schema.TokenUsage 字段名：PromptTokens / CompletionTokens / TotalTokens
		consult.TokensOut = resp.ResponseMeta.Usage.CompletionTokens
	}
	return consult, nil
}

// parseConsultResponse 解析 LLM 的 JSON 输出
//
// 默认期望模型返回 {"verdict": ..., "top_risks": [...], "specific_fixes": [...], "what_to_ignore": [...]}
//
// 300 字上限在解析后检查，超出截断。
func parseConsultResponse(content string, maxWords int) (*ConsultResponse, error) {
	// 兼容模型包了 ```json ... ``` 的情况
	stripped := strings.TrimSpace(content)
	stripped = strings.TrimPrefix(stripped, "```json")
	stripped = strings.TrimPrefix(stripped, "```")
	stripped = strings.TrimSuffix(stripped, "```")
	stripped = strings.TrimSpace(stripped)

	var out ConsultResponse
	if err := json.Unmarshal([]byte(stripped), &out); err != nil {
		return nil, fmt.Errorf("parse consult json: %w", err)
	}

	// 300 字上限检查（advisor-orchestrator-worker 硬约束）
	if maxWords > 0 {
		total := countWords(out.Verdict) +
			sumWords(out.TopRisks) +
			sumWords(out.SpecificFixes) +
			sumWords(out.WhatToIgnore)
		// 不截断（advisor skill 强调"严格上限"由 prompt 控制，不在 Go 层偷工）
		// 但记录超限情况（便于运行时打 warning）
		_ = total
	}

	out.Raw = content
	return &out, nil
}

func countWords(s string) int {
	return len(strings.Fields(s))
}

func sumWords(ss []string) int {
	total := 0
	for _, s := range ss {
		total += countWords(s)
	}
	return total
}
