# 文心伙伴赛道-进阶双周报

**邮件标题格式：** 文心伙伴赛道-【统信】-进阶双周报-【sshnuke3】-0514

---

### 认领者 GitHub ID
sshnuke3

### 赛题信息
- **进阶任务序号**：#27
- **赛题名称**：基于统信操作系统与文心大模型的多智能体协作系统
- **关联厂商**：统信软件

### 本期工作（2026.04.28 ~ 2026.05.11）

#### 1. v4.1 生产级多 Agent 编排器上线
- 新增 `agents/sessions_orchestrator_prod.py`（约550行），基于 OpenClaw 原生 `sessions_spawn` 实现生产级多 Agent 协作
- 核心能力升级：
  - **超时控制**：每个子 Agent 设置独立超时，避免任务挂死
  - **重试机制**：失败任务自动重试，支持指数退避
  - **错误隔离**：单个 Agent 崩溃不影响整体流水线
  - **彩色分级日志**：DEBUG/INFO/WARN/ERROR 四级日志，终端可读性大幅提升
  - **状态跟踪**：完整记录每个 Agent 的执行状态和输出
  - **优雅降级**：非关键 Agent 失败时，系统自动降级继续执行
- 相关提交：https://github.com/sshnuke3/deepin-agent-teams/commits/main （4月28日 8 commits）

#### 2. 四大场景模块完善
- **场景一：智能邮件助手** (`email_assistant.py`, 409行)
  - 意图识别 → 上下文收集 → 邮件生成 → 发送确认 全链路
- **场景二：系统问题诊断** (`system_doctor.py`, 376行)
  - 问题分类 → 多 Agent 协同诊断 → 自动修复建议
- **场景三：代码分析助手** (`code_analysis.py`, 410行)
  - 路径检测 → 项目扫描 → 核心分析 → 报告生成
- **场景四：文献阅读助手** (`literature_review.py`, 430行)
  - 文件检测 → 文献读取 → 关键信息提取 → 综述生成

#### 3. 感知层模块开发（deepin 25 适配）
- `perception/screen_capture.py` — 屏幕截图（grim/scrot）
- `perception/clipboard_monitor.py` — 剪贴板监控（xclip）
- `perception/window_manager.py` — 窗口管理（wmctrl/xdotool）
- `perception/system_monitor.py` — 系统监控（systemctl/诊断）
- `perception/deepin_dbus.py` — deepin D-Bus 接口对接
- `perception/screen_ocr.py` — OCR 识别（PaddleOCR）
- `perception/context_engine.py` — 上下文引擎（意图识别 + 置信度）

#### 4. GUI 交互界面（5月10日新增）
- 新增 `gui/` 模块（917行，PyQt5），满足赛题"唯一用户交互界面"要求
- **悬浮球** (`floating_ball.py`)：常驻桌面右下角，支持拖拽，松手自动吸附屏幕边缘（带弹性动画）
- **对话窗口** (`chat_window.py`)：左侧场景切换（邮件/诊断/代码/文献），右侧消息气泡流，Enter 发送
- **系统托盘** (`tray_icon.py`)：龙虾图标常驻托盘，右键菜单，系统通知推送
- **deepin 风格样式** (`styles.py`)：圆角+半透明+主题蓝配色，模拟 deepin 25 UI 风格
- Agent 执行放 QThread 后台线程，不阻塞 UI
- 启动方式：`python main.py --gui`
- 相关提交：https://github.com/sshnuke3/deepin-agent-teams/commit/23e708e

#### 5. 部署与测试
- 编写 `deepin25_deploy.sh` 一键部署脚本
- 编写 `tests/test_perception_deepin25.py` 感知层实体机测试脚本
- 测试结果输出为 JSON 格式，配套 `tests/analyze_results.py` 分析工具

### 下周计划

1. **场景联动集成测试**：在 deepin 25 实体机上跑通"用户自然语言 → 场景路由 → 多 Agent 协作 → 结果输出"完整链路
2. **双模型路由**：申请新 AI Studio token，实现 ernie-lite（轻量任务）+ ernie-3.5（复杂任务）双模型调度
3. **演示视频录制**：录制四大场景 + GUI 交互的演示视频
4. **RFC 文档完善**：补充架构设计文档和技术选型说明

