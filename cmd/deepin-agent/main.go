// deepin-agent: deepin 系统设置 AI Agent (v4)
//
// 用法：
//
//	deepin-agent chat "帮我切到深色模式"
//	deepin-agent chat "整理一下 Downloads" --apply   # 真移文件
//	deepin-agent demo
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/sshnuke3/deepin-agent-teams/internal/config"
	"github.com/sshnuke3/deepin-agent-teams/internal/model"
	"github.com/sshnuke3/deepin-agent-teams/internal/orchestrator"
)

const version = "v4.0.0-m2.3"

func main() {
	var (
		showVersion = flag.Bool("version", false, "show version")
		runDemo     = flag.Bool("demo", false, "run built-in demo")
		applyMode   = flag.Bool("apply", false, "file organize: really move files (default: preview)")
	)
	flag.Parse()

	if *showVersion {
		fmt.Printf("deepin-agent %s\n", version)
		return
	}

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("config load failed: %v", err)
	}

	ctx := context.Background()
	chatModel, err := model.NewChatModel(ctx, cfg.LLMProvider, cfg.APIKey, cfg.BaseURL, cfg.Model)
	if err != nil {
		log.Fatalf("chat model init failed: %v", err)
	}
	log.Printf("✅ ChatModel: provider=%s model=%s", cfg.LLMProvider, cfg.Model)

	orch := orchestrator.New(chatModel)

	if *runDemo {
		runBuiltInDemo(ctx, orch)
		return
	}

	args := flag.Args()
	if len(args) == 0 {
		fmt.Println("用法: deepin-agent [--demo] chat \"你的指令\"")
		fmt.Println("     deepin-agent chat \"整理 Downloads\" --apply   # 真移文件")
		os.Exit(1)
	}

	userInput := args[0]
	if args[0] == "chat" && len(args) > 1 {
		userInput = args[1]
	}

	// 如果是文件整理且 --apply，转发给 Intent
	if *applyMode {
		userInput = userInput + " (apply mode)"
	}

	result, err := orch.Run(ctx, userInput)
	if err != nil {
		log.Fatalf("orchestrator run failed: %v", err)
	}
	fmt.Println(result)
}

func runBuiltInDemo(ctx context.Context, orch *orchestrator.Orchestrator) {
	testCases := []string{
		"帮我把系统调成深色模式",
		"切换到浅色主题吧",
		"自动主题跟随系统",
		"看一下系统信息",
		// 文件整理场景 (M2)
		"整理一下 ~/Downloads 看看",
		// 日程提醒场景 (M2)
		"提醒我明天下午 3 点开会",
		// 邮件草稿场景 (M2)
		"帮 alice@example.com 起草一封项目进度同步邮件，主题：v4 M2 完成",
	}

	fmt.Println()
	fmt.Println("===== deepin-agent v4 M2 内置 demo =====")
	fmt.Println()
	for _, input := range testCases {
		fmt.Printf("👤 User: %s\n", input)
		result, err := orch.Run(ctx, input)
		if err != nil {
			log.Printf("❌ Error: %v\n\n", err)
			continue
		}
		fmt.Printf("🤖 Agent:\n%s\n", result)
	}
}
