# deepin-agent-teams 演示视频录制指南

> 第十期飞桨黑客松 · 统信 × 百度飞桨 · 进阶任务 #27
> 录制日期：2026-05-16

---

## 一、录制前准备

### 1.0 终端初始化操作（终端新开时必做）

```bash
# 进入项目目录
cd ~/Desktop/deepin-agent-teams

# 激活虚拟环境
source venv/bin/activate

# 验证环境正常
python --version
# 预期输出：Python 3.11.x 或类似
```

### 1.1 检查 ffmpeg

```bash
ffmpeg -version | head -1
```

确认输出：`ffmpeg version 6.1.1-2deepin9`（已装好）

### 1.2 清理桌面

录制前把桌面整理干净：
- 关闭不必要的窗口
- 保持桌面简洁（只留终端和关键窗口）
- 浏览器可以开着（证明是在 deepin 25 上操作）

### 1.3 打开演示窗口

打开以下内容（按顺序）：
1. **终端**（在桌面，位置居中）
2. 浏览器打开 deepin 官网或 AI Studio（可选）

---

## 二、录制命令

### 2.1 开始录制

```bash
ffmpeg -f x11grab -r 30 -s 1280x800 -i :0.0 -c:v libx264 -preset fast ~/Desktop/deepin_demo.mp4
```

### 2.2 录制中操作步骤

**第一步：打开交互模式（0-10秒）**
```
等待屏幕录制开始...
在终端输入：
python main.py -i
回车
```

**第二步：演示环境感知（10-40秒）**
```
输入：
tests/test_perception_deepin25.py
（完整命令在下方）

实际命令：
python3 tests/test_perception_deepin25.py

等待测试跑完...（大约10秒）
展示屏幕截图正常 / 窗口管理正常 / D-Bus 正常
```

**第三步：演示邮件助手（40-90秒）**
```
等测试结束
Ctrl+C 停止测试

输入：
exit
回车

输入：
python main.py -i
回车

输入：
给张三发邮件，主题：项目进度，邮件内容：已完成80%，预计下周上线
回车

等待邮件生成完成（大约10秒）

输入：
exit
回车
```

**第四步：演示系统诊断（90-140秒）**
```
输入：
python main.py -i
回车

输入：
打印机连不上了
回车

等待诊断完成（大约10秒）

输入：
exit
回车
```

**第五步：结束录制**
```
Ctrl+C
```

---

## 三、完整操作序列（复制粘贴用）

```bash
# === 第一步：测试感知层 ===
python3 tests/test_perception_deepin25.py
# 等待约10秒，让测试跑完，看到测试结果
# 按 Ctrl+C 停止（也可以等它自己结束）

# === 第二步：演示邮件助手 ===
exit
python main.py -i
给张三发邮件，主题：项目进度，邮件内容：已完成80%，预计下周上线
# 等待邮件生成
exit

# === 第三步：演示系统诊断 ===
python main.py -i
打印机连不上了
# 等待诊断结果
exit

# === 第四步：停止录制 ===
Ctrl+C
```

---

## 四、录制参数说明

| 参数 | 含义 |
|------|------|
| `-f x11grab` | 捕获 X11 屏幕 |
| `-r 30` | 帧率 30fps |
| `-s 1280x800` | 分辨率（根据实际屏幕调整） |
| `-i :0.0` | 第一个显示器 |
| `-c:v libx264` | H.264 编码 |
| `-preset fast` | 快速编码（文件较大但速度快） |

---

## 五、文件位置

录制的视频会保存到：
```
~/Desktop/deepin_demo.mp4
```

---

## 六、验证视频

```bash
# 检查文件是否存在
ls -lh ~/Desktop/deepin_demo.mp4

# 查看视频时长
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 ~/Desktop/deepin_demo.mp4
```

---

## 七、注意事项

1. **不需要麦克风** — 只录屏幕，没有声音
2. **输入命令时慢一点** — 给观众时间看清你在打什么
3. **每步之间稍停2-3秒** — 让观众理解当前操作
4. **尽量在安静环境** — 虽然没录音频，但环境噪音可能影响判断

---

## 八、提交

录完后把视频文件（`~/Desktop/deepin_demo.mp4`）拷回来发给我

我帮你配字幕和文字说明

```bash
# 打包
tar -czvf demo.tar.gz ~/Desktop/deepin_demo.mp4
```

---

🦞 deepin-agent-teams 演示录制指南 | 2026-05-16