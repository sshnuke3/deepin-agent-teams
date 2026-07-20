# demos/multi-agent-failure-recorder

> **目的**：采集 deepin-agent-teams 在多 Agent 协作场景下的**真实失败样本**，沉淀出"3+ 次同类规律"，为将来的多 Agent SOP 立项达标。
> **状态**：立项启动（2026-07-21）
> **背景**：见 `~/.openclaw/workspace/drafts/multi-agent-sop/RFC.md`

## 为什么立项

ai-ops-sop 已发布（v0.6.0 + v0.7.0/v0.8.0 延伸阅读），但**只覆盖单 Agent**。
多 Agent 协作 = bojieli《AI Agent》ch10 核心：
- 群体的智能可以高于个体（人类文明是明证）
- 单 Agent 受限于模型能力 + 上下文窗口
- Google DeepMind 把"大规模多 Agent 集体"列为通往 ASI 的关键路径

**门槛**：按 `~/.openclaw/workspace/methodology/INDEX.md` §"升级门槛" = 3+ 次同类规律 或 跨 2 个场景 才升 methodology。
当前现状：跨 2 场景（deepin-agent-teams + ai-website-cloner-openclaw）已达成，**但 3+ 次失败样本 尚未采集**。

本 demo = 失败样本采集器。**不是多 Agent SOP 本身**，是 SOP 立项的输入。

## 5 大失败模式（按 ch10 列）

| 模式 | 含义 | 采集判断标志 |
|---|---|---|
| **F1 互相等待** | Agent A 等 Agent B 的输出，B 等 A | 主循环超时 / 死锁检测告警 |
| **F2 信息冲突** | 多 agent 对同一上下文有不同理解 | 同一问题多个 agent 给出矛盾答案 |
| **F3 角色漂移** | Agent 角色边界模糊，做了不该做的事 | 任务越界 / 工具调用违反 role |
| **F4 资源死锁** | Agent 同时争抢同资源 | LLM 调用并发上限 / 文件锁 |
| **F5 涌现失序** | 群体行为不可预测，整体混乱 | 群体决策分数低于单 agent |

## 工作流

```
1. 在 deepin-agent-teams / 其他项目里跑多 agent 任务
2. 跑挂 → bash scripts/capture-failure.sh --mode=<F1-F5> --description=...
3. 脚本记录：时间 / 场景 / 失败现象 / 涉及 agent / 根因猜测
4. 写到 runs/<date>-failure-<n>.json + runs/timeline.txt 追加
5. 跨 3 个 mode 各有样本 → 立项门槛达成，可写多 Agent SOP
```

## 与 deepin-agent-teams 主体关系

- **不修改** v4 主线代码（M3 已完成、M4 在做 Web UI）
- **新增** demos/ 子目录，**只读** v4 的 agent / orchestrator 组件作为黑盒
- **采集**真实跑挂的样本，但**不发起**新的多 agent 实现
- **观察期** 1-2 周（按主人 RFC §D3 节奏）

## 目录结构

```
demos/multi-agent-failure-recorder/
├── README.md            # 本文件
├── PROJECT_WIKI/
│   └── overview.md      # L1 总览（≤5KB）
├── docs/
│   └── spec.md          # 5 大失败模式 + 采集模板
├── runs/
│   ├── timeline.txt     # 时间线（append only）
│   └── <date>-failure-<n>.json  # 单个失败样本
├── scripts/
│   └── capture-failure.sh  # 一键记录失败样本
├── configs/
│   └── red_lines.yaml   # 多 Agent 场景的红线
└── AGENTS.md            # AI 接力点
```

## 主人下一步

- 跑实际多 agent 任务（v4 GUI / Wails / D-Bus 集成都可触发）
- 看到挂 → 用 `scripts/capture-failure.sh` 记一笔
- 等到 F1-F5 各有 1-2 个样本 → 立项升级到多 Agent SOP

> **不在范围**：本 demo **不**实现多 agent 框架本身；**只采集样本**。如要写多 agent 框架，参考 v4-plan.md M4+。

---

# 2026-07-21 创建 · 立项自检 ✓
# 主人定的两条规则: 加注释 ✓ / 完全剥离 ✓ (本 demo 全是内部使用)