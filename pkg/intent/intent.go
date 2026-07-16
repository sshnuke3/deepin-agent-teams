// Package intent 定义意图识别的数据结构
//
// 这个包是导出的（pkg/），目的是让外部工具/插件也能复用这些定义
package intent

import "encoding/json"

// Action 类型
const (
	ActionChangeTheme   = "change_theme"
	ActionGetSystemInfo = "get_system_info"
	ActionOrganizeFiles = "organize_files"
	ActionUnknown       = "unknown"
)

// 整理文件的分类规则（按扩展名）
var OrganizeCategories = map[string][]string{
	"images":   {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"},
	"docs":     {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"},
	"sheets":   {".xls", ".xlsx", ".csv", ".ods"},
	"videos":   {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"},
	"audio":    {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
	"archives": {".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz"},
	"code":     {".go", ".py", ".js", ".ts", ".rs", ".java", ".cpp", ".c", ".h", ".sh"},
}

// Theme 枚举
const (
	ThemeDark  = "deepin-dark"
	ThemeLight = "deepin-light"
	ThemeAuto  = "deepin-auto"
)

// Intent 是 LLM 返回的结构化意图
type Intent struct {
	Action string `json:"action"`
	Theme  string `json:"theme,omitempty"`
	// 文件整理相关
	Directory string `json:"directory,omitempty"` // 目标目录（默认 ~/Downloads）
	Mode      string `json:"mode,omitempty"`      // "preview" (默认) | "apply" 是否真移文件
}

// Parse 从 LLM 返回的 JSON 字符串解析 Intent
// 容错处理：即使 LLM 包了 markdown 也能解析
func Parse(s string) (*Intent, error) {
	// 去除可能的 markdown 包裹
	s = stripMarkdown(s)

	var i Intent
	if err := json.Unmarshal([]byte(s), &i); err != nil {
		return nil, err
	}

	// 校验
	switch i.Action {
	case ActionChangeTheme, ActionGetSystemInfo, ActionOrganizeFiles, ActionUnknown:
		// OK
	default:
		i.Action = ActionUnknown
	}

	// 文件整理的安全默认值
	if i.Action == ActionOrganizeFiles {
		if i.Directory == "" {
			i.Directory = "~/Downloads"
		}
		if i.Mode == "" {
			i.Mode = "preview" // 默认只看不摸
		}
	}
	return &i, nil
}

// stripMarkdown 去除 ```json ... ``` 包裹
func stripMarkdown(s string) string {
	if len(s) >= 7 && s[:7] == "```json" {
		s = s[7:]
		if idx := indexOf(s, "```"); idx >= 0 {
			s = s[:idx]
		}
	} else if len(s) >= 3 && s[:3] == "```" {
		s = s[3:]
		if idx := indexOf(s, "```"); idx >= 0 {
			s = s[:idx]
		}
	}
	return s
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
