// Package tools - email_drafter.go
//
// v4 M2: 邮件草稿 demo
// 工具实现：把邮件草稿写到 ~/.local/share/deepin-agent/drafts/
//
// 跟 reminder.go 同构：
// - preview 模式：只生成草稿（包含 Planner 生成的正文），不写入磁盘
// - apply 模式：真的写入文件（带 ID 命名 + 时间戳）
//
// 暂不接 SMTP / MAPI（v4 M3 再接），先把"Planner 生成正文 → 落盘 → 验证"的链路打通。
package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// EmailDraftReport 邮件草稿报告
type EmailDraftReport struct {
	Recipient   string `json:"recipient"`    // 收件人邮箱
	Subject     string `json:"subject"`      // 主题
	Purpose     string `json:"purpose"`      // 用户原始目的描述
	Body        string `json:"body"`         // Planner 生成的正文
	Tone        string `json:"tone"`         // formal | casual | urgent
	Mode        string `json:"mode"`         // preview | applied
	DraftID     string `json:"draft_id"`     // apply 模式下生成的 ID
	StoragePath string `json:"storage_path"` // apply 模式下文件的实际路径
	VerifPassed bool   `json:"verified"`
	VerifMsg    string `json:"verify_msg,omitempty"`
}

// DraftEmail 生成邮件草稿
//
// mode="preview": 生成正文 + 报告，不写入磁盘
// mode="apply":   写入 ~/.local/share/deepin-agent/drafts/<id>.eml
func DraftEmail(ctx context.Context, recipient, subject, purpose, body, tone, mode string) *EmailDraftReport {
	report := &EmailDraftReport{
		Recipient: recipient,
		Subject:   subject,
		Purpose:   purpose,
		Body:      body,
		Tone:      tone,
		Mode:      mode,
	}

	// 1. 基础校验
	if strings.TrimSpace(subject) == "" && strings.TrimSpace(purpose) == "" {
		report.VerifPassed = false
		report.VerifMsg = "主题和目的至少要有一个"
		return report
	}

	// 2. preview 模式：展示报告，不落盘
	if mode != "apply" {
		report.VerifPassed = true
		preview := subject
		if preview == "" {
			preview = "(未指定主题)"
		}
		report.VerifMsg = fmt.Sprintf("预览模式: 邮件草稿已生成（收件人=%s, 主题=%q）", recipientOrPlaceholder(recipient), preview)
		return report
	}

	// 3. apply 模式：写入存储
	home, err := os.UserHomeDir()
	if err != nil {
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("获取 HOME 失败: %v", err)
		return report
	}
	dir := filepath.Join(home, ".local", "share", "deepin-agent", "drafts")
	if err := os.MkdirAll(dir, 0755); err != nil {
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("建目录失败: %v", err)
		return report
	}

	// ID 用 timestamp + subject slug
	slug := slugify(subject)
	if slug == "" || slug == "reminder" {
		// slugify 中文字符被全丢了，用 timestamp+hash 兜底
		slug = fmt.Sprintf("draft-%x", time.Now().UnixNano())[:10]
	}
	id := fmt.Sprintf("%d-%s", time.Now().Unix(), slug)
	storagePath := filepath.Join(dir, id+".eml")

	// 用 .eml 格式（收件人/主题/正文/日期），方便任何邮件客户端打开
	content := buildEML(recipient, subject, body, tone)
	if err := os.WriteFile(storagePath, []byte(content), 0644); err != nil {
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("写入失败: %v", err)
		return report
	}

	report.DraftID = id
	report.StoragePath = storagePath
	report.VerifPassed = true
	report.VerifMsg = fmt.Sprintf("已写入: %s（ID=%s）", storagePath, id)
	return report
}

// VerifyEmailDraft 验证邮件草稿是否真的写入
//
// 校验：文件存在 + 可读 + 包含主题（subject 或正文片段）
func VerifyEmailDraft(ctx context.Context, storagePath, expectedSubject string) (bool, string) {
	if storagePath == "" {
		return false, "StoragePath 为空"
	}
	data, err := os.ReadFile(storagePath)
	if err != nil {
		return false, fmt.Sprintf("读取失败: %v", err)
	}
	content := string(data)

	// 必须包含 To: Subject: 头部
	if !strings.Contains(content, "To:") {
		return false, "文件缺少 To: 头部"
	}
	if !strings.Contains(content, "Subject:") {
		return false, "文件缺少 Subject: 头部"
	}

	// 如果期望主题非空，校验一致
	if expectedSubject != "" && !strings.Contains(content, "Subject: "+expectedSubject) {
		return false, fmt.Sprintf("Subject 不匹配: 期望=%q", expectedSubject)
	}

	return true, fmt.Sprintf("邮件草稿验证通过: %s", storagePath)
}

// buildEML 把邮件拼成 RFC 822 兼容的 .eml 文本
func buildEML(recipient, subject, body, tone string) string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("To: %s\r\n", recipientOrPlaceholder(recipient)))
	sb.WriteString(fmt.Sprintf("Subject: %s\r\n", fallbackSubject(subject)))
	sb.WriteString(fmt.Sprintf("Date: %s\r\n", time.Now().Format(time.RFC1123Z)))
	sb.WriteString(fmt.Sprintf("X-Agent-Tone: %s\r\n", fallbackTone(tone)))
	sb.WriteString("X-Agent-Generated: deepin-agent v4 M2\r\n")
	sb.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
	sb.WriteString("\r\n")
	sb.WriteString(body)
	return sb.String()
}

func recipientOrPlaceholder(r string) string {
	r = strings.TrimSpace(r)
	if r == "" {
		return "<收件人待填>"
	}
	return r
}

func fallbackSubject(s string) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return "(无主题)"
	}
	return s
}

func fallbackTone(t string) string {
	t = strings.TrimSpace(t)
	if t == "" {
		return "formal"
	}
	return t
}

// 保留 json 包导入以便后续扩展元数据字段
var _ = json.Marshal
