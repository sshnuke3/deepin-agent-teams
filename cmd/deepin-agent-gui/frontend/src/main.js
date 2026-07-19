// v4 GUI 前端 - 跟 Wails 后端 App.Run / App.GetStatus 通信
//
// Wails 自动生成 wailsjs/go/main/App.js，我们直接 import 即可。

import './style.css';
import {Run, GetStatus} from '../wailsjs/go/main/App';

const chatEl = document.getElementById('chat');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
const statusEl = document.getElementById('status');

/**
 * 添加一条消息到聊天窗口
 * @param {string} role - 'user' | 'assistant' | 'system' | 'error' | 'loading'
 * @param {string} text - 消息内容
 * @returns {HTMLElement} 气泡 DOM（用于更新 loading 状态）
 */
function addMessage(role, text) {
    const msg = document.createElement('div');
    msg.className = `message ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;

    msg.appendChild(bubble);
    chatEl.appendChild(msg);

    // 滚动到底部
    chatEl.scrollTop = chatEl.scrollHeight;
    return bubble;
}

/**
 * 处理用户输入
 */
async function handleSend() {
    const text = inputEl.value.trim();
    if (!text) return;

    // 1. 显示用户消息
    addMessage('user', text);
    inputEl.value = '';
    sendBtn.disabled = true;

    // 2. 显示 loading
    const loadingBubble = addMessage('loading', '思考中...');

    try {
        // 3. 调 Wails 后端
        const reply = await Run(text);

        // 4. 替换 loading 为回复
        loadingBubble.parentElement.classList.remove('loading');
        loadingBubble.parentElement.classList.add('assistant');
        loadingBubble.textContent = reply;
        chatEl.scrollTop = chatEl.scrollHeight;
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

// 启动时获取状态，显示在 header
async function refreshStatus() {
    try {
        const status = await GetStatus();
        statusEl.textContent = status.ready
            ? `${status.llm}`
            : '⚠️ LLM 未配置（请设置 API key）';
    } catch (err) {
        statusEl.textContent = `❌ ${err}`;
    }
}
refreshStatus();

// 自动聚焦输入框
inputEl.focus();