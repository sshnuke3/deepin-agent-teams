# deepin-agent-teams

**多智能体协作系统** — 第十期飞桨黑客松统信 × 百度飞桨 进阶任务 #27

> 在 deepin 25 操作系统上，基于 OpenClaw 多智能体框架和文心大模型 API，实现复杂任务的自动化拆解与协同执行。

## 核心架构

```
用户请求（自然语言）
    ↓ 环境感知层（perception/）
    ↓ 意图识别（关键词 + 置信度）
    ↓
┌──────────────────────────────────────────┐
│           🎯 场景路由器                   │
│  邮件? → EmailAssistant                  │
│  系统? → SystemDoctor                    │
│  代码? → CodeAnalysisAssistant           │
│  文献? → LiteratureAssistant             │
└──────────────────────────────────────────┘
    ↓ 任务拆分 + Agent 调度
┌──────────┬──────────┬──────────┐
│ 系统操作员 │ 信息收集员 │ 内容创作员 │
│(SystemOp)│(InfoColl)│(ContCre)│
└──────────┴──────────┴──────────┘
    ↓ 协同执行 + 结果汇总
```

## 4个场景（统一自包含模式）

所有场景遵循统一架构：`detect_intent → collect_context → process → generate_output → handle_command`

| 场景 | 文件 | 行数 | 功能 |
|------|------|------|------|
| 📧 场景一 | `email_assistant.py` | 409 | 智能邮件助手：意图识别→上下文收集→邮件生成→发送确认 |
| 🩺 场景二 | `system_doctor.py` | 376 | 系统问题诊断：问题分类→多Agent诊断→自动修复 |
| 🔍 场景三 | `code_analysis.py` | 410 | 代码分析助手：路径检测→项目扫描→核心分析→报告生成 |
| 📚 场景四 | `literature_review.py` | 430 | 文献阅读助手：文件检测→文献读取→关键提取→综述生成 |

## 快速开始

### 环境要求

- Python 3.10+
- deepin 25 / Ubuntu 20.04+
- 文心大模型 API（AI Studio token）

### 安装

```bash
git clone https://github.com/sshnuke3/deepin-agent-teams.git
cd deepin-agent-teams

# deepin 25 一键部署（推荐）
bash deepin25_deploy.sh

# 或手动安装
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 AI Studio Access Token
```

### 运行演示

```bash
# 所有场景批量演示
python main.py -d all

# 单个场景演示
python main.py -d email                              # 邮件助手
python main.py -d doctor                             # 系统诊断
python main.py -d code-analysis -p /path/to/project  # 代码分析
python main.py -d literature -f a.pdf b.pdf -q 问题  # 文献阅读

# 交互模式（支持所有4个场景自动路由）
python main.py -i

# v4.1 生产级模式（sessions_spawn）
python main.py --v41 "分析项目"
```

## 环境感知层（perception/）

| 模块 | 功能 |
|------|------|
| `screen_capture.py` | 屏幕截图（grim/scrot） |
| `clipboard_monitor.py` | 剪贴板监控（xclip） |
| `window_manager.py` | 窗口管理（wmctrl/xdotool） |
| `system_monitor.py` | 系统监控（systemctl/诊断） |
| `deepin_dbus.py` | deepin D-Bus 接口 |
| `screen_ocr.py` | OCR 识别（PaddleOCR） |
| `context_engine.py` | 上下文引擎（意图识别） |

### 实体机测试

```bash
# 在 deepin 25 实体机上运行
python3 tests/test_perception_deepin25.py

# 结果文件: tests/test_results_TIMESTAMP.json
# 拷回本机分析:
python3 tests/analyze_results.py tests/test_results_*.json
```

## 项目结构

```
deepin-agent-teams/
├── main.py                          # CLI 入口
├── config.py                        # 配置
├── deepin_agent.py                  # Agent 入口
├── deepin25_deploy.sh               # deepin25 部署脚本
├── requirements.txt
├── perception/                      # 环境感知层
│   ├── screen_capture.py            # 屏幕截图
│   ├── clipboard_monitor.py         # 剪贴板监控
│   ├── window_manager.py            # 窗口管理
│   ├── system_monitor.py            # 系统监控
│   ├── deepin_dbus.py               # D-Bus 接口
│   ├── screen_ocr.py                # OCR 识别
│   └── context_engine.py            # 上下文引擎
├── agents/                          # Agent 模块
│   ├── system_operator.py           # 系统操作员
│   ├── information_collector.py     # 信息收集员
│   ├── content_creator.py           # 内容创作员
│   ├── sessions_orchestrator_prod.py # 生产级编排器
│   └── ...
├── scenarios/                       # 4个场景
│   ├── email_assistant.py           # 场景一：智能邮件助手
│   ├── system_doctor.py             # 场景二：系统问题诊断
│   ├── code_analysis.py             # 场景三：代码分析助手
│   └── literature_review.py         # 场景四：文献阅读助手
└── tests/                           # 测试脚本
    ├── test_perception_deepin25.py  # 感知层测试
    └── analyze_results.py           # 结果分析
```

## 技术栈

- **Agent 框架**: OpenClaw（sessions_spawn 多 Agent 协作）
- **大模型**: 文心大模型（erniebot SDK）
- **编程语言**: Python 3.10+
- **OCR**: PaddleOCR
- **目标系统**: deepin 25

## 实施进度

| 阶段 | 时间 | 状态 |
|------|------|------|
| 第1周 部署+框架 | 4/1-4/7 | ✅ |
| 第2周 Lead+Researcher | 4/8-4/14 | ✅ |
| 第3周 Coder+场景一 | 4/15-4/21 | ✅ |
| 第4周 架构重构+场景扩展 | 4/22-4/28 | ✅ |
| 第5周 感知层实体机验证 | 4/29-5/5 | 🔄 进行中 |
| 第6-8周 场景联动+集成 | 5/6-5/26 | ❌ |
| 第9-10周 录屏+提交 | 5/27-6/9 | ❌ |

## 参考资料

- [OpenClaw 文档](https://docs.openclaw.ai)
- [erniebot SDK](https://github.com/PaddlePaddle/ERNIE-SDK)
- [第十期飞桨黑客松任务](https://github.com/PaddlePaddle/community/blob/master/hackathon/hackathon_10th/【Hackathon_10th】文心合作伙伴任务合集.md)
