# deepin-agent-teams 技术报告

> 第十期飞桨黑客松 · 统信×百度飞桨 · 进阶任务 #27
> deepin Agent Teams 智能体团队协作系统

---

## 一、项目概述

### 1.1 项目背景

随着大模型技术的飞速发展，AI 应用的落地部署对硬件的多元化适配、操作系统的兼容性与适配性提出了更高要求。本项目基于 deepin 25 操作系统，设计并实现一个具备"环境感知"能力的多智能体协作系统，通过分析用户的实时操作行为（窗口标题、屏幕内容、剪贴板、交互动作等），主动理解用户意图并调用相应智能体提供辅助。

### 1.2 核心目标

1. **多模态环境感知**：融合屏幕截图、OCR识别、窗口元数据、剪贴板内容等多源信息
2. **复杂意图识别**：基于大模型理解用户真实意图，支持多轮对话澄清
3. **多智能体协同**：构建系统操作员、信息收集员、内容创作员三个专业化智能体团队
4. **场景落地**：实现智能邮件助手和系统问题诊断两个核心场景

### 1.3 技术指标

| 指标 | 数值 |
|------|------|
| 环境感知模块 | 7个（屏幕/剪贴板/窗口/系统监控/D-Bus/OCR/上下文） |
| 智能体数量 | 3个（SystemOperator/InformationCollector/ContentCreator） |
| 意图识别准确率 | ≥90%（演示场景） |
| 场景覆盖率 | 2个（邮件助手/系统诊断） |
| 代码规模 | ~5000行 |

---

## 二、系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   悬浮球    │  │  交互窗口   │  │     终端 CLI            │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
└─────────┼────────────────┼──────────────────────┼────────────────┘
          │                │                      │
          ▼                ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     智能决策调度层                               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              🎯 意图识别引擎 (ContextEngine)                  ││
│  │  • 关键词匹配 + 置信度计算                                   ││
│  │  • 多轮对话意图澄清                                         ││
│  │  • 跨应用上下文理解                                          ││
│  └──────────────────────────┬──────────────────────────────────┘│
│                             │                                   │
│  ┌──────────────────────────▼──────────────────────────────────┐│
│  │           📋 任务分类与智能体调度                            ││
│  │  • 场景路由（邮件/诊断/代码/文献）                           ││
│  │  • 能力匹配（根据任务选择合适Agent）                         ││
│  │  • 动态编排（多Agent协同执行）                              ││
│  └──────────────────────────┬──────────────────────────────────┘│
└─────────────────────────────┼───────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  🛠️ 系统操作员  │  │  📊 信息收集员  │  │  ✍️ 内容创作员  │
│ SystemOperator  │  │InformationColl..│  │  ContentCreator │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ • systemctl     │  │ • 文件搜索      │  │ • 邮件生成      │
│ • bash执行      │  │ • 剪贴板读取    │  │ • 报告撰写      │
│ • 配置修改      │  │ • 网页抓取      │  │ • 代码分析      │
│ • 服务管理      │  │ • 日志分析      │  │ • 文献综述      │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
┌────────────────────────────▼───────────────────────────────────┐
│                      环境感知层 (perception/)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │屏幕截图  │ │剪贴板监控│ │窗口管理  │ │系统监控  │          │
│  │grim/scrot│ │ xclip    │ │ wmctrl   │ │systemctl │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                       │
│  │deepin   │ │OCR识别   │ │上下文引擎│                       │
│  │D-Bus    │ │PaddleOCR │ │意图分类  │                       │
│  └──────────┘ └──────────┘ └──────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      deepin 25 操作系统                         │
│  • X11会话 (1280x800)                                           │
│  • D-Bus 系统总线 (103个服务)                                    │
│  • NetworkManager / CUPS / PulseAudio                           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 层次说明

**用户交互层**：提供三种交互方式
- 悬浮球（GUI）：点击弹出对话窗口
- 交互窗口：独立窗口，支持多轮对话
- 终端CLI：命令行模式，适合高级用户

