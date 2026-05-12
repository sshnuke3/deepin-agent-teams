# deepin-agent-teams RFC

> 技术请求评论文档 - 记录架构决策与技术选型

---

## 1. 项目概述

| 属性 | 值 |
|------|------|
| **项目名** | deepin-agent-teams |
| **赛题** | #27 基于统信操作系统与文心大模型的多智能体协作系统 |
| **厂商** | 统信软件（deepin） |
| **赛道** | 第十期飞桨黑客松·文心合作伙伴·进阶任务 |
| **目标系统** | deepin 25 操作系统 |
| **核心技术** | OpenClaw sessions_spawn + 文心大模型 API |
| **仓库** | https://github.com/sshnuke3/deepin-agent-teams |

---

## 2. 架构演进

### v1（已废弃）— 伪多 Agent
```
Lead → Researcher → Coder → Result
```
**问题**：三个 Python 类，串行调用 LLM，无真正的 Agent 隔离

### v2 — 多进程固定分工
```
Orchestrator
  ├── subprocess: Researcher（读文件）
  └── subprocess: Coder（分析代码）
```
**改进**：进程级隔离，独立运行
**问题**：分工固化，难以扩展新 Agent

### v3 — Registry 驱动可扩展
```
AgentRegistry（注册中心 + 任务队列 + fcntl.flock 文件锁）
  └── Worker（自主认领任务）
```
**改进**：动态注册，按需扩展
**问题**：能力通过 Python 函数定义，非真正的 LLM Agent

### v4（当前）— sessions_spawn 原生多 Agent
```
Orchestrator（OpenClaw Agent）
    ↓ sessions_spawn
    ├── Researcher（OpenClaw tools: read/web_fetch/search）
    ├── Coder（OpenClaw tools: read/exec）
    └── General（OpenClaw tools: read/exec/write）
    ↓ sessions_send
    子 Agent 返回 Markdown 报告
```
**改进**：真正的 OpenClaw 子 Agent，LLM 推理 + 系统上下文 + 原生工具

---

## 3. 技术选型对比

### Agent 框架选型

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **LangChain Agents** | 生态丰富 | 重量级，deepin 兼容性差 | ❌ |
| **CrewAI** | 多 Agent 协作成熟 | 依赖 OpenAI，非国产 | ❌ |
| **AutoGen** | 微软背书 | 复杂，国产系统适配不佳 | ❌ |
| **OpenClaw sessions_spawn** | 国产开源，真正的进程隔离 Agent | 文档较少 | ✅ **选用** |

### 大模型选型

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **GPT-4** | 能力强 | 需翻墙，费用高，赛题不符 | ❌ |
| **Claude** | 推理强 | 需翻墙，国产系统适配差 | ❌ |
| **文心 erinebot** | 赛题要求，国产 | 额度有限 | ✅ **选用** |

### OCR 选型

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **Tesseract** | Linux 原生，部署简单 | 中文识别率低 | ❌ |
| **PaddleOCR** | 飞桨生态，中文强，Linux 兼容 | 资源占用较高 | ✅ **选用** |

### GUI 框架选型

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **Electron** | 跨平台，生态好 | 资源重，deepin 适配一般 | ❌ |
| **GTK** | deepin 官方 | Python 绑定不友好 | ❌ |
| **PyQt5** | deepin 官方使用，Linux 兼容最佳 | 学习曲线 | ✅ **选用** |

---

## 4. 双模型路由设计

### 路由策略

```python
# model_router.py

def get_model_for_task(task_type: str) -> str:
    """
    任务类型 → 模型选择
    """
    lite_tasks = {"email", "simple_query", "status_check"}
    pro_tasks = {"code_analysis", "literature", "complex_reasoning", "system_diagnosis"}

    if task_type in lite_tasks:
        return "ernie-lite"   # 快速、便宜
    elif task_type in pro_tasks:
        return "ernie-3.5"   # 强大、昂贵
    else:
        return "ernie-lite"   # 默认轻量
```

### 降级策略

```
ernie-3.5 请求失败
    ↓
自动切换 ernie-lite 重试（1次）
    ↓
ernie-lite 仍失败
    ↓
返回降级结果 + 错误提示
```

---

## 5. 感知层设计

### 数据流

