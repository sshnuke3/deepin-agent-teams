# 质量标准

> 基于三角架构（状态机 + Verifier + Worker）的质量保障体系

---

## 一、状态机质量标准

### 状态定义完整性

| 状态 | 前驱状态 | 跳转条件 | trace 字段 |
|------|---------|---------|-----------|
| PENDING | — | submit_task() | from/to/ts |
| CLAIMED | PENDING, FAILED | worker_id 存在 | from/to/ts/worker_id |
| RUNNING | CLAIMED | start_time 记录 | from/to/ts/start_time |
| VERIFIED | RUNNING | Verifier PASS | from/to/ts/verdict |
| COMPLETED | VERIFIED | 自动 | from/to/ts |
| RETRY | RUNNING | FAIL + retry<3 | from/to/ts/verdict/causes |
| FAILED | PENDING/CLAIMED/RUNNING/RETRY | 超时/重试耗尽 | from/to/ts/error_msg |

### 跳转规则约束

- 所有跳转条件必须**代码写死**，禁止模型主观判断
- 每次跳转必须写 trace，trace 写入 `/tmp/deepin_traces/{task_id}.jsonl`
- 非法跳转（不在规则表中的）必须**拒绝**，不得静默通过

### 超时规则

```
DEFAULT_TIMEOUT = 60s（从 CLAIMED 开始计时）
HEARTBEAT_INTERVAL = 5s
超时检测：RUNNING 状态超过 DEFAULT_TIMEOUT → FAILED
```

---

## 二、Verifier 验收标准

### 4 项强制检查

#### 1. deliverable_exists
- 结果非空（`result != {} and result != [] and result is not None`）
- 失败时记录：`{"check": "deliverable_exists", "result": "FAIL", "reason": "..."}`

#### 2. functional_correctness（按 task type 分叉）

| Task Type | 必填字段 | 检查逻辑 |
|-----------|---------|---------|
| code_analysis | lines, functions/classes 至少一项 | `lines > 0` |
| shell_executor | command, exit_code | `exit_code in (0, 1, 2, ...)` |
| file_reader | content 或 size | `size > 0 or content != ""` |
| web_search | results, count | `count > 0 and len(results) > 0` |
| ast_parser | ast | `ast is not None` |

#### 3. trace_integrity
- 必须包含：`task_id`, `capabilities_used`
- 缺失即为 FAIL，不得绕过

#### 4. error_free
- 无未预期错误（E_NETWORK / E_PARSE 等）
- **例外**（不算 FAIL）：`E_TIMEOUT`（用户可重试）/ `E_BLOCKED`（CAPTCHA）

### 决策规范

```
PASS    → 4 项检查全部通过
FAIL    → 至少 1 项检查失败，附 causes[]
RETRY   → 可恢复错误（暂时性），附 cause
```

### 约束

- Verifier **不能**是 Worker 的同一个认知主体
- Verifier **不能**读取 Worker 的内部上下文
- Verifier 验收标准是清单（checklist），不是模型主观判断

---

## 三、Worker 能力质量标准

### 能力签名规范

每个 capability 必须返回以下结构：

```python
{
    "task_id": str,           # 任务 ID（trace_integrity 必需）
    "capabilities_used": [str],  # 已使用的 capability 列表
    "error_type": str,        # "OK" / "E_TIMEOUT" / "E_NETWORK" / "E_BLOCKED" / "E_PARSE"
    "error": Optional[str],   # 错误描述
    # 业务字段 ...
}
```

### 错误码体系

| 错误码 | 说明 | 处置 |
|--------|------|------|
| OK | 正常完成 | — |
| E_TIMEOUT | 请求超时 | 不算 FAIL，可重试 |
| E_NETWORK | 网络故障 | FAIL |
| E_PARSE | 解析失败 | FAIL |
| E_BLOCKED | 被反爬/CAPTCHA | 不算 FAIL，可重试 |
| E_NOTFOUND | 资源不存在 | FAIL |

### 超时约束

- 所有 subprocess 调用必须设置 timeout
- 建议 timeout 值：
  - `curl` 网络请求：15s
  - `shell` 执行：30s
  - `file_read`：5s

---

## 四、Checkpoint 质量标准

### 文件格式

```json
// /tmp/deepin_checkpoints/{task_id}/metadata.json
{
    "task_id": "task-xxx",
    "created_at": 1747891234.5,
    "attempts": 2,
    "completed_steps": ["file_reader", "code_analyzer"]
}

// /tmp/deepin_checkpoints/{task_id}/{capability}-meta.json
{
    "task_id": "task-xxx",
    "capability": "code_analyzer",
    "completed_at": 1747891234.5,
    "result_hash": "a1b2c3d4...",  // sha256 前 16 位
    "result_size": 1234,
    "step": 1
}

// /tmp/deepin_checkpoints/{task_id}/{capability}-result.json
{...}  // 实际执行结果
```

### 验证规则

- `result_hash` 必须与实际结果的 sha256 前 16 位一致
- 不一致 → 数据被篡改，拒绝使用
- `cleanup()` 必须在任务成功后调用，清理 checkpoint 目录

---

## 五、代码规范

### 完成标准（Definition of Done）

- [ ] 代码能正常运行（无 SyntaxError/ImportError）
- [ ] 核心逻辑有 try/except 降级方案
- [ ] 外部调用（subprocess/网络/D-Bus）有 timeout
- [ ] 公开方法有 docstring
- [ ] GUI 模块不包含业务逻辑
- [ ] 推送到 GitHub 前通过语法检查

### 代码审查清单

- [ ] 敏感数据（token/密码）不硬编码
- [ ] 文件操作有异常处理
- [ ] 没有裸 `except:`（捕获具体异常）
- [ ] 循环中有退出条件（避免死循环）
- [ ] 大文件/数据流有限制（max_chars/max_lines）

### 文件路径约束

| 目录 | 用途 | 约束 |
|------|------|------|
| `/tmp/deepin_traces/` | 状态机 trace | JSONL 格式，每行一 JSON |
| `/tmp/deepin_checkpoints/` | 检查点文件 | JSON 格式 |
| `/tmp/agent_registry.json` | Agent 注册表 | fcntl.flock 保护 |
| `/tmp/agent_results/` | Worker 执行结果 | JSON 格式 |

---

## 六、测试覆盖率

### 单元测试要求

| 模块 | 覆盖项 | 通过标准 |
|------|--------|---------|
| task_state_machine.py | 5 种跳转路径 | 5/5 通过 |
| verifier.py | PASS/FAIL/RETRY 决策 | 6/6 通过 |
| checkpoint_manager.py | save/load/cleanup/verify | 6/6 通过 |
| model_router.py | 初始化/message 构建/stats | 4/4 通过（不调 API） |

### 集成测试

- `orchestrator_v3.py` 必须能完整跑通一个任务
- trace 文件必须生成且格式合法
- checkpoint 必须在失败后正确恢复

---

## 七、赛题合规性检查

| 要求 | 达标条件 |
|------|---------|
| 状态机驱动 | 所有停止条件代码写死，不是模型感觉 |
| 独立 Verifier | Verifier ≠ 执行者，独立世界观 |
| 多模型路由 | 至少 2 款模型（MiniMax + ERNIE） |
| trace 可追溯 | 每次跳转写 trace，决策链路清晰 |
| 检查点恢复 | 失败不整体重来，从 checkpoint 恢复 |

---

**最后更新**：2026-05-22