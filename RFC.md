## 架构演进（重大重构）

### 重构前（假多 Agent）
- 三个"Agent"只是三个 Python class
- 本质：串行 LLM 调用链
- 问题：无独立上下文、无真正并行、无工具隔离

### 重构后（真多 Agent）
- Orchestrator 调度器：erniebot 推理 + 进程管理
- Researcher/Coder：独立子进程（PID 隔离）
- 进程间通信：文件系统传递任务/结果
- 真正并行：threading 并发分发 + 子进程同时执行

### 技术架构图

```
Orchestrator (Lead Agent)
├── erniebot.lite → 任务拆解 + 结果整合
├── subprocess Researcher (PID 隔离)
│   └── 独立工具集：文件读取、Shell 执行
└── subprocess Coder (PID 隔离)
    └── 独立工具集：AST 分析、语法检查、文档生成

进程通信：
Orchestrator → Worker: /tmp/agent_task_{role}.json
Worker → Orchestrator: /tmp/agent_result_{role}.json
```

## 七、提交物清单

- [x] RFC.md（本文档）
- [x] README.md（环境安装、一键运行说明）
- [x] agents/orchestrator.py - 多 Agent 调度器（erniebot 推理 + 进程管理）
- [x] agents/worker_researcher.py - Researcher 子进程（独立工具集）
- [x] agents/worker_coder.py - Coder 子进程（独立工具集）
- [x] config.py - 统一配置管理
- [x] main.py - 命令行入口（支持 --multi 多进程模式）
- [x] scenarios/code_analysis.py - 场景一（✅已演示）
- [x] scenarios/literature_review.py - 场景二（✅已演示）
- [ ] README 截图/录屏

## 实施进度

| 阶段 | 时间 | 状态 | 说明 |
|------|------|------|------|
| 第一周 | 4/1-4/7 | ✅ | Agent 框架搭建 |
| 第二周 | 4/8-4/14 | ✅ | 两大场景框架 |
| 第三周 | 4/15-4/21 | ✅ | 场景一 + 端到端演示 |
| 第四周 | 4/22-4/28 | ✅ | 架构重构：真多进程 Agent |
| 第五周 | 4/29-5/5 | ⏳ | 演示材料 + 提交 |

## 演示验证

### 多进程多 Agent 演示（--multi 模式）
- Orchestrator spawn 2 独立子进程（PID 1927455 + 1927456）
- erniebot 推理任务拆解（parallel=true）
- 并行分发任务给 Researcher + Coder
- 子进程独立执行（文件分析、AST 分析）
- 结果文件收集 + erniebot 整合
- 子进程优雅退出
- 状态：✅ 通过

## 代码结构（最新）

```
deepin-agent-teams/
├── config.py              # 统一配置
├── main.py                # 入口（-m 多进程模式）
├── requirements.txt
├── .env.example
├── .gitignore
├── agents/
│   ├── orchestrator.py     # 多 Agent 调度器（核心）
│   ├── worker_researcher.py # Researcher 子进程
│   ├── worker_coder.py     # Coder 子进程
│   ├── base.py            # 旧版 BaseAgent（兼容）
│   ├── lead.py            # 旧版 LeadAgent（兼容）
│   ├── researcher.py      # 旧版 ResearcherAgent（兼容）
│   └── coder.py          # 旧版 CoderAgent（兼容）
└── scenarios/
    ├── code_analysis.py
    └── literature_review.py
```

