# deepin-agent v4

> AI Agent 编排系统，专为 deepin / 国产 OS 生态设计
> 用 Go + CloudWeGo Eino 重新实现，支持多 LLM provider

[![Go Version](https://img.shields.io/badge/Go-1.22+-00ADD8?logo=go&logoColor=white)](https://go.dev)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Eino](https://img.shields.io/badge/Powered%20by-Eino-FF6B6B)](https://github.com/cloudwego/eino)

---

## 这是什么

v4 是 **deepin-agent-teams** 项目的下一代架构：从 Python 重写为 Go + CloudWeGo Eino，目标是成为 deepin / 国产 OS 生态的 AI Agent 编排标杆。

**核心特性**：

- 🦀 **Go 单二进制**：23MB，启动 < 200ms，内存 < 30MB
- 🔌 **多 LLM 支持**：Agnes / Qwen / OpenAI / 豆包 / DeepSeek / Ollama 一行切换
- 🧠 **Eino 编排**：Lambda Chain（Intent → Planner → Executor → Verifier），类型安全
- ✅ **状态机精华继承**：v3 的 7 种状态压成 3 段 Chain + 独立 Verifier 强制校验
- 🪶 **国产友好**：原厂支持 Qwen（通义千问）、豆包、DeepSeek
- 🛠️ **deepin 集成（计划中）**：DTK/DDE D-Bus 工具调用，MCP 协议
- 🛡️ **安全阀**：文件整理默认 preview（只看不动），--apply 才真移

---

## 30 秒跑起来

```bash
# 1. 准备 API Key（任选一个）
export QWEN_API_KEY="***"        # 推荐（快 8-12x，免费）
# 或
export AGNES_API_KEY="***"       # 备选（永久免费，慢）

# 2. 跑内置 demo（5 个意图测试）
git clone https://github.com/sshnuke3/deepin-agent-teams
cd deepin-agent-teams
git checkout v4-redesign
make demo
```

预期输出：
```
✅ ChatModel: provider=qwen model=qwen3.6-35b-a3b
===== deepin-agent v4 内置 demo =====
👤 帮我把系统调成深色模式    → ✅ 已切换到 deepin-dark 主题
👤 切换到浅色主题吧        → ✅ 已切换到 deepin-light 主题
👤 自动主题跟随系统        → ✅ 已切换到 deepin-auto 主题
👤 看一下系统信息          → ✅ 主机名: ..., 系统: deepin 25
👤 整理一下 ~/Downloads 看看 → 📋 文件整理预览 + Verifier 自洽报告（M2 新增）
```

### 文件整理 demo（M2 新增）

```bash
# Preview 模式（默认安全）—— 只看不摸
./bin/deepin-agent chat "整理一下 ~/Downloads"

# Apply 模式 —— 真移文件 + Verifier 实地校验
./bin/deepin-agent chat "整理 ~/Downloads" --apply
```

**分类规则**（7 个分类）：images / docs / sheets / videos / audio / archives / code
**安全机制**：默认 mode=preview、Verifier 独立 Agent、执行后实地校验
**示例输出**（apply 模式）：
```
🚀 文件整理已执行
📂 目录: /tmp/test-organize
📊 待整理: 9 个文件

分类明细:
  archives/: 1 个
  code/: 1 个
  images/: 2 个
  docs/: 3 个
  videos/: 1 个
  audio/: 1 个
  其他: 1 个

验证: ✅ 验证通过
```

---

## 切换模型

v4 设计：**一个配置 + 一个 provider 名字 = 切任意模型**。

### 支持的 Provider

| Provider | 默认 BaseURL | 默认 Model | 所需环境变量 |
|----------|-------------|-----------|------------|
| `agnes` | `https://apihub.agnes-ai.com/v1` | `agnes-1.5-flash` | `AGNES_API_KEY` |
| `qwen` | `https://ai.tdp.fan/api/v1` | `qwen3.6-35b-a3b` | `QWEN_API_KEY` |
| `openai` / `doubao` / `deepseek` / `ollama` | (需手动设) | (需手动设) | 自定义 |

```bash
# Agnes（默认）
AGNES_API_KEY=*** ./bin/deepin-agent --demo

# Qwen (TDP 镜像，推荐)
QWEN_API_KEY=*** LLM_PROVIDER=qwen ./bin/deepin-agent --demo

# 自定义 BaseURL + Model（覆盖预设）
LLM_PROVIDER=qwen \
QWEN_API_KEY=*** \
LLM_BASE_URL=https://your-proxy.com/v1 \
LLM_MODEL=custom-model \
./bin/deepin-agent chat "你的问题"
```

### Reasoning 模型注意

Qwen 3.6 是 reasoning 模型（带思考过程），`max_tokens=2000` 才能完整输出。普通模型（Agnes/OpenAI 等）默认 100 token 够用。

---

## 架构

```
deepin-agent v4
├── cmd/deepin-agent/         # CLI 入口（cobra）
├── internal/
│   ├── config/               # 配置加载（环境变量 + provider 预设）
│   ├── model/                # ChatModel 抽象（多 LLM 统一接口）
│   ├── orchestrator/         # Eino Lambda Chain 编排核心
│   ├── agents/               # Agent 实现
│   │   ├── intent_agent.go   #   - Intent: LLM 识别用户意图
│   │   ├── planner_agent.go  #   - Planner: LLM 判断执行参数（M2）
│   │   ├── verifier_agent.go #   - Verifier: 执行后强制校验（M2）
│   │   └── json_helper.go    #   - JSON 容错解析
│   └── tools/                # 工具实现
│       ├── appearance.go     #   - 主题切换（mock DTK）
│       └── file_organizer.go #   - 文件整理（真 IO，M2）
├── pkg/intent/               # 意图数据结构（导出包，外部可用）
├── Makefile                  # build / run / demo / test / build-all
└── go.mod / go.sum
```

**Eino 三段 Lambda Chain**（M2 架构）：

```
User Input
    ↓
┌─────────────────────────────────────────────┐
│ Stage 1: IntentAgent → PlannerAgent        │
│   识别意图 + 生成执行计划（directory/mode）  │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Stage 2: Executor（直接调工具，不快不慢）   │
│   appearance / file_organizer / sysinfo     │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Stage 3: VerifierAgent（独立校验）          │
│   preview: 报告自洽检查                      │
│   apply: 实地验证分类目录文件数              │
└─────────────────────────────────────────────┘
    ↓
Formatted Output
```

```go
chain := compose.NewChain[string, *PipelineContext]().
    AppendLambda(stagePlan).     // Intent + Planner
    AppendLambda(stageExecute).  // Executor
    AppendLambda(stageVerify)    // Verifier
```

**v3 vs v4 状态机**：
- v3: Python 状态机 = 7 个状态 + 状态转换表 + 重试逻辑 = ~400 行
- v4: Eino Lambda Chain = 3 个 Lambda 节点 + PipelineContext = ~150 行（60%↓）

---

## v3 vs v4

| 维度 | v3 (Python) | v4 (Go+Eino) |
|------|------------|--------------|
| 启动时间 | ~3s | **< 200ms** |
| 内存占用 | ~150MB | **< 30MB** |
| 模型支持 | 2 (ERNIE) | **4+ (Agnes/Qwen/OpenAI/...)** |
| 部署 | 需 Python 运行时 | **单二进制** |
| 类型安全 | ❌ 动态 | ✅ 编译期 |
| 并发 | asyncio 复杂 | goroutine 简单 |
| 国产模型支持 | ERNIE | Qwen / 豆包 / DeepSeek |

---

## 路线图

- [x] **v4.0 M1 骨架**（2026-07-16，commit `8cf8207`）：Eino + ChatModel + Lambda Chain 跑通，5/5 intent 全对
- [x] **v4.0 M2 文件整理 demo**（2026-07-17，commit `3348c49`）：三段 Chain + Verifier + 6/6 单元测试 PASS
  - 新增 `PlannerAgent` / `VerifierAgent` / `file_organizer` 工具
  - 默认 preview 模式 + `--apply` 标志
  - 真实 demo 跑通：9 文件按 7 分类归位 + 实地校验通过
- [ ] **v4.0 M2 续**：迁剩余 4 个 demo（日程提醒 / 邮件草稿 / 软件安装 / 系统设置），**优先级待定**
- [ ] **v4.1**：流式响应（Eino first-class）
- [ ] **v4.2**：MCP 工具层（标准协议 + 国产生态互操作）
- [ ] **v4.3**：DTK/DDE D-Bus 集成（真 deepin 系统控制）
- [ ] **v4.4**：Web UI（Go + htmx 轻量管理界面）
- [ ] **v5.0**：自学习（基于历史任务优化 Planner）

详细计划见 [PLAN.md](./PLAN.md)。

---

## 性能实测

### Qwen 3.6-35b-a3b（TDP 镜像，免费）

| Case | 响应时间 |
|------|---------|
| 切深色模式 | 0.95s |
| 切浅色模式 | 2.82s |
| 自动主题 | 4.35s |
| 系统信息 | 1.55s |
| 未知意图 | 2.75s |
| **平均** | **~2.5s** |

### 对比 Agnes 1.5-flash

- Agnes：20-30s
- Qwen：~2.5s
- **Qwen 快 8-12 倍**

---

## 开发

```bash
# 编译
make build

# 跑
./bin/deepin-agent --demo

# 单元测试
make test

# 跨平台编译
make build-all
```

支持的平台：
- linux/amd64（主）
- linux/arm64（Apple Silicon / ARM 服务器）
- darwin/arm64（macOS）

---

## 贡献

欢迎 PR！特别是：

- 新的 LLM provider 适配（在 `internal/config/config.go` 加预设）
- 新的工具实现（在 `internal/tools/` 加）
- 新的演示场景（在 `cmd/deepin-agent/main.go` 加 test case）
- 文档改进

---

## 许可

Apache-2.0

---

## 致谢

- [CloudWeGo Eino](https://github.com/cloudwego/eino) — Go 智能体框架
- [Agnes AI](https://agnes-ai.space) — 永久免费 LLM 兜底
- [deepin](https://www.deepin.org) — 国产 OS 生态

---

> v4 项目于 2026-07-16 启动，2026-07-17 完成 M2 文件整理 demo
> 作者：[@sshnuke3](https://github.com/sshnuke3)
> v3 项目（Python）保留在 main 分支作参考实现

## 测试

```bash
go test ./... -v
```

**当前状态**：6/6 PASS
- `internal/agents`：2 测试（Verifier 报告自洽 / 未知 mode 拒绝）
- `internal/tools`：4 测试（preview / apply / verify / ~ 展开）
