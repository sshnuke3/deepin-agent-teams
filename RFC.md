## 架构演进

### v1（假多 Agent）- 废弃
- 三个 Python class，共享 erniebot 调用
- 本质：串行 LLM 调用链

### v2（多进程）- 固定分工
- Orchestrator spawn 独立子进程
- 固定：researcher 读文件 / coder 分析代码
- 问题：分工硬编码，扩展需改代码

### v3（可扩展架构）- 当前版本
- **AgentRegistry**: 能力注册中心 + 任务队列
  - fcntl.flock 并发安全
  - 任务 submit → claim → complete 流程
- **worker_v2.py**: 可扩展 Worker
  - 启动时注册 capabilities
  - 从 Registry 自主认领任务
  - 13 种能力：file_reader/dir_scanner/code_analyzer/ast_parser/syntax_checker/dependency_analyzer/shell_executor/git_analyzer/web_search/web_fetcher/markdown_writer 等
- **orchestrator_extensible.py**: 能力驱动编排
  - erniebot 分解为 capabilities（不指定谁执行）
  - Worker 自主认领（基于能力匹配）
  - 真正自主分工

### 技术架构图

```
┌─────────────────────────────────────────────┐
│         ExtensibleOrchestrator               │
│  erniebot 分解 → submit_task(Registry)      │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│              AgentRegistry                   │
│  Worker 注册 (capabilities)                 │
│  任务队列 (submit / claim / complete)      │
│  文件锁 (fcntl.flock)                      │
└─────────────────────────────────────────────┘
         ↑                    ↑              ↑
    researcher           coder          general
    [file_reader,     [code_analyzer, [dir_scanner,
     dir_scanner,      ast_parser,     code_analyzer,
     web_search]      shell_exec]     shell_exec]

Worker 自主认领任务，自主选择能力执行
```

## 七、提交物清单

- [x] agents/orchestrator.py - 多进程调度器（v2 固定分工）
- [x] agents/orchestrator_extensible.py - 可扩展编排器（v3 能力驱动）
- [x] agents/registry.py - Agent 注册中心 + 任务队列
- [x] agents/worker_v2.py - 可扩展 Worker（Registry 模式）
- [x] agents/worker_researcher.py - Researcher 子进程（兼容 v2）
- [x] agents/worker_coder.py - Coder 子进程（兼容 v2）
- [x] README.md

## 实施进度

| 阶段 | 状态 | 说明 |
|------|------|------|
| 第1-2周 | ✅ | Agent 框架 + 场景演示 |
| 第3-4周 | ✅ | 架构重构：多进程 → 可扩展 |
| 第5周 | 🔄 进行中 | 演示材料整理 |

## 演示验证

### v3 可扩展架构演示
- 3 Worker 并行注册到 Registry
- erniebot 分解为 capabilities（不指定执行者）
- general Worker 自主认领 shell_executor 任务
- Worker 自主执行，Registry 协调结果
- 状态：✅ 通过

