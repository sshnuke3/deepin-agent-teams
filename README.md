# deepin-agent-teams

**多智能体协作系统** — 第十期飞桨黑客松统信 × 百度飞桨 进阶任务 #27

> 在 deepin 25 操作系统上，基于 OpenClaw 多智能体框架和文心大模型 API，实现复杂任务的自动化拆解与协同执行。

## 核心架构（v4.1 - 推荐）

**Sessions-Spawn 架构（OpenClaw 原生多 Agent）**

```
用户请求
    ↓ erniebot 分解为 capabilities
    ↓
    OpenClaw Agent（在这里执行 sessions_spawn 调用）
    ↓ sessions_spawn
    ├── Researcher 子Agent → OpenClaw 工具：read, web_fetch, search
    ├── Coder 子Agent → OpenClaw 工具：read, exec
    └── General 子Agent → OpenClaw 工具：read, exec, write
    ↓ sessions_send
    子Agent 执行并返回 Markdown 报告
    ↓
    整合最终结果
```

**v4.1 生产级增强**：在 v4 基础上增加超时控制、重试机制、错误隔离、彩色分级日志、完整状态跟踪、优雅降级。

**架构对比：**

| 版本 | 实现方式 | 工具能力 | 推荐场景 |
|------|---------|---------|---------|
| **v4.1（推荐）** | `sessions_spawn` + 生产级增强 | OpenClaw 原生工具 | 生产级多 Agent 协作 |
| v4 | `sessions_spawn` 基础版 | OpenClaw 原生工具 | 快速演示 |
| v3 | Registry + Python Worker | Python 函数 | 能力驱动扩展 |
| v2 | Python subprocess | Python 函数 | 固定分工演示 |

## 快速开始

### 环境要求

- Python 3.10+
- deepin 25 / Ubuntu 20.04+
- 文心大模型 API（AI Studio token）
- OpenClaw（用于 v4 模式）

### 安装

```bash
git clone https://github.com/sshnuke3/deepin-agent-teams.git
cd deepin-agent-teams
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 AI Studio Access Token
```

### 运行

#### v4.1 模式（推荐）- Sessions-Spawn 生产级

```bash
# 分解任务，输出 sessions_spawn 指令（推荐方式）
python agents/sessions_orchestrator_prod.py "分析项目代码结构并生成文档"

# 通过 main.py 调用
python main.py --v41 "分析项目"

# 将输出的 Python 指令复制到 OpenClaw 对话中执行

# 可选参数：
#   --timeout 120      单 Agent 超时秒数（默认 120）
#   --global-timeout 300 全局超时秒数（默认 300）
#   --retry 2          最大重试次数（默认 2）
#   --quiet            静默模式
```

#### v4 模式 - Sessions-Spawn 基础版

```bash
# 分解任务，输出 sessions_spawn 指令
python agents/sessions_orchestrator.py "分析项目代码结构并生成文档"

# 将输出的 Python 指令复制到 OpenClaw 对话中执行
```

#### v3 模式 - 可扩展架构

```bash
python main.py -e "分析项目"
```

#### v2 模式 - 多进程固定分工

```bash
python main.py -m "分析项目"
```

#### v1 模式 - 单进程演示

```bash
python main.py --demo code-analysis
```

## v4 Sessions-Spawn 详解

### 工作原理

1. **任务分解**：erniebot 将用户需求分解为 capabilities
2. **Spawn 子Agent**：`sessions_spawn()` 创建有 OpenClaw 工具的真正子 Agent
3. **分发任务**：`sessions_send()` 向子 Agent 发送具体任务
4. **执行并返回**：子 Agent 用 OpenClaw 工具执行，返回 Markdown 报告

### sessions_spawn 调用示例

```python
sessions_spawn(
    task='''你是 Researcher Agent，在 deepin-agent-teams 中工作。
使用 read/web_fetch/search 工具分析信息，完成后以「[任务完成]」结尾。''',
    label='researcher-1',
    mode='run',
    runTimeoutSeconds=120,
)
```

### sessions_send 调用示例

```python
sessions_send(
    sessionKey='agent:main:subagent:<uuid>',
    message='任务：分析 /path/to/project 的代码结构',
    timeoutSeconds=120,
)
```

## 项目结构

```
deepin-agent-teams/
├── main.py                          # CLI 入口
├── config.py                        # 配置
├── requirements.txt
├── .env.example
├── agents/
│   ├── base.py                      # Agent 基类（erniebot 封装）
│   ├── lead.py                     # Lead Agent
│   ├── researcher.py                # Researcher Agent
│   ├── coder.py                    # Coder Agent
│   ├── registry.py                 # Agent 注册中心（v3）
│   ├── orchestrator.py             # 多进程 Orchestrator（v2）
│   ├── orchestrator_extensible.py # 可扩展 Orchestrator（v3）
│   ├── sessions_orchestrator.py     # Sessions-Spawn 编排器（v4）
│   ├── sessions_orchestrator_prod.py # Sessions-Spawn 生产级编排器（v4.1）⭐
│   ├── worker_v2.py               # 可扩展 Worker（v3）
│   ├── worker_researcher.py       # Researcher 子进程（v2）
│   └── worker_coder.py           # Coder 子进程（v2）
└── scenarios/
    ├── code_analysis.py           # 场景一
    └── literature_review.py        # 场景二
```

## 技术栈

- **Agent 框架**: OpenClaw（sessions_spawn 多 Agent 协作）
- **大模型**: 文心大模型（erniebot SDK）
- **编程语言**: Python 3.10+

## 实施进度

| 阶段 | 时间 | 状态 |
|------|------|------|
| 第1周 部署+框架 | 4/1-4/7 | ✅ |
| 第2周 Lead+Researcher | 4/8-4/14 | ✅ |
| 第3周 Coder+场景一 | 4/15-4/21 | ✅ |
| 第4周 架构重构 | 4/22-4/28 | ✅ |
| 第5周 sessions_spawn v4 | 4/29-5/5 | ✅ |

## 参考资料

- [OpenClaw 文档](https://docs.openclaw.ai)
- [erniebot SDK](https://github.com/PaddlePaddle/ERNIE-SDK)
- [第十期飞桨黑客松任务](https://github.com/PaddlePaddle/community/blob/master/hackathon/hackathon_10th/【Hackathon_10th】文心合作伙伴任务合集.md)
