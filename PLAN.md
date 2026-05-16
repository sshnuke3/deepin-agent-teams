# deepin-agent-teams 黑客松实现规划

> 第十期飞桨黑客松 - 统信×deepin Agent Teams 进阶任务 #27
> 规划时间：2026-04-28 | 答辩：2026年6月

---

## 当前状态（2026-05-16 更新）

| 模块 | 状态 | 说明 |
|------|------|------|
| v4.1 sessions_spawn 框架 | ✅ 完成 | 667行生产级编排器 |
| 多 Agent 协同架构 | ✅ 完成 | Lead + Researcher + Coder |
| 环境感知层 perception/ | ✅ 完成 | 7个模块，deepin 25 验证通过(34/34) |
| 3个专业 Agent | ✅ 完成 | SystemOperator / InformationCollector / ContentCreator |
| 场景一：智能邮件助手 | ✅ 完成 | EmailAssistant |
| 场景二：系统问题诊断 | ✅ 完成 | SystemDoctor |
| 场景三：代码分析助手 | ✅ 完成 | CodeAnalysisAssistant |
| 场景四：文献阅读助手 | ✅ 完成 | LiteratureAssistant |
| deepin 系统适配 | ✅ 完成 | D-Bus/wmctrl/xclip 全部验证通过 |
| PaddleOCR 感知 | ✅ 完成 | 实体机验证可用 |
| 演示视频 | ✅ 完成 | 已录制+字幕(157秒) |
| 技术报告 | ✅ 完成 | TECHNICAL_REPORT.md |
| 赛题完成度自查 | ✅ 完成 | CHECKLIST.md |

---

## 总体架构

```
用户操作（deepin桌面）
    ↓ 环境感知层（perception/）
┌─────────────────────────────────┐
│   🎯 意图识别引擎               │
│   - 窗口标题 / 剪贴板 / 屏幕上下文 │
│   - 关键词匹配 + 置信度计算      │
└─────────────────────────────────┘
    ↓ 任务分类 + Agent 调度
┌──────────┬──────────┬──────────┐
│ 系统操作员 │ 信息收集员 │ 内容创作员 │
│(SystemOp)│(InfoColl)│(ContCre)│
└──────────┴──────────┴──────────┘
    ↓ 协同执行 + 结果汇总
    ↓ 工具调用（deepin API / bash / systemctl）
```

---

## 4个场景（统一自包含模式）

所有场景遵循统一架构：
```
detect_intent() → collect_context() → process → generate_output() → handle_command()
```

### 场景一：智能邮件助手 `email_assistant.py`（409行）
- **意图识别**：邮件关键词检测 + 收件人/主题提取
- **上下文收集**：剪贴板/文件系统/当前窗口
- **邮件生成**：ContentCreator 生成结构化邮件
- **发送**：Thunderbird / mailx / 文件输出

### 场景二：系统问题诊断 `system_doctor.py`（376行）
- **问题分类**：声音/网络/打印/蓝牙/安装（5类关键词匹配）
- **协同诊断**：SystemOperator 执行 systemctl/诊断命令
- **修复方案**：自动生成修复计划 + 执行确认
- **反馈**：修复结果反馈给用户

### 场景三：代码分析助手 `code_analysis.py`（410行）
- **意图识别**：代码分析关键词 + 路径检测
- **项目扫描**：InformationCollector 收集项目结构
- **核心分析**：ContentCreator 分析核心代码文件
- **报告生成**：结构化项目分析报告

### 场景四：文献阅读助手 `literature_review.py`（430行）
- **意图识别**：文献/论文关键词 + 文件路径检测
- **文献读取**：支持 PDF/TXT/DOCX
- **关键提取**：ContentCreator 提取各文献核心信息
- **综述生成**：对比分析 + 结构化综述报告

---

## 环境感知层（perception/）

### 模块清单
| 模块 | 功能 | 状态 |
|------|------|------|
| `screen_capture.py` | 屏幕截图（grim/scrot） | ✅ 代码完成 |
| `clipboard_monitor.py` | 剪贴板监控（xclip） | ✅ 代码完成 |
| `window_manager.py` | 窗口管理（wmctrl/xdotool） | ✅ 代码完成 |
| `system_monitor.py` | 系统监控（systemctl/诊断） | ✅ 代码完成 |
| `deepin_dbus.py` | deepin D-Bus 接口 | ✅ 代码完成 |
| `screen_ocr.py` | OCR 识别（PaddleOCR） | ✅ 代码完成 |
| `context_engine.py` | 上下文引擎（意图识别） | ✅ 代码完成 |

