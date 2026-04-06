## 七、提交物清单

- [x] RFC.md（本文档）
- [x] 核心代码框架（agents/lead.py, researcher.py, coder.py, base.py）
- [x] config.py - 统一配置管理
- [x] main.py - 命令行入口
- [ ] 完整源代码（场景演示）
- [ ] README.md（环境安装、一键运行说明）
- [ ] 场景演示截图/录屏

## 实施进度

| 阶段 | 时间 | 状态 | 说明 |
|------|------|------|------|
| 第一周 | 4/1-4/7 | ✅ | OpenClaw 环境部署 + Agent 框架搭建 |
| 第二周 | 4/8-4/14 | 🔄 进行中 | Lead Agent + Researcher Agent 基础协作 |
| 第三周 | 4/15-4/21 | ⏳ 待开始 | Coder Agent，串联第一个完整场景 |
| 第四周 | 4/22-4/28 | ⏳ 待开始 | 第二个场景开发，输出 Demo |
| 第五周 | 4/29-5/5 | ⏳ 待开始 | 完善 README 和复现文档 |

## 代码结构

```
deepin-agent-teams/
├── config.py           # 统一配置（API 凭证、Agent 参数）
├── main.py             # 命令行入口
├── requirements.txt    # 依赖列表
└── agents/
    ├── __init__.py
    ├── base.py         # BaseAgent 基类（erniebot 封装）
    ├── lead.py         # Lead Agent（任务拆解 + 结果整合）
    ├── researcher.py   # Researcher Agent（文献分析 + 文件读取）
    └── coder.py        # Coder Agent（代码分析 + Shell 执行）
```

