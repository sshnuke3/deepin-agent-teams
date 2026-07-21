package advisor

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
)

// fakeChatModel 测试用 mock：返回预设的 JSON / 错误
type fakeChatModel struct {
	resp     string
	err      error
	gotMsgs  []*schema.Message
	callCnt  int
}

func (f *fakeChatModel) Generate(ctx context.Context, in []*schema.Message, opts ...model.Option) (*schema.Message, error) {
	f.callCnt++
	f.gotMsgs = in
	if f.err != nil {
		return nil, f.err
	}
	return &schema.Message{
		Role:    schema.Assistant,
		Content: f.resp,
		ResponseMeta: &schema.ResponseMeta{
			Usage: &schema.TokenUsage{
				PromptTokens:     10,
				CompletionTokens: 42,
				TotalTokens:      52,
			},
		},
	}, nil
}

// 编译期断言 fakeChatModel 满足 agents.ChatModel
var _ agents.ChatModel = (*fakeChatModel)(nil)

func TestAdvisor_HappyPath_JSON(t *testing.T) {
	resp := `{
		"verdict": "Plan is reasonable but risks missing the auth wire-up",
		"top_risks": ["Workers may not share OAuth scope", "No retry on 429"],
		"specific_fixes": ["Add 'use refresh_token' to worker brief", "Cap QPS to 5 in executor"],
		"what_to_ignore": ["Cosmetic: field name 'rationale' vs 'reasoning'"]
	}`
	fm := &fakeChatModel{resp: resp}
	a := NewAdvisorAgent(fm)

	got, err := a.Consult(context.Background(), ConsultRequest{
		Type:     TypePlanReview,
		Task:     "Plan a multi-file refactor with 3 workers",
		Question: "Will these parallel dispatches race?",
		Material: Material{"workers": []string{"a", "b", "c"}},
	})
	if err != nil {
		t.Fatalf("Consult: %v", err)
	}

	if got.Verdict == "" || len(got.TopRisks) == 0 {
		t.Errorf("expected non-empty verdict & risks, got %+v", got)
	}
	if got.TokensOut != 42 {
		t.Errorf("expected CompletionTokens=42 in ledger, got %d", got.TokensOut)
	}
	if fm.callCnt != 1 {
		t.Errorf("expected 1 LLM call, got %d", fm.callCnt)
	}

	// 检查 prompt 把素材序列化成 JSON 传过去
	if len(fm.gotMsgs) < 2 {
		t.Fatal("expected system + user messages")
	}
	userContent := fm.gotMsgs[1].Content
	if !strings.Contains(userContent, "CONSULT TYPE: plan_review") {
		t.Error("prompt 缺 CONSULT TYPE 行")
	}
	if !strings.Contains(userContent, "QUESTION: Will these parallel dispatches race?") {
		t.Error("prompt 缺 QUESTION 行")
	}
	if !strings.Contains(userContent, "workers") {
		t.Error("prompt 缺 material 序列化的内容")
	}
}

func TestAdvisor_MarkdownJSONStripped(t *testing.T) {
	// 模型习惯包 ```json ... ```，解析层要能剥掉
	resp := "```json\n{\"verdict\": \"ok\", \"top_risks\": [\"x\"], \"specific_fixes\": [], \"what_to_ignore\": []}\n```"
	fm := &fakeChatModel{resp: resp}
	a := NewAdvisorAgent(fm)

	got, err := a.Consult(context.Background(), ConsultRequest{
		Type:     TypeEscalation,
		Task:     "verifier 第二次还失败",
		Question: "should we keep retrying?",
	})
	if err != nil {
		t.Fatalf("Consult: %v", err)
	}
	if got.Verdict != "ok" {
		t.Errorf("expected verdict=ok, got %q", got.Verdict)
	}
	if len(got.TopRisks) != 1 || got.TopRisks[0] != "x" {
		t.Errorf("top_risks parse fail: %+v", got.TopRisks)
	}
}

func TestAdvisor_BadJSON_FallsBackToRaw(t *testing.T) {
	// LLM 偶尔输出非 JSON：应保留 Raw，让上层能打 warning
	resp := "Sure! I think the plan looks fine. 👍"
	fm := &fakeChatModel{resp: resp}
	a := NewAdvisorAgent(fm)

	got, err := a.Consult(context.Background(), ConsultRequest{
		Type:     TypeTastePass,
		Task:     "taste pass",
		Question: "ready to ship?",
	})
	if err != nil {
		t.Fatalf("Consult should not error on bad JSON: %v", err)
	}
	if got.Verdict != "(parse-failed)" {
		t.Errorf("expected verdict=(parse-failed), got %q", got.Verdict)
	}
	if !strings.Contains(got.Raw, "👍") {
		t.Error("Raw 应保留原始文本")
	}
}

func TestAdvisor_LLMError(t *testing.T) {
	fm := &fakeChatModel{err: fmt.Errorf("network down")}
	a := NewAdvisorAgent(fm)

	_, err := a.Consult(context.Background(), ConsultRequest{
		Type:     TypePlanReview,
		Task:     "task",
		Question: "q",
	})
	if err == nil || !strings.Contains(err.Error(), "llm generate") {
		t.Errorf("expected LLM error wrapped, got %v", err)
	}
}

func TestAdvisor_InputValidation(t *testing.T) {
	a := NewAdvisorAgent(&fakeChatModel{})

	cases := []struct {
		name string
		req  ConsultRequest
	}{
		{"empty type", ConsultRequest{Task: "t", Question: "q"}},
		{"empty question", ConsultRequest{Type: TypePlanReview, Task: "t"}},
		{"empty task", ConsultRequest{Type: TypePlanReview, Question: "q"}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := a.Consult(context.Background(), c.req)
			if err == nil {
				t.Errorf("expected validation error for %s", c.name)
			}
		})
	}
}

func TestAdvisor_WithMaxWords_Returns(t *testing.T) {
	// 显式 WithMaxWords 是链式 API，要返回 self
	a := NewAdvisorAgent(&fakeChatModel{}).WithMaxWords(500)
	if a.maxWords != 500 {
		t.Errorf("expected 500, got %d", a.maxWords)
	}
	// 0 和负数：不变更（用默认值 300）
	a2 := NewAdvisorAgent(&fakeChatModel{}).WithMaxWords(0)
	if a2.maxWords != 300 {
		t.Errorf("expected default 300 when 0 passed, got %d", a2.maxWords)
	}
}

// 防呆测试：ConsultRequest / ConsultResponse 的 JSON 字段名不能改（prompt 用）
//
// 一旦改字段名，advisor-consult 协议就破，要重新跑 evals。
func TestAdvisor_JSONFieldNamesLocked(t *testing.T) {
	ref := ConsultResponse{
		Verdict:       "v",
		TopRisks:      []string{"r1"},
		SpecificFixes: []string{"f1"},
		WhatToIgnore:  []string{"i1"},
	}
	b, _ := json.Marshal(ref)

	for _, key := range []string{`"verdict":"v"`, `"top_risks":`, `"specific_fixes":`, `"what_to_ignore":`} {
		if !strings.Contains(string(b), key) {
			t.Errorf("协议字段名 %q 被改了——这条会破 prompt 兼容性", key)
		}
	}
}
