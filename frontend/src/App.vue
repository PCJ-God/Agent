<script setup>
import { ref, nextTick } from 'vue'
import { login, register, uploadFile, chatStream } from './api'

const token = ref(localStorage.getItem('acp_token') || '')
const user = ref(JSON.parse(localStorage.getItem('acp_user') || 'null'))

// —— 登录 / 注册 ——
const authMode = ref('login')
const username = ref('')
const password = ref('')
const authError = ref('')
const authBusy = ref(false)

// —— 聊天 ——
const MODES = [
  { key: 'chat', label: '普通对话', hint: '纯文本多轮' },
  { key: 'rag', label: 'RAG 检索', hint: '本地知识库' },
  { key: 'agent', label: 'Agent', hint: '检索+联网' },
  { key: 'memory', label: '记忆', hint: '长期画像' },
]
const mode = ref('chat')
const messages = ref([])
const input = ref('')
const busy = ref(false)
const sessionId = ref('sess-' + Math.random().toString(36).slice(2, 10))
const toast = ref('')
const scrollBox = ref(null)

async function doAuth() {
  authError.value = ''
  if (username.value.length < 3 || password.value.length < 8) {
    authError.value = '用户名至少 3 字符，密码至少 8 位'
    return
  }
  authBusy.value = true
  try {
    const fn = authMode.value === 'login' ? login : register
    const data = await fn(username.value, password.value)
    token.value = data.token
    user.value = data.user
    localStorage.setItem('acp_token', data.token)
    localStorage.setItem('acp_user', JSON.stringify(data.user))
    password.value = ''
  } catch (e) {
    authError.value = e.message
  } finally {
    authBusy.value = false
  }
}

function logout() {
  token.value = ''
  user.value = null
  messages.value = []
  localStorage.removeItem('acp_token')
  localStorage.removeItem('acp_user')
}

function showToast(text) {
  toast.value = text
  setTimeout(() => {
    if (toast.value === text) toast.value = ''
  }, 4000)
}

async function scrollToBottom() {
  await nextTick()
  if (scrollBox.value) scrollBox.value.scrollTop = scrollBox.value.scrollHeight
}

function buildBody(text) {
  if (mode.value === 'chat') {
    const history = messages.value
      .filter((m) => m.role !== 'system' && m.content)
      .map((m) => ({ role: m.role, content: m.content }))
    history.push({ role: 'user', content: text })
    return { messages: history }
  }
  if (mode.value === 'rag' || mode.value === 'agent') {
    return { query: text }
  }
  return {
    user_id: String(user.value?.ID ?? user.value?.id ?? 'guest'),
    session_id: sessionId.value,
    message: text,
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || busy.value) return
  input.value = ''

  const body = buildBody(text)
  messages.value.push({ role: 'user', content: text })
  const assistant = { role: 'assistant', content: '', sources: null, steps: null, profile: null }
  messages.value.push(assistant)
  busy.value = true
  scrollToBottom()

  try {
    await chatStream(`/api/chat/${mode.value}`, body, token.value, (ev) => {
      if (ev.error) assistant.content += `\n[错误] ${ev.error}`
      if (ev.delta) assistant.content += ev.delta
      if (ev.answer) assistant.content = ev.answer
      if (ev.sources) assistant.sources = ev.sources
      if (ev.steps) assistant.steps = ev.steps
      if (ev.profile) assistant.profile = ev.profile
      scrollToBottom()
    })
  } catch (e) {
    assistant.content = `[请求失败] ${e.message}`
  } finally {
    busy.value = false
    scrollToBottom()
  }
}

async function onUpload(ev) {
  const file = ev.target.files?.[0]
  ev.target.value = ''
  if (!file) return
  try {
    const data = await uploadFile(token.value, file)
    showToast(`已上传 ${file.name}，后台异步解析中`)
    messages.value.push({ role: 'system', content: `已上传文档：${file.name}（状态：${data.status}）` })
    scrollToBottom()
  } catch (e) {
    showToast('上传失败：' + e.message)
  }
}
</script>

