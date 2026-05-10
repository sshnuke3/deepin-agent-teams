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