**智能决策调度层**：核心控制中枢
- 意图识别引擎：解析用户输入，判断任务类型
- 任务分类：根据意图路由到对应场景
- 智能体调度：根据任务选择合适的智能体组合

**智能体执行层**：三个专业化智能体
- **SystemOperator**：执行系统级操作（bash/systemctl/配置）
- **InformationCollector**：收集多源信息（文件/剪贴板/网页/日志）
- **ContentCreator**：生成结构化内容（邮件/报告/代码/综述）

**环境感知层**：7个感知模块
- **screen_capture**：屏幕截图（grim/scrot）
- **clipboard_monitor**：剪贴板监控（xclip）
- **window_manager**：窗口管理（wmctrl/xdotool）
- **system_monitor**：系统监控（systemctl/diagnostic）
- **deepin_dbus**：deepin D-Bus接口
- **screen_ocr**：OCR识别（PaddleOCR）
- **context_engine**：上下文引擎

---

## 三、多模态融合意图识别原理

### 3.1 感知数据来源

```python
感知数据 = {
    "视觉": ["屏幕截图", "OCR文本", "窗口截图"],
    "窗口": ["活动窗口标题", "窗口类名", "进程ID", "窗口列表"],
    "系统": ["服务状态", "硬件状态", "D-Bus信号", "/proc信息"],
    "输入": ["用户文本输入", "剪贴板内容", "历史命令"]
}
```

### 3.2 意图识别流程

```
用户输入 → 关键词匹配 → 置信度计算 → 意图分类 → 多轮澄清（如需）
                           │
                           ▼
                    ┌──────────────┐
                    │  意图类型    │
                    ├──────────────┤
                    │ email        │ → 智能邮件助手
                    │ system_fix   │ → 系统问题诊断
                    │ code_analysis│ → 代码分析助手
                    │ literature   │ → 文献阅读助手
                    │ search       │ → 信息搜索
                    └──────────────┘
```

### 3.3 多源信息融合机制

**Step 1：原始数据采集**
```python
# 同时采集多源数据
screenshots = capture_screen()           # 屏幕截图
clipboard_text = get_clipboard_text()    # 剪贴板
active_window = get_active_window()      # 活动窗口
window_list = get_window_list()         # 窗口列表
service_status = check_service(...)     # 服务状态
```

**Step 2：特征提取**
```python
# 对每种数据源进行特征提取
window_features = {
    "title": active_window.title,
    "class": active_window.class_name,
    "pid": active_window.pid
}

context_features = {
    "clipboard_preview": clipboard_text[:100],
    "window_count": len(window_list),
    "window_titles": [w.title for w in window_list[:5]]
}
```

**Step 3：融合与推理**
```python
# 大模型基于融合特征进行意图推理
prompt = f"""
用户输入: {user_input}
当前窗口: {window_features}
上下文: {context_features}
剪贴板: {clipboard_text[:200]}

判断用户意图（email/system_fix/code_analysis/literature）
"""
```

### 3.4 多轮意图澄清

当单次输入信息不足时，系统主动追问：

```python
# 示例：用户说"给张三发邮件"
# 系统识别到：收件人=张三，但缺少主题和正文

系统: "你要给张三发邮件，具体说什么内容呢？"
用户: "项目进度"
系统: "好的，主题是'项目进度'，现在开始收集信息..."
```

---

## 四、多智能体动态编排与任务调度机制

### 4.1 智能体架构

```
用户指令
    │
    ▼
┌─────────────────────────────────────────┐
│          Lead Agent（任务编排）          │
│  • 解析任务                             │
│  • 拆解子任务                           │
│  • 分配给专业Agent                      │
│  • 汇总结果                             │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│ System │  │Info      │  │ Content  │
│Operator│  │Collector │  │ Creator  │
│        │  │          │  │          │
│执行命令│  │收集信息 │  │生成内容 │
└────┬───┘  └─────┬────┘  └─────┬────┘
     │            │             │
     └────────────┴─────────────┘
                 │
                 ▼
          Lead Agent 汇总结果
                 │
                 ▼
           用户输出
```

### 4.2 三大专业智能体

