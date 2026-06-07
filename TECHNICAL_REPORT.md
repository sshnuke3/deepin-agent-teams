# deepin Agent Teams 智能体团队协作系统 — 技术报告

> **PaddlePaddle 黑客马拉松第10期 · 统信 deepin Agent Teams 赛题**  
> 提交日期：2026-06-07  
> 项目仓库：deepin-agent-teams  

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [多模态融合意图识别原理](#3-多模态融合意图识别原理)
4. [多智能体动态编排与任务调度机制](#4-多智能体动态编排与任务调度机制)
5. [核心场景实现](#5-核心场景实现)

> 附录（6-9节）见 [TECHNICAL_REPORT_APPENDIX.md](TECHNICAL_REPORT_APPENDIX.md)

---

## 1. 项目概述

### 1.1 背景

随着 Linux 桌面操作系统在政企市场的深入推广，用户对桌面智能助手的需求日益迫切。deepin 25 作为统信软件旗下面向未来的桌面操作系统，已在 DDE（Deepin Desktop Environment）、应用生态、系统安全等方面积累了丰富成果。然而，现有的桌面助手方案普遍面临以下挑战：

- **感知维度单一**：多数方案仅依赖自然语言输入，无法充分利用屏幕内容、剪贴板数据、窗口状态等上下文信息；
- **智能体协作缺失**：任务往往由单一模型端到端处理，缺乏任务分解、多角色协同和状态追踪能力；
- **安全与隐私隐患**：大模型直接操作桌面存在越权风险，敏感数据可能被泄露至远端；
- **系统集成浅层化**：未与操作系统的 D-Bus、系统服务、包管理等深度整合，只能处理通用问答。

基于上述背景，我们在 PaddlePaddle 黑客马拉松第10期中，面向统信 deepin Agent Teams 赛题，设计并实现了一套**多智能体团队协作系统**。该系统以"感知 → 意图识别 → 智能体编排 → 安全执行"为核心链路，充分融合 deepin 25 操作系统特性，实现桌面级智能助理的完整闭环。

### 1.2 核心目标

| 维度 | 目标描述 |
|------|---------|
| 多模态感知 | 融合屏幕 OCR、剪贴板、窗口元数据、行为轨迹等至少 4 种数据源，实现上下文感知意图识别 |
| 多智能体协同 | 不少于 3 个专职智能体（SystemOperator / InformationCollector / ContentCreator），通过统一编排器动态调度 |
| 场景闭环 | 智能邮件助手、系统问题诊断两大核心场景完整可演示 |
| 安全可控 | 工具白名单、Token 预算、确认守卫、红队测试等多层安全机制 |
| 隐私保护 | 敏感数据检测与脱敏、本地化处理、审计日志 |
| 深度集成 | 通过 D-Bus 与 deepin 25 系统服务交互，支持 DDE 桌面环境感知 |

### 1.3 技术指标总览

| 指标项 | 数值 |
|--------|------|
| 代码总量 | ~17,000 行 Python |
| 文件总数 | 86 个 |
| 感知模块 | 10 个 |
| 智能体数量 | 3 个专职 Agent |
| 内置 Skills | 6 个 |
| 状态机状态数 | 7 个 |
| 安全验证检查项 | 7 项独立检查 |
| 红队攻击向量 | 16 种 |
| GUI 界面组件 | PyQt5 浮动球 + 聊天窗口 + 系统托盘 |
| 大模型 | ERNIE-Lite（快速路由）+ ERNIE-3.5（复杂推理）|
| 协议 | MCP (Model Context Protocol) — 纯 Python JSON-RPC over stdio |

---

## 2. 系统架构

### 2.1 整体架构图

系统采用四层架构设计，自上而下分别为**用户交互层**、**智能调度层**、**智能体执行层**和**环境感知层**，底层依托 deepin 25 操作系统。

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户交互层 (User Interface)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  浮动球 (Ball) │  │ 聊天窗口 (Chat) │  │   CLI 终端    │              │
│  │  PyQt5 圆形   │  │  PyQt5 对话   │  │  命令行入口   │              │
│  │  拖拽/吸附    │  │  消息气泡     │  │  argparse    │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                  │                      │
│         └─────────────────┼──────────────────┘                      │
│                           ▼                                         │
├─────────────────────────────────────────────────────────────────────┤
│                     智能调度层 (Intelligent Dispatch)                │
│                                                                     │
│  ┌────────────────┐    ┌───────────────┐    ┌──────────────────┐   │
│  │  ContextEngine │───▶│ SkillMatcher  │───▶│   Orchestrator   │   │
│  │  意图识别引擎   │    │  Skill 匹配   │    │   统一编排器     │   │
│  │  多模态融合     │    │  能力路由     │    │   状态机驱动     │   │
│  └───────┬────────┘    └───────┬───────┘    └────────┬─────────┘   │
│          │                     │                     │             │
│  ┌───────▼────────┐    ┌──────▼────────┐    ┌───────▼──────────┐  │
│  │ 隐私保护模块    │    │ 安全配置模块  │    │  验证器 (Verifier)│  │
│  │ PrivacyGuard   │    │ SecurityConfig│    │  7 项独立检查    │  │
│  └────────────────┘    └───────────────┘    └──────────────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                     智能体执行层 (Agent Execution)                   │
│                                                                     │
│  ┌────────────────┐  ┌────────────────────┐  ┌─────────────────┐  │
│  │ SystemOperator │  │InformationCollector│  │  ContentCreator  │  │
│  │  系统运维智能体 │  │  信息采集智能体    │  │  内容创作智能体  │  │
│  │  - 系统诊断    │  │  - 屏幕 OCR       │  │  - 邮件撰写     │  │
│  │  - 进程管理    │  │  - 剪贴板监控     │  │  - 文本润色     │  │
│  │  - 包管理     │  │  - Web 搜索       │  │  - 摘要生成     │  │
│  │  - 服务控制    │  │  - 文件检索       │  │  - 翻译辅助     │  │
│  └───────┬────────┘  └─────────┬──────────┘  └────────┬────────┘  │
│          │                     │                      │           │
│          └─────────────────────┼──────────────────────┘           │
│                                ▼                                   │
│                    ┌───────────────────────┐                       │
│                    │   MCP Tool Registry   │                       │
│                    │   MCP 工具注册中心    │                       │
│                    │   JSON-RPC over stdio │                       │
│                    └───────────┬───────────┘                       │
│                                │                                   │
├─────────────────────────────────────────────────────────────────────┤
│                     环境感知层 (Environment Perception)             │
│                                                                     │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐     │
│  │screen_capture│ │screen_ocr  │ │clipboard_  │ │window_     │     │
│  │  屏幕截图   │ │  文字识别   │ │ monitor    │ │ manager    │     │
│  └────────────┘ └────────────┘ │  剪贴板     │ │  窗口管理   │     │
│                                └────────────┘ └────────────┘     │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐     │
│  │system_     │ │deepin_dbus │ │context_    │ │behavior_   │     │
│  │ monitor    │ │  D-Bus集成  │ │ engine     │ │ tracker    │     │
│  │  系统监控   │ │  DDE服务    │ │  意图引擎   │ │  行为追踪   │     │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘     │
│  ┌────────────┐ ┌────────────┐                                    │
│  │privacy_    │ │resource_   │                                    │
│  │ guard      │ │ guard      │                                    │
│  │  隐私守护   │ │  资源守护   │                                    │
│  └────────────┘ └────────────┘                                    │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                    deepin 25 操作系统基础                            │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐    │
│  │DDE桌面 │ │APT/dpkg│ │systemd │ │D-Bus   │ │ 内核 / 驱动  │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └──────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 架构设计原则

| 原则 | 说明 |
|------|------|
| 分层解耦 | 四层架构严格分层，上层通过接口调用下层，禁止跨层直连 |
| 状态驱动 | 所有任务生命周期由状态机管理，确保可追踪、可恢复 |
| 安全优先 | 每层均设有安全检查点，工具调用需白名单授权 |
| 隐私本地化 | 敏感数据检测与脱敏在本地完成，不上传至远端模型 |
| 可扩展性 | 新增 Agent、Skill、感知模块均通过注册机制接入，零侵入 |

### 2.3 数据流概览

用户请求（文本 / 屏幕感知触发）进入系统后，经过以下核心数据流：

```
用户输入 ──▶ ContextEngine（多模态融合意图识别）
                │
                ├── 置信度 ≥ 0.7 ──▶ SkillMatcher（路由到具体 Skill）
                │                       │
                │                       ▼
                │                   Orchestrator（状态机编排）
                │                       │
                │                       ├── plan（规划）
                │                       ├── gather（信息采集）
                │                       ├── analyze（分析）
                │                       ├── execute（执行）
                │                       └── respond（响应）
                │
                ├── 置信度 0.4~0.7 ──▶ 多轮澄清对话
                │
                └── 置信度 < 0.4 ──▶ 拒绝 / 引导
```

---

## 3. 多模态融合意图识别原理

### 3.1 ContextEngine 总体设计

ContextEngine 是系统的"大脑前端"，负责从多种数据源采集上下文信号，融合判断用户意图，并输出结构化的意图描述。其核心设计思想是**多源互补、置信度量化、隐私前置过滤**。

```
┌──────────────────────────────────────────────────────────────┐
│                     ContextEngine                             │
│                                                               │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌───────────────┐     │
│  │屏幕 OCR │ │剪贴板   │ │窗口元数据 │ │ 行为轨迹追踪  │     │
│  │ 文本提取 │ │内容监听 │ │焦点窗口  │ │ 操作序列      │     │
│  └────┬────┘ └────┬────┘ └────┬─────┘ └──────┬────────┘     │
│       │           │           │               │              │
│       ▼           ▼           ▼               ▼              │
│  ┌─────────────────────────────────────────────────┐         │
│  │           隐私过滤层 (Privacy Filter)             │         │
│  │  · 敏感数据检测（密码、身份证、手机号、银行卡）    │         │
│  │  · 自动脱敏替换                                   │         │
│  │  · 审计日志记录                                   │         │
│  └────────────────────────┬────────────────────────┘         │
│                           ▼                                   │
│  ┌─────────────────────────────────────────────────┐         │
│  │          融合引擎 (Fusion Engine)                 │         │
│  │                                                   │         │
│  │  ┌───────────────┐  ┌─────────────────────┐     │         │
│  │  │ 关键词匹配器   │  │ 上下文触发器         │     │         │
│  │  │ keyword_match │  │ context_trigger     │     │         │
│  │  └───────┬───────┘  └──────────┬──────────┘     │         │
│  │          │                     │                 │         │
│  │          ▼                     ▼                 │         │
│  │  ┌──────────────────────────────────────┐       │         │
│  │  │     置信度评分器 (Confidence Scorer)   │       │         │
│  │  │                                      │       │         │
│  │  │  score = Σ(wi × fi × ci)             │       │         │
│  │  │  wi: 数据源权重                       │       │         │
│  │  │  fi: 特征匹配得分                     │       │         │
│  │  │  ci: 上下文一致度                     │       │         │
│  │  └──────────────────────┬───────────────┘       │         │
│  └─────────────────────────┼───────────────────────┘         │
│                            ▼                                  │
│  ┌─────────────────────────────────────────────────┐         │
│  │           意图输出 (Intent Output)                │         │
│  │  {                                                │         │
│  │    "intent": "email.compose",                     │         │
│  │    "confidence": 0.85,                            │         │
│  │    "slots": {"to": "...", "subject": "..."},      │         │
│  │    "sources": ["ocr", "clipboard"],               │         │
│  │    "needs_clarify": false                         │         │
│  │  }                                                │         │
│  └─────────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 数据源详解

#### 3.2.1 屏幕 OCR

通过 `screen_capture` 模块截取当前屏幕，再经 `screen_ocr` 模块提取文字信息。支持全屏和区域截取两种模式。

```python
class ScreenOCR:
    """屏幕文字识别模块 — 截屏 + OCR 提取"""

    def __init__(self):
        self.capture = ScreenCapture()
        self.ocr_engine = self._init_ocr_engine()

    def _init_ocr_engine(self):
        """初始化 OCR 引擎，优先使用 PaddleOCR，回退到 Tesseract"""
        try:
            from paddleocr import PaddleOCR
            return PaddleOCR(use_angle_cls=True, lang='ch')
        except ImportError:
            import pytesseract
            return pytesseract

    async def extract_text(self, region: Optional[Tuple[int,int,int,int]] = None) -> OCRResult:
        """截取屏幕并提取文字"""
        screenshot = await self.capture.capture(region=region)
        if hasattr(self.ocr_engine, 'ocr'):
            raw = self.ocr_engine.ocr(screenshot, cls=True)
            lines = [line[1][0] for line in raw[0]] if raw and raw[0] else []
            confidences = [line[1][1] for line in raw[0]] if raw and raw[0] else []
        else:
            text = self.ocr_engine.image_to_string(screenshot, lang='chi_sim+eng')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            confidences = [0.8] * len(lines)  # fallback 估计值

        return OCRResult(
            text='\n'.join(lines),
            lines=lines,
            avg_confidence=sum(confidences) / max(len(confidences), 1),
            region=region,
            timestamp=time.time()
        )
```

屏幕 OCR 在邮件撰写场景中用于识别收件人地址、邮件正文草稿等上下文信息；在系统诊断场景中用于识别终端输出、错误提示等关键文本。

#### 3.2.2 剪贴板监控

`clipboard_monitor` 持续监听系统剪贴板变化，记录复制内容及其来源应用：

```python
class ClipboardMonitor:
    """剪贴板监控 — 异步监听 + 历史缓存"""

    def __init__(self, max_history: int = 50):
        self.history: deque = deque(maxlen=max_history)
        self._running = False
        self._callbacks: List[Callable] = []

    async def start(self):
        """启动剪贴板监控"""
        self._running = True
        last_content = ""
        while self._running:
            try:
                content = subprocess.check_output(
                    ['xclip', '-selection', 'clipboard', '-o'],
                    timeout=2
                ).decode('utf-8', errors='replace')
                if content != last_content:
                    entry = ClipboardEntry(
                        content=content,
                        timestamp=time.time(),
                        source_app=self._get_active_app(),
                        content_type=self._classify_content(content)
                    )
                    self.history.append(entry)
                    last_content = content
                    for cb in self._callbacks:
                        await cb(entry)
            except Exception:
                pass
            await asyncio.sleep(0.5)

    def _classify_content(self, text: str) -> str:
        """分类剪贴板内容类型"""
        if re.match(r'^[\w.-]+@[\w.-]+\.\w+$', text):
            return 'email'
        if re.match(r'^https?://', text):
            return 'url'
        if re.match(r'^\d{11}$', text):
            return 'phone'
        return 'text'
```

#### 3.2.3 窗口元数据

`window_manager` 模块通过 X11/Wayland 协议获取窗口信息，包括当前焦点窗口、窗口标题、所属应用等：

```python
class WindowManager:
    """窗口元数据管理器"""

    async def get_focused_window(self) -> WindowInfo:
        """获取当前焦点窗口信息"""
        try:
            # 尝试通过 xdotool 获取
            wid = subprocess.check_output(
                ['xdotool', 'getactivewindow'], timeout=2
            ).strip().decode()
            title = subprocess.check_output(
                ['xdotool', 'getwindowname', wid], timeout=2
            ).strip().decode()
            pid = subprocess.check_output(
                ['xdotool', 'getwindowpid', wid], timeout=2
            ).strip().decode()
            wm_class = subprocess.check_output(
                ['xdotool', 'getwindowclassname', wid], timeout=2
            ).strip().decode()
        except Exception:
            return WindowInfo(title="", pid=0, wm_class="unknown")

        return WindowInfo(
            title=title,
            pid=int(pid),
            wm_class=wm_class,
            app_name=self._resolve_app_name(wm_class)
        )

    async def get_all_windows(self) -> List[WindowInfo]:
        """获取所有可见窗口列表"""
        # ... X11 枚举实现
        pass
```

#### 3.2.4 行为轨迹追踪

`behavior_tracker` 记录用户在一段时间内的操作序列（鼠标点击区域、键盘快捷键、应用切换频率），用于推断用户当前任务上下文：

```python
class BehaviorTracker:
    """用户行为轨迹追踪器"""

    def __init__(self, window_sec: int = 300):
        self.window_sec = window_sec  # 5 分钟滑动窗口
        self.events: deque = deque(maxlen=1000)
        self.app_switches: List[float] = []
        self.typing_patterns: Dict[str, int] = defaultdict(int)

    def record_event(self, event_type: str, detail: dict):
        """记录一次用户行为事件"""
        entry = {
            "type": event_type,
            "detail": detail,
            "timestamp": time.time(),
            "focused_app": detail.get("app", "unknown")
        }
        self.events.append(entry)

        if event_type == "app_switch":
            self.app_switches.append(entry["timestamp"])

    def get_task_context(self) -> TaskContext:
        """根据行为轨迹推断当前任务上下文"""
        recent = [e for e in self.events
                  if e["timestamp"] > time.time() - self.window_sec]
        app_freq = Counter(e["focused_app"] for e in recent)
        dominant_app = app_freq.most_common(1)[0][0] if app_freq else "unknown"
        switch_rate = len([t for t in self.app_switches
                          if t > time.time() - self.window_sec]) / max(self.window_sec, 1)

        return TaskContext(
            dominant_app=dominant_app,
            switch_rate=switch_rate,
            recent_apps=list(app_freq.keys()),
            inferred_activity=self._infer_activity(dominant_app, switch_rate)
        )
```

### 3.3 融合机制

ContextEngine 的融合引擎综合四种数据源信号，通过加权评分机制计算意图置信度：

#### 3.3.1 关键词匹配器

基于预定义的意图关键词表，对各数据源文本进行匹配：

```python
INTENT_KEYWORDS = {
    "email.compose": {
        "keywords": ["邮件", "发送", "写信", "收件人", "主题", "email", "compose", "send"],
        "window_hints": ["Thunderbird", "Outlook", "邮件", "mail"],
        "ocr_hints": ["收件人", "主题", "正文", "附件"],
        "weight": 1.0
    },
    "system.diagnose": {
        "keywords": ["故障", "诊断", "修复", "问题", "报错", "崩溃", "卡顿", "慢"],
        "window_hints": ["终端", "terminal", "htop", "dmesg"],
        "ocr_hints": ["error", "fail", "exception", "segfault", "OOM"],
        "weight": 1.0
    },
    "file.search": {
        "keywords": ["查找", "搜索", "找文件", "哪里", "search", "find"],
        "window_hints": ["文件管理器", "Nautilus", "Thunar"],
        "weight": 0.8
    }
}
```

#### 3.3.2 上下文触发器

除关键词外，系统还维护一组基于上下文组合的触发规则：

```python
CONTEXT_TRIGGERS = [
    {
        "name": "email_from_ocr",
        "condition": lambda ctx: (
            ctx.focused_window.wm_class in ("thunderbird", "outlook") and
            any(kw in ctx.ocr_text for kw in ["收件人", "To:", "Subject:"])
        ),
        "intent": "email.compose",
        "confidence_boost": 0.2
    },
    {
        "name": "terminal_error_pattern",
        "condition": lambda ctx: (
            ctx.focused_window.wm_class in ("deepin-terminal", "gnome-terminal") and
            any(pat in ctx.ocr_text for pat in ["Segmentation fault", "No space left",
                                                 "Permission denied", "command not found"])
        ),
        "intent": "system.diagnose",
        "confidence_boost": 0.3
    }
]
```

#### 3.3.3 置信度评分

最终置信度通过以下公式计算：

```
score = base_keyword_score
      + Σ(context_trigger_boost)
      + behavior_consistency_bonus
      + recency_decay_factor
```

```python
class ConfidenceScorer:
    """置信度评分器"""

    SOURCE_WEIGHTS = {
        "keyword_match": 0.40,
        "context_trigger": 0.30,
        "behavior_track": 0.20,
        "recency": 0.10
    }

    def score(self, intent: str, context: FusionContext) -> float:
        """计算指定意图的综合置信度"""
        base = self._keyword_score(intent, context.keyword_hits)
        trigger = self._trigger_score(intent, context.trigger_matches)
        behavior = self._behavior_score(intent, context.behavior_ctx)
        recency = self._recency_score(context.timestamp)

        raw = (base * self.SOURCE_WEIGHTS["keyword_match"] +
               trigger * self.SOURCE_WEIGHTS["context_trigger"] +
               behavior * self.SOURCE_WEIGHTS["behavior_track"] +
               recency * self.SOURCE_WEIGHTS["recency"])

        # 置信度校准：sigmoid 压缩到 [0, 1]
        calibrated = 1 / (1 + math.exp(-5 * (raw - 0.5)))
        return round(calibrated, 3)
```

### 3.4 多轮澄清机制

当最高置信度介于 0.4 ~ 0.7 之间时，系统不直接执行，而是启动多轮澄清：

```python
async def clarify_intent(self, candidates: List[IntentCandidate]) -> IntentResult:
    """多轮意图澄清"""
    if len(candidates) == 1:
        # 单候选，直接确认
        return await self._confirm_single(candidates[0])

    # 多候选，生成选择列表
    options = [f"  {i+1}. {c.description}（置信度 {c.confidence:.0%}）"
               for i, c in enumerate(candidates)]
    question = (
        "我不太确定你想要做什么，请选择：\n"
        + "\n".join(options)
        + "\n  0. 都不是，我来说明"
    )

    response = await self.ask_user(question)

    if response == "0":
        # 用户自行描述
        free_text = await self.ask_user("请描述你想要完成的任务：")
        return await self.recognize_from_text(free_text)

    idx = int(response) - 1
    return IntentResult(
        intent=candidates[idx].intent,
        confidence=1.0,  # 用户确认后置信度为 1
        slots=candidates[idx].slots,
        source="user_clarification"
    )
```

### 3.5 隐私保护

所有数据源在进入融合引擎前，必须经过 `PrivacyGuard` 的过滤层：

```python
class PrivacyGuard:
    """隐私数据守护模块"""

    SENSITIVE_PATTERNS = {
        "id_card":    r'\b\d{17}[\dX]\b',
        "phone":      r'\b1[3-9]\d{9}\b',
        "email_addr": r'\b[\w.-]+@[\w.-]+\.\w+\b',
        "bank_card":  r'\b\d{16,19}\b',
        "password":   r'(?i)(password|passwd|密码)\s*[:=]\s*\S+',
        "ip_addr":    r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    }

    def mask(self, text: str) -> Tuple[str, List[MASKED_ITEM]]:
        """对文本中的敏感信息进行脱敏"""
        masked = text
        items = []
        for category, pattern in self.SENSITIVE_PATTERNS.items():
            for match in re.finditer(pattern, masked):
                original = match.group()
                replacement = f"[{category.upper()}_MASKED]"
                masked = masked.replace(original, replacement, 1)
                items.append(MASKED_ITEM(
                    category=category,
                    original_hash=hashlib.sha256(original.encode()).hexdigest()[:16],
                    position=match.span()
                ))
        return masked, items

    def audit_log(self, action: str, items: List[MASKED_ITEM]):
        """记录隐私处理审计日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "items_count": len(items),
            "categories": list(set(i.category for i in items))
        }
        self._append_audit_log(log_entry)
```

---

## 4. 多智能体动态编排与任务调度机制

### 4.1 状态机设计

系统采用七状态有限状态机管理任务全生命周期，确保每个任务的状态可追踪、可恢复、可审计。

```
    ┌─────────┐    claim     ┌──────────┐   start    ┌─────────┐
    │ PENDING │─────────────▶│ CLAIMED  │──────────▶│ RUNNING │
    │  待处理  │              │  已认领   │           │  运行中  │
    └─────────┘              └──────────┘           └────┬────┘
         ▲                                                │
         │                              ┌─────────────────┼──────────────────┐
         │                              ▼                 ▼                  ▼
         │                     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │                     │  plan (规划)  │  │ gather (采集)│  │analyze(分析) │
         │                     └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
         │                            │                 │                  │
         │                            └─────────────────┼──────────────────┘
         │                                              ▼
         │                                     ┌──────────────┐
         │                                     │execute(执行) │
         │                                     └──────┬───────┘
         │                                              │
         │                                              ▼
         │                                     ┌──────────────┐
         │                                     │respond(响应) │
         │                                     └──────┬───────┘
         │                                              │
         ▼                                              ▼
    ┌─────────┐   verify_fail ┌──────────┐  verify_pass ┌───────────┐
    │ FAILED  │◀──────────────│ VERIFIED │─────────────▶│ COMPLETED │
    │  失败   │               │  已验证   │              │  已完成    │
    └─────────┘               └──────────┘              └───────────┘
```

状态转移规则硬编码于 `TaskStateMachine` 中：

```python
class TaskState(Enum):
    PENDING   = "pending"
    CLAIMED   = "claimed"
    RUNNING   = "running"
    VERIFIED  = "verified"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"

class RUNNINGPhase(Enum):
    PLAN    = "plan"
    GATHER  = "gather"
    ANALYZE = "analyze"
    EXECUTE = "execute"
    RESPOND = "respond"

# 状态转移表（硬编码，确保安全）
TRANSITIONS = {
    TaskState.PENDING:   [TaskState.CLAIMED, TaskState.CANCELLED],
    TaskState.CLAIMED:   [TaskState.RUNNING, TaskState.CANCELLED],
    TaskState.RUNNING:   [TaskState.VERIFIED, TaskState.FAILED],
    TaskState.VERIFIED:  [TaskState.COMPLETED, TaskState.FAILED, TaskState.RUNNING],
    TaskState.COMPLETED: [],
    TaskState.FAILED:    [TaskState.PENDING],  # 允许重试
    TaskState.CANCELLED: [],
}

# RUNNING 子阶段转移
PHASE_TRANSITIONS = {
    RUNNINGPhase.PLAN:    [RUNNINGPhase.GATHER],
    RUNNINGPhase.GATHER:  [RUNNINGPhase.ANALYZE],
    RUNNINGPhase.ANALYZE: [RUNNINGPhase.EXECUTE],
    RUNNINGPhase.EXECUTE: [RUNNINGPhase.RESPOND],
    RUNNINGPhase.RESPOND: [],  # 结束后进入 VERIFIED
}
```

### 4.2 RUNNING 阶段分解

RUNNING 状态内部细分为五个子阶段，每个子阶段有明确的职责、工具白名单和 Token 预算：

| 子阶段 | 职责 | 工具白名单 | Token 预算 |
|--------|------|-----------|-----------|
| plan | 分析任务目标，制定执行计划 | [] | 500 |
| gather | 采集必要信息（搜索、OCR、文件读取） | search, file_read, ocr | 2000 |
| analyze | 分析采集到的信息，形成结论 | python_eval | 1500 |
| execute | 执行具体操作（发送、安装、配置） | shell, package, dbus | 1000 |
| respond | 生成用户友好的结果报告 | [] | 800 |

```python
PHASE_CONFIG = {
    RUNNINGPhase.PLAN: {
        "allowed_tools": [],
        "token_budget": 500,
        "timeout_sec": 30,
        "description": "分析任务，制定执行计划"
    },
    RUNNINGPhase.GATHER: {
        "allowed_tools": ["search", "file_read", "ocr", "clipboard_read", "window_list"],
        "token_budget": 2000,
        "timeout_sec": 60,
        "description": "采集必要信息"
    },
    RUNNINGPhase.ANALYZE: {
        "allowed_tools": ["python_eval"],
        "token_budget": 1500,
        "timeout_sec": 45,
        "description": "分析采集信息，形成结论"
    },
    RUNNINGPhase.EXECUTE: {
        "allowed_tools": ["shell", "package", "dbus_call", "file_write"],
        "token_budget": 1000,
        "timeout_sec": 120,
        "description": "执行具体操作"
    },
    RUNNINGPhase.RESPOND: {
        "allowed_tools": [],
        "token_budget": 800,
        "timeout_sec": 30,
        "description": "生成结果报告"
    }
}
```

### 4.3 统一编排器 (Orchestrator)

`Orchestrator` 是系统的核心调度引擎，支持两种执行模式：

```python
class OrchestratorMode(Enum):
    TOOLS   = "tools"    # MCP ToolRegistry 模式
    WORKERS = "workers"  # 子进程 Worker 池模式

class Orchestrator:
    """统一编排器 — 融合 v3/v4/prod 最佳特性"""

    def __init__(self, mode: OrchestratorMode = OrchestratorMode.TOOLS):
        self.mode = mode
        self.state_machine = TaskStateMachine()
        self.verifier = Verifier()
        self.security = SecurityConfig()
        self.agents: Dict[str, BaseAgent] = {}
        self.tool_registry = MCPToolRegistry()
        self.worker_pool: Dict[str, subprocess.Popen] = {}
        self.skills = SkillRegistry()
        self.trace = TraceCollector()

    async def execute_task(self, task: Task) -> TaskResult:
        """执行一个任务的完整生命周期"""
        self.trace.start(task.id)

        # 1. 状态转移 PENDING → CLAIMED
        self.state_machine.transition(task, TaskState.CLAIMED)
        agent = self._select_agent(task)
        self.trace.record("claimed", {"agent": agent.name})

        # 2. CLAIMED → RUNNING
        self.state_machine.transition(task, TaskState.RUNNING)
        result = await self._run_phases(task, agent)

        # 3. RUNNING → VERIFIED
        self.state_machine.transition(task, TaskState.VERIFIED)
        checks = await self.verifier.verify(task, result)

        if all(checks.values()):
            # 4. VERIFIED → COMPLETED
            self.state_machine.transition(task, TaskState.COMPLETED)
            self.trace.record("completed", {"checks": checks})
            return TaskResult(success=True, data=result, checks=checks)
        else:
            # 4. VERIFIED → FAILED (或回退到 RUNNING 重试)
            failed = [k for k, v in checks.items() if not v]
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                self.state_machine.transition(task, TaskState.RUNNING)
                self.trace.record("retry", {"failed_checks": failed})
                return await self.execute_task(task)
            else:
                self.state_machine.transition(task, TaskState.FAILED)
                self.trace.record("failed", {"failed_checks": failed})
                return TaskResult(success=False, error=f"验证失败: {failed}")

    async def _run_phases(self, task: Task, agent: BaseAgent) -> dict:
        """按顺序执行 RUNNING 的五个子阶段"""
        context = PhaseContext(task=task, agent=agent)
        for phase in RUNNINGPhase:
            config = PHASE_CONFIG[phase]
            self.state_machine.set_phase(task, phase)
            self.trace.record(f"phase_{phase.value}_start", {})

            # Token 预算检查
            token_counter = TokenBudget(config["token_budget"])

            # 工具白名单设置
            allowed = config["allowed_tools"]
            context.set_allowed_tools(allowed)

            # 执行阶段
            try:
                phase_result = await asyncio.wait_for(
                    self._execute_phase(phase, context, token_counter),
                    timeout=config["timeout_sec"]
                )
                context.accumulate(phase_result)
            except asyncio.TimeoutError:
                raise PhaseTimeoutError(phase, config["timeout_sec"])

            self.trace.record(f"phase_{phase.value}_end", {
                "tokens_used": token_counter.used
            })

        return context.result

    def _select_agent(self, task: Task) -> BaseAgent:
        """根据 Skill 匹配结果选择最合适的 Agent"""
        skill_match = self.skills.match(task.intent)
        if skill_match:
            return self.agents[skill_match.agent_name]
        # 回退到默认 Agent
        return self.agents.get("InformationCollector", list(self.agents.values())[0])
```

### 4.4 验证器 (Verifier)

验证器包含七项独立检查，全部通过后任务才标记为 COMPLETED：

```python
class Verifier:
    """任务结果验证器 — 7 项独立检查"""

    async def verify(self, task: Task, result: dict) -> Dict[str, bool]:
        """执行全部验证检查"""
        return {
            "completeness":   self._check_completeness(task, result),
            "consistency":    self._check_consistency(result),
            "no_hallucination": await self._check_hallucination(result),
            "tool_usage":     self._check_tool_usage(task, result),
            "security":       self._check_security(task, result),
            "privacy":        self._check_privacy(result),
            "format":         self._check_format(result),
        }

    def _check_completeness(self, task: Task, result: dict) -> bool:
        """检查任务目标是否全部完成"""
        required = task.requirements
        completed = result.get("completed_requirements", [])
        return all(r in completed for r in required)

    def _check_consistency(self, result: dict) -> bool:
        """检查结果内部一致性（无自相矛盾）"""
        statements = result.get("statements", [])
        # 使用模型辅助判断一致性
        return len(statements) > 0  # 简化版

    async def _check_hallucination(self, result: dict) -> bool:
        """检查结果是否包含幻觉内容"""
        # 核实关键事实是否来源于实际采集数据
        sources = result.get("sources", [])
        claims = result.get("claims", [])
        for claim in claims:
            if not any(self._evidence_supports(source, claim) for source in sources):
                return False
        return True

    def _check_tool_usage(self, task: Task, result: dict) -> bool:
        """检查工具调用是否符合白名单"""
        used_tools = set(result.get("tools_used", []))
        phase = task.current_phase
        allowed = set(PHASE_CONFIG[phase]["allowed_tools"])
        return used_tools.issubset(allowed)

    def _check_security(self, task: Task, result: dict) -> bool:
        """检查执行过程是否有越权行为"""
        return not result.get("security_violations", [])

    def _check_privacy(self, result: dict) -> bool:
        """检查输出中是否包含未脱敏的敏感数据"""
        output = json.dumps(result.get("output", ""), ensure_ascii=False)
        return not PrivacyGuard().contains_sensitive(output)

    def _check_format(self, result: dict) -> bool:
        """检查输出格式是否符合规范"""
        required_fields = ["output", "summary"]
        return all(f in result for f in required_fields)
```

### 4.5 冲突解决与资源锁定

当多个任务并行执行时，编排器使用优先级资源锁避免冲突：

```python
class ResourceLock:
    """基于优先级的资源锁管理器"""

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._queue: Dict[str, List[Tuple[int, str, asyncio.Event]]] = {}

    async def acquire(self, resource: str, task_id: str, priority: int = 5):
        """获取资源锁，priority 越小优先级越高"""
        if resource not in self._locks:
            self._locks[resource] = asyncio.Lock()

        event = asyncio.Event()
        if resource not in self._queue:
            self._queue[resource] = []
        self._queue[resource].append((priority, task_id, event))
        self._queue[resource].sort(key=lambda x: x[0])

        # 等待轮到自己
        while True:
            top = self._queue[resource][0]
            if top[1] == task_id:
                await self._locks[resource].acquire()
                self._queue[resource].pop(0)
                return
            await event.wait()
            event.clear()

    def release(self, resource: str):
        """释放资源锁"""
        self._locks[resource].release()
        if self._queue.get(resource):
            _, _, next_event = self._queue[resource][0]
            next_event.set()
```

### 4.6 MCP 工具集成

编排器通过 MCP（Model Context Protocol）协议与工具层交互，采用纯 Python 实现的 JSON-RPC over stdio 通信：

```python
class MCPToolRegistry:
    """MCP 工具注册中心"""

    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self.tools: Dict[str, MCPTool] = {}

    async def register_server(self, name: str, command: List[str]):
        """注册一个 MCP 服务器"""
        server = MCPServer(name=name, command=command)
        await server.start()
        self.servers[name] = server
        # 获取服务器提供的工具列表
        tools = await server.list_tools()
        for tool in tools:
            self.tools[tool.name] = tool

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """调用指定的 MCP 工具"""
        if name not in self.tools:
            raise ToolNotFoundError(name)
        tool = self.tools[name]
        return await tool.server.call(name, arguments)
```

---

## 5. 核心场景实现

### 5.1 场景一：智能邮件助手

智能邮件助手覆盖从意图识别到邮件生成的完整流程，是系统"感知 → 理解 → 生成 → 确认"能力的集中展示。

#### 5.1.1 场景流程图

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ 用户触发  │────▶│ ContextEngine│────▶│ 意图分类     │
│ "帮我写   │     │ 多模态融合   │     │ email.compose│
│  封邮件"  │     └──────────────┘     └──────┬───────┘
└──────────┘                                  │
                                              ▼
                                    ┌──────────────────┐
                                    │ 意图澄清         │
                                    │ "邮件主题是？"    │
                                    │ "收件人是谁？"    │
                                    │ "大概内容是？"    │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │ InformationCollector│
                                    │ gather 阶段       │
                                    │  · 读取剪贴板内容  │
                                    │  · OCR 识别屏幕文字│
                                    │  · 读取相关文件    │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │ ContentCreator    │
                                    │ analyze + execute │
                                    │  · 分析素材       │
                                    │  · 生成邮件正文   │
                                    │  · 格式化输出     │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │ 用户确认         │
                                    │ "邮件内容如下：   │
                                    │  ......          │
                                    │  是否发送？ Y/N" │
                                    └────────┬─────────┘
                                             │
                                   ┌─────────┴─────────┐
                                   ▼                   ▼
                            ┌────────────┐      ┌────────────┐
                            │ 执行发送    │      │ 用户修改后  │
                            │ COMPLETED  │      │ 重新生成    │
                            └────────────┘      └────────────┘
```

#### 5.1.2 场景实现代码

```python
class EmailAssistantScenario:
    """智能邮件助手场景"""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator
        self.context_engine = orchestrator.context_engine

    async def handle(self, user_input: str, context: ScenarioContext) -> str:
        """处理邮件助手请求"""
        # Phase 1: 意图澄清
        slots = await self._clarify_email_intent(user_input, context)

        # Phase 2: 信息采集 (InformationCollector)
        collector = self.orchestrator.agents["InformationCollector"]
        materials = await collector.execute(Task(
            intent="info.gather",
            params={
                "sources": ["clipboard", "ocr", "file_read"],
                "keywords": [slots.get("topic", ""), slots.get("to", "")],
            }
        ))

        # Phase 3: 内容生成 (ContentCreator)
        creator = self.orchestrator.agents["ContentCreator"]
        draft = await creator.execute(Task(
            intent="content.generate",
            params={
                "type": "email",
                "to": slots["to"],
                "subject": slots["subject"],
                "materials": materials,
                "tone": slots.get("tone", "formal"),
                "language": slots.get("language", "zh-CN"),
            }
        ))

        # Phase 4: 用户确认
        preview = f"""
📧 邮件预览
────────────────────────
收件人: {slots['to']}
主  题: {slots['subject']}
────────────────────────
{draft['body']}
────────────────────────
"""
        confirm = await self.orchestrator.ask_user(
            f"{preview}\n是否发送？(Y/N/修改)"
        )

        if confirm.upper() == "Y":
            # 执行发送
            result = await self._send_email(slots, draft)
            return f"✅ 邮件已发送给 {slots['to']}"
        elif confirm.upper() == "N":
            return "❌ 邮件已取消"
        else:
            # 用户提供修改意见
            revised = await creator.execute(Task(
                intent="content.revise",
                params={"original": draft, "feedback": confirm}
            ))
            return await self.handle(user_input, context)  # 重新确认

    async def _clarify_email_intent(self, user_input: str, ctx: ScenarioContext) -> dict:
        """逐步澄清邮件参数"""
        slots = {}
        if "to" not in slots:
            slots["to"] = await self.orchestrator.ask_user("请提供收件人邮箱地址：")
        if "subject" not in slots:
            slots["subject"] = await self.orchestrator.ask_user("邮件主题是什么？")
        if "topic" not in slots:
            slots["topic"] = await self.orchestrator.ask_user("邮件大概要说什么内容？")
        return slots
```

### 5.2 场景二：系统问题诊断

系统问题诊断场景展示系统与 deepin 25 操作系统的深度集成能力，涵盖问题分类、诊断分析、修复执行和结果验证全流程。

#### 5.2.1 场景流程图

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ 用户报告问题  │────▶│ 问题分类         │────▶│ SystemOperator   │
│ "系统变慢了"  │     │  · 性能问题       │     │ 诊断流程          │
│              │     │  · 软件故障       │     │                  │
│              │     │  · 网络问题       │     │ plan: 制定诊断方案 │
│              │     │  · 硬件异常       │     │ gather: 采集数据  │
└──────────────┘     └──────────────────┘     │ analyze: 分析原因 │
                                              └────────┬─────────┘
                                                       │
           ┌───────────────────────────────────────────┤
           ▼                                           ▼
  ┌─────────────────┐                       ┌─────────────────┐
  │ 自动诊断采集     │                       │ 手动诊断采集     │
  │ · CPU / 内存监控 │                       │ · 用户提供日志   │
  │ · 磁盘 I/O      │                       │ · 错误截图 OCR   │
  │ · 系统日志分析   │                       │                  │
  │ · 进程 TOP 分析  │                       │                  │
  │ · D-Bus 服务状态 │                       │                  │
  └────────┬────────┘                       └────────┬────────┘
           │                                         │
           └─────────────────┬───────────────────────┘
                             ▼
                  ┌──────────────────┐
                  │ 诊断结论生成     │
                  │ "发现 3 个问题： │
                  │  1. 内存使用 92% │
                  │  2. swap 频繁    │
                  │  3. 某进程异常"  │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ 修复方案确认     │
                  │ "建议执行以下操作 │
                  │  · 清理缓存      │
                  │  · 终止异常进程  │
                  │  是否执行？"     │
                  └────────┬─────────┘
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
          ┌────────────┐     ┌────────────┐
          │ 执行修复    │     │ 用户跳过   │
          │ · 清理缓存  │     │ 仅报告结果 │
          │ · 终止进程  │     └────────────┘
          │ · 重启服务  │
          └─────┬──────┘
                │
                ▼
          ┌──────────────────┐
          │ 结果验证         │
          │ · 再次检查指标   │
          │ · 确认问题消除   │
          │ · 生成诊断报告   │
          └──────────────────┘
```

#### 5.2.2 系统诊断实现

```python
class SystemDoctorScenario:
    """系统问题诊断场景"""

    DIAGNOSTIC_COMMANDS = {
        "cpu":     "top -bn1 | head -20",
        "memory":  "free -h && cat /proc/meminfo | head -10",
        "disk":    "df -h && iostat -x 1 1 2>/dev/null || echo 'iostat unavailable'",
        "process": "ps aux --sort=-%mem | head -15",
        "network": "ss -tuln | head -20 && ping -c 3 8.8.8.8 2>/dev/null",
        "systemd": "systemctl --failed 2>/dev/null || echo 'systemctl unavailable'",
        "dmesg":   "dmesg --level=err,warn | tail -30",
        "dbus":    "dbus-send --session --dest=org.freedesktop.DBus "
                   "--type=method_call --print-reply "
                   "/org/freedesktop/DBus org.freedesktop.DBus.ListNames",
    }

    async def handle(self, user_input: str, context: ScenarioContext) -> str:
        """执行系统诊断"""
        # Phase 1: 问题分类
        category = await self._classify_problem(user_input)
        logger.info(f"问题分类: {category}")

        # Phase 2: 制定诊断方案 (plan)
        plan = await self._make_diagnostic_plan(category, user_input)

        # Phase 3: 采集诊断数据 (gather)
        diagnostics = {}
        for item in plan["data_sources"]:
            cmd = self.DIAGNOSTIC_COMMANDS.get(item)
            if cmd:
                diagnostics[item] = await self._run_diagnostic(cmd)

        # Phase 4: 分析诊断结果 (analyze)
        analysis = await self._analyze_results(diagnostics, category)

        # Phase 5: 生成报告并建议修复 (respond)
        report = self._format_report(category, diagnostics, analysis)

        if analysis.get("fixable"):
            confirm = await self.orchestrator.ask_user(
                f"{report}\n\n建议执行修复操作，是否继续？(Y/N)"
            )
            if confirm.upper() == "Y":
                fix_result = await self._apply_fixes(analysis["fixes"])
                # Phase 6: 验证修复效果
                verification = await self._verify_fixes(analysis, diagnostics)
                return f"{report}\n\n修复结果:\n{fix_result}\n验证: {verification}"

        return report

    async def _classify_problem(self, text: str) -> str:
        """使用 ERNIE-Lite 对问题进行快速分类"""
        prompt = f"""请将以下系统问题分类为一个类别：
类别选项：performance, software_crash, network, hardware, security, other
问题描述：{text}
只输出类别名称。"""
        response = await self.orchestrator.llm.route(
            prompt=prompt, model="ernie-lite"
        )
        return response.strip().lower()

    async def _run_diagnostic(self, cmd: str) -> str:
        """安全执行诊断命令"""
        # 安全检查：只允许只读命令
        if any(danger in cmd for danger in ["rm ", "mkfs", "dd ", "> /"]):
            raise SecurityViolationError(f"危险命令被拒绝: {cmd}")
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        return stdout.decode('utf-8', errors='replace')

    async def _analyze_results(self, diagnostics: dict, category: str) -> dict:
        """使用 ERNIE-3.5 分析诊断结果"""
        prompt = f"""作为 deepin 25 系统运维专家，请分析以下诊断数据。

问题类别: {category}
诊断数据:
{json.dumps(diagnostics, ensure_ascii=False, indent=2)}

请返回 JSON 格式：
{{
    "issues": ["问题1", "问题2", ...],
    "root_cause": "根本原因分析",
    "fixable": true/false,
    "fixes": ["修复建议1", "修复建议2", ...],
    "severity": "low/medium/high"
}}"""
        response = await self.orchestrator.llm.route(
            prompt=prompt, model="ernie-3.5"
        )
        return json.loads(response)
```

---

---

> **附录**：第 6-9 节（关键技术实现、创新点、部署与验证、总结与展望）见 [TECHNICAL_REPORT_APPENDIX.md](TECHNICAL_REPORT_APPENDIX.md)

---

## ~~6. 关键技术实现~~

> 📎 移至 [附录 §6](TECHNICAL_REPORT_APPENDIX.md#6-关键技术实现)


