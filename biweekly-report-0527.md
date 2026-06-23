# 文心伙伴赛道-进阶双周报（第2期）

**邮件标题格式：** 文心伙伴赛道-【统信】-进阶双周报-【sshnuke3】-0527

---

### 认领者 GitHub ID
sshnuke3

### 赛题信息
- **进阶任务序号**：#27
- **赛题名称**：基于统信操作系统与文心大模型的多智能体协作系统
- **关联厂商**：统信软件

### 本期工作（2026.05.12 ~ 2026.05.27）

#### 1. deepin 25 实体机验证（5月16日）✅
- 在 deepin 25 实体机上完成感知层全量测试
- **测试结果：34/34 全部通过**
- 验证内容：屏幕截图、OCR识别、窗口管理、剪贴板监控、系统监控、D-Bus 接口、上下文引擎、行为追踪等全部感知模块
- 测试脚本兼容性修复：WindowInfo 序列化、intent 方法、pulseaudio 兼容
- venv 安装修复 + pip 镜像加速
- 相关提交：`933c9a3` `30e8d93` `a50bb60` `85668f9`

#### 2. 演示视频录制（5月16日）✅
- 录制演示视频 `deepin_demo.mp4`（5.8MB，157秒）
- 配套编写 `DEMO_RECORDING_GUIDE.md` 录制指南
- 相关提交：`864a1df`

#### 3. 技术报告完成（5月16日）✅
- 完成多模态融合意图识别 + 多智能体动态编排的技术报告
- 新增赛题完成度自查清单 `CHECKLIST.md`，逐项对照赛题要求
- 更新 PLAN.md 和 README 进度状态为全部完成
- 相关提交：`5c5db64` `baaa6e8` `16e50ad`

#### 4. P0 核心架构补完 — 状态机引擎 + Verifier + orchestrator_v3（5月22日）✅
- **状态机引擎** (`agents/task_state_machine.py`, 359行)
  - 7 种任务状态：PENDING → CLAIMED → RUNNING → VERIFIED → COMPLETED / FAILED / RETRY
  - 所有跳转条件用代码写死，不依赖模型主观判断
  - 每次跳转写 trace → `data/traces/{task_id}.jsonl`
  - 单元测试 5/5 通过
- **独立 Verifier** (`agents/verifier.py`, 332行)
  - 不读 Worker 上下文，完全独立世界观
  - 验收标准是清单（checklist），不是模型主观判断
  - 决策只有三种：PASS / FAIL(causes[]) / RETRY(cause)
  - 4 项检查：deliverable_exists / functional_correctness / trace_integrity / error_free
  - 单元测试 6/6 通过
- **orchestrator_v3** (`agents/orchestrator_v3.py`, 396行)
  - 集成状态机 + Verifier 的生产级编排器
  - 完整流程：decompose → submit → claim → run → verify → integrate
  - 失败自动重试（≤3次），超时自动 FAILED
  - 替代旧版 orchestrator v1/v2（已删除）
- 相关提交：`048cdcb` `d0c9d3b`

#### 5. P1 系统可靠性 — 能力补坑 + Checkpoint + Trace（5月22日）✅
- **能力实现补坑**：web_search + web_fetcher 集成到 worker_base.py
- **Checkpoint 恢复机制** (`tools/checkpoint_manager.py`, 262行)
  - 任务中断后从 checkpoint 恢复，不整体重来
  - 自动保存中间状态到磁盘
- **Trace 分析工具** (`tools/analyze_traces.py`, 184行)
  - 分析 `data/traces/` 下的任务执行轨迹
  - 支持统计成功率、耗时分布、失败原因
- 相关提交：`e5409ed`

#### 6. P2 长期积累 — 双文心模型路由 + 能力分析（5月22日）✅
- **双文心模型路由器** (`agents/model_router.py`, 361行)
  - 轻量任务（意图识别/摘要/分类）→ **ernie-lite**
  - 复杂任务（代码分析/诊断/邮件生成/文献综述）→ **ernie-3.5**
  - 路由表遵循 config.py MODEL_ROUTING，支持 13 种任务类型
  - 满足赛题要求"至少调用两款文心大模型 API"
- **能力分析工具** (`tools/analyze_capabilities.py`, 273行)
  - 分析 Agent 能力覆盖情况
  - 输出能力矩阵和缺口报告
- 相关提交：`3787687`

