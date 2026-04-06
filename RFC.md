## 七、提交物清单

- [x] RFC.md（本文档）
- [x] 核心代码框架（agents/lead.py, researcher.py, coder.py, base.py）
- [x] config.py - 统一配置管理
- [x] main.py - 命令行入口（交互/任务/演示模式）
- [x] scenarios/code_analysis.py - 场景一：代码分析+文档生成
- [x] scenarios/literature_review.py - 场景二：文献综述助手
- [ ] 场景一完整演示（需 ERNIEBOT_API_KEY）
- [ ] 场景二完整演示（需 PDF 文件）
- [ ] README.md（环境安装、一键运行说明）

## 实施进度

| 阶段 | 时间 | 状态 | 说明 |
|------|------|------|------|
| 第一周 | 4/1-4/7 | ✅ | OpenClaw 环境部署 + Agent 框架搭建 |
| 第二周 | 4/8-4/14 | ✅ | Lead/Researcher/Coder 协作 + 两大场景框架 |
| 第三周 | 4/15-4/21 | 🔄 进行中 | 场景串联 + 端到端测试 |
| 第四周 | 4/22-4/28 | ⏳ 待开始 | 第二个场景开发，输出 Demo |
| 第五周 | 4/29-5/5 | ⏳ 待开始 | 完善 README 和复现文档 |

## 代码结构

```
deepin-agent-teams/
├── config.py           # 统一配置（API 凭证、Agent 参数）
├── main.py             # 命令行入口
├── requirements.txt    # 依赖列表
├── .env.example        # 环境变量示例
├── agents/
│   ├── __init__.py
│   ├── base.py         # BaseAgent 基类（erniebot 封装）
│   ├── lead.py         # Lead Agent（任务拆解 + 结果整合）
│   ├── researcher.py   # Researcher Agent（文献分析 + 文件读取）
│   └── coder.py        # Coder Agent（代码分析 + Shell 执行）
└── scenarios/
    ├── __init__.py
    ├── code_analysis.py    # 场景一：代码分析+文档生成
    └── literature_review.py # 场景二：文献综述助手
```

## 快速使用

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API 凭证
cp .env.example .env
# 编辑 .env 填入 ERNIEBOT_API_KEY

# 运行代码分析演示（分析当前项目）
python main.py --demo code-analysis

# 交互模式
python main.py -i

# 分析指定项目
python main.py "帮我分析 /path/to/project"
```

