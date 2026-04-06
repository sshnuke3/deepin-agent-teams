# deepin-agent-teams

**多智能体协作系统** — 第十期飞桨黑客松统信 × 百度飞桨 进阶任务 #27

> 在 deepin 25 操作系统上，基于 OpenClaw 多智能体框架和文心大模型 API，实现复杂任务的自动化拆解与协同执行。

## 核心架构

### 两种模式

**可扩展架构（能力驱动）- 推荐**
```
erniebot 分解任务 → Registry 能力匹配 → Worker 自主认领 → 自主执行
                          ↑
            Researcher(注册能力) ←→ Coder(注册能力) ←→ General(注册能力)
```

**多进程架构（固定分工）**
```
Orchestrator → spawn Researcher 子进程 → 独立执行
             → spawn Coder 子进程 → 独立执行
             ↓
        erniebot 整合结果
```

## 快速开始

### 环境要求

- Python 3.10+
- deepin 25 / Ubuntu 20.04+
- 文心大模型 API（AI Studio token）

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
# ERNIEBOT_ACCESS_TOKEN=your_token_here
```

### 运行

```bash
# 交互模式
python main.py -i

# 代码分析演示（分析指定项目）
python main.py --demo code-analysis -p /path/to/project

# 文献综述演示
python main.py --demo literature -f file1.txt file2.txt -q "你的研究问题"

# 单次任务
python main.py "帮我分析 /path/to/project"
```

## 场景演示

### 场景一：代码分析 + 文档生成

输入项目路径，自动完成：
1. Lead Agent 拆解任务
2. Researcher Agent 遍历目录结构
3. Coder Agent 分析核心代码
4. 生成 Markdown 格式项目文档

### 场景二：文献综述助手

输入多个文件 + 研究问题，自动完成：
1. Lead Agent 拆解分析任务
2. Researcher Agent 并行读取文献
3. 提取与研究问题相关的信息
4. 生成结构化综述报告

## Agent 角色

| Agent | 职责 | 核心能力 |
|-------|------|---------|
| **Lead** | 任务拆解 + 结果整合 | 理解高层需求，协调多 Agent |
| **Researcher** | 信息检索 + 文献分析 | 文件读取，内容提取 |
| **Coder** | 代码分析 + 文档生成 | Shell 执行，代码解读 |

## 项目结构

```
deepin-agent-teams/
├── config.py              # 统一配置（API 凭证、Agent 参数）
├── main.py                # 命令行入口
├── requirements.txt       # 依赖列表
├── .env.example           # 环境变量示例
├── .gitignore
├── agents/
│   ├── __init__.py
│   ├── base.py            # BaseAgent 基类（erniebot 封装）
│   ├── lead.py            # Lead Agent（任务拆解 + 结果整合）
│   ├── researcher.py       # Researcher Agent（文献分析 + 文件读取）
│   └── coder.py           # Coder Agent（代码分析 + Shell 执行）
└── scenarios/
    ├── __init__.py
    ├── code_analysis.py    # 场景一：代码分析+文档生成
    └── literature_review.py # 场景二：文献综述助手
```

## 技术栈

- **Agent 框架**: OpenClaw
- **大模型**: 文心大模型（erniebot SDK）
- **编程语言**: Python 3.10+

## 实施进度

| 阶段 | 时间 | 状态 |
|------|------|------|
| 第1周 部署 + 框架 | 4/1-4/7 | ✅ |
| 第2周 Lead+Researcher 协作 | 4/8-4/14 | ✅ |
| 第3周 Coder Agent + 场景一 | 4/15-4/21 | ✅ |
| 第4周 场景二 + Demo | 4/22-4/28 | 🔄 进行中 |
| 第5周 README + 文档 | 4/29-5/5 | ⏳ |

## 参考资料

- [OpenClaw 官方文档](https://docs.openclaw.ai)
- [erniebot SDK](https://github.com/PaddlePaddle/ERNIE-SDK)
- [deepin 25 系统下载](https://www.deepin.org/zh/download/)
- [第十期飞桨黑客松任务合集](https://github.com/PaddlePaddle/community/blob/master/hackathon/hackathon_10th/【Hackathon_10th】文心合作伙伴任务合集.md)
