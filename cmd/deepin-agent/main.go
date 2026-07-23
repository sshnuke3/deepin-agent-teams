// deepin-agent: deepin 系统设置 AI Agent (v4)
//
// 用法：
//
//	deepin-agent chat "帮我切到深色模式"
//	deepin-agent chat "整理一下 Downloads" --apply   # 真移文件
//	deepin-agent demo
//	deepin-agent complex "帮我 ..."     # 走 RunComplex (advisor-orchestrator-worker 团队模式)
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/sshnuke3/deepin-agent-teams/internal/advisor"
	"github.com/sshnuke3/deepin-agent-teams/internal/config"
	"github.com/sshnuke3/deepin-agent-teams/internal/model"
	"github.com/sshnuke3/deepin-agent-teams/internal/orchestrator"
)

const version = "v4.0.0-m2.4"

func main() {
	var (
		showVersion = flag.Bool("version", false, "show version")
		runDemo     = flag.Bool("demo", false, "run built-in demo")
		applyMode   = flag.Bool("apply", false, "file organize: really move files (default: preview)")
		noAdvisor   = flag.Bool("no-advisor", false, "disable Advisor Agent (fall back to no-advisor Run mode; useful when mengyu.ltd is 503)")
		useComplex  = flag.Bool("complex", false, "use RunComplex (v5 team mode: plan_review + escalation + taste_pass); default false (use Run)")
		budget      = flag.Int("budget", 10, "RunComplex dispatches/consults total budget")
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
	log.Printf("✅ Orchestrator ChatModel: provider=%s model=%s", cfg.LLMProvider, cfg.Model)

	orch := orchestrator.New(chatModel)

	// v5 M5+: Advisor 默认接 mengyu.ltd 中转的 KAT-Coder-Exp-72B-1010
	// --no-advisor 可强制跳过(降级到与老版一致的行为)
	var advisorAgent *advisor.AdvisorAgent
	if !*noAdvisor {
		advCfg := model.AdvisorConfigFromEnv()
		if advCfg.Enabled {
			advCM, advErr := model.NewAdvisorChatModel(ctx, advCfg)
			if advErr != nil {
				log.Printf("⚠️  Advisor init failed (降级到 no-advisor): %v", advErr)
			} else {
				advisorAgent = advisor.NewAdvisorAgent(advCM)
				log.Printf("✅ Advisor ChatModel: provider=%s model=%s (base=%s)",
					advCfg.Provider, advCfg.Model, advCfg.BaseURL)
			}
		} else {
			log.Printf("ℹ️  Advisor disabled (no ADVISOR_API_KEY; 需 --no-advisor 显式跳过)")
		}
	} else {
		log.Printf("⏭  --no-advisor: 跳过 Advisor, 走纯 Run 路径")
	}

	if *runDemo {
		runBuiltInDemo(ctx, orch)
		return
	}

	args := flag.Args()
	if len(args) == 0 {
		fmt.Println("用法: deepin-agent [--demo] [--complex] [--no-advisor] chat \"你的指令\"")
		fmt.Println("     deepin-agent chat \"整理 Downloads\" --apply   # 真移文件")
		fmt.Println("     deepin-agent --complex chat \"整理 Downloads\"  # 团队模式 (advisor 介入)")
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

	// v5+: --complex 走 RunComplex(团队模式);默认走 Run(原有路径,不破)
	var result string
	if *useComplex {
		log.Printf("🔀 --complex: 走 RunComplex (budget=%d, advisor=%v)", *budget, advisorAgent != nil)
		result, err = orch.RunComplex(ctx, userInput, orchestrator.RunComplexOpts{
			AdvisorAgent:   advisorAgent,
			Budget:         *budget,
			SuccessCriteria: []string{
				"完成用户请求",
				"未触发副作用",
			},
		})
	} else {
		result, err = orch.Run(ctx, userInput)
	}
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
		// 系统设置场景 (M2)
		"帮我把音量调到 80",
		"切到深色模式",
		"关掉 WiFi",
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
