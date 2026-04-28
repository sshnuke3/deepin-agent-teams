# deepin-agent-teams 黑客松实现规划

> 第十期飞桨黑客松 - 统信×deepin Agent Teams 进阶任务
> 规划时间：2026-04-28 | 答辩：2026年6月

---

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| v4.1 sessions_spawn 框架 | ✅ 完成 | 667行生产级编排器 |
| 多 Agent 协同架构 | ✅ 完成 | Lead + Researcher + Coder |
| 场景生成器 | ✅ 完成 | README / Test 自动生成 |
| 环境感知层 | ❌ 未开始 | 屏幕/剪贴板/窗口 |
| 场景一：智能邮件 | ❌ 未开始 | — |
| 场景二：系统诊断 | ❌ 未开始 | — |
| deepin 系统适配 | ❌ 未开始 | D-Bus / wmctrl |
| PaddleOCR 感知 | ❌ 未开始 | 多模态识别 |
| 演示视频 | ❌ 未开始 | — |

---

## 总体架构

```
用户操作（deepin桌面）
    ↓ 环境感知层
┌─────────────────────────────────┐
│   🎯 意图识别引擎（Lead Agent）   │
│   - 窗口标题 / 剪贴板 / 屏幕上下文 │
│   - ERNIEBot 判断用户意图          │
└─────────────────────────────────┘
    ↓ 任务拆分 + Agent 调度
┌──────────┬──────────┬──────────┐
│ 系统操作员 │ 信息收集员 │ 内容创作员 │
│ (Agent)  │ (Agent)  │ (Agent)  │
└──────────┴──────────┴──────────┘
    ↓ 协同执行 + 结果汇总
    ↓ 工具调用（deepin API）
```

---

## 阶段一：环境感知层（1周）

### 目标
构建 deepin 系统感知工具集，供所有 Agent 调用。

### 文件结构
```
perception/
├── __init__.py
├── screen_capture.py    # 屏幕截图
├── clipboard_monitor.py  # 剪贴板监控
├── window_manager.py    # 窗口标题/进程
├── system_monitor.py    # 系统状态（CPU/内存/服务）
└── deepin_dbus.py       # deepin D-Bus 接口
```

### 任务清单

- [ ] `screen_capture.py`：调用 `grim` / `swappy` 截取屏幕，保存为 PNG
- [ ] `clipboard_monitor.py`：监听 `xclip` / DBus clipboard 变化
- [ ] `window_manager.py`：调用 `wmctrl` 或读取 `/proc` 获取当前活动窗口
- [ ] `system_monitor.py`：检查服务状态 (`systemctl`)、音频状态、网络状态
- [ ] `deepin_dbus.py`：调用 deepin 控制中心 D-Bus API（可选）

### 验证方法
```python
# 每完成一个模块，运行测试：
python -c "from perception import screen_capture, clipboard_monitor; print('OK')"
```

---

## 阶段二：核心 Agent 团队重构（1周）

### 目标
将现有 v4.1 orchestrator 改造成适配 deepin 场景的 3 类专业 Agent。

### 新增 Agent

| Agent | 职责 | 工具能力 |
|-------|------|---------|
| **SystemOperator** | 执行 bash / 修改系统配置 / 重启服务 | exec, bash, systemctl |
| **InformationCollector** | 搜索文件 / 查日志 / 抓取网络信息 | read, search, web_fetch |
| **ContentCreator** | 撰写邮件 / 总结报告 / 生成回复 | write, erniebot |

### 改动文件
- `agents/system_operator.py`（新建）
- `agents/information_collector.py`（新建）
- `agents/content_creator.py`（新建）
- `agents/sessions_orchestrator_prod.py`（适配为场景编排器）

### 验证方法
```bash
python main.py --demo "帮我检查系统声音有没有问题"
# 应能调用 SystemOperator 执行诊断命令
```

---

## 阶段三：场景一 —— 智能邮件助手（1.5周）

### 工作流程
```
1. 用户说出"给张三发邮件说项目进度"
       ↓
2. Lead 识别为「发送邮件」意图
       ↓
3. InformationCollector 收集信息：
   - 从文件系统搜索相关项目文档
   - 读取剪贴板最近内容
   - 读取当前窗口上下文（邮箱界面）
       ↓
4. ContentCreator 生成邮件正文
       ↓
5. SystemOperator 调用邮件客户端 / 输出邮件内容
```

### 新增文件
```
scenarios/
└── email_assistant.py    # 智能邮件助手场景编排
```

### 实现要点
- 意图判断：关键词 + 上下文双重确认
- 多源信息聚合：文件系统搜索 + 剪贴板 + 屏幕 OCR
- 邮件生成：ERNIEBot 根据收集到的信息生成结构化邮件

### 验收
- [ ] 能识别"发邮件"意图
- [ ] 能从剪贴板/文件获取相关信息
- [ ] 能生成完整邮件（主题+正文+收件人）

---

## 阶段四：场景二 —— 系统问题诊断修复（1.5周）

