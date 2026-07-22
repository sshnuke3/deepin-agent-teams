package ledger

import (
	"bytes"
	"encoding/json"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestLedger_EmitAndRead(t *testing.T) {
	var buf bytes.Buffer
	l := OpenWriter(&buf)

	l.Subtask("run-1", "task-a", "PASS", "ok", 50, 1)
	l.Subtask("run-1", "task-b", "FIX", "needs redispatch", 100, 1)
	l.Subtask("run-1", "task-c", "ESCALATE", "advisor needed", 200, 2)

	lines := bytes.Split(bytes.TrimRight(buf.Bytes(), "\n"), []byte("\n"))
	if len(lines) != 3 {
		t.Fatalf("expected 3 events, got %d", len(lines))
	}

	// JSONL 解析 + 字段断言
	var events []Event
	for _, line := range lines {
		var e Event
		if err := json.Unmarshal(line, &e); err != nil {
			t.Fatalf("parse line: %v", err)
		}
		events = append(events, e)
	}

	if events[0].Verdict != "PASS" || events[0].Type != EventSubtaskPass {
		t.Errorf("PASS 事件映射错: %+v", events[0])
	}
	if events[1].Verdict != "FIX" || events[1].Type != EventSubtaskFix {
		t.Errorf("FIX 事件映射错: %+v", events[1])
	}
	if events[2].Verdict != "ESCALATE" || events[2].Type != EventSubtaskEsc {
		t.Errorf("ESCALATE 事件映射错: %+v", events[2])
	}

	for _, e := range events {
		if e.RunID != "run-1" {
			t.Errorf("RunID 丢失: %+v", e)
		}
		if e.Timestamp.IsZero() {
			t.Error("Timestamp 应自动填")
		}
	}
}

func TestLedger_AllEventTypes(t *testing.T) {
	// 防止 EventType 常量被改而没人发现
	var buf bytes.Buffer
	l := OpenWriter(&buf)

	allTypes := []EventType{
		EventRunStart, EventFrame, EventPlan, EventPlanReview,
		EventDispatch, EventVerify, EventTastePass, EventRunEnd,
		EventEscalation, EventSubtaskPass, EventSubtaskFix,
		EventSubtaskEsc, EventRedispatch,
	}
	for _, typ := range allTypes {
		l.Emit(Event{Type: typ, SubtaskID: "x", RunID: "r"})
	}

	for _, typ := range allTypes {
		if !strings.Contains(buf.String(), string(typ)) {
			t.Errorf("event type %q 没出现在输出中", typ)
		}
	}
}

func TestLedger_ConcurrentSafety(t *testing.T) {
	// 100 个并发 Emit 不能让输出错乱
	var buf bytes.Buffer
	l := OpenWriter(&buf)

	var wg sync.WaitGroup
	const n = 100
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(i int) {
			defer wg.Done()
			l.Emit(Event{
				Type:      EventDispatch,
				SubtaskID: "t",
				RunID:     "r",
				Extra:     map[string]any{"i": i},
			})
		}(i)
	}
	wg.Wait()

	lines := bytes.Split(bytes.TrimRight(buf.Bytes(), "\n"), []byte("\n"))
	if len(lines) != n {
		t.Errorf("expected %d lines, got %d", n, len(lines))
	}
	// 每行必须能解析回 JSON
	for i, line := range lines {
		var e Event
		if err := json.Unmarshal(line, &e); err != nil {
			t.Errorf("line %d parse fail: %v", i, err)
		}
	}
}

func TestLedger_NilSafe(t *testing.T) {
	// ledger 为 nil 时调用不能 panic（用户在测试里常用 nil 跳过记账）
	var l *Ledger
	l.Subtask("r", "t", "PASS", "ok", 1, 1)
	l.Emit(Event{Type: EventDispatch})

	// 也测试 OpenWriter(nil).Emit——保证不 panic
	OpenWriter(nil).Emit(Event{Type: EventRunStart})
}

func TestLedger_NewRunID(t *testing.T) {
	id1 := NewRunID()
	time.Sleep(time.Millisecond) // 保证时间戳不重
	id2 := NewRunID()

	if id1 == id2 {
		t.Error("同一进程内 run id 应不同（时间不同）")
	}
	if !strings.HasPrefix(id1, "run_") {
		t.Errorf("run id 应当以 run_ 开头，实际=%q", id1)
	}
}

func TestLedger_AutoTimestamp(t *testing.T) {
	var buf bytes.Buffer
	l := OpenWriter(&buf)
	before := time.Now()
	l.Emit(Event{Type: EventRunStart})
	after := time.Now()

	var e Event
	if err := json.Unmarshal(bytes.TrimRight(buf.Bytes(), "\n"), &e); err != nil {
		t.Fatalf("parse: %v", err)
	}
	if e.Timestamp.Before(before) || e.Timestamp.After(after) {
		t.Errorf("auto timestamp 应在 before/after 之间，实际=%v", e.Timestamp)
	}
}
