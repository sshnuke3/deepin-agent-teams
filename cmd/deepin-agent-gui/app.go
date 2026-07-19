// Package main - app.go
//
// v4 GUI: Wails 后端，暴露 Orchestrator.Run 给前端 JS。
//
// 架构：
//   - 前端 (HTML/CSS/JS): Wails 自动生成 wailsjs/go/main/App.js，前端调 window.go.main.App.Run(input)
//   - 后端 (这里): App.Run() 包装 Orchestrator.Run()
//   - LLM 客户端: 复用主仓的 config.Load() + model.NewChatModel()
//
// 环境变量：
//   - 主仓 config.Load() 读 ~/.openclaw/workspace/deepin-agent-teams/.env（gitignored）
//   - 或系统环境变量 QWEN_API_KEY / AGNES_API_KEY / OPENAI_API_KEY 至少一个
//   - DEEPIN_DBUS=mock (Ubuntu/CI 用，否则需要 deepin 25 真机)
package main

import (
	"context"
	"fmt"
	"os"

	"github.com/sshnuke3/deepin-agent-teams/internal/config"
	"github.com/sshnuke3/deepin-agent-teams/internal/model"
	"github.com/sshnuke3/deepin-agent-teams/internal/orchestrator"
)

// App struct 持有 GUI 状态
type App struct {
	ctx         context.Context
	orch        *orchestrator.Orchestrator
	chatModelID string
}

// NewApp 创建一个新的 App 应用结构
func NewApp() *App {
	return &App{}
}

// startup 是 Wails 应用启动回调
func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	a.tryInitOrchestrator()
}

// tryInitOrchestrator 尝试从环境初始化 Orchestrator（懒加载）
//
// 失败不 panic — 让 Run() 时再返回错误（前端可以先展示 GUI shell）
func (a *App) tryInitOrchestrator() {
	cfg, err := config.Load()
	if err != nil {
		fmt.Printf("[GUI] config load failed: %v (will retry on first Run)\n", err)
		return
	}

	cm, err := model.NewChatModel(a.ctx, cfg.LLMProvider, cfg.APIKey, cfg.BaseURL, cfg.Model)
	if err != nil {
		fmt.Printf("[GUI] ChatModel creation failed: %v (will retry on first Run)\n", err)
		return
	}
	a.orch = orchestrator.New(cm)
	a.chatModelID = fmt.Sprintf("%s/%s", cfg.LLMProvider, cfg.Model)
	fmt.Printf("[GUI] ready: provider=%s model=%s\n", cfg.LLMProvider, cfg.Model)
}

// Run 是 Wails 暴露给前端的方法
//
// 入参：用户在输入框里打的字
// 返回：Orchestrator 处理后的回复（多意图用 --- 分隔）
func (a *App) Run(userInput string) (string, error) {
	if userInput == "" {
		return "", fmt.Errorf("输入为空")
	}

	if a.orch == nil {
		a.tryInitOrchestrator()
	}
	if a.orch == nil {
		return "", fmt.Errorf("LLM 未配置：请设置 %s 环境变量或 .env 文件", "QWEN_API_KEY / AGNES_API_KEY / OPENAI_API_KEY 之一")
	}

	return a.orch.RunMulti(a.ctx, userInput)
}

// GetStatus 是 Wails 暴露给前端的方法
//
// 返回当前 GUI 状态，前端用来在 header 显示
func (a *App) GetStatus() Status {
	mock := ""
	if os.Getenv("DEEPIN_DBUS") == "mock" {
		mock = "（演示模式）"
	}
	return Status{
		LLM:   a.chatModelID + mock,
		Ready: a.orch != nil,
	}
}

// Status 是 GetStatus 返回的结构体
type Status struct {
	LLM   string `json:"llm"`
	Ready bool   `json:"ready"`
}