// deepin-agent: deepin 系统设置 AI Agent (v4)
//
// 用法：
//   deepin-agent chat "帮我切到深色模式"
//   deepin-agent demo   # 跑内置演示
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/sshnuke3/deepin-agent-teams/internal/agents"
	"github.com/sshnuke3/deepin-agent-teams/internal/config"
	"github.com/sshnuke3/deepin-agent-teams/internal/model"
	"github.com/sshnuke3/deepin-agent-teams/internal/orchestrator"
)

const version = "v4.0.0-spike"

func main() {
	var (
		showVersion = flag.Bool("version", false, "show version")
		runDemo     = flag.Bool("demo", false, "run built-in demo")
	)
	flag.Parse()

	if *showVersion {
		fmt.Printf("deepin-agent %s\n", version)
		return
	}

	// 加载配置
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("config load failed: %v", err)
	}

	// 初始化 ChatModel
	ctx := context.Background()
	chatModel, err := model.NewChatModel(ctx, cfg.LLMProvider, cfg.APIKey, cfg.BaseURL, cfg.Model)
	if err != nil {
		log.Fatalf("chat model init failed: %v", err)
	}
	log.Printf("✅ ChatModel: provider=%s model=%s", cfg.LLMProvider, cfg.Model)

	// 初始化 Agent + Orchestrator
	intentAgent := agents.NewIntentAgent(chatModel)
	orch := orchestrator.New(intentAgent)

	// demo 模式
	if *runDemo {
		runBuiltInDemo(ctx, orch)
		return
	}

	// chat 模式
	args := flag.Args()
	if len(args) == 0 {
		fmt.Println("用法: deepin-agent [--demo] chat \"你的指令\"")
		fmt.Println("     deepin-agent --demo")
		os.Exit(1)
	}

	userInput := args[0]
	if args[0] == "chat" && len(args) > 1 {
		userInput = args[1]
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
		"今天北京天气怎么样",
	}

	fmt.Println("\n===== deepin-agent v4 内置 demo =====\n")
	for _, input := range testCases {
		fmt.Printf("👤 User: %s\n", input)
		result, err := orch.Run(ctx, input)
		if err != nil {
			log.Printf("❌ Error: %v\n\n", err)
			continue
		}
		fmt.Printf("🤖 Agent: %s\n\n", result)
	}
}
