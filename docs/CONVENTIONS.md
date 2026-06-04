# 编码规范

> 最后更新：2026-06-04

## 文件命名

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块文件 | snake_case.py | `screen_capture.py` |
| 类名 | PascalCase | `BehaviorTracker` |
| 函数/变量 | snake_case | `get_active_window` |
| 常量 | UPPER_SNAKE_CASE | `AGENT_PRIORITY` |
| 私有成员 | _前缀 | `_ocr_cache` |

## 目录组织

- `perception/` — 所有环境感知模块（纯读取，不修改系统）
- `agents/` — Agent 定义和编排器（只含逻辑，不含 UI）
- `scenarios/` — 端到端场景（串联多个 Agent 完成完整任务）
- `tools/` — 工具适配器（MCP 协议）
- `skills/` — 预定义技能（触发关键词 + 工具依赖 + 提示模板）
- `gui/` — PyQt5 图形界面（不包含业务逻辑）

## 代码风格

- Python 3.8+ 兼容
- 类型注解（typing）用于所有公开方法
- dataclass 用于数据结构定义
- 每个模块文件顶部包含模块说明 docstring
- 公开方法必须有 docstring
- 异常处理：捕获具体异常，避免裸 `except:`

## 导入规范

- 标准库在前，第三方库在中，本地模块在后
- 本地模块使用 `sys.path.insert` 确保路径正确
- 避免循环导入

## 错误处理

- 外部命令调用（subprocess）必须设 timeout
- 文件操作用 `try/except` 包裹
- D-Bus 调用必须降级方案（deepin 以外的系统）
- 网络请求设 10 秒超时

## 测试

- 每个模块底部可放 `if __name__ == "__main__":` 测试块
- 核心函数应可独立测试（不依赖全局状态）
