package orchestrator

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/schema"

	"github.com/sshnuke3/deepin-agent-teams/internal/advisor"
	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
	"github.com/sshnuke3/deepin-agent-teams/internal/ledger"
)

// fakeChatModelForComplex 同 agents.FakeChatModel，加一个 mode 切流向
type fakeChatModelForComplex struct {
	// 有时候 MockIntent 返回特定 action
	intentAction string

	// advisor 的返回（RunComplex 走 plan_review 或 escalation 时会调）
	advisorResp  string
	advisorErr   error
	advisorCalls int

	// intent 调用次数（去重：plan 时 1 次；不走 execute 时不会再调）
	intentCalls int
}

func (f *fakeChatModelForComplex) Generate(ctx context.Context, in []*schema.Message, opts ...model.Option) (*schema.Message, error) {
	// 简化：按 prompt 内容判定是哪个 agent
	prompt := ""
	for _, m := range in {
		prompt += m.Content + "\n"
	}

	if strings.Contains(prompt, "board advisor") || strings.Contains(prompt, "VERDICT:") {
		f.advisorCalls++
		if f.advisorErr != nil {
			return nil, f.advisorErr
		}
		return &schema.Message{
			Role: schema.Assistant,
			Content: f.advisorResp,
			ResponseMeta: &schema.ResponseMeta{
				Usage: &schema.TokenUsage{CompletionTokens: 10, PromptTokens: 5, TotalTokens: 15},
			},
		}, nil
	}

	// Intent/Planner 路径：返回 intent 识别 JSON
	f.intentCalls++
	action := f.intentAction
	if action == "" {
		action = "organize_files"
	}
	// 用默认 mode=preview，让 Execute 走 toolbar.Report 但不真改
	resp := `{"action":"` + action + `","directory":"~/Downloads","mode":"preview"}`
	return &schema.Message{
		Role:    schema.Assistant,
		Content: resp,
		ResponseMeta: &schema.ResponseMeta{
			Usage: &schema.TokenUsage{CompletionTokens: 3, PromptTokens: 2, TotalTokens: 5},
		},
	}, nil
}

func TestRunComplex_NoAdvisorHappyPath(t *testing.T) {
	// 最简：opts.AdvisorAgent == nil，整次走 Run 路径
	fm := &fakeChatModelForComplex{intentAction: "organize_files"}
	o := New(fm)

	var ldgBuf bytes.Buffer
	ldg := ledger.OpenWriter(&ldgBuf)
	out, err := o.RunComplex(context.Background(), "帮我整理 ~/Downloads 文件",
		RunComplexOpts{
			Ledger: ldg,
			SuccessCriteria: []string{"文件已分类", "MovePlan 非空"},
			Budget: 10,
		})
	if err != nil {
		t.Fatalf("RunComplex: %v", err)
	}
	if out == "" {
		t.Error("expected non-empty output")
	}
	if !strings.Contains(out, "文件整理") {
		t.Errorf("output 缺整理结果: %q", out)
	}

	// ledger 至少要有 RunStart / Frame / Plan / Dispatch / Verify / RunEnd
	events := parseEvents(t, &ldgBuf)
	wantTypes := map[string]bool{
		"run_start": false, "frame": false, "plan": false,
		"dispatch": false, "verify": false, "run_end": false,
	}
	for _, e := range events {
		if _, ok := wantTypes[string(e.Type)]; ok {
			wantTypes[string(e.Type)] = true
		}
	}
	for k, v := range wantTypes {
		if !v {
			t.Errorf("ledger 缺事件类型 %s", k)
		}
	}
	if fm.advisorCalls != 0 {
		t.Errorf("nil AdvisorAgent 时不应调 LLM，got %d calls", fm.advisorCalls)
	}
}

func TestRunComplex_PlanReviewCalled(t *testing.T) {
	// 给 AdvisorAgent，应该在 Plan 后看到一次 plan_review consult
	advResp := `{
		"verdict": "Plan looks fine — but add safety check on file count",
		"top_risks": ["可能分类不均", "有同名冲突"],
		"specific_fixes": ["增加同名 .bak 策略", "扫描前先获取 lock"],
		"what_to_ignore": ["UI 上的提示语调整"]
	}`
	fm := &fakeChatModelForComplex{
		intentAction: "organize_files",
		advisorResp:  advResp,
	}
	o := New(fm)
	adv := advisor.NewAdvisorAgent(fm)

	var ldgBuf bytes.Buffer
	ldg := ledger.OpenWriter(&ldgBuf)
	_, err := o.RunComplex(context.Background(), "整理 ~/Downloads",
		RunComplexOpts{
			Ledger:       ldg,
			AdvisorAgent: adv,
			SuccessCriteria: []string{"ok"},
		})
	if err != nil {
		t.Fatalf("RunComplex: %v", err)
	}

	if fm.advisorCalls != 1 {
		t.Errorf("expected 1 advisor call (plan_review), got %d", fm.advisorCalls)
	}

	events := parseEvents(t, &ldgBuf)
	var foundPR bool
	for _, e := range events {
		if e.Type == "plan_review" {
			foundPR = true
			if e.Verdict == "" {
				t.Error("plan_review 事件缺 verdict")
			}
			if e.Extra == nil {
				t.Error("plan_review 事件缺 extra (top_risks 等)")
			} else {
				if _, ok := e.Extra["top_risks"]; !ok {
					t.Error("plan_review 事件缺 top_risks 字段")
				}
			}
		}
	}
	if !foundPR {
		t.Errorf("ledger 缺 plan_review 事件")
	}
}