```
deepin 25 桌面环境
    │
    ├─→ screen_capture.py   ──→ 图片
    │         ↓
    │    screen_ocr.py      ──→ 文字
    │
    ├─→ clipboard_monitor.py ──→ 文本
    ├─→ window_manager.py   ──→ 窗口信息
    ├─→ system_monitor.py   ──→ 系统状态
    ├─→ deepin_dbus.py     ──→ 控制中心API
    │
    └─→ context_engine.py  ──→ 意图识别
              ↓
         置信度阈值 > 0.8 → 执行
         置信度阈值 0.5-0.8 → 意图澄清
         置信度阈值 < 0.5 → 响应"我不太理解"
```

### 隐私保护（6类敏感数据）

```python
# perception/privacy_guard.py

SENSITIVE_PATTERNS = [
    r"手机号[：:]?\d{11}",           # 手机号
    r"身份证[：:]?\d{17}[\dXx]",     # 身份证
    r"密码[：:]\S+",                  # 密码
    r"\d{16,19}",                    # 银行卡号
    r"[A-Za-z0-9._%+-]+@[a-z]+\.[a-z]+",  # 邮箱
    r"地址[：:][^\s]{10,}",          # 详细地址
]
```

---

## 6. 多 Agent 协作流程

### sessions_spawn 流程

```
用户输入自然语言请求
    ↓
Lead Agent（总调度）
    ↓ 任务拆分
sessions_spawn(Researcher + Coder + General)
    ↓ 并行执行
  ┌──┴──┐
  ↓     ↓
Researcher Coder
(read+   (exec+
 web_    code_
 fetch)  analyze)
  ↓     ↓
sessions_send(子Agent, task)
    ↓
子Agent 返回 Markdown 报告
    ↓
Lead 汇总 → 格式化输出 → 用户
```

### 冲突解决机制

```python
# agents/conflict_resolver.py

def resolve_conflict(agent_a_task, agent_b_task) -> Resolution:
    """
    检测任务冲突并协商解决
    """
    # 冲突类型：
    # 1. 资源竞争（同时访问同一文件）
    # 2. 指令矛盾（A要写，B要删）
    # 3. 循环依赖（A等B，B等A）

    if conflict_type == "file_access":
        # 文件锁机制，按优先级排序
        return prioritize_by_priority(agent_a_task, agent_b_task)
    elif conflict_type == "circular_dep":
        # 中断循环，选择更高优先级任务继续
        return interrupt_and_continue()
```

---

## 7. 验证记录

### sessions_spawn 演示（2026-04-06）

| 测试项 | 结果 |
|--------|------|
| sessions_spawn 成功返回 childSessionKey | ✅ |
| sessions_send 成功分发任务 | ✅ |
| 子 Agent 返回 Markdown 报告 | ✅ |
| Lead 汇总子 Agent 结果 | ✅ |

### 感知层模块测试

```bash
# 在 deepin 25 实体机运行
python3 tests/test_perception_deepin25.py

# 测试结果输出到:
# tests/test_results_TIMESTAMP.json
```

---

## 8. 部署方案

### deepin 25 一键部署

```bash
bash deepin25_deploy.sh
```

**部署内容：**
1. 检查 Python 3.10+
2. 安装系统依赖（grim/scrot/xclip/wmctrl/xdotool）
3. 安装 PaddleOCR 及其模型
4. 安装 Python 依赖（erniebot/PyQt5/psutil）
5. 验证感知层模块可导入

### 依赖清单

| 依赖 | 用途 |
|------|------|
| `erniebot` | 文心大模型 API |
| `Pillow` | 图像处理 |
| `PaddleOCR` | OCR 文字识别 |
| `PyQt5` | GUI 图形界面 |
| `psutil` | 系统资源监控 |
| `python-dotenv` | 环境变量管理 |

---

## 9. 未来扩展方向

1. **MCP 协议深度集成**：接入更多 MCP Server 扩展工具能力
2. **记忆系统**：引入长期记忆，支持跨会话上下文
3. **多模态感知**：结合语音输入/输出，实现语音交互
4. **分布式 Agent**：支持跨机器 Agent 协作
5. **安全沙箱**：为每个子 Agent 提供独立的受限执行环境

---

## 10. 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-04-06 | v1 | 初始版本，伪多 Agent |
| 2026-04-10 | v2 | 多进程架构 |
| 2026-04-15 | v3 | Registry 可扩展架构 |
| 2026-04-28 | v4 | sessions_spawn 原生多 Agent |
| 2026-05-10 | v4.1 | 生产级编排器 + GUI |

---

*本文档由 sshnuke3 维护，最后更新：2026-05-12*