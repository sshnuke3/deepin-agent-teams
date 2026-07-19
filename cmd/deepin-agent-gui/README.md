# deepin-agent-gui (v4)

v4 图形界面 — Wails v2.13 + Go + HTML/CSS/JS。

## 架构

```
cmd/deepin-agent-gui/
├── main.go              # Wails 入口
├── app.go               # 暴露 Orchestrator.Run 给前端
├── wails.json           # Wails 配置
├── go.mod               # 独立 module（replace 指向主仓 ../..）
└── frontend/
    ├── index.html       # 聊天界面
    └── src/
        ├── main.js      # 调 window.go.main.App.Run()
        └── style.css    # 深色主题
```

## 依赖

- **Go** 1.23+(Wails 要求 1.25,用 toolchain 自动升)
- **Node.js** 16+(前端 Vite)
- **libwebkit2gtk-4.1-dev**(Ubuntu 24.04 / deepin 25)
- **libgtk-3-dev**

### Ubuntu / deepin 25 安装

```bash
sudo apt install -y libwebkit2gtk-4.1-dev libgtk-3-dev
```

## 构建

```bash
# 关键：用 webkit2_41 tag（Ubuntu 24.04 / deepin 25 用 webkit2gtk 4.1）
wails build -tags webkit2_41

# 产物：build/bin/deepin-agent-gui (~20MB 单二进制)
```

**注意**:`wails build` 默认用 `webkit2gtk-4.0` tag,在装了 4.1 的系统上会报
`Package 'webkit2gtk-4.0' was not found`,**必须显式加 `-tags webkit2_41`**。
（这块需要等 Wails 升级后默认改 — 跟踪 issue #Wails-2376。）

## 运行

```bash
# 需要 LLM key
export QWEN_API_KEY=sk-...
# 或用 .env（主仓的 config.Load() 会读）

# Ubuntu 上跑（mock 模式，避免调 D-Bus）
DEEPIN_DBUS=mock ./build/bin/deepin-agent-gui

# deepin 25 上跑（真 D-Bus 调主题/音量/亮度）
./build/bin/deepin-agent-gui
```

## 开发模式

```bash
# 热重载（前端改 HTML/CSS/JS 即时生效）
wails dev -tags webkit2_41
```

## 与主仓的关系

- **Module**:独立 module `github.com/sshnuke3/deepin-agent-teams/cmd/deepin-agent-gui`
- **Replace**:`go.mod` 里 `replace github.com/sshnuke3/deepin-agent-teams => ../..`
- **复用**:直接 import 主仓的 `internal/orchestrator`,零代码重复

## 当前限制(M3 阶段)

- **没有悬浮球**:只做了聊天窗口(悬浮球是 v3 PyQt5 的特性,v4 暂不做)
- **没有系统托盘**:同上
- **不感知剪贴板/窗口**:v3 的 perception/ 模块 v4 没继承

## Apply 开关(M3 后期加)

header 右上角有 iOS-style toggle:
- 未勾(预览模式):只打印计划,不真改
- 已勾(应用模式):真去调 D-Bus / 移文件 / 写 JSON / 存 .eml

后端实现:勾选时拼上 `(apply mode)` 后缀给 Orchestrator,跟 CLI 的 `--apply` 行为一致。

这些是 v4 M3 的取舍 — 先把"GUI 能跑通 + apply 开关"验证了,再增量加。

## 验证状态

| 项 | 状态 |
|---|---|
| Wails CLI 安装 | ✅ |
| 依赖装齐 | ✅ |
| `go build` 编译 | ✅ 25MB |
| `wails build` 完整打包 | ✅ 20MB |
| 前端 Vite 构建 | ✅ |
| 二进制启动 | ⚠️ 本机无 X server 没法验证(主人有 deepin 25 才能跑) |