**SystemOperator（系统操作员）**
```python
capabilities = [
    "bash_execution",        # 执行bash命令
    "service_management",   # 服务管理
    "package_installation", # 包安装
    "system_configuration", # 系统配置
    "file_operations"       # 文件操作
]

# 执行流程
def execute(task):
    if task.type == "service_restart":
        return systemctl_restart(task.target)
    elif task.type == "install_package":
        return apt_install(task.package)
    elif task.type == "config_change":
        return modify_config(task.path, task.value)
```

**InformationCollector（信息收集员）**
```python
capabilities = [
    "file_search",         # 文件搜索
    "clipboard_access",    # 剪贴板读取
    "web_fetch",           # 网页抓取
    "log_analysis",        # 日志分析
    "email_collection"     # 邮件收集
]

# 执行流程
def collect(task):
    if task.type == "search_files":
        return search_files(task.keyword, task.path)
    elif task.type == "get_clipboard":
        return get_clipboard_content()
    elif task.type == "fetch_web":
        return fetch_url(task.url)
    elif task.type == "analyze_log":
        return analyze_log(task.path, task.pattern)
```

**ContentCreator（内容创作员）**
```python
capabilities = [
    "email_generation",    # 邮件生成
    "report_writing",      # 报告撰写
    "code_analysis",       # 代码分析
    "literature_review"    # 文献综述
]

# 执行流程
def create(task):
    if task.type == "generate_email":
        return generate_email(task.context, task.recipient, task.topic)
    elif task.type == "write_report":
        return write_report(task.sections)
    elif task.type == "analyze_code":
        return analyze_code(task.code, task.language)
```

### 4.3 动态编排策略

```python
class Orchestrator:
    def dispatch(self, task):
        # 1. 任务分析
        task_type = self.analyze_task(task)
        
        # 2. 选择Agent组合
        if task_type == "email":
            agents = [InfoCollector, ContentCreator]
        elif task_type == "system_fix":
            agents = [InfoCollector, SystemOperator]
        elif task_type == "code_analysis":
            agents = [InfoCollector, ContentCreator]
        
        # 3. 并行/串行执行
        results = []
        for agent in agents:
            result = agent.execute(task.subtasks[agent])
            results.append(result)
            task = self.merge_context(task, result)
        
        # 4. 结果汇总
        return self.aggregate_results(results)
```

### 4.4 任务调度流程

```
用户: "打印机连不上了"
     │
     ▼
┌──────────────────────────────────────┐
│ Lead Agent 任务拆解                   │
├──────────────────────────────────────┤
│ 1. 意图分类 → system_fix              │
│ 2. 拆解子任务:                        │
│    - 信息收集: 检查CUPS服务状态       │
│    - 信息收集: 列出已配置打印机       │
│    - 诊断分析: 分析问题根因           │
│    - 方案生成: 生成修复方案           │
└──────────────────┬───────────────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   InfoCollector InfoCollector SystemOperator
        │          │          │
        │          │          │
        ▼          ▼          ▼
   cups状态    打印机列表   诊断命令
        │          │          │
        └──────────┼──────────┘
                   │
                   ▼
         Lead Agent 结果汇总
                   │
                   ▼
         ┌─────────────────┐
         │ 诊断结果+修复方案│
         └─────────────────┘
```

---

## 五、核心场景实现

### 5.1 场景一：智能邮件助手

**场景描述**：用户输入"给张三发邮件说项目进度"，系统自动完成意图识别、信息收集、邮件生成、发送确认全流程。

**实现流程**：

```
用户输入
    │
    ▼ [Step 1] 意图识别
┌─────────────────────────────┐
│ ContextEngine               │
│ • 检测邮件关键词            │
│ • 提取收件人：张三          │
│ • 置信度：90%               │
│ • 动作：compose             │
└─────────────┬───────────────┘
              │
              ▼ [Step 2] 多轮澄清（如需）
┌─────────────────────────────┐
│ 缺失: 主题/正文             │
│ 系统: "具体说什么内容呢？"  │
│ 用户: "项目进度"            │
└─────────────┬───────────────┘
              │
              ▼ [Step 3] 上下文收集
┌─────────────────────────────┐
│ InformationCollector        │
│ • 剪贴板内容               │
│ • 相关文件搜索             │
│ • 活动窗口上下文           │
└─────────────┬───────────────┘
              │
              ▼ [Step 4] 邮件生成
┌─────────────────────────────┐
│ ContentCreator              │
│ • 构建邮件结构             │
│ • LLM生成正文              │
│ • 格式美化                  │
└─────────────┬───────────────┘
              │
              ▼ [Step 5] 用户确认
┌─────────────────────────────┐
│ 发送预览 + 修改/发送选项    │
│ 用户确认后 → 执行发送      │
└─────────────────────────────┘
```

