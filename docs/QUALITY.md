# 质量标准

> 基于三角架构（状态机 + Verifier + Worker）的质量保障体系
>
> 最后更新：2026-06-10

---

## 一、状态机质量标准

### 状态定义完整性

| 状态 | 前驱状态 | 跳转条件 | trace 字段 |
|------|---------|---------|-----------|
| PENDING | — | submit_task() | from/to/ts |
| CLAIMED | PENDING, FAILED | worker_id 存在 | from/to/ts/worker_id |
| PLANNING | CLAIMED | 生成结构化计划 | from/to/ts/start_time |
| RUNNING | PLANNING | start_time 记录 + plan_ready | from/to/ts/start_time |
| VERIFIED | RUNNING | Verifier PASS | from/to/ts/verdict |
| COMPLETED | VERIFIED | 自动 | from/to/ts |
| FAILED | PENDING/CLAIMED/RUNNING/RETRY | 超时/重试耗尽/Token超限 | from/to/ts/error_msg |
| RETRY | RUNNING | FAIL + retry<3 | from/to/ts/verdict/causes |

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

### 11 项检查（含 3 项安全检查 + 4 项增强检查）

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

#### 5. tool_compliance（P0 安全增强）
- 验证 Worker 只使用了当前状态/阶段允许的工具
- 违规返回 FAIL，附违规工具列表

#### 6. token_budget（P0 安全增强）
- 验证 Token 消耗在预算范围内
- 全局上限 15000，超限返回 FAIL

#### 7. dangerous_ops_confirmed（P0 安全增强）
- 验证所有危险操作（shell_executor 高危命令）都经过确认
- 未确认返回 FAIL

#### 8. plan_completeness（Plan-and-Solve 增强）
- 验证执行计划中的所有步骤都已标记完成（status = "done"）
- 有待完成步骤返回 FAIL

#### 9. plan_coherence（Plan-and-Solve 增强）
- 验证计划步骤的依赖关系是否合理
- 检查循环依赖（DFS 检测）
- 检查依赖引用是否存在
- 存在循环依赖或无效引用返回 FAIL

#### 10. context_overflow（上下文管理增强）
- 验证上下文 token 量是否超出窗口限制
- 超出 1.5 倍上限返回 FAIL

#### 11. summary_quality（上下文管理增强）
- 验证子Agent摘要是否包含关键信息
- 摘要为空字符串返回 FAIL
- 摘要过长（>2000 字符）返回 FAIL

### 决策规范

```
PASS    → 11 项检查全部通过
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
| E_TOOL_BLOCKED | 工具白名单拦截 | FAIL（安全违规） |
| E_USER_DENIED | 用户拒绝危险操作 | FAIL（用户决策） |
| E_CONFIRM_REQUIRED | 危险操作需确认 | FAIL（未完成确认流程） |

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

## 五、安全增强质量标准（P0）

### 工具白名单

- 每个状态/阶段必须有明确的工具白名单
- `is_tool_allowed()` 必须在 `execute_capability()` 入口调用
- 非法工具调用必须被拦截并返回 `E_TOOL_BLOCKED`
- 新增工具必须显式加入白名单配置

### Token 预算

- 每状态/阶段必须有 Token 上限
- 超限必须自动触发 FAILED（`check_and_enforce_token_budget()`）
- TokenTracker 必须记录每次消耗（状态/阶段/模型维度）

### 危险操作确认

- 所有 critical/high 级危险操作必须经过用户确认
- 确认回调必须支持四值（allow/always/deny/exit）
- `always` 必须记录到白名单，后续同类操作自动放行
- 新增危险模式必须补充对应的 Red Team 测试

---

## 六、质量保障标准（P1）

### 离线评测

- AIMock 必须覆盖核心任务路径
- 评测报告必须保存到 `tests/reports/`
- CI 必须零 API 消耗（全部使用 AIMock）

### 可观测性

- 三大指标必须采集：Token 消耗、执行延迟、错误率
- 指标数据保存到 `tests/metrics/`（JSONL 格式）
- 支持按 state/phase/model 分维度查询

### Red Teaming

- 19 个攻击向量必须全部被防御（防御率 100%）
- 新增危险模式后必须补充对应的 Red Team 测试
- Red Team 测试必须集成到 CI，每次提交自动运行

---

## 七、架构升级标准（P2）

### Brain/Hands 分离

- 编排层（Brain）只依赖 `HandsInterface` 抽象接口
- 执行层（Hands）可替换（Local/Docker/Mock）
- MockHands 必须支持确定性输出（CI 零成本）

### 环境隔离

- shared 环境必须有配额限制
- task 环境销毁时必须清理文件系统
- 资源配额检查必须在执行前调用

---

## 八、代码规范

### 完成标准（Definition of Done）

- [ ] 代码能正常运行（无 SyntaxError/ImportError）
- [ ] 核心逻辑有 try/except 降级方案
- [ ] 外部调用（subprocess/网络/D-Bus）有 timeout
- [ ] 公开方法有 docstring
- [ ] GUI 模块不包含业务逻辑
- [ ] 推送到 GitHub 前通过语法检查
- [ ] 安全相关变更必须通过 Red Team 测试（19/19）

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

## 九、测试覆盖率

### 单元测试要求

| 模块 | 覆盖项 | 通过标准 |
|------|--------|----------|
| security_config.py | 工具白名单 + Token 预算 + 危险操作 + 四值确认 | 5/5 通过 |
| task_state_machine.py | 状态跳转 + 安全增强（白名单/Token/确认） | 12/12 通过 |
| verifier.py | PASS/FAIL + 安全检查（白名单/Token/危险操作） | 13/13 通过 |
| worker_base.py | 安全执行（白名单拦截 + Confirming 守卫） | 5/5 通过 |
| eval_runner.py | AIMock + 评测管道 + 报告 | 6/6 通过 |
| metrics_collector.py | 指标收集 + Span + Timer | 8/8 通过 |
| red_team_tests.py | 19 个攻击向量防御 | 19/19 DEFENDED |
| hands_interface.py | 请求/响应 + MockHands + Factory | 7/7 通过 |
| environment_isolation.py | 三级隔离 + 配额 + 销毁 | 8/8 通过 |
| checkpoint_manager.py | save/load/cleanup/verify | 6/6 通过 |
| model_router.py | 初始化/路由表/message 构建/stats/双模型覆盖 | 7/7 通过（不调 API） |

**总计：96/96 测试通过，19/19 攻击向量防御**

### 集成测试

- `orchestrator_v3.py` 必须能完整跑通一个任务
- trace 文件必须生成且格式合法
- checkpoint 必须在失败后正确恢复

---

## 十、赛题合规性检查

| 要求 | 达标条件 |
|------|----------|
| 状态机驱动 | 所有停止条件代码写死，不是模型感觉 |
| 独立 Verifier | Verifier ≠ 执行者，独立世界观（7 项检查含安全检查） |
| 多模型路由 | 至少 2 款模型（ernie-lite + ernie-3.5） |
| trace 可追溯 | 每次跳转写 trace，决策链路清晰 |
| 检查点恢复 | 失败不整体重来，从 checkpoint 恢复 |
| 安全增强 | 工具白名单 + Token 预算 + Confirming 守卫 |
| 离线评测 | AIMock 确定性 Fixture，CI 零 API 消耗 |
| 可观测性 | Token/延迟/错误率，Span 管理 |
| Red Teaming | 19 个攻击向量，防御率 100% |
| Brain/Hands 分离 | 编排层与执行层解耦，可替换执行后端 |
| 环境隔离 | shared / isolated / task 三级隔离 |
