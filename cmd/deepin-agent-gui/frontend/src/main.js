// v4 GUI 前端 - 跟 Wails 后端 App.Run / App.GetStatus 通信
//
// Wails 自动生成 wailsjs/go/main/App.js，我们直接 import 即可。

import './style.css';
import {Run, GetStatus} from '../wailsjs/go/main/App';

const chatEl = document.getElementById('chat');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
const statusEl = document.getElementById('status');
const applyCheckbox = document.getElementById('apply-checkbox');
const applyText = document.getElementById('apply-text');
const applyLabel = document.getElementById('apply-label');

/**
 * 添加一条消息到聊天窗口
 */
function addMessage(role, text) {
    const msg = document.createElement('div');
    msg.className = `message ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;

    msg.appendChild(bubble);
    chatEl.appendChild(msg);

    chatEl.scrollTop = chatEl.scrollHeight;
    return bubble;
}

/**
 * 读取当前 apply 状态
 */
function isApplyMode() {
    return applyCheckbox.checked;
}

/**
 * 处理用户输入
 */
async function handleSend() {
    const text = inputEl.value.trim();
    if (!text) return;

    const apply = isApplyMode();

    // 1. 显示用户消息（apply 模式下加红色边框标识）
    const userMsg = document.createElement('div');
    userMsg.className = `message user${apply ? ' apply' : ''}`;
    const userBubble = document.createElement('div');
    userBubble.className = 'bubble';
    userBubble.textContent = apply ? `⚡ ${text}` : text;
    userMsg.appendChild(userBubble);
    chatEl.appendChild(userMsg);

    inputEl.value = '';
    sendBtn.disabled = true;

    // 2. 显示 loading（区分模式）
    const loadingBubble = addMessage('loading', apply ? '正在执行...' : '思考中...');

    try {
        // 3. 调 Wails 后端
        const reply = await Run(text, apply);

        // 4. 替换 loading 为回复
        loadingBubble.parentElement.classList.remove('loading');
        loadingBubble.parentElement.classList.add('assistant');
        loadingBubble.textContent = reply;
        chatEl.scrollTop = chatEl.scrollHeight;

        // apply 模式下在消息末尾加 ✓ 标识
        if (apply) {
            const tag = document.createElement('div');
            tag.className = 'apply-tag';
            tag.textContent = '✓ 已应用';
            loadingBubble.appendChild(tag);
        }
    } catch (err) {
        // 5. 错误显示
        loadingBubble.parentElement.classList.remove('loading');
        loadingBubble.parentElement.classList.add('error');
        loadingBubble.textContent = `❌ ${err.message || err}`;
    } finally {
        sendBtn.disabled = false;
        inputEl.focus();
    }
}

// 发送按钮
sendBtn.addEventListener('click', handleSend);

// Enter 发送，Shift+Enter 换行
inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});

// apply toggle 切换
function updateApplyUI() {
    if (applyCheckbox.checked) {
        applyText.textContent = '应用模式';
        document.body.classList.add('apply-mode');
    } else {
        applyText.textContent = '预览模式';
        document.body.classList.remove('apply-mode');
    }
}
applyCheckbox.addEventListener('change', updateApplyUI);
updateApplyUI();

// 启动时获取状态
async function refreshStatus() {
    try {
        const status = await GetStatus();
        statusEl.textContent = status.ready
            ? `${status.llm}`
            : '⚠️ LLM 未配置';
    } catch (err) {
        statusEl.textContent = `❌ ${err}`;
    }
}
refreshStatus();

// 自动聚焦输入框
inputEl.focus();