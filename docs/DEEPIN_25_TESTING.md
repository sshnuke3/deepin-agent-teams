# deepin 25 真机测试说明

> 适用版本：deepin-agent-teams v4 M3（commit `48f1f1a` 及以后）
> 测试环境：deepin 25.x 实机或 VM（不是 Ubuntu，也不是 deepin 23）

---

## GUI 测试（Wails v2.13）

v4 M3 阶段交付了一个 Wails 图形界面。

### 装依赖

```bash
# 装 libwebkit2gtk-4.1-dev（Ubuntu 24.04 / deepin 25）
sudo apt install -y libwebkit2gtk-4.1-dev libgtk-3-dev

# 装 Wails CLI
go install github.com/wailsapp/wails/v2/cmd/wails@latest
export PATH=$PATH:$(go env GOPATH)/bin
```

### 构建

```bash
cd cmd/deepin-agent-gui/
# 必须加 -tags webkit2_41（Wails 默认 4.0 tag 在装 4.1 的系统上会报 Package not found）
wails build -tags webkit2_41
# 产物：build/bin/deepin-agent-gui（~20MB）
```

### 运行

```bash
# 设置 LLM key（任一）
export QWEN_API_KEY=sk-...

# Ubuntu 上跑（mock 模式，避免调 D-Bus）
DEEPIN_DBUS=mock ./build/bin/deepin-agent-gui

# deepin 25 上跑（真 D-Bus 调主题/音量/亮度）
./build/bin/deepin-agent-gui
```

### 验证清单

- [ ] 窗口出现，header 显示「🦞 deepin Agent Teams」
- [ ] 输入框输入"切到深色模式"，点发送
- [ ] 显示用户消息气泡（蓝色）
- [ ] 显示 assistant 回复气泡（灰色）
- [ ] reply 含主题切换预览（不开 apply 模式）
- [ ] 在 deepin 25 上，点发送后系统主题真切换
- [ ] 输入"切深色 + 音量 30 + 提醒明早开会"，多意图用 --- 分隔

### 当前限制

- 没悬浮球/系统托盘（v3 PyQt5 特性，v4 M3 暂不做）
- 没剪贴板/窗口感知（v3 perception/ 模块，v4 未继承）

### Apply 模式开关

v4 M3 GUI 后期加了 **Apply 开关**（ header 右上角 iOS-style toggle）：

| 状态 | 按钮文字 | 行为 | 跟 CLI 的对应 |
|------|---------|------|--------------|
| 未勾 | `预览模式` | 只打印计划，不真改系统 | `./deepin-agent chat "..."` |
| 已勾 | `应用模式` | 真去调 D-Bus / 移文件 / 写 JSON / 存 .eml | `./deepin-agent chat "..." --apply` |

实现机制：勾选时后端把 `(apply mode)` 拼在用户输入后，跟 CLI 的 `--apply` 参数行为一致。Intent Agent 的 prompt 看到这个词，自动把 Intent.Mode 填 "apply"。

**误操作提醒**：
- apply 模式下用户消息气泡左边会有 ⚡ 标记
- apply 模式下输入框边框变蓝色（提示状态）
- apply 完成后 assistant 回复气泡末尾有 ✓ 已应用 标签

---

---

## 0. 前置检查

```bash
# 0.1 gdbus 命令必须可用（deepin 默认装）
gdbus --version
# 期望：gdbus 版本 2.x

# 0.2 当前是 X11 还是 Wayland
echo $XDG_SESSION_TYPE
# 期望：x11 或 wayland

# 0.3 D-Bus session bus 在跑
gdbus call --session \
    --dest org.freedesktop.DBus \
    --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.ListNames | head -c 200
# 期望：一堆 com.deepin.* 服务名
```

如果 `gdbus` 没装：
```bash
sudo apt install libglib2.0-bin   # deepin 25 走 apt
# 或 deepin 25 走玲珑包（如果你是这个分支）：
ll-cli install libglib2.0-bin
```

---

## 1. 拉代码 + 编译

```bash
cd /root/.openclaw/workspace/deepin-agent-teams/
git pull origin v4-redesign
go build -o deepin-agent ./cmd/deepin-agent

# 跑一遍单元测试（应该全过 171/171）
go test ./...
```

---

## 2. 接口真实性验证（第一步必做）

**直接跑 demo 之前**,先用 `gdbus introspect` 看下 deepin 25 上 D-Bus 方法名跟我们的代码对不对得上。

### 2.1 Appearance（主题）

