# AGENTS.md — demos/multi-agent-failure-recorder

> 这是 deepin-agent-teams 内部的 demo 项目的 AI 接力入口
> 与 ~/.openclaw/workspace-public/ai-ops-sop/examples/gh-issue-summarizer/AGENTS.md 风格一致

## §0 你的角色

你是 multi-agent-failure-recorder 项目的 AI 助手。

**当前状态**：立项启动（2026-07-21），**未采集到真实样本**，等主人真实跑挂多 agent 任务后采集。

**项目边界**：
- ✅ 采集失败样本（写 runs/）
- ✅ 维护 scripts/ 和 configs/
- ❌ 不实现多 agent 框架（v4-plan.md 已规划，本 demo 只采集）
- ❌ 不修改 deepin-agent-teams 主体代码

## §1 接力入口 · 3 件必做

1. **读 `docs/spec.md` §0-§3** —— 知道 5 大失败模式 + JSON 数据模型
2. **读 `runs/timeline.txt`** —— 看是否有半年前的旧样本
3. **看 `configs/red_lines.yaml` 的 `load_policy.on_session_start`** —— 知道采集纪律

## §2 别动什么

| 不要做 | 为什么 |
|---|---|
| 修改 deepin-agent-teams 主体代码 | demo 只采集样本，**不**改主线 |
| 在 samples 写 false 失败样本（除测试） | RL-DEMO-1 红线 |
| 跳过 timeline append | SOP §"跨会话知识传承" |
| 改 mode 含义 | 5 大失败模式按 ch10 定，**不能改** |

## §3 失败分诊 · 决策树

```
新会话接手
  │
  ├─ 有 5+ 样本？→ §5 立项升级判定
  │
  ├─ 0 样本？→ 等主人跑挂，无需主动动作
  │
  └─ 介于中间？→ 继续采集 + 等
```

## §4 触发硬关卡 HK

| HK | 何时 | 触发条件 |
|---|---|---|
| **HK-DEMO-1** | 立项升级达成 | 5 大 mode 跨 3+ 各有 1 样本 |
| **HK-DEMO-2** | 归档触发 | 6 月无新样本 |
| **HK-DEMO-3** | 主人问"还要继续吗" | 任何时候 |

## §5 立项升级判定（未来用）

按 `docs/spec.md §5 立项升级门槛`：

```
跨 3 mode 各有 1+ 样本
+ 跨 2 项目/场景
+ 至少 1 high severity 样本
= 立项升级，可写 multi-agent-pipeline.md methodology
```

## §6 链接

- 项目说明：`README.md`
- L1 总览：`PROJECT_WIKI/overview.md`
- 失败模式定义：`docs/spec.md` §3
- 采集脚本：`scripts/capture-failure.sh`
- 红线配置：`configs/red_lines.yaml`
- 立项 RFC：`~/.openclaw/workspace/drafts/multi-agent-sop/RFC.md`
- 父项目：`/root/.openclaw/workspace/deepin-agent-teams/`
- 参考书：`~/.openclaw/workspace-public/ai-agent-book/book/chapter10.md`

---

# 2026-07-21 创建 · AI 接力点
# 主人定的两条规则: 加注释 ✓ / 完全剥离 ✓ (本 demo 内部使用)