### 实体机验证脚本
```bash
# 在 deepin 25 实体机上
bash deepin25_deploy.sh                           # 一键部署
python3 tests/test_perception_deepin25.py          # 运行测试
# 结果文件: tests/test_results_TIMESTAMP.json
# 拷回本机分析:
python3 tests/analyze_results.py tests/test_results_*.json
```

---

## 时间安排（2026-05-16 更新：所有任务已完成）

| 周 | 时间 | 任务 | 状态 |
|----|------|------|------|
| 第1周 | 4/1-4/7 | 部署+框架 | ✅ |
| 第2周 | 4/8-4/14 | Lead+Researcher | ✅ |
| 第3周 | 4/15-4/21 | Coder+场景一 | ✅ |
| 第4周 | 4/22-4/28 | 架构重构+场景扩展 | ✅ |
| 第5周 | 4/29-5/5 | sessions_spawn v4 | ✅ |
| 第6周 | 5/6-5/12 | 感知层+GUI完善 | ✅ |
| 第7-8周 | 5/13-5/26 | 场景联动+实体机验证 | ✅ |
| 第9-10周 | 5/27-6/9 | 演示+提交 | ✅ 完成 |

---

## 文件结构（当前）

```
deepin-agent-teams/
├── main.py                          # CLI 入口（4个场景演示）
├── config.py                        # 配置
├── deepin_agent.py                  # Agent 入口
├── deepin25_deploy.sh               # 🆕 deepin25 部署脚本
├── requirements.txt
├── PLAN.md                          # 本文件
├── RFC.md                           # 项目 RFC
├── README.md                        # 项目说明
├── perception/                      # 环境感知层（8个模块）
│   ├── __init__.py
│   ├── screen_capture.py            # 屏幕截图
│   ├── clipboard_monitor.py         # 剪贴板监控
│   ├── window_manager.py            # 窗口管理
│   ├── system_monitor.py            # 系统监控
│   ├── deepin_dbus.py               # deepin D-Bus
│   ├── screen_ocr.py                # OCR 识别
│   └── context_engine.py            # 上下文引擎
├── agents/                          # Agent 模块
│   ├── base.py                      # Agent 基类
│   ├── lead.py                      # Lead Agent
│   ├── researcher.py                # Researcher Agent
│   ├── coder.py                     # Coder Agent
│   ├── system_operator.py           # 系统操作员
│   ├── information_collector.py     # 信息收集员
│   ├── content_creator.py           # 内容创作员
│   ├── sessions_orchestrator_prod.py # 生产级编排器
│   └── ...
├── scenarios/                       # 4个场景（统一自包含模式）
│   ├── __init__.py
│   ├── email_assistant.py           # 场景一：智能邮件助手
│   ├── system_doctor.py             # 场景二：系统问题诊断
│   ├── code_analysis.py             # 场景三：代码分析助手
│   └── literature_review.py         # 场景四：文献阅读助手
├── tests/                           # 测试脚本
│   ├── test_perception_deepin25.py  # 感知层测试（deepin25 实体机）
│   └── analyze_results.py           # 测试结果分析
└── docs/
    └── ...
```

---

## 关键风险

| 风险 | 影响 | 应对 |
|------|------|------|
| deepin 实体机不可用 | 感知层无法验证 | 优先级最高的阻塞项 |
| PaddleOCR 性能差 | OCR 响应慢 | 限制识别区域，不用全屏 |
| 中期检查来得早 | 场景还没联动 | 优先跑通场景一可演示版本 |
| D-Bus 接口不稳定 | 系统控制失败 | 降级为 bash 命令执行 |

---

## 快速启动

```bash
# deepin 25 实体机部署
bash deepin25_deploy.sh

# 运行演示
python main.py -d all                    # 所有场景
python main.py -d email                  # 邮件助手
python main.py -d doctor                 # 系统诊断
python main.py -d code-analysis -p .     # 代码分析
python main.py -d literature -f a.pdf    # 文献阅读
python main.py -i                        # 交互模式

# 感知层测试
python3 tests/test_perception_deepin25.py
```
