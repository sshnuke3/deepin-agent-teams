# 质量标准

## 完成标准（Definition of Done）

- [ ] 代码能正常运行（无 SyntaxError/ImportError）
- [ ] 核心逻辑有 try/except 降级方案
- [ ] 外部调用（subprocess/网络/D-Bus）有 timeout
- [ ] 公开方法有 docstring
- [ ] GUI 模块不包含业务逻辑
- [ ] 推送到 GitHub 前通过语法检查

## 代码审查清单

- [ ] 敏感数据（token/密码）不硬编码
- [ ] 文件操作有异常处理
- [ ] 没有裸 `except:`（捕获具体异常）
- [ ] 循环中有退出条件（避免死循环）
- [ ] 大文件/数据流有限制（max_chars/max_lines）

## 已知技术债

| 项目 | 严重程度 | 说明 |
|------|---------|------|
| ERNIE-3.5 token 配额耗尽 | 高 | 当前只有 ernie-lite 可用 |
| deepin 25 实体机未测试 | 高 | 所有 D-Bus 接口未在真机验证 |
| GUI 与 main.py 集成 | 中 | --gui 参数未与 Agent 系统完全联通 |
| 截图在 Wayland 下不兼容 | 中 | 需要 X11 或 deepin 原生支持 |