**关键代码**：
```python
class EmailAssistant:
    def run(self, user_input, auto_send=False):
        # 1. 意图识别
        intent = self.engine.detect_intent(user_input)
        
        # 2. 信息收集
        context = self.collector.collect_context_for_email(intent.get("topic"))
        
        # 3. 邮件生成
        draft = self.creator.generate_email(
            context, 
            recipient=intent.get("recipient"),
            topic=intent.get("topic")
        )
        
        # 4. 返回草稿，等待确认
        return {"success": True, "draft": draft}
```

### 5.2 场景二：系统问题智能诊断与修复

**场景描述**：用户输入"打印机连不上了"，系统自动进行问题分类、系统诊断、方案生成、修复确认。

**实现流程**：

```
用户输入
    │
    ▼ [Step 1] 问题分类
┌─────────────────────────────┐
│ ContextEngine               │
│ • 检测问题类型：printer     │
│ • 置信度：80%              │
│ • 影响组件：cups/驱动      │
└─────────────┬───────────────┘
              │
              ▼ [Step 2] 系统诊断
┌─────────────────────────────┐
│ SystemOperator + InfoCollector│
│ 诊断命令并行执行:            │
│ • systemctl status cups     │
│ • lpstat -a                 │
│ • check_service(pulseaudio) │
│ 收集诊断结果                │
└─────────────┬───────────────┘
              │
              ▼ [Step 3] 问题分析
┌─────────────────────────────┐
│ 问题:                      │
│ • cups_service: True       │
│ • printers_configured: False│
│ 根因: 未配置打印机         │
└─────────────┬───────────────┘
              │
              ▼ [Step 4] 修复方案生成
┌─────────────────────────────┐
│ SystemOperator             │
│ 自动步骤:                   │
│ 1. 检查CUPS服务            │
│ 2. 列出打印机              │
│ 需确认步骤:               │
│ 1. 重启CUPS服务（需sudo）  │
│ 2. 添加打印机（需sudo）    │
└─────────────┬───────────────┘
              │
              ▼ [Step 5] 用户确认执行
┌─────────────────────────────┐
│ 用户选择执行方案           │
│ 系统自动执行修复操作       │
│ 验证修复结果              │
└─────────────────────────────┘
```

**关键代码**：
```python
class SystemDoctor:
    def run(self, user_input, auto_fix=False):
        # 1. 问题分类
        problem_type = self.classify_problem(user_input)
        
        # 2. 系统诊断
        diagnosis = self.diagnose(problem_type)
        
        # 3. 生成修复方案
        solution = self.generate_solution(diagnosis)
        
        # 4. 执行或等待确认
        if auto_fix:
            return self.execute_solution(solution)
        else:
            return {"solution": solution, "pending_confirmation": True}
```

---

## 六、关键技术实现

### 6.1 环境感知模块

**screen_capture.py**：屏幕截图
```python
def capture_screen(output_path="/tmp/screenshot.png"):
    # 支持 deepin 25 X11 会话
    session_type = detect_session()  # x11 or wayland
    if session_type == "x11":
        return subprocess.run(["scrot", "-o", output_path])
    else:
        return subprocess.run(["grim", output_path])
```

**window_manager.py**：窗口管理
```python
def get_active_window():
    # 使用 wmctrl 获取活动窗口
    result = subprocess.run(["wmctrl", "-a"], capture_output=True)
    return parse_window_info(result.stdout)

def get_window_list():
    # 列出所有窗口
    result = subprocess.run(["wmctrl", "-l"], capture_output=True)
    return [parse_window_info(line) for line in result.stdout.lines()]
```

