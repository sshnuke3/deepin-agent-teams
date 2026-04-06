# deepin-agent-teams RFC

## 项目概述

**名称**: deepin-agent-teams
**任务**: 第十期飞桨黑客松统信 × 百度飞桨 进阶任务 #27
**目标**: 在 deepin 25 上基于 OpenClaw 多智能体框架和文心大模型，实现复杂任务的自动化拆解与协同执行

## 架构演进

### v1（废弃）- 假多 Agent
- 三个 Python class，串行 LLM 调用链
- 本质：串行 LLM 调用链

### v2（多进程）- 固定分工
- Orchestrator spawn 独立子进程
- 固定：researcher 读文件 / coder 分析代码
- 问题：分工硬编码，扩展需改代码

### v3（可扩展）- Registry 驱动
- AgentRegistry: 能力注册中心 + 任务队列
- fcntl.flock 并发安全
- Worker 从 Registry 自主认领任务
- 能力：file_reader/dir_scanner/code_analyzer 等 Python 函数

### v4（sessions_spawn）- OpenClaw 原生 当前版本
- sessions_spawn 创建真正的 OpenClaw 子 Agent
- 子 Agent 有 OpenClaw 原生工具：read, exec, web_fetch
- 有 LLM 推理能力，有 system prompt 上下文

```
Orchestrator（OpenClaw Agent）
    ↓ sessions_spawn
    ├── Researcher 子Agent → OpenClaw 工具：read, web_fetch, search
    ├── Coder 子Agent → OpenClaw 工具：read, exec
    └── General 子Agent → OpenClaw 工具：read, exec, write
    ↓ sessions_send
    子Agent 执行并返回 Markdown 报告
```

## 验证记录

### sessions_spawn 演示（2026-04-06）
- main Agent spawn 2 个子 Agent（Researcher + Coder）
- sessions_spawn 成功返回 childSessionKey
- sessions_send 分发任务并获取 Markdown 报告
- Researcher 返回：项目结构分析
- Coder 返回：深度代码分析（类/函数/依赖/设计模式）
- 状态：完全通过

## 代码结构

```
deepin-agent-teams/
├── main.py                          # CLI 入口
├── config.py                        # 配置
├── agents/
│   ├── base.py                      # Agent 基类（erniebot 封装）
│   ├── lead.py                     # Lead Agent
│   ├── researcher.py                # Researcher Agent
│   ├── coder.py                    # Coder Agent
│   ├── registry.py                 # Agent 注册中心（v3）
│   ├── orchestrator.py            # 多进程 Orchestrator（v2）
│   ├── orchestrator_extensible.py # 可扩展 Orchestrator（v3）
│   ├── sessions_orchestrator.py   # Sessions-Spawn 编排器（v4）
│   ├── worker_v2.py              # 可扩展 Worker（v3）
│   ├── worker_researcher.py       # Researcher 子进程（v2）
│   └── worker_coder.py           # Coder 子进程（v2）
└── scenarios/
    ├── code_analysis.py           # 场景一
    └── literature_review.py      # 场景二
```

## 实施进度

| 阶段 | 时间 | 状态 |
|------|------|------|
| 第1周 部署+框架 | 4/1-4/7 | 完成 |
| 第2周 Lead+Researcher | 4/8-4/14 | 完成 |
| 第3周 Coder+场景一 | 4/15-4/21 | 完成 |
| 第4周 架构重构 | 4/22-4/28 | 完成 |
| 第5周 sessions_spawn v4 | 4/29-5/5 | 完成 |
