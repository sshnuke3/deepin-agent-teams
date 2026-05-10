# 架构文档

## 项目概述

deepin Agent Teams 是运行在 deepin 25 操作系统上的多智能体协作系统，基于文心大模型 API。

## 模块结构

```
deepin-agent-teams/
├── main.py                    # CLI 入口 + GUI 入口
├── config.py                  # 全局配置（模型、路径、参数）
├── model_router.py            # 双模型路由器（ernie-lite / ernie-3.5）
│
├── perception/                # 环境感知层
│   ├── screen_capture.py      # 屏幕截图（Pillow）
│   ├── screen_ocr.py          # OCR 文字识别（PaddleOCR）
│   ├── clipboard_monitor.py   # 剪贴板监控
│   ├── window_manager.py      # 窗口信息获取
│   ├── context_engine.py      # 上下文融合引擎
│   ├── behavior_tracker.py    # 行为序列追踪器
│   ├── resource_guard.py      # 资源占用控制器
│   ├── privacy_guard.py       # 隐私保护机制
│   └── deepin_dbus.py         # deepin D-Bus 接口对接
│
├── agents/                    # 智能体层
│   ├── base.py                # Agent 基类（接入 model_router）
│   ├── lead.py                # Lead（总调度，强模型）
│   ├── coder.py               # Coder
│   ├── researcher.py          # Researcher（lite 模型）
│   ├── content_creator.py     # Content Creator（强模型）
│   ├── information_collector.py # Information Collector（强模型）
│   ├── system_operator.py     # System Operator
│   ├── orchestrator.py        # 协同编排器 v1
│   ├── orchestrator_extensible.py # 可扩展编排器
│   ├── conflict_resolver.py   # 冲突解决器
│   ├── registry.py            # Agent 注册中心
│   ├── sessions_orchestrator.py   # 会话编排器
│   ├── sessions_orchestrator_prod.py # 生产会话编排器
│   └── worker_base.py         # Worker 基类
│
├── scenarios/                 # 场景层
│   ├── email_assistant.py     # 场景一：智能邮件助手
│   ├── system_doctor.py       # 场景二：系统诊断修复
│   ├── code_analysis.py       # 场景三：代码分析
│   └── literature_review.py   # 场景四：文献阅读
│
├── tools/                     # 工具层
│   └── mcp_adapter.py         # MCP 工具适配器
│
├── skills/                    # 技能库
│   └── __init__.py            # Skills 注册中心
│
└── gui/                       # 图形界面层
    ├── main_gui.py            # GUI 主入口
    ├── floating_ball.py       # 悬浮球
    ├── chat_window.py         # 对话窗口
    ├── tray_icon.py           # 系统托盘
    └── styles.py              # 深色主题样式
```

## 数据流

```
用户操作
  ↓
[感知层] 屏幕截图 → OCR → 窗口信息 → 剪贴板
  ↓
[上下文引擎] 多源融合 → 意图识别 → 行为预测
  ↓
[编排器] 任务拆解 → Agent 分配 → 冲突检测
  ↓
[Agent 执行] 调用工具/MCP → 生成结果
  ↓
[场景层] 邮件助手 / 系统诊断 / 代码分析 / 文献阅读
  ↓
[GUI] 悬浮球 → 对话窗口 → 系统托盘通知
```

## 关键设计决策

1. **双模型路由**：ernie-lite（快/便宜）处理轻量任务，ernie-3.5（强/贵）处理复杂任务，强模型失败自动降级
2. **多轮对话**：场景层维护 `_clarification_pending` 状态，支持意图澄清后继续流程
3. **行为追踪**：记录窗口切换/剪贴板变化，基于模式预测下一步操作
4. **隐私保护**：6 类敏感数据检测 + 自动脱敏 + 审计日志