**deepin_dbus.py**：deepin D-Bus 接口
```python
import dbus

def get_audio_volume():
    bus = dbus.SystemBus()
    proxy = bus.get_object("org.deepin.dde.Volume1", "/org/deepin/dde/Volume1")
    interface = dbus.Interface(proxy, "org.deepin.dde.Volume1")
    return interface.GetVolume()

def get_brightness():
    bus = dbus.SystemBus()
    proxy = bus.get_object("org.deepin.dde.Appearance1", "/org/deepin/dde/Appearance1")
    interface = dbus.Interface(proxy, "org.deepin.dde.Appearance1")
    return interface.GetBrightness()
```

### 6.2 意图识别引擎

**context_engine.py**：上下文引擎
```python
class ContextEngine:
    def detect_intent(self, user_input):
        # 关键词匹配
        for intent_type, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, user_input):
                    confidence = self.calculate_confidence(user_input)
                    return {
                        "intent_type": intent_type,
                        "confidence": confidence,
                        "entities": self.extract_entities(user_input)
                    }
        return {"intent_type": "unknown", "confidence": 0}
```

### 6.3 智能体基类

**agents/base.py**：智能体基类
```python
class BaseAgent:
    def __init__(self, name, capabilities):
        self.name = name
        self.capabilities = capabilities
    
    def can_handle(self, task):
        return any(cap in self.capabilities for cap in task.required_capabilities)
    
    def execute(self, task):
        raise NotImplementedError

class SystemOperator(BaseAgent):
    capabilities = ["bash_execution", "service_management", ...]
    
class InformationCollector(BaseAgent):
    capabilities = ["file_search", "clipboard_access", ...]
    
class ContentCreator(BaseAgent):
    capabilities = ["email_generation", "report_writing", ...]
```

---

## 七、部署与验证

### 7.1 deepin 25 部署

**部署脚本**：`deepin25_deploy.sh`
```bash
#!/bin/bash
# 一键部署 deepin-agent-teams

# 1. 安装系统依赖
sudo apt install -y python3-venv scrot xclip wmctrl

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装 Python 依赖
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 4. 运行测试
python3 tests/test_perception_deepin25.py
```

### 7.2 验证结果

**感知层测试结果**：34/34 通过 ✅

| 模块 | 测试项 | 结果 |
|------|--------|------|
| screen | 会话类型检测/屏幕信息/截图 | ✅ 6/6 |
| clipboard | 剪贴板读取/监控器初始化 | ✅ 2/2 |
| window | 活动窗口/窗口列表 | ✅ 2/2 |
| system | 服务检查/音频诊断/网络诊断/打印机诊断 | ✅ 6/6 |
| dbus | deepin检测/系统信息/音量/亮度/服务列表 | ✅ 5/5 |
| ocr | OCR可用性/图像识别/屏幕识别 | ✅ 3/3 |
| context | 上下文引擎初始化/意图识别(3项) | ✅ 4/4 |
| agents | SystemOperator/InformationCollector/ContentCreator | ✅ 3/3 |
| scenarios | EmailAssistant/SystemDoctor | ✅ 2/2 |
| orchestrator | ProductionExecutor | ✅ 1/1 |

### 7.3 场景演示结果

**智能邮件助手**：
- 输入：`给张三发邮件，主题：项目进度，邮件内容：已完成80%`
- 意图识别：✅ 收件人=张三，置信度90%
- 上下文收集：✅ 从活动窗口获取上下文
- 邮件生成：✅ 生成完整邮件正文
- 发送确认：✅ 等待用户确认

**系统问题诊断**：
- 输入：`打印机连不上了`
- 问题分类：✅ 打印机（置信度80%）
- 系统诊断：✅ cups运行中，未配置打印机
- 修复方案：✅ 自动步骤2项+需确认步骤2项

---

## 八、创新点

### 8.1 多模态感知融合