```bash
gdbus introspect --session \
    -d com.deepin.daemon.Appearance \
    -o /com/deepin/daemon/Appearance \
    | grep -E "Set(Get)?(Current|Gtk)Theme"
```

**期望输出**（含以下方法之一即可）：

```
<interface name="com.deepin.daemon.Appearance">
  <method name="SetCurrentTheme">
    <arg type="s" direction="in"/>
  </method>
  <method name="SetGtkTheme">
    <arg type="s" direction="in"/>
  </method>
  <method name="GetCurrentTheme">
    <arg type="s" direction="out"/>
  </method>
</interface>
```

如果方法名变了（比如 deepin 26 改名 `SetTheme`），把输出贴给开发者，我们改 `internal/tools/appearance.go`。

### 2.2 Audio（音量）

```bash
gdbus introspect --session \
    -d com.deepin.daemon.Audio \
    -o /com/deepin/daemon/Audio \
    | grep -E "SinkSetVolume|SetSinkVolume"
```

**期望**：

```
<method name="SinkSetVolume">
    <arg type="d" direction="in"/>  # double
</method>
```

> ⚠️ 部分 deepin 25 子版本用的是 `com.deepin.daemon.Audio1`（注意末尾的 `1`）。如果是这个，把 settings.go 里的 `com.deepin.daemon.Audio` 全局替换成 `com.deepin.daemon.Audio1` 即可。

### 2.3 Display（亮度）

```bash
# 先试 Display
gdbus introspect --session \
    -d com.deepin.daemon.Display \
    -o /com/deepin/daemon/Display \
    | grep -i "brightness"

# 如果没有，试 Power.Display
gdbus introspect --session \
    -d com.deepin.daemon.Power \
    -o /com/deepin/daemon/Display \
    | grep -i "brightness"
```

**期望至少有一个有 `SetBrightness(double)` 方法**。

> ⚠️ deepin 25 把亮度服务从 `Display` 改到 `Power.Display` 是已知的版本变化。我们代码默认走 `Display`，如果你的机器上是 `Power.Display`，把 settings.go 里的 `com.deepin.daemon.Display` 改成 `com.deepin.daemon.Power`，路径 `/com/deepin/daemon/Display` 不变。

### 2.4 Network（WiFi）

```bash
gdbus introspect --session \
    -d com.deepin.daemon.Network \
    -o /com/deepin/daemon/Network \
    | grep -E "EnableWifi|DisableWifi"
```

**期望**：

```
<method name="EnableWifi"/>
<method name="DisableWifi"/>
```

> ⚠️ 某些 deepin 25 子版本 Network 服务在 `system` bus 而非 `session`。如果 `gdbus introspect --session` 找不到，换 `--system`，代码里把对应的 `dbusCall` 改成 `dbusCallSystem`（已经在 `dbus.go` 实现）。

---

## 3. Preview 模式（只读，安全）

```bash
./deepin-agent chat "看下系统信息"
./deepin-agent chat "切到深色模式"
./deepin-agent chat "音量调到 30"
./deepin-agent chat "亮度调到 50"
./deepin-agent chat "整理 ~/Downloads"
./deepin-agent chat "提醒我明早 9 点开会"
```

每个都会调 D-Bus **读**类方法（如 `GetCurrentTheme`），不会改系统状态。

**预期输出示例**：

```
ℹ️ 主机名: mydeepin, 系统: Deepin 25, 当前主题: deepin-light
📋 主题预览（未真改，加 --apply 才会执行）
   deepin-dark
⚙️ 系统设置预览（未应用，加 --apply 才会真改）
   ...
```

---

## 4. Apply 模式（真改系统）

**测试顺序：从最易回滚的开始**。

### 4.1 主题（最容易验证 + 回滚）

```bash
./deepin-agent chat "切到深色模式" --apply
```

打开 **控制中心 → 个性化 → 主题**，确认是深色。

回滚：
```bash
./deepin-agent chat "切到浅色模式" --apply
```

### 4.2 亮度（硬件可控）

```bash
./deepin-agent chat "亮度调到 30" --apply
# 看屏幕是不是变暗了

./deepin-agent chat "亮度调到 80" --apply
# 看屏幕是不是变亮了
```

### 4.3 音量（系统音频）

```bash
./deepin-agent chat "音量调到 0" --apply
# 听声音

./deepin-agent chat "音量调到 50" --apply
# 听声音
```

### 4.4 网络（⚠️ 慎用，会断 WiFi）

```bash
./deepin-agent chat "关 WiFi" --apply
# 如果是 WiFi 连的，会断网

./deepin-agent chat "开 WiFi" --apply
# 恢复
```

