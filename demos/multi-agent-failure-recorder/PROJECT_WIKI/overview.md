# overview.md — multi-agent-failure-recorder L1 总览

> 按 ai-ops-sop §2 "三层知识地图" 模板写的 L1 总览（≤5KB）

## 项目一句话

采集 deepin-agent-teams 多 Agent 协作场景的真实失败样本，为多 Agent SOP 立项达标提供输入。

## 边界（in / out）

**In**：
- 多 agent 跑挂 → 记录到 runs/
- 跨多个 mode 采集
- 维护采集纪律红线

**Out**：
- 多 agent 框架本身（v4-plan.md 已有）
- 改 deepin-agent-teams 主体
- 写多 Agent SOP（未立项）

## 5 大失败模式（速记）

- **F1** 互相等待（deadlock）
- **F2** 信息冲突（conflict）
- **F3** 角色漂移（role drift）
- **F4** 资源死锁（resource contention）
- **F5** 涌现失序（emergent chaos）

详见 `docs/spec.md §3`。

## 当前状态

- 启动日期：2026-07-21
- 当前样本数：0（仅测试样本已删）
- 立项升级门槛：跨 3 mode 各 1+ 样本
- 观察期：1-2 周

## 工作流

```
1. 跑实际多 agent 任务
2. 跑挂 → bash scripts/capture-failure.sh
3. 脚本收集信息 + 写 JSON + append timeline
4. 跨 3 mode 各有样本 → 立项升级
```

## 链接

- 项目说明：`README.md`
- spec：`docs/spec.md`
- AGENTS：`AGENTS.md`
- 立项 RFC：`~/.openclaw/workspace/drafts/multi-agent-sop/RFC.md`

---

# 2026-07-21 创建 · L1 总览（≤5KB）
# 主人定的两条规则: 加注释 ✓ / 完全剥离 ✓