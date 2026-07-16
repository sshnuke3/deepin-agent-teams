package agents

import (
	"encoding/json"
	"strings"
)

// jsonUnmarshal 带 markdown 容错的 JSON 解析
func jsonUnmarshal(content string, v any) error {
	content = stripMarkdownFence(content)
	return json.Unmarshal([]byte(content), v)
}

func stripMarkdownFence(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```json") {
		s = strings.TrimPrefix(s, "```json")
		if idx := strings.Index(s, "```"); idx >= 0 {
			s = s[:idx]
		}
	} else if strings.HasPrefix(s, "```") {
		s = strings.TrimPrefix(s, "```")
		if idx := strings.Index(s, "```"); idx >= 0 {
			s = s[:idx]
		}
	}
	return strings.TrimSpace(s)
}