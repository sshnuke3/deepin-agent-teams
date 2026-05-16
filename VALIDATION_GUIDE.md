# deepin-agent-teams 实体机验证指南

> 第十期飞桨黑客松 · 统信 × 百度飞桨 · 进阶任务 #27
> 验证日期：2026-05-16

---

## 一、环境部署

### 1.1 克隆项目

```bash
git clone https://github.com/sshnuke3/deepin-agent-teams.git
cd deepin-agent-teams
```

### 1.2 运行一键部署

```bash
bash deepin25_deploy.sh
```

脚本会自动安装：
- 系统工具：grim、scrot、wmctrl、xdotool、xclip、imagemagick
- Python 依赖：erniebot、PyQt5、psutil 等
- PaddleOCR（可选）

### 1.3 配置 Token

```bash
cp .env.example .env
nano .env
```

填入你的 AI Studio Access Token：

```
ERNIEBOT_ACCESS_TOKEN=你的token
```

### 1.4 验证依赖

```bash
source venv/bin/activate

python3 -c "import erniebot; print('erniebot OK')"
python3 -c "from perception import deepin_dbus; print('perception OK')"
python3 -c "from scenarios.email_assistant import EmailAssistant; print('scenarios OK')"
```

---

## 二、感知层测试

### 2.1 运行完整测试

```bash
cd deepin-agent-teams
source venv/bin/activate
python3 tests/test_perception_deepin25.py
```

会生成两个结果文件：
- `tests/test_results_YYYYMMDD_HHMMSS.json`（详细结果）
- `tests/test_results_YYYYMMDD_HHMMSS_summary.txt`（汇总）

### 2.2 单模块测试（可选）

```bash
# 测试屏幕截图
python3 -c "from perception.screen_capture import capture_screen; print(capture_screen())"

# 测试剪贴板
python3 -c "from perception.clipboard_monitor import get_clipboard_text; print(get_clipboard_text())"

# 测试窗口管理
python3 -c "from perception.window_manager import get_active_window; print(get_active_window())"

# 测试 deepin D-Bus
python3 -c "from perception.deepin_dbus import get_deepin_info; print(get_deepin_info())"

# 测试 OCR
python3 -c "from perception.screen_ocr import is_ocr_available; print(is_ocr_available())"

# 测试意图识别
python3 -c "from perception.context_engine import ContextEngine; e=ContextEngine(); print(e.classify_intent('给张三发邮件')))"
```

---

## 三、场景演示测试

### 3.1 场景一：智能邮件助手

```bash
python main.py -d email
```

测试输入：
```
帮我给张三发一封邮件说项目进度
```

预期行为：
1. 意图识别为"邮件"
2. 询问收件人/主题/邮件内容
3. 多源信息聚合
4. 生成邮件预览

### 3.2 场景二：系统问题诊断

```bash
python main.py -d doctor
```

测试输入：
```
打印机连不上了
```

预期行为：
1. 多模态问题分析
2. 检查服务状态/驱动/配置
3. 生成修复方案
4. 等待用户确认后执行

### 3.3 交互模式（综合测试）

```bash
python main.py -i
```

可以自由输入各种指令，测试意图识别和智能体调度。

---

## 四、GUI 测试（可选）

```bash
python main.py --gui
```

测试内容：
- 悬浮球是否正常显示
- 点击能否打开对话窗口
- 场景切换是否正常
- 托盘图标是否显示

---

## 五、演示视频录制

### 5.1 安装录制工具

```bash
sudo apt install -y ffmpeg
```

### 5.2 开始录制

```bash
ffmpeg -f x11grab -r 30 -s 1920x1080 -i :0.0 -c:v libx264 -preset fast output.mp4
```

### 5.3 演示流程（建议5-8分钟）

**第一部分：环境感知展示（1-2分钟）**
- 展示屏幕截图功能
- 展示剪贴板监控
- 展示窗口管理器
- 展示 deepin D-Bus 接口

**第二部分：智能邮件助手（2-3分钟）**
- 输入："给张三发邮件说项目进度"
- 展示意图识别
- 展示多源信息聚合
- 展示邮件生成结果

**第三部分：系统问题诊断（2-3分钟）**
- 输入："打印机连不上了"
- 展示多模态感知
- 展示协同诊断
- 展示修复方案

### 5.4 停止录制

```
Ctrl+C
```

---

## 六、结果收集

### 6.1 打包测试结果

```bash
cd deepin-agent-teams
tar -czvf test_results.tar.gz \
    tests/test_results*.json \
    tests/test_results*.txt \
    tests/*.png \
    output.mp4
```

### 6.2 拷贝回本机

方式一：scp
```bash
scp user@deepin-ip:/path/to/test_results.tar.gz ./
```

方式二：U盘

方式三：直接复制文件内容

---

## 七、验证清单

| 验证项 | 通过标准 | 状态 |
|--------|---------|------|
| 部署脚本执行成功 | 无报错 | □ |
| erniebot 可调用 | 能对话 | □ |
| 屏幕截图正常 | 生成图片文件 | □ |
| 剪贴板监控正常 | 能读取文本 | □ |
| 窗口管理正常 | 能获取活动窗口 | □ |
| deepin D-Bus 正常 | 能获取系统信息 | □ |
| OCR 识别正常 | 能识别文字 | □ |
| 意图识别正常 | 输入邮件相关语句能识别 | □ |
| 智能体调度正常 | 能分配任务给不同 Agent | □ |
| 场景一运行正常 | 邮件助手完整流程 | □ |
| 场景二运行正常 | 系统诊断完整流程 | □ |
| 演示视频录制 | 时长5-8分钟 | □ |

---

## 八、常见问题

### Q0: venv 创建失败 / ensurepip is not available

```bash
sudo apt install -y python3.12-venv python3-venv
```

修复后重新运行 `bash deepin25_deploy.sh`

### Q1: ModuleNotFoundError

```bash
source venv/bin/activate
```

### Q2: 截图工具不存在

```bash
sudo apt install grim scrot
```

### Q3: Token 无效

去 https://aistudio.baidu.com/ 重新申请 access_token

### Q4: PaddleOCR 安装失败

```bash
pip install paddlepaddle paddleocr --prefer-binary
```

或者跳过 OCR 部分，不影响核心功能

### Q5: DBus 检测失败

检查系统是否是 deepin 25，DBus 在 deepin 上应该自带

---

## 九、提交清单

验证完成后，准备以下材料：

- [ ] 测试结果文件（test_results_*.json）
- [ ] 测试汇总文件（test_results_*.txt）
- [ ] 演示视频（output.mp4）
- [ ] 截图证据（如有）
- [ ] 技术报告更新

---

🦞 deepin-agent-teams 验证脚本 | 2026-05-16