#### 7. 文档全面同步（5月22日）✅
- README.md 重写（适配 v3 架构）
- docs/ARCHITECTURE.md 大幅扩展（+247行）
- docs/QUALITY.md 完善（+203行）
- docs/TECH_DECISIONS.md 新增（+58行）
- OPTIMIZATION_PLAN.md 优化执行计划（P0/P1/P2 全部标记完成）
- 相关提交：`b7dc77c` `129ad8f`

#### 8. GitHub 仓库同步 ✅
- 本地 main 分支与 origin/main 完全同步（commit `129ad8f`）
- 新 GitHub token 已配置并验证 push 成功
- 远程仓库：https://github.com/sshnuke3/deepin-agent-teams

### 本期代码变更统计

| 指标 | 数值 |
|------|------|
| 新增文件 | 12 个 |
| 删除文件 | 2 个（旧编排器） |
| 新增行数 | +3,256 行 |
| 删除行数 | -987 行 |
| 净增行数 | +2,269 行 |
| 涉及模块 | agents/ tools/ docs/ media/ |

### 当前阻塞

| 阻塞项 | 严重程度 | 状态 | 说明 |
|--------|---------|------|------|
| ernie-3.5 token | 🟡 中 | 待申请 | 主力模型已配置为 ernie-lite（轻量）+ ernie-3.5（复杂），ernie-3.5 token 耗尽时自动降级到 ernie-lite |

### 赛题双模型满足说明

- **赛题要求**：至少调用两款文心大模型 API
- **实现方案**：
  - ernie-lite：6 种轻量任务（意图识别/摘要/分类/实体提取/翻译/通用对话）
  - ernie-3.5：7 种复杂任务（邮件生成/系统诊断/代码分析/文献综述/复杂推理/任务规划/报告生成）
  - 两款模型通过 config.py MODEL_ROUTING 路由表自动切换

### 下周计划（2026.05.28 ~ 2026.06.03）

1. **最终检查与提交准备**：对照 CHECKLIST.md 逐项确认，确保所有交付物齐全
2. **演示视频优化**：如有需要，补充带字幕版本的演示视频
3. **ernie-3.5 token 续期**（可选）：如能获取新 token，可升级双模型路由的复杂任务处理能力
4. **提交材料打包**：代码 + 文档 + 视频 + 技术报告，按赛题要求格式整理

### 交付物进展

| 交付物 | 状态 | 备注 |
|--------|:----:|------|
| RFC 技术报告 | ✅ 已完成 | 多模态融合意图识别 + 多智能体动态编排，5/16 完成 |
| 代码实现 | ✅ 已完成 | v3 编排器 + 状态机 + Verifier + 4场景 + 感知层 + GUI |
| README | ✅ 已完成 | 适配 v3 架构，5/22 重写 |
| 演示视频 | ✅ 已完成 | deepin_demo.mp4，157秒，5/16 录制 |
| 赛题自查清单 | ✅ 已完成 | CHECKLIST.md，5/22 新增 |
| GitHub 仓库 | ✅ 已同步 | origin/main = local main (`129ad8f`) |
| 部署脚本 | ✅ 已完成 | deepin25_deploy.sh + init.sh |

### 项目架构概览（v3 最终版）