> 建议在测试前先把手机热点开起来当 fallback。

### 4.5 文件整理（落盘到 `~/.local/share/`）

```bash
# 先 preview 看分类计划
./deepin-agent chat "整理 ~/Downloads"

# 确认 OK 后真整理
./deepin-agent chat "整理 ~/Downloads" --apply
```

整理后的文件在 `~/Downloads/images/`、`~/Downloads/docs/` 等子目录里。

### 4.6 日程提醒

```bash
./deepin-agent chat "提醒我明天上午 9 点开会" --apply
```

文件落在 `~/.local/share/deepin-agent/reminders/`。

### 4.7 邮件草稿

```bash
./deepin-agent chat "帮 alice@example.com 起草项目进度邮件" --apply
```

文件落在 `~/.local/share/deepin-agent/drafts/`，是 `.eml` 格式，可以直接用邮件客户端打开。

---

## 5. 多意图测试（M3 阶段 1）

```bash
./deepin-agent chat "切到深色模式 + 音量调到 30 + 提醒我明早 9 点开会"
# 加 --apply 才真改，否则是 preview
```

**预期输出**：

```
⚙️ 系统设置预览：theme = deepin-dark ...
---
⚙️ 系统设置预览：volume = 30 ...
---
📅 日程提醒预览：开会 @ 2026-07-20T09:00:00+08:00 ...
```

中间用 `---` 分隔，说明 3 个意图都识别 + 跑了。

---

## 6. 故障排查

### 6.1 `Error: GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown`

服务没装 / 没运行。
```bash
systemctl --user status dde-session-daemon
# 如果没跑：
systemctl --user start dde-session-daemon
```

### 6.2 `Error: GDBus.Error:org.freedesktop.DBus.Error.AccessDenied`

权限不够。这种服务通常需要 session bus + 用户已登录 DDE。
```bash
loginctl list-sessions
# 确认你当前 session 是 active
```

### 6.3 `Error: GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod`

方法名不对。回到 **第 2 节** 跑 `introspect` 看真实方法名。

### 6.4 程序崩了 / panic

```bash
# 跑一次拿 stacktrace
./deepin-agent chat "切到深色模式" --apply 2>&1 | tee /tmp/deepin-agent.log
```

把日志贴给开发者。

### 6.5 想强制走 mock（演示用）

```bash
DEEPIN_DBUS=mock ./deepin-agent chat "切到深色模式" --apply
# 输出会包含 "(演示模式)" 标记
```

---

## 7. 完整 demo 脚本（手动测试用）

按这个顺序跑一遍，验证所有功能能跑通：

```bash
# === 准备 ===
clear
echo "=== deepin-agent-teams v4 演示 ==="
echo
cd /root/.openclaw/workspace/deepin-agent-teams
./deepin-agent chat "看下系统信息"
sleep 2

# === 多意图 ===
./deepin-agent chat "切到深色模式 + 音量调到 30 + 提醒我明早 9 点开会"
sleep 3

# === preview + apply 对比 ===
./deepin-agent chat "整理 ~/Downloads"            # preview
sleep 2
./deepin-agent chat "整理 ~/Downloads" --apply    # 真整理
sleep 3

# === 邮件草稿 ===
./deepin-agent chat "帮 alice@example.com 起草项目进度邮件"
sleep 2

# === 回滚 ===
./deepin-agent chat "切到浅色模式" --apply
./deepin-agent chat "音量调到 70" --apply
echo
echo "=== 演示结束 ==="
```

---

## 8. 验证清单（提交前勾）

- [ ] `go test ./...` 全过（171/171）
- [ ] `gdbus introspect` 4 个服务都返回正确方法
- [ ] Preview 模式 5 个 demo 都能输出（不真改）
- [ ] Apply 模式 4 类 settings 都能真改
- [ ] 多意图 "切深色 + 音量 30 + 提醒开会" 输出有 `---` 分隔
- [ ] 文件整理 preview → apply 后 `~/Downloads/{images,docs,...}/` 有文件
- [ ] 日程提醒 apply 后 `~/.local/share/deepin-agent/reminders/` 有 JSON
- [ ] 邮件草稿 apply 后 `~/.local/share/deepin-agent/drafts/` 有 `.eml`

---

## 9. 反馈

跑出问题就贴：

1. **命令**（精确复制粘贴）
2. **完整 stderr 输出**
3. **`gdbus introspect` 输出**（如果怀疑方法名问题）

到仓库 issue 或 PR。

---

*最后更新：2026-07-19 v4-redesign@38e14d3*