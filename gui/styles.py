"""
deepin-agent-teams GUI 样式表
模拟 deepin 25 的 UI 风格：圆角、半透明、深色/浅色主题
"""

# deepin 风格配色
COLORS = {
    "primary": "#0081FF",       # deepin 主题蓝
    "primary_hover": "#339DFF",
    "primary_pressed": "#006AD4",
    "bg_main": "#FFFFFF",       # 主背景
    "bg_chat": "#F7F7F7",      # 聊天区域背景
    "bg_input": "#FFFFFF",      # 输入框背景
    "bg_user_msg": "#0081FF",   # 用户消息气泡
    "bg_agent_msg": "#E8E8E8",  # Agent 消息气泡
    "text_primary": "#1A1A1A",  # 主文本
    "text_secondary": "#666666",# 次要文本
    "text_user_msg": "#FFFFFF", # 用户消息文本
    "text_agent_msg": "#1A1A1A",# Agent 消息文本
    "border": "#E0E0E0",       # 边框
    "shadow": "rgba(0,0,0,0.15)",
    "scene_email": "#4CAF50",   # 邮件场景绿
    "scene_doctor": "#FF5722",  # 诊断场景橙
    "scene_code": "#9C27B0",    # 代码场景紫
    "scene_literature": "#2196F3", # 文献场景蓝
}

# 悬浮球样式
FLOATING_BALL_STYLE = f"""
QFrame#floatingBall {{
    background-color: {COLORS['primary']};
    border-radius: 28px;
    border: none;
}}
QFrame#floatingBall:hover {{
    background-color: {COLORS['primary_hover']};
}}
QLabel#ballIcon {{
    color: white;
    font-size: 22px;
    background: transparent;
}}
"""

# 主聊天窗口样式
CHAT_WINDOW_STYLE = f"""
QMainWindow#chatWindow {{
    background-color: {COLORS['bg_main']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}
QFrame#titleBar {{
    background-color: {COLORS['primary']};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    min-height: 44px;
    max-height: 44px;
}}
QLabel#titleLabel {{
    color: white;
    font-size: 15px;
    font-weight: bold;
    background: transparent;
}}
QPushButton#closeBtn {{
    background: transparent;
    color: white;
    font-size: 18px;
    border: none;
    border-radius: 12px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
}}
QPushButton#closeBtn:hover {{
    background-color: rgba(255,255,255,0.2);
}}

/* 场景选择栏 */
QFrame#sceneBar {{
    background-color: {COLORS['bg_chat']};
    border-bottom: 1px solid {COLORS['border']};
    min-height: 48px;
    max-height: 48px;
}}
QPushButton#sceneBtn {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 16px;
    font-size: 13px;
    color: {COLORS['text_secondary']};
    min-height: 32px;
}}
QPushButton#sceneBtn:hover {{
    color: {COLORS['primary']};
}}
QPushButton#sceneBtn[active="true"] {{
    color: {COLORS['primary']};
    border-bottom: 2px solid {COLORS['primary']};
    font-weight: bold;
}}

/* 聊天消息区域 */
QScrollArea#chatArea {{
    background-color: {COLORS['bg_chat']};
    border: none;
}}
QWidget#chatContent {{
    background-color: {COLORS['bg_chat']};
}}

/* 用户消息 */
QFrame#userMsgBubble {{
    background-color: {COLORS['bg_user_msg']};
    border-radius: 12px;
    border-top-right-radius: 4px;
    padding: 10px 14px;
}}
QLabel#userMsgText {{
    color: {COLORS['text_user_msg']};
    font-size: 14px;
    background: transparent;
}}

/* Agent 消息 */
QFrame#agentMsgBubble {{
    background-color: {COLORS['bg_agent_msg']};
    border-radius: 12px;
    border-top-left-radius: 4px;
    padding: 10px 14px;
}}
QLabel#agentMsgText {{
    color: {COLORS['text_agent_msg']};
    font-size: 14px;
    background: transparent;
}}

/* 输入区域 */
QFrame#inputBar {{
    background-color: {COLORS['bg_main']};
    border-top: 1px solid {COLORS['border']};
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
    min-height: 60px;
    max-height: 120px;
}}
QTextEdit#inputBox {{
    background-color: {COLORS['bg_input']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 14px;
    color: {COLORS['text_primary']};
}}
QTextEdit#inputBox:focus {{
    border: 1px solid {COLORS['primary']};
}}
QPushButton#sendBtn {{
    background-color: {COLORS['primary']};
    color: white;
    border: none;
    border-radius: 8px;
    min-width: 60px;
    max-width: 60px;
    min-height: 36px;
    font-size: 14px;
    font-weight: bold;
}}
QPushButton#sendBtn:hover {{
    background-color: {COLORS['primary_hover']};
}}
QPushButton#sendBtn:pressed {{
    background-color: {COLORS['primary_pressed']};
}}
QPushButton#sendBtn:disabled {{
    background-color: #CCCCCC;
}}

/* 状态栏 */
QLabel#statusLabel {{
    color: {COLORS['text_secondary']};
    font-size: 11px;
    background: transparent;
}}
"""

# 系统托盘菜单样式
TRAY_MENU_STYLE = f"""
QMenu {{
    background-color: {COLORS['bg_main']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px;
    font-size: 13px;
    color: {COLORS['text_primary']};
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {COLORS['primary']};
    color: white;
}}
"""
