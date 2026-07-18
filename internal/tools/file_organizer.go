// Package tools 提供 deepin 系统工具的实现
//
// file_organizer: 按扩展名分类整理目录中的文件
// 当前是真实文件操作（不是 mock），但默认 preview 模式不真移
package tools

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	intentpkg "github.com/sshnuke3/deepin-agent-teams/pkg/intent"
)

// OrganizeReport 文件整理报告
type OrganizeReport struct {
	Directory   string         `json:"directory"`
	Mode        string         `json:"mode"` // "preview" | "applied"
	TotalFiles  int            `json:"total_files"`
	Categories  map[string]int `json:"categories"` // 分类 → 文件数
	OtherCount  int            `json:"other_count"`
	OtherFiles  []string       `json:"other_files,omitempty"`
	MovePlan    []MoveEntry    `json:"move_plan,omitempty"`
	AppliedCmds []string       `json:"applied_cmds,omitempty"`
	VerifPassed bool           `json:"verified"`
	VerifMsg    string         `json:"verify_msg,omitempty"`
}

// MoveEntry 一次移动操作
type MoveEntry struct {
	Src  string `json:"src"`
	Dst  string `json:"dst"`
	Kind string `json:"kind"` // 分类
}

// OrganizeFiles 按分类整理目录中的文件
//
// mode="preview": 只扫描 + 生成 MovePlan，不动文件
// mode="apply":   真的移动文件到分类子目录
func OrganizeFiles(ctx context.Context, directory, mode string) *OrganizeReport {
	// 展开 ~ 为 HOME
	if strings.HasPrefix(directory, "~/") {
		home, _ := os.UserHomeDir()
		directory = filepath.Join(home, directory[2:])
	}

	report := &OrganizeReport{
		Directory:  directory,
		Mode:       mode,
		Categories: make(map[string]int),
	}

	// 1. 扫描目录
	entries, err := os.ReadDir(directory)
	if err != nil {
		report.VerifPassed = false
		report.VerifMsg = fmt.Sprintf("扫描失败: %v", err)
		return report
	}

	// 2. 分类 + 生成 MovePlan
	for _, entry := range entries {
		if entry.IsDir() {
			continue // 跳过子目录
		}
		name := entry.Name()
		ext := strings.ToLower(filepath.Ext(name))

		category := classifyByExt(ext)
		if category == "" {
			report.OtherCount++
			report.OtherFiles = append(report.OtherFiles, name)
			continue
		}

		report.TotalFiles++
		report.Categories[category]++

		srcPath := filepath.Join(directory, name)
		dstPath := filepath.Join(directory, category, name)
		report.MovePlan = append(report.MovePlan, MoveEntry{
			Src:  srcPath,
			Dst:  dstPath,
			Kind: category,
		})
	}

	// 3. 执行 or 预览
	if mode == "apply" {
		for _, m := range report.MovePlan {
			if err := os.MkdirAll(filepath.Dir(m.Dst), 0755); err != nil {
				report.VerifPassed = false
				report.VerifMsg = fmt.Sprintf("建目录失败 %s: %v", filepath.Dir(m.Dst), err)
				return report
			}
			if err := os.Rename(m.Src, m.Dst); err != nil {
				report.VerifPassed = false
				report.VerifMsg = fmt.Sprintf("移动失败 %s → %s: %v", m.Src, m.Dst, err)
				return report
			}
			report.AppliedCmds = append(report.AppliedCmds, fmt.Sprintf("mv %s %s", m.Src, m.Dst))
		}
		report.VerifPassed = true
		report.VerifMsg = fmt.Sprintf("已应用 %d 个移动操作", len(report.MovePlan))
	} else {
		// preview 模式：不执行，但显示计划
		report.VerifPassed = true
		report.VerifMsg = fmt.Sprintf("预览模式：%d 个文件待整理（未真移）", len(report.MovePlan))
	}

	return report
}

// classifyByExt 根据扩展名返回分类
func classifyByExt(ext string) string {
	for category, exts := range intentpkg.OrganizeCategories {
		for _, e := range exts {
			if e == ext {
				return category
			}
		}
	}
	return ""
}

// VerifyOrganize 验证整理结果（v3 状态机精华：执行后必须验证）
//
// 校验：分类目录是否存在 + 文件数与报告一致
func VerifyOrganize(ctx context.Context, directory string, expected map[string]int) (bool, string) {
	if strings.HasPrefix(directory, "~/") {
		home, _ := os.UserHomeDir()
		directory = filepath.Join(home, directory[2:])
	}

	for category, expectedCount := range expected {
		catDir := filepath.Join(directory, category)
		entries, err := os.ReadDir(catDir)
		if err != nil {
			return false, fmt.Sprintf("分类目录不存在: %s", catDir)
		}
		actual := 0
		for _, e := range entries {
			if !e.IsDir() {
				actual++
			}
		}
		if actual != expectedCount {
			return false, fmt.Sprintf("%s: 期望 %d 个文件，实测 %d 个", category, expectedCount, actual)
		}
	}
	return true, "验证通过"
}
