# Plan: deepin-agent-teams v4 (Go + Eino 重写)

> v3 Python 已交付（黑客松结束），v4 是纯技术迭代期：用 Go + CloudWeGo Eino 全量重写
> 最后更新：2026-07-17

## 进度总览

- [x] **M1 骨架**（2026-07-16，commit `8cf8207`）—— Eino + ChatModel + Lambda Chain + 5/5 intent 全对
- [x] **M2 文件整理 demo**（2026-07-17，commit `3348c49`）—— 三段 Chain + Verifier + 6/6 测试 PASS
- [ ] **M2 续**：剩余 2 个 demo（软件安装 / 系统设置）
- [ ] **M3 打磨**：多模型（豆包/DeepSeek/Ollama）+ MCP 协议 + DTK/DDE 真集成
- [ ] **M4 Web UI**（v4.4）
- [ ] **v5.0 自学习**（基于历史任务优化 Planner）

## M2 文件整理 demo 详情

### 新增文件（6）
| 文件 | 说明 |
|------|------|
| `internal/agents/planner_agent.go` | Planner Agent：LLM 判断 directory/mode 参数 |
| `internal/agents/verifier_agent.go` | Verifier Agent：v3 状态机精华 - 执行后强制校验 |
| `internal/agents/json_helper.go` | JSON markdown 容错解析 |
| `internal/agents/verifier_agent_test.go` | Verifier 单元测试 |
| `internal/tools/file_organizer.go` | 真实文件 IO（按扩展名分类，7 分类） |
| `internal/tools/file_organizer_test.go` | 工具单元测试（4 个用例）|

### 修改文件（4）
| 文件 | 改动 |
|------|------|
| `cmd/deepin-agent/main.go` | 加 --apply 标志 |
| `internal/agents/intent_agent.go` | prompt 加 organize_files 格式 |
| `internal/orchestrator/orchestrator.go` | 三段 Chain 重构（PipelineContext 传递）|
| `pkg/intent/intent.go` | 加 ActionOrganizeFiles + OrganizeCategories（7 分类规则）|

### 验证

| 项 | 结果 |
|---|------|
| go build ./... | ✅ 干净 |
| go vet ./... | ✅ 干净 |
| go test ./... | ✅ **6/6 PASS**（agents 2 + tools 4）|
| 真 LLM preview demo | ✅ 9 文件 / 7 分类 / "preview 报告自洽" |
| 真 LLM apply demo | ✅ 文件正确归位 + Verifier 实地校验 "验证通过" |

### 架构（v3 状态机 → v4 Lambda Chain）

```
User Input
    ↓
Stage 1: IntentAgent → PlannerAgent  (识别 + 规划)
    ↓ PipelineContext
Stage 2: Executor  (直接调工具，不快不慢)
    ↓ PipelineContext
Stage 3: VerifierAgent  (独立校验)
    ↓
Formatted Output
```

**v3 vs v4 状态机**：
- v3: Python 状态机 = 7 个状态 + 状态转换表 + 重试逻辑 = ~400 行
- v4: Eino Lambda Chain = 3 个 Lambda 节点 + PipelineContext = ~150 行（**60%↓**）

## 待办（按优先级）

### 短期（M2 续）
- [x] **迁日程提醒 demo**（commit `e062e20`）：Planner 翻译自然语言时间 + 写 ~/.local/.../reminders/
- [x] **迁邮件草稿 demo**（2026-07-18）：Planner 撰文 + 写 RFC822 `.eml` + Verifier 校验 `.eml` 头部
- [x] **迁系统设置 demo**（2026-07-18）：theme/volume/brightness/network 4 类 + 写 ~/.local/.../settings.json + 4/4 测试
- [ ] **迁软件安装 demo**：v3 用 apt + sudo，v4 用 package manager 抽象层

### 中期（M3 打磨）
- [ ] **多模型接入**：豆包 / DeepSeek / Ollama 至少 3 家
- [ ] **MCP 工具层**：把 mock 工具替换成真 D-Bus
- [ ] **DTK/DDE 真集成**：com.deepin.daemon.Appearance 真切换主题
- [ ] **流式响应**：Eino first-class
- [ ] **错误恢复 + 重试**：v3 状态机精髓，v4 用 Eino Graph 分支

### 长期（M4+）
- [ ] Web UI（Go + htmx 轻量管理界面）
- [ ] 自学习（基于历史任务优化 Planner）
- [ ] 跨架构编译（amd64 + arm64 + loong64）

## 关键决策（已沉淀进 MEMORY.md）

1. **状态机范式**：Eino Lambda Chain（不用 Graph，90% 场景够用）
2. **安全阀**：文件整理默认 preview，--apply 才真移
3. **路径**：v4 代码在 `/root/.openclaw/workspace/deepin-agent-teames/`，**不在** `deepin-agent-v4/`
4. **Token 存储**：GitHub PAT 持久化（~/.git-credentials chmod 600），LLM key 不持久化
5. **git push 方式**：直接 push，不用 Git Data API

## 参考

- v3 Python 计划：[plan.md](./plan.md)（归档）
- 6 周时间盒：[drafts/deepin-agent-teams-v4-plan.md](../drafts/deepin-agent-teams-v4-plan.md)（早期草案）