<template>
  <div class="app">
    <!-- 登录 / 注册 -->
    <div v-if="!token" class="auth">
      <div class="auth-card">
        <h1>ACP Copilot</h1>
        <p class="sub">阿里云认证学习助手</p>

        <div class="tabs">
          <button :class="{ active: authMode === 'login' }" @click="authMode = 'login'">登录</button>
          <button :class="{ active: authMode === 'register' }" @click="authMode = 'register'">注册</button>
        </div>

        <input v-model="username" placeholder="用户名（3-64 字符）" autocomplete="username" />
        <input v-model="password" type="password" placeholder="密码（至少 8 位）" autocomplete="current-password" />
        <div v-if="authError" class="error">{{ authError }}</div>
        <button class="primary" :disabled="authBusy" @click="doAuth">
          {{ authBusy ? '请稍候…' : authMode === 'login' ? '登录' : '注册' }}
        </button>
      </div>
    </div>

    <!-- 聊天 -->
    <div v-else class="chat">
      <header>
        <div class="brand">ACP Copilot</div>
        <nav class="modes">
          <button
            v-for="m in MODES"
            :key="m.key"
            :class="{ active: mode === m.key }"
            :title="m.hint"
            @click="mode = m.key"
          >
            {{ m.label }}
          </button>
        </nav>
        <div class="user-area">
          <span class="who">{{ user?.username || user?.Username || '用户' }}</span>
          <button class="ghost" @click="logout">退出</button>
        </div>
      </header>

      <main ref="scrollBox">
        <div v-if="messages.length === 0" class="empty">
          <p>选择上方模式开始提问</p>
          <p class="hint">例如：什么是对象存储 OSS？/ 专有网络 VPC 有哪些组件？</p>
        </div>

        <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
          <div class="bubble">
            <div v-if="m.sources?.length" class="meta">
              <div class="meta-title">引用来源</div>
              <div v-for="(s, j) in m.sources" :key="j" class="meta-line">
                {{ s.header_path || s.source }}（{{ Math.round((s.score ?? 0) * 100) }}%）
              </div>
            </div>
            <div v-if="m.steps?.length" class="meta">
              <div class="meta-title">工具调用轨迹</div>
              <div v-for="(s, j) in m.steps" :key="j" class="meta-line">
                {{ s.tool }}<template v-if="s.args?.query"> · {{ s.args.query }}</template>
              </div>
            </div>
            <div v-if="m.profile?.length" class="meta">
              <div class="meta-title">长期画像</div>
              <div v-for="(f, j) in m.profile" :key="j" class="meta-line">{{ f }}</div>
            </div>
            <div class="content">{{ m.content }}<span v-if="busy && i === messages.length - 1" class="cursor">▍</span></div>
          </div>
        </div>
      </main>

      <footer>
        <input
          v-model="input"
          :disabled="busy"
          placeholder="输入问题，回车发送…"
          @keydown.enter="send"
        />
        <label class="upload" title="上传文档（md/txt/pdf），后台异步解析入知识库">
          📎
          <input type="file" accept=".md,.txt,.pdf" @change="onUpload" />
        </label>
        <button class="primary" :disabled="busy || !input.trim()" @click="send">发送</button>
      </footer>
    </div>

    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --bg: #f5f6f8;
  --card: #ffffff;
  --border: #e5e7eb;
  --accent: #4f46e5;
  --accent-weak: #eef0ff;
  --text: #1f2937;
  --muted: #6b7280;
}

body {
  font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
}

.app {
  height: 100vh;
  display: flex;
}

/* —— 登录 —— */
.auth {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.auth-card {
  width: 340px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 32px 28px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.auth-card h1 {
  font-size: 22px;
  text-align: center;
}

.auth-card .sub {
  text-align: center;
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 6px;
}

.tabs {
  display: flex;
  gap: 8px;
}

.tabs button {
  flex: 1;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  cursor: pointer;
  font-size: 14px;
}

.tabs button.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.auth-card input {
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
}

.error {
  color: #dc2626;
  font-size: 13px;
}

/* —— 聊天布局 —— */
.chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 960px;
  margin: 0 auto;
  width: 100%;
}

header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
}

.brand {
  font-weight: 700;
  font-size: 16px;
  white-space: nowrap;
}

.modes {
  display: flex;
  gap: 6px;
  flex: 1;
}

.modes button {
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg);
  cursor: pointer;
  font-size: 13px;
}

.modes button.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.user-area {
  display: flex;
  align-items: center;
  gap: 10px;
}

.who {
  font-size: 13px;
  color: var(--muted);
}

button.primary {
  padding: 10px 18px;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  font-size: 14px;
}

button.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

button.ghost {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
}

main {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty {
  margin: auto;
  text-align: center;
  color: var(--muted);
}

.empty .hint {
  font-size: 13px;
  margin-top: 8px;
}

.msg {
  display: flex;
}

.msg.user {
  justify-content: flex-end;
}

.msg.assistant {
  justify-content: flex-start;
}

.msg.system {
  justify-content: center;
}

.bubble {
  max-width: 78%;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.msg.user .bubble {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.msg.assistant .bubble {
  background: var(--card);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.msg.system .bubble {
  background: var(--accent-weak);
  color: var(--muted);
  font-size: 12px;
  padding: 6px 12px;
}

.content {
  white-space: pre-wrap;
  word-break: break-word;
}

.cursor {
  animation: blink 1s step-start infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.meta {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--muted);
}

.meta-title {
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}

.meta-line {
  margin: 2px 0;
}

/* —— 输入区 —— */
footer {
  display: flex;
  gap: 10px;
  padding: 14px 20px;
  background: var(--card);
  border-top: 1px solid var(--border);
}

footer input[type="text"],
footer > input {
  flex: 1;
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
}

.upload {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  font-size: 18px;
  background: var(--bg);
}

.upload input {
  display: none;
}

.toast {
  position: fixed;
  bottom: 90px;
  left: 50%;
  transform: translateX(-50%);
  background: #111827;
  color: #fff;
  padding: 10px 18px;
  border-radius: 8px;
  font-size: 13px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}
</style>