func TestRunComplex_AdvisorErrorIsNonFatal(t *testing.T) {
	// Advisor 报错不应该让主流程崩——advisor 可降级
	fm := &fakeChatModelForComplex{
		intentAction: "organize_files",
		advisorErr:   errors.New("network down"),
	}
	o := New(fm)
	adv := advisor.NewAdvisorAgent(fm)

	out, err := o.RunComplex(context.Background(), "整理 ~/Downloads",
		RunComplexOpts{
			Ledger:       ledger.OpenWriter(&bytes.Buffer{}),
			AdvisorAgent: adv,
		})
	if err != nil {
		t.Fatalf("Advisor error should NOT propagate, got: %v", err)
	}
	if out == "" {
		t.Error("expected non-empty output even when advisor fails")
	}
}

func TestRunComplex_RunIDProvided(t *testing.T) {
	fm := &fakeChatModelForComplex{intentAction: "organize_files"}
	o := New(fm)

	var ldgBuf bytes.Buffer
	_, err := o.RunComplex(context.Background(), "整理 ~/Downloads",
		RunComplexOpts{
			Ledger: ledger.OpenWriter(&ldgBuf),
			RunID:  "test-run-42",
		})
	if err != nil {
		t.Fatalf("RunComplex: %v", err)
	}
	events := parseEvents(t, &ldgBuf)
	for _, e := range events {
		if e.RunID != "test-run-42" {
			t.Errorf("RunID 错: %q", e.RunID)
		}
	}
}

func TestRunComplex_BudgetExhaustionAnnotated(t *testing.T) {
	// Budget=2, advisor 一次 plan_review 消耗 1, ESCALATE 触发另一次消耗 → 主流程跑完后 budget 0
	// 我们看看 budget=1 时是否 annotation 出现
	fm := &fakeChatModelForComplex{intentAction: "organize_files"}
	o := New(fm)
	adv := advisor.NewAdvisorAgent(fm)

	out, err := o.RunComplex(context.Background(), "整理 ~/Downloads",
		RunComplexOpts{
			Ledger:       ledger.OpenWriter(&bytes.Buffer{}),
			AdvisorAgent: adv,
			Budget:       1,
		})
	if err != nil {
		t.Fatalf("RunComplex: %v", err)
	}
	if !strings.Contains(out, "Budget exhausted") {
		t.Errorf("budget 耗尽应输出 annotation，got: %q", out)
	}
}

func TestRunComplex_NoBudget_BudgetAnnotationAppendedOnExhausted(t *testing.T) {
	// Budget=0 触发 default = 20，所以默认不会耗尽；这测主流程+
	fm := &fakeChatModelForComplex{intentAction: "organize_files"}
	o := New(fm)

	out, err := o.RunComplex(context.Background(), "整理 ~/Downloads",
		RunComplexOpts{Ledger: ledger.OpenWriter(&bytes.Buffer{})},
	)
	if err != nil {
		t.Fatalf("RunComplex: %v", err)
	}
	if strings.Contains(out, "Budget exhausted") {
		t.Errorf("默认 budget 应该够，annotation 不应出现: %q", out)
	}
}

// helpers

func parseEvents(t *testing.T, buf *bytes.Buffer) []ledger.Event {
	t.Helper()
	var events []ledger.Event
	for _, line := range bytes.Split(bytes.TrimRight(buf.Bytes(), "\n"), []byte("\n")) {
		if len(line) == 0 {
			continue
		}
		var e ledger.Event
		if err := json.Unmarshal(line, &e); err != nil {
			t.Fatalf("parse event: %v", err)
		}
		events = append(events, e)
	}
	return events
}

// 防止 chatModel 接口漂移无人发现
var _ agents.ChatModel = (*fakeChatModelForComplex)(nil)

// 给 RunComplex 一个 now 注入，确认 opts.Now 也被调用了
func TestRunComplex_NowInjected(t *testing.T) {
	fm := &fakeChatModelForComplex{intentAction: "organize_files"}
	o := New(fm)

	called := false
	_, err := o.RunComplex(context.Background(), "整理 ~/Downloads",
		RunComplexOpts{
			Ledger: ledger.OpenWriter(&bytes.Buffer{}),
			Now: func() time.Time {
				called = true
				return time.Now()
			},
		})
	if err != nil {
		t.Fatalf("RunComplex: %v", err)
	}
	if !called {
		t.Error("opts.Now 注入未被调用")
	}
}
