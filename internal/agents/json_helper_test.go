package agents

import (
	"testing"
)

func TestStripMarkdownFence_PlainJSON(t *testing.T) {
	got := stripMarkdownFence(`{"action":"test"}`)
	want := `{"action":"test"}`
	if got != want {
		t.Errorf("plain JSON should pass through, got %q want %q", got, want)
	}
}

func TestStripMarkdownFence_JSONFenced(t *testing.T) {
	got := stripMarkdownFence("```json\n{\"action\":\"test\"}\n```")
	want := "{\"action\":\"test\"}"
	if got != want {
		t.Errorf("```json fence should be stripped, got %q want %q", got, want)
	}
}

func TestStripMarkdownFence_GenericFenced(t *testing.T) {
	got := stripMarkdownFence("```\n{\"action\":\"test\"}\n```")
	want := "{\"action\":\"test\"}"
	if got != want {
		t.Errorf("``` fence should be stripped, got %q want %q", got, want)
	}
}

func TestStripMarkdownFence_NoClosingFence(t *testing.T) {
	got := stripMarkdownFence("```json\n{\"action\":\"test\"}")
	want := "{\"action\":\"test\"}"
	if got != want {
		t.Errorf("missing closing fence should still strip prefix, got %q want %q", got, want)
	}
}

func TestStripMarkdownFence_WithSurroundingWhitespace(t *testing.T) {
	got := stripMarkdownFence("\n  ```json\n{\"action\":\"test\"}\n```  \n")
	want := "{\"action\":\"test\"}"
	if got != want {
		t.Errorf("whitespace around fence should be trimmed, got %q want %q", got, want)
	}
}

func TestStripMarkdownFence_Empty(t *testing.T) {
	got := stripMarkdownFence("")
	if got != "" {
		t.Errorf("empty string should return empty, got %q", got)
	}
}

func TestStripMarkdownFence_OnlyFenceMarker(t *testing.T) {
	got := stripMarkdownFence("```json```")
	want := ""
	if got != want {
		t.Errorf("empty fenced block should return empty, got %q want %q", got, want)
	}
}

func TestStripMarkdownFence_FencedJSONNoNewline(t *testing.T) {
	got := stripMarkdownFence("```json{\"action\":\"test\"}```")
	want := "{\"action\":\"test\"}"
	if got != want {
		t.Errorf("compact ```json``` block should strip, got %q want %q", got, want)
	}
}

func TestJSONUnmarshal_PlainJSON(t *testing.T) {
	type payload struct {
		Action string `json:"action"`
	}
	var p payload
	if err := jsonUnmarshal(`{"action":"hello"}`, &p); err != nil {
		t.Fatalf("plain JSON should parse, got %v", err)
	}
	if p.Action != "hello" {
		t.Errorf("got %q want %q", p.Action, "hello")
	}
}

func TestJSONUnmarshal_MarkdownFenced(t *testing.T) {
	type payload struct {
		Action string `json:"action"`
	}
	var p payload
	in := "```json\n{\"action\":\"hello\"}\n```"
	if err := jsonUnmarshal(in, &p); err != nil {
		t.Fatalf("fenced JSON should parse, got %v", err)
	}
	if p.Action != "hello" {
		t.Errorf("got %q want %q", p.Action, "hello")
	}
}

func TestJSONUnmarshal_InvalidJSON(t *testing.T) {
	type payload struct {
		Action string `json:"action"`
	}
	var p payload
	if err := jsonUnmarshal("not json at all", &p); err == nil {
		t.Error("invalid JSON should return error")
	}
}

func TestJSONUnmarshal_GenericFence(t *testing.T) {
	type payload struct {
		Action string `json:"action"`
	}
	var p payload
	in := "```\n{\"action\":\"hello\"}\n```"
	if err := jsonUnmarshal(in, &p); err != nil {
		t.Fatalf("generic fence should parse, got %v", err)
	}
	if p.Action != "hello" {
		t.Errorf("got %q want %q", p.Action, "hello")
	}
}

func TestJSONUnmarshal_WhitespaceAround(t *testing.T) {
	type payload struct {
		Action string `json:"action"`
	}
	var p payload
	in := "\n  ```json\n{\"action\":\"hello\"}\n```  \n"
	if err := jsonUnmarshal(in, &p); err != nil {
		t.Fatalf("whitespace-padded fence should parse, got %v", err)
	}
	if p.Action != "hello" {
		t.Errorf("got %q want %q", p.Action, "hello")
	}
}

// Sanity: stripMarkdownFence must never panic on weird inputs.
func TestStripMarkdownFence_NoPanicOnEdgeCases(t *testing.T) {
	edge := []string{
		"`",
		"```",
		"```json",
		"```json\n",
		"```\n",
		"junk```json```junk", // 只有前缀没匹配 prefix（TrimSpace 后是 "junk```json```junk"），不应崩
	}
	for _, s := range edge {
		_ = stripMarkdownFence(s)
	}
}