```
deepin-agent-teams/
├── main.py                         # CLI 入口（-d all/-i/--v41/--gui）
├── config.py                       # 配置管理
├── agents/                         # Agent 模块
│   ├── orchestrator_v3.py          # v3 编排器（状态机+Verifier，396行）⭐
│   ├── task_state_machine.py       # 状态机引擎（7状态+trace，359行）
│   ├── verifier.py                 # 独立质检员（清单验收，332行）
│   ├── conflict_resolver.py        # 冲突解决器（文件锁+7级优先级）
│   ├── worker_base.py              # Worker 基类（shell/scan/search/fetch）
│   ├── lead.py                     # Lead Agent
│   ├── researcher.py               # Researcher Agent
│   ├── coder.py                    # Coder Agent
│   ├── system_operator.py          # 系统操作员
│   ├── information_collector.py    # 信息收集员
│   └── content_creator.py          # 内容创作员
├── perception/                     # 环境感知层（10个模块）
│   ├── screen_capture.py           # 屏幕截图
│   ├── clipboard_monitor.py        # 剪贴板监控
│   ├── window_manager.py           # 窗口管理
│   ├── system_monitor.py           # 系统监控
│   ├── deepin_dbus.py              # D-Bus 接口
│   ├── screen_ocr.py               # OCR 识别（PaddleOCR）
│   ├── context_engine.py           # 上下文引擎
│   ├── behavior_tracker.py         # 行为序列记录
│   ├── resource_guard.py           # 资源占用控制
│   └── privacy_guard.py            # 隐私保护（6类敏感数据脱敏）
├── scenarios/                      # 4个场景
│   ├── email_assistant.py          # 智能邮件助手（409行）
│   ├── system_doctor.py            # 系统问题诊断（376行）
│   ├── code_analysis.py            # 代码分析助手（410行）
│   └── literature_review.py        # 文献阅读助手（430行）
├── tools/                          # 工具层
│   ├── mcp_adapter.py              # MCP/Skills 适配器
│   ├── checkpoint_manager.py       # Checkpoint 恢复（262行）
│   ├── analyze_traces.py           # Trace 分析（184行）
│   └── analyze_capabilities.py     # 能力分析（273行）
├── gui/                            # GUI 模块（PyQt5, 917行）
│   ├── floating_ball.py            # 悬浮球（拖拽+边缘吸附+动画）
│   ├── chat_window.py              # 对话窗口（场景切换+消息气泡）
│   ├── tray_icon.py                # 系统托盘（右键菜单+通知）
│   └── styles.py                   # deepin 25 风格样式
├── docs/                           # 知识库
│   ├── ARCHITECTURE.md             # 架构文档
│   ├── CONVENTIONS.md              # 编码规范
│   ├── TECH_DECISIONS.md           # 技术决策记录
│   └── QUALITY.md                  # 质量标准
├── media/
│   └── deepin_demo.mp4             # 演示视频（157秒，5.8MB）
├── RFC.md                          # 技术报告
├── README.md                       # 项目文档
├── CHECKLIST.md                    # 赛题完成度自查清单
├── OPTIMIZATION_PLAN.md            # P0/P1/P2 优化计划（全部完成）
├── DEMO_RECORDING_GUIDE.md         # 演示视频录制指南
├── PLAN.md                         # 项目计划
├── tasks.json                      # 任务队列
├── deepin25_deploy.sh              # deepin 25 一键部署
└── init.sh                         # 环境检查脚本
```

### 技术栈

| 组件 | 技术选型 |
|------|---------|
| Agent 框架 | OpenClaw（sessions_spawn 多 Agent 协作） |
| 大模型 | **ernie-lite**（轻量）+ **ernie-3.5**（复杂） |
| 编排器 | orchestrator_v3（状态机驱动 + 独立 Verifier） |
| GUI | PyQt5（悬浮球+对话窗口+系统托盘） |
| 编程语言 | Python 3.10+ |
| OCR | PaddleOCR |
| 目标系统 | deepin 25 |

### 赛题完成度自查（更新于 2026-05-22）

| 阶段 | 要求 | 状态 |
|------|------|:----:|
| 一、多模态环境感知 | 屏幕截图+OCR+窗口+剪贴板+D-Bus+系统监控+行为追踪+意图置信度 | ✅ |
| 一、复杂意图识别 | 多轮对话+跨应用上下文+意图置信度 | ✅ |
| 二、状态机引擎 | 7状态+代码写死跳转+trace可追溯 | ✅ |
| 二、独立 Verifier | 清单验收+独立世界观+PASS/FAIL/RETRY | ✅ |
| 二、Checkpoint 恢复 | 中断后从 checkpoint 恢复，不整体重来 | ✅ |
| 二、智能体团队 | Lead+Researcher+Coder+Operator+Collector+Creator | ✅ |
| 二、动态编排 | 任务拆解+分配+交接+冲突解决+结果汇总 | ✅ |
| 二、工具使用 | Bash+文件搜索+网页搜索+网页获取+MCP+多模型路由 | ✅ |
| 三、四大场景 | 邮件助手+系统诊断+代码分析+文献阅读 | ✅ |
| 四、GUI 界面 | 悬浮球+对话窗口+系统托盘（PyQt5） | ✅ |
| 四、deepin 25 适配 | 34/34 测试通过 | ✅ |
| 五、技术报告 | RFC.md + ARCHITECTURE.md + TECH_DECISIONS.md | ✅ |
| 五、演示视频 | deepin_demo.mp4（157秒） | ✅ |

### 关键时间线

| 日期 | 里程碑 | 状态 |
|------|--------|:----:|
| 5/16 | deepin 25 实体机验证 34/34 通过 | ✅ |
| 5/16 | 演示视频录制 + 技术报告完成 | ✅ |
| 5/22 | P0/P1/P2 工程优化全部完成 | ✅ |
| 5/22 | 文档全面同步 + GitHub push | ✅ |
| 6/3-4 | 最终检查 + 提交材料打包 | ⬜ |
| **6/5** | **提交截止** | ⬜ |