### 工作流程
```
1. 用户输入"打印机连不上" 或 系统检测到错误日志
       ↓
2. Lead 识别为「系统问题」
       ↓
3. SystemOperator 执行诊断：
   - systemctl status cups（打印机服务）
   - amixer / pactl info（音频）
   - systemctl status NetworkManager（网络）
       ↓
4. InformationCollector 收集诊断结果
       ↓
5. Lead 分析根因 → SystemOperator 执行修复
   - 重启服务 / 重装驱动 / 修改配置
       ↓
6. 反馈结果给用户，等待确认
```

### 新增文件
```
scenarios/
└── system_doctor.py     # 系统诊断修复场景编排
```

### 实现要点
- 常见问题分类：声音/网络/打印/安装/显示
- 修复策略库：每类问题预定义修复方案
- 需用户确认后再执行危险操作

### 验收
- [ ] 能诊断至少3类常见问题
- [ ] 能执行修复并反馈结果
- [ ] 有用户确认环节

---

## 阶段五：多模态感知增强（1周）

### 目标
集成 PaddleOCR/PaddleOCR-VL，实现屏幕内容理解。

### 实现方式
```python
# perception/screen_ocr.py
from paddleocr import PaddleOCR

def ocr_screen(region=None):
    """截取屏幕指定区域并 OCR 识别"""
    screenshot = capture_screen(region=region)
    ocr = PaddleOCR(lang='ch')
    result = ocr.ocr(screenshot)
    return extract_text(result)
```

### 触发条件
- 用户复制了代码错误信息 → 自动识别"调试"意图
- 用户打开了PDF/文档 → 自动识别"阅读总结"意图
- 剪贴板出现长文本 → 提示"是否需要摘要"

### 依赖
```bash
pip install paddlepaddle paddleocr
# 或用 PaddleOCR-VL（如果 deepin 有 GPU）
```

---

## 阶段六：集成 + 演示（1周）

### 交互界面
```bash
# 启动 deepin-agent-teams
python main.py --agent
# 打开一个悬浮窗口接受自然语言指令
```

### 演示视频脚本

**开场（30秒）**：
> "这是 deepin Agent Teams，演示两个核心场景"

**场景一（2分钟）**：
1. 用户在 deepin 桌面说"给张三发邮件说项目进度"
2. 系统识别意图，收集剪贴板/文件信息
3. 生成邮件，预览 → 发送

**场景二（2分钟）**：
1. 用户说"打印机连不上了"
2. 系统自动诊断（检测 cups 服务）
3. 发现问题 → 询问用户 → 执行修复
4. 反馈结果

**技术亮点（1分钟）**：
- 环境感知层演示（窗口标题/剪贴板监控）
- 多 Agent 协同工作流可视化

---

## 时间安排

| 周 | 时间 | 任务 | 交付物 |
|----|------|------|--------|
| 第1周 | 4/29-5/5 | 环境感知层 | `perception/` 模块 |
| 第2周 | 5/6-5/12 | 核心 Agent 重构 | 3个专业 Agent |
| 第3周 | 5/13-5/19 | 场景一：智能邮件 | `email_assistant.py` |
| 第4周 | 5/20-5/26 | 场景二：系统诊断 | `system_doctor.py` |
| 第5周 | 5/27-6/2 | PaddleOCR 增强 | OCR 感知集成 |
| 第6周 | 6/3-6/9 | 集成 + 录屏 | 演示视频 + 技术报告 |

> ⚠️ 如果中期检查在5月中，请优先确保第1-3周内容可用

---

## 文件结构（最终）

```
deepin-agent-teams/
├── main.py                        # CLI 入口
├── config.py                      # 配置
├── requirements.txt
├── perception/                    # 🆕 环境感知层
│   ├── __init__.py
│   ├── screen_capture.py
│   ├── clipboard_monitor.py
│   ├── window_manager.py
│   ├── system_monitor.py
│   └── deepin_dbus.py
├── agents/
│   ├── sessions_orchestrator_prod.py  # 生产级编排器（已有）
│   ├── system_operator.py          # 🆕
│   ├── information_collector.py   # 🆕
│   └── content_creator.py           # 🆕
├── scenarios/
│   ├── email_assistant.py          # 🆕 场景一
│   └── system_doctor.py            # 🆕 场景二
├── demos/
│   ├── demo_email.sh               # 场景一演示脚本
│   └── demo_doctor.sh              # 场景二演示脚本
└── docs/
    ├── architecture.md              # 系统架构图
    ├── intent_recognition.md       # 意图识别原理
    └── deployment.md               # 部署文档
```

---

## 关键风险

| 风险 | 影响 | 应对 |
|------|------|------|
| deepin 硬件环境不可用 | 无法测试 | 用 Docker / VM 模拟核心功能 |
| PaddleOCR 性能差 | 感知速度慢 | 限制 OCR 区域，不用全屏 |
| 中期检查来得早 | 场景还没做完 | 优先实现场景一可演示版本 |
| 多 Agent 调试复杂 | 排查困难 | 用日志分级，先跑通再优化 |

---

## 快速启动命令

```bash
# 依赖安装
pip install paddlepaddle paddleocr erniebot python-dotenv

# 感知层测试
python -c "from perception import screen_capture; screen_capture.test()"

# Agent 测试
python main.py --demo "检查系统网络"

# 完整场景（需 deepin 环境）
python main.py --agent --scenario email
```