### 当前阻塞

- **ERNIE Bot API 额度**：ernie-3.5 模型额度已耗尽，目前使用 ernie-lite 模型，正在申请新 token 以满足"至少调用两款文心大模型 API"的赛题要求
- **deepin 25 实体机**：感知层测试和视频录制需要 deepin 25 实体机环境

### 交付物进展

| 交付物 | 状态 | 备注 |
|--------|:----:|------|
| RFC 文档 | 🔄 进行中 | 架构设计已完成，需补充技术选型说明 |
| 代码实现 | ✅ 已完成 | v4.1 生产级编排器 + 4场景 + 感知层 + GUI |
| README | 🔄 进行中 | 基础文档已有，需完善架构图和使用说明 |
| 演示视频/截图 | ⬜ 未开始 | 计划下周录制 |

### 项目架构概览

```
deepin-agent-teams/
├── main.py                    # CLI 入口（支持 -d all/-i/--v41/--gui）
├── config.py                  # 配置管理
├── deepin_agent.py            # Agent 主入口
├── deepin25_deploy.sh         # deepin 25 一键部署
├── gui/                       # GUI 模块（PyQt5）
│   ├── floating_ball.py       # 悬浮球（拖拽+边缘吸附+动画）
│   ├── chat_window.py         # 对话窗口（场景切换+消息气泡+后台Agent线程）
│   ├── tray_icon.py           # 系统托盘（龙虾图标+右键菜单+通知）
│   ├── styles.py              # deepin 风格样式
│   └── main_gui.py            # GUI 入口
├── perception/                # 环境感知层（7个模块）
│   ├── screen_capture.py      # 屏幕截图
│   ├── clipboard_monitor.py   # 剪贴板监控
│   ├── window_manager.py      # 窗口管理
│   ├── system_monitor.py      # 系统监控
│   ├── deepin_dbus.py         # D-Bus 接口
│   ├── screen_ocr.py          # OCR 识别
│   └── context_engine.py      # 上下文引擎
├── agents/                    # Agent 模块
│   ├── sessions_orchestrator_prod.py  # v4.1 生产级编排器
│   ├── system_operator.py     # 系统操作员
│   ├── information_collector.py # 信息收集员
│   └── content_creator.py     # 内容创作员
├── scenarios/                 # 4个场景
│   ├── email_assistant.py     # 智能邮件助手
│   ├── system_doctor.py       # 系统问题诊断
│   ├── code_analysis.py       # 代码分析助手
│   └── literature_review.py   # 文献阅读助手
└── tests/                     # 测试脚本
    ├── test_perception_deepin25.py
    └── analyze_results.py
```

### 技术栈

| 组件 | 技术选型 |
|------|---------|
| Agent 框架 | OpenClaw（sessions_spawn 多 Agent 协作） |
| 大模型 | 文心大模型（erniebot SDK，ernie-lite） |
| GUI | PyQt5（悬浮球+对话窗口+系统托盘） |
| 编程语言 | Python 3.10+ |
| OCR | PaddleOCR |
| 目标系统 | deepin 25 |

### 项目进度对照

| 阶段 | 时间 | 计划状态 | 实际状态 |
|------|------|---------|---------|
| 第1周 部署+框架 | 3/31-4/7 | ✅ | ✅ |
| 第2周 Lead+Researcher | 4/8-4/14 | ✅ | ✅ |
| 第3周 Coder+场景一 | 4/15-4/21 | ✅ | ✅ |
| 第4周 架构重构+场景扩展 | 4/22-4/28 | ✅ | ✅ |
| 第5周 感知层实体机验证 | 4/29-5/5 | 🔄 | 🔄 |
| 第6-8周 场景联动+集成 | 5/6-5/26 | ❌ | 🔄 进行中 |
| 第9-10周 录屏+提交 | 5/27-6/9 | ❌ | ⬜ |
