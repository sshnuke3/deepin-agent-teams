# 技术选型决策

## 文心大模型 API（erniebot SDK）

**选型原因：** 赛题要求使用飞桨文心大模型 API
**API 类型：** aistudio（AI Studio 平台 token 认证）
**已知限制：**
- 不支持 system role，需用 user role 替代
- 有调用频率限制和 token 配额
- 模型名称：`ernie-lite`（轻量）、`ernie-3.5`（强力）

**双模型路由策略：**
- 轻量任务（意图识别/摘要/分类）→ ernie-lite（快/便宜）
- 复杂任务（邮件生成/诊断/代码分析）→ ernie-3.5（强/贵）
- 强模型失败自动降级到 lite

**更新（2026-05-22）：** 当前 token 已耗尽，ERNIE 仅作降级备选。

## PyQt5

**选型原因：** 赛题要求提供 GUI 交互界面，deepin 25 预装 Qt 库
**替代方案对比：**
- tkinter：功能太弱，不支持深色主题
- Electron：太重，打包后 100MB+
- GTK：Python 绑定文档少
**已知限制：** 截图功能在部分 Wayland 环境下不兼容

## PaddleOCR

**选型原因：** 飞桨生态，中文识别准确率高，离线可用
**替代方案对比：**
- Tesseract：中文识别率低
- 百度 OCR API：需要网络，有调用费用
**已知限制：** 首次加载模型较慢（约 3-5 秒）

## deepin D-Bus

**选型原因：** deepin 25 的系统管理都通过 D-Bus 接口暴露
**实现方式：** 使用 `dbus-send` 命令行工具（不依赖 dbus-python 库）
**已知限制：** D-Bus 接口可能随 deepin 版本变化

## 文件锁（fcntl）

**选型原因：** 多 Agent 并行执行时需要进程级互斥
**实现方式：** fcntl.flock() 文件锁 + 进程内 dict 锁
**已知限制：** 仅 Linux 可用，Windows 不兼容

## 多模型路由（ModelRouter）

**选型原因：** MiniMax 为主力模型，ERNIE 作降级备选。避免单点故障。
**实现方式：** 按优先级尝试调用，失败自动切换。
**路由链：** MiniMax → ERNIE-lite → ERNIE-3.5 → Fallback（返回错误信息）
**响应格式：** 统一 ModelResponse（content/success/error/latency_ms/token_used）
**环境变量：** `MINIMAX_API_KEY` / `ERNIE_TOKEN`

## 状态机引擎（TaskStateMachine）

**选型原因：** 替代轮询+模型主观判断，所有停止条件代码写死。
**核心原则：**
- 状态跳转条件写死在代码，不靠模型主观判断
- 每次跳转写 trace（/tmp/deepin_traces/{task_id}.jsonl）
- 状态机本身无状态，所有状态存在 Registry 层

**7 种状态：** PENDING / CLAIMED / RUNNING / VERIFIED / COMPLETED / FAILED / RETRY
**跳转规则：** 见 ARCHITECTURE.md 状态转换表
**超时检测：** RUNNING 状态超过 DEFAULT_TIMEOUT（60s）自动标记 FAILED
**重试策略：** RETRY → RUNNING，最多 MAX_RETRY（3）次，超时耗尽跳 FAILED

## 独立 Verifier

**选型原因：** VERIFIER ≠ 执行者，不能是同一个认知主体。
**设计原则：**
- 不读 Worker 上下文，完全独立的世界观
- 验收标准是清单（checklist），不是模型主观判断
- 决策只有三种：PASS / FAIL(reasons) / RETRY(cause)

**4 项检查：** deliverable_exists / functional_correctness / trace_integrity / error_free
**类型分叉：** 不同 task type 有不同验收标准：
- `code_analysis` → 需 `lines` 字段
- `shell_executor` → 需 `command` + `exit_code`
- `file_reader` → 需 `content` 或 `size`
- `web_search` → 需 `results` 列表
- `ast_parser` → 需 `ast` 字段
**可接受错误：** E_TIMEOUT / E_BLOCKED 不算 FAIL（用户可重试），其他算 FAIL

## CheckpointManager

**选型原因：** 失败恢复时不让 Worker 整体重来，跳过已完成的 capability。
**目录结构：** /tmp/deepin_checkpoints/{task_id}/
**关键方法：**
- `save(capability, result)` — 每步能力执行完写 checkpoint
- `is_completed(capability)` — 检查是否已完成
- `last_checkpoint()` — 重试时从最近 checkpoint 恢复
- `verify(capability, result)` — hash 验证防篡改
- `cleanup()` — 成功后清理所有 checkpoint 文件

## 网页搜索（duckduckgo html）

**选型原因：** 无需 API key，直接 curl duckduckgo html 端即可。
**限制：** 可能被 CAPTCHA/cloudflare 拦截（标记为 E_BLOCKED，不算 FAIL）
**解析方式：** 正则提取 `<a class="result__a">` 标题和链接
**备选：** 如果 duckduckgo 也被拦，考虑 Bing 搜索 API 或 SearXNG

## MCP 工具协议（mcp_protocol.py）

**选型原因：** 解耦工具层，实现「加工具不改 Agent」。
**决策时间：** 2026-06-03

**方案对比：**

| 方案 | 优点 | 缺点 |
|------|------|------|
| 硬编码（v3） | 简单直接 | 工具和 Agent 强耦合 |
| 官方 MCP SDK | 协议完整 | PEP 668 限制，无法 pip install |
| **纯 Python 实现（选用）** | 零依赖、协议兼容、深信适配 | 需自行实现 JSON-RPC |

**实现要点：**
- JSON-RPC over stdio，与官方 MCP 协议一致
- MCPServer：装饰器注册工具，自动处理 initialize/list/call
- MCPClient：连接子进程，自动发现和调用工具
- ToolRegistry：统一工具注册表，支持本地 + MCP 两种来源

**核心收益：**
- 加新工具 = 写 MCP Server + `connect_server()` 一行代码
- 每个 Server 可独立运行、独立测试
- 工具列表自动生成 LLM Function Calling 格式

**相关文件：** `mcp_servers/mcp_protocol.py`、`tools/tool_registry.py`、`agents/orchestrator_v4.py`