传统意图识别仅依赖用户输入文本，本系统创新性地融合了：
- **视觉感知**：屏幕截图 + OCR 识别
- **窗口上下文**：活动窗口标题/类名/进程
- **系统状态**：服务状态/硬件状态/D-Bus信号
- **输入上下文**：剪贴板内容/历史命令

通过多源信息融合，大模型能够更准确地理解用户真实意图。

### 8.2 动态智能体编排

区别于静态的 Agent 组合，本系统实现了：
- **任务驱动的动态选择**：根据任务类型自动选择合适的 Agent 组合
- **能力匹配**：根据任务需求匹配具有相应能力的 Agent
- **上下文传递**：Agent 间通过上下文共享实现信息传递
- **结果聚合**：Lead Agent 汇总各 Agent 结果，生成最终输出

### 8.3 多轮意图澄清机制

当用户输入信息不足时，系统主动进行多轮对话澄清：
- **缺失检测**：识别用户输入中的信息缺失
- **主动追问**：系统提出具体问题逐步澄清
- **上下文保持**：多轮对话中保持原始任务上下文
- **渐进式完成**：从模糊意图到清晰任务逐步完善

### 8.4 deepin 特色集成

充分利用 deepin 操作系统的特性：
- **D-Bus 系统总线**：读取系统音量/亮度/服务状态
- **deepin 专属服务**：com.deepin.dde.* 系列服务
- **控制中心 API**：系统配置和设置接口
- **桌面环境特性**：窗口管理、剪贴板监控等

### 8.5 MCP 工具解耦架构（v4）

基于 Agent 工程方法论评估（Build✅ Connect❌ Scale⚠️ Verify✅），发现工具层硬编码是最大短板。创新性地实现了：

- **轻量 MCP 协议**：纯 Python 实现 JSON-RPC over stdio，无需官方 MCP SDK，兼容 PEP 668
- **ToolRegistry 统一注册表**：本地 handler 和远程 MCP Server 两种来源，调用方完全不感知底层差异
- **零侵入扩展**：加新工具 = 写 MCP Server 文件 + connect_server() 一行代码，不改 orchestrator
- **OrchestratorV4**：自动扫描并连接所有内置 MCP Server，工具列表自动生成 LLM Function Calling 格式

架构变化：
```
Before（v3）：orchestrator → 硬编码 → model_router / file ops / shell
After（v4）：orchestrator → ToolRegistry → MCP Client → model-service
                                                → MCP Client → file-service
                                                → MCP Client → system-service
```

---

## 九、总结与展望

### 9.1 项目成果

1. **完整的多智能体协作系统**：实现了 SystemOperator、InformationCollector、ContentCreator 三个专业智能体的协作
2. **全面的环境感知能力**：7个感知模块覆盖屏幕、剪贴板、窗口、系统、D-Bus、OCR、上下文
3. **三角架构创新**：状态机引擎 + 独立 Verifier + Worker 池，所有停止条件代码写死
4. **MCP 工具解耦**：v4 编排器通过 MCP 协议标准化工具连接，加工具零侵入
5. **deepin 25 实体机验证**：34/34 测试项通过
6. **测试覆盖**：39/39 单元测试通过（状态机 5 + Verifier 6 + Checkpoint 6 + ModelRouter 4 + ToolRegistry 8 + MCP 8 + 其他 2）

### 9.2 未来工作

1. **扩展场景**：代码分析助手、文献阅读助手
2. **增强感知**：支持 Wayland 会话、PaddleOCR 性能优化
3. **隐私保护**：增加敏感操作确认、权限控制
4. **GUI 完善**：悬浮球交互优化、系统托盘集成
5. **多 Agent 协作模式**：引入辩论模式、群组模式等高级协作方式
6. **可观测性**：集成 OpenTelemetry，实现全链路 Trace

---

## 十、参考文档

- [deepin 25 部署脚本](./deepin25_deploy.sh)
- [感知层测试脚本](./tests/test_perception_deepin25.py)
- [验证指南](./VALIDATION_GUIDE.md)
- [项目计划](./PLAN.md)

---

**项目仓库**：https://github.com/sshnuke3/deepin-agent-teams

**提交时间**：2026-05-16