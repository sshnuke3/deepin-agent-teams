// Package ledger 提供团队运行账本（failure ledger）。
//
// 对应 advisor-orchestrator-worker skill 的 Finish 段：
// "Return: the deliverable, the plan, a verification ledger per subtask,
//  advisor notes applied and rejected, and remaining risks."
//
// Ledger 把一次完整运行的（subtask_id, verdict, reason, duration, ...）落盘成 JSONL，
// 后续可做：rate 趋势图、advisor 介入频次审计、replay 调试。
//
// 关键设计：
//   - JSONL（一行一事件）便于追加 + tail 解析
//   - 每条事件带 run_id（对应 orchestrator 一次完整 Run）
//   - 落盘路径可配置；默认为 ~/.cache/deepin-agent-teams/ledger.jsonl
package ledger

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// EventType 事件类型
//
// 用于 orchestrator 的 7 步 loop 每一步打点。
type EventType string

const (
	EventRunStart     EventType = "run_start"
	EventFrame        EventType = "frame"
	EventPlan         EventType = "plan"
	EventPlanReview   EventType = "plan_review"   // advisor consult #1
	EventDispatch     EventType = "dispatch"
	EventVerify       EventType = "verify"
	EventTastePass    EventType = "taste_pass"    // advisor consult #2
	EventRunEnd       EventType = "run_end"
	EventEscalation   EventType = "escalation"    // advisor consult (commitment boundary)
	EventSubtaskPass  EventType = "subtask_pass"
	EventSubtaskFix   EventType = "subtask_fix"
	EventSubtaskEsc   EventType = "subtask_escalate"
	EventRedispatch   EventType = "redispatch"
)

// Event 单条账本事件
type Event struct {
	Timestamp time.Time      `json:"ts"`
	RunID     string         `json:"run_id"`
	Type      EventType      `json:"type"`
	SubtaskID string         `json:"subtask_id,omitempty"`
	Verdict   string         `json:"verdict,omitempty"` // PASS / FIX / ESCALATE
	Reason    string         `json:"reason,omitempty"`
	DurationMs int64         `json:"duration_ms,omitempty"`
	Attempt   int            `json:"attempt,omitempty"` // 重派次数（FIX 时递增）
	Extra     map[string]any `json:"extra,omitempty"`
}

// Ledger 账本写入器
//
// 并发安全：多个 worker / stage 可同时 Emit。
type Ledger struct {
	mu   sync.Mutex
	w    io.Writer
	path string
}

// New 创建 ledger；默认写到 ~/.cache/deepin-agent-teams/ledger.jsonl
func New() (*Ledger, error) {
	path, err := defaultPath()
	if err != nil {
		return nil, fmt.Errorf("ledger default path: %w", err)
	}
	return Open(path)
}

// Open 打开或创建指定路径的 ledger（追加模式）
func Open(path string) (*Ledger, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, fmt.Errorf("ledger mkdir: %w", err)
	}
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return nil, fmt.Errorf("ledger open: %w", err)
	}
	return &Ledger{w: f, path: path}, nil
}

// OpenWriter 自定义 io.Writer（测试可注入 buffer）
func OpenWriter(w io.Writer) *Ledger {
	return &Ledger{w: w, path: "(memory)"}
}

func defaultPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".cache", "deepin-agent-teams", "ledger.jsonl"), nil
}

// Path 当前 ledger 落盘路径
func (l *Ledger) Path() string {
	if l == nil {
		return ""
	}
	return l.path
}

// Emit 写一条事件
//
// 静默吞 io error——ledger 不能让主流程崩（best-effort 记账）
func (l *Ledger) Emit(e Event) {
	if l == nil || l.w == nil {
		return
	}
	if e.Timestamp.IsZero() {
		e.Timestamp = time.Now()
	}
	b, err := json.Marshal(e)
	if err != nil {
		return
	}
	b = append(b, '\n')

	l.mu.Lock()
	defer l.mu.Unlock()
	_, _ = l.w.Write(b)
}

// Subtask 把 verifier 三态记成对应事件
//
// 适配 agents.Verdict / workerpool.Verdict（都是 string alias）
func (l *Ledger) Subtask(runID, subtaskID, verdict, reason string, durationMs int64, attempt int) {
	if l == nil {
		return
	}
	var t EventType
	switch verdict {
	case "PASS":
		t = EventSubtaskPass
	case "FIX":
		t = EventSubtaskFix
	case "ESCALATE":
		t = EventSubtaskEsc
	default:
		t = EventVerify
	}
	l.Emit(Event{
		RunID:      runID,
		Type:       t,
		SubtaskID:  subtaskID,
		Verdict:    verdict,
		Reason:     reason,
		DurationMs: durationMs,
		Attempt:    attempt,
	})
}

// Close 落盘（如果底层是 *os.File）
func (l *Ledger) Close() error {
	if l == nil || l.path == "(memory)" {
		return nil
	}
	if f, ok := l.w.(*os.File); ok {
		return f.Close()
	}
	return nil
}

// NewRunID 生成一次 Run 的 UUID 风格 ID
//
// 用时间戳 + 随机数；不引外部依赖。
func NewRunID() string {
	return fmt.Sprintf("run_%d_%d", time.Now().UnixNano(), os.Getpid())
}
