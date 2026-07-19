// Package intent 定义意图识别的数据结构
//
// 这个包是导出的（pkg/），目的是让外部工具/插件也能复用这些定义
package intent

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

// Action 类型
const (
	ActionChangeTheme      = "change_theme"
	ActionGetSystemInfo    = "get_system_info"
	ActionOrganizeFiles    = "organize_files"
	ActionScheduleReminder = "schedule_reminder" // v4 M2: 日程提醒 demo
	ActionDraftEmail       = "draft_email"       // v4 M2: 邮件草稿 demo
	ActionApplySettings    = "apply_settings"    // v4 M2: 系统设置 demo
	ActionUnknown          = "unknown"
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

// 系统设置分类枚举
const (
	SettingsCategoryTheme      = "theme"
	SettingsCategoryVolume     = "volume"
	SettingsCategoryBrightness = "brightness"
	SettingsCategoryNetwork    = "network"
)

// Intent 是 LLM 返回的结构化意图
type Intent struct {
	Action string `json:"action"`
	Theme  string `json:"theme,omitempty"`
	// 文件整理相关
	Directory string `json:"directory,omitempty"` // 目标目录（默认 ~/Downloads）
	Mode      string `json:"mode,omitempty"`      // "preview" (默认) | "apply" 是否真移文件
	// 日程提醒相关（v4 M2）
	Title    string `json:"title,omitempty"`    // 提醒标题
	DueAt    string `json:"due_at,omitempty"`   // 提醒时间 (ISO8601 或自然语言描述)
	Priority string `json:"priority,omitempty"` // "low" | "normal" | "high"
	// 邮件草稿相关（v4 M2）
	Recipient string `json:"recipient,omitempty"` // 收件人邮箱
	Subject   string `json:"subject,omitempty"`   // 邮件主题
	Purpose   string `json:"purpose,omitempty"`   // 邮件目的/要点（自然语言描述）
	// 系统设置相关（v4 M2）
	SettingsCategory string `json:"settings_category,omitempty"` // theme/volume/brightness/network
	SettingsValue    string `json:"settings_value,omitempty"`    // 值（如 deepin-dark / 50 / on）
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
	case ActionChangeTheme, ActionGetSystemInfo, ActionOrganizeFiles, ActionScheduleReminder, ActionDraftEmail, ActionApplySettings, ActionUnknown:
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

	// 日程提醒的安全默认值
	if i.Action == ActionScheduleReminder {
		if i.Priority == "" {
			i.Priority = "normal"
		}
		// Mode 复用：preview=只看不建，apply=真的写入 ~/.local/share/deepin-agent/reminders/
		if i.Mode == "" {
			i.Mode = "preview"
		}
		// Title 必填，没填就当 unknown
		if i.Title == "" {
			i.Action = ActionUnknown
		}
	}

	// 邮件草稿的安全默认值
	if i.Action == ActionDraftEmail {
		// Mode 复用：preview=只看不存，apply=真的写入 ~/.local/share/deepin-agent/drafts/
		if i.Mode == "" {
			i.Mode = "preview"
		}
		// Subject/Purpose 至少要有一个，否则 unknown
		if i.Subject == "" && i.Purpose == "" {
			i.Action = ActionUnknown
		}
	}

	// 系统设置的安全默认值
	if i.Action == ActionApplySettings {
		if i.Mode == "" {
			i.Mode = "preview"
		}
		// category 必填
		switch i.SettingsCategory {
		case SettingsCategoryTheme, SettingsCategoryVolume, SettingsCategoryBrightness, SettingsCategoryNetwork:
			// OK
		default:
			i.Action = ActionUnknown
		}
		// value 必填
		if i.SettingsValue == "" {
			i.Action = ActionUnknown
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

// ParseMulti 解析多意图输入（v4 M3 新增）
//
// 支持三种输入形式：
//  1. 单个 JSON 对象：{"action":...} → 返回 [Intent]
//  2. JSON 数组：[{"action":...},{"action":...}] → 返回多 Intent
//  3. LLM 偶发返回单个对象带 JSON array 字段的复合输入：{"intents":[...]} → 返回多 Intent
//
// 返回的 intents 中含 ActionUnknown 的会被丢弃（除非全部都是 unknown）。
func ParseMulti(s string) ([]*Intent, error) {
	s = stripMarkdown(s)
	s = strings.TrimSpace(s)

	if len(s) == 0 {
		return nil, errors.New("empty input")
	}

	// 检测首字符：[ → JSON 数组
	if s[0] == '[' {
		var arr []map[string]any
		if err := json.Unmarshal([]byte(s), &arr); err != nil {
			return nil, fmt.Errorf("parse array: %w", err)
		}
		result := make([]*Intent, 0, len(arr))
		for i, item := range arr {
			// 把 map 重新序列化，然后走单意图 Parse 路径（安全校验逻辑不重复）
			b, err := json.Marshal(item)
			if err != nil {
				return nil, fmt.Errorf("marshal item %d: %w", i, err)
			}
			it, err := Parse(string(b))
			if err != nil {
				return nil, fmt.Errorf("parse item %d: %w", i, err)
			}
			result = append(result, it)
		}
		if len(result) == 0 {
			return nil, errors.New("empty array")
		}
		return result, nil
	}

	// 检测是否是 {"intents":[...]} 包装形式
	if s[0] == '{' {
		var probe struct {
			Intents []map[string]any `json:"intents"`
		}
		if err := json.Unmarshal([]byte(s), &probe); err == nil && len(probe.Intents) > 0 {
			result := make([]*Intent, 0, len(probe.Intents))
			for i, item := range probe.Intents {
				b, err := json.Marshal(item)
				if err != nil {
					return nil, fmt.Errorf("marshal intents[%d]: %w", i, err)
				}
				it, err := Parse(string(b))
				if err != nil {
					return nil, fmt.Errorf("parse intents[%d]: %w", i, err)
				}
				result = append(result, it)
			}
			return result, nil
		}
	}

	// 默认：当作单意图处理
	it, err := Parse(s)
	if err != nil {
		return nil, err
	}
	return []*Intent{it}, nil
}
