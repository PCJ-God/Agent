<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import * as api from './api'

const token = ref(localStorage.getItem('acp_token') || '')
const user = ref(JSON.parse(localStorage.getItem('acp_user') || 'null'))
const isAdmin = ref(false)
const view = ref(token.value ? 'chat' : 'auth')

// 登录 / 注册
const authMode = ref('login')
const username = ref('')
const password = ref('')
const authError = ref('')
const authBusy = ref(false)

// 对话
const messages = ref([])
const input = ref('')
const files = ref([])
const sessionId = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now())
const streaming = ref(false)
const fileInput = ref(null)
const chatBox = ref(null)

// 管理员
const adminFiles = ref([])
const adminMsg = ref('')
const adminBusy = ref(false)

function saveAuth(t, u) {
  token.value = t
  user.value = u
  isAdmin.value = !!(u && u.role === 'admin')
  localStorage.setItem('acp_token', t)
  localStorage.setItem('acp_user', JSON.stringify(u))
}

async function doAuth(isRegister) {
  authError.value = ''
  authBusy.value = true
  try {
    const fn = isRegister ? api.register : api.login
    const data = await fn(username.value, password.value)
    saveAuth(data.token, data.user)
    view.value = 'chat'
  } catch (e) {
    authError.value = e.message
  } finally {
    authBusy.value = false
  }
}

function logout() {
  api.logout(token.value).catch(() => {})
  token.value = ''
  user.value = null
  isAdmin.value = false
  localStorage.removeItem('acp_token')
  localStorage.removeItem('acp_user')
  messages.value = []
  view.value = 'auth'
}

onMounted(async () => {
  if (token.value) {
    try {
      const u = await api.me(token.value)
      saveAuth(token.value, u)
    } catch {
      logout()
    }
  }
})

function pickFiles(e) {
  files.value = Array.from(e.target.files || [])
}

function fmtSize(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function scrollDown() {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}

function pushAssistant() {
  const m = reactive({ role: 'assistant', text: '', steps: [], sources: [], error: '' })
  messages.value.push(m)
  return m
}

async function pollStatus(ids) {
  for (let i = 0; i < 60; i++) {
    const { statuses } = await api.getFileStatus(token.value, ids)
    const vals = Object.values(statuses)
    if (vals.every((s) => s === 'done' || s === 'failed' || s === 'error')) return
    await new Promise((r) => setTimeout(r, 1500))
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  input.value = ''
  const names = files.value.map((f) => f.name)
  messages.value.push({ role: 'user', text, files: names })
  scrollDown()

  streaming.value = true
  let taskIds = []
  try {
    if (files.value.length) {
      const res = await api.uploadFiles(token.value, files.value, 'chat')
      taskIds = res.task_ids || []
      await pollStatus(taskIds)
    }
    const m = pushAssistant()
    await api.chatStream(
      token.value,
      { message: text, session_id: sessionId, task_ids: taskIds },
      (ev) => {
        if (ev.type === 'step') m.steps.push(ev.text)
        else if (ev.type === 'delta') m.text += ev.text
        else if (ev.type === 'sources') m.sources = ev.sources || []
        else if (ev.type === 'error') m.error = ev.text
        scrollDown()
      },
    )
  } catch (e) {
    const m = pushAssistant()
    m.error = e.message
  } finally {
    streaming.value = false
    files.value = []
    if (fileInput.value) fileInput.value.value = ''
    scrollDown()
  }
}

function pickAdminFiles(e) {
  adminFiles.value = Array.from(e.target.files || [])
}

async function adminUpload() {
  if (!adminFiles.value.length || adminBusy.value) return
  adminBusy.value = true
  adminMsg.value = ''
  try {
    const res = await api.uploadFiles(token.value, adminFiles.value, 'ingest')
    adminMsg.value = `已入队 ${res.task_ids.length} 个解析任务，worker 解析完成后会自动写入知识库。`
    adminFiles.value = []
  } catch (e) {
    adminMsg.value = `上传失败：${e.message}`
  } finally {
    adminBusy.value = false
  }
}

async function adminReindex() {
  adminBusy.value = true
  adminMsg.value = '正在重灌课程知识库（分块 + 向量化，可能需要 1–3 分钟）…'
  try {
    const res = await api.reindex(token.value)
    adminMsg.value = `完成：摄入 ${res.ingested} 个切片，共 ${(res.sources || []).length} 篇文档。`
  } catch (e) {
    adminMsg.value = `重灌失败：${e.message}`
  } finally {
    adminBusy.value = false
  }
}
</script>

<template>
  <div v-if="view === 'auth'" class="auth">
    <form class="card" @submit.prevent="doAuth(authMode === 'register')">
      <h1>ACP Copilot</h1>
      <p class="sub">阿里云认证学习助手</p>
      <div class="tabs">
        <button type="button" :class="{ on: authMode === 'login' }" @click="authMode = 'login'">登录</button>
        <button type="button" :class="{ on: authMode === 'register' }" @click="authMode = 'register'">注册</button>
      </div>
      <label>用户名</label>
      <input v-model="username" autocomplete="username" placeholder="3–64 位" required />
      <label>密码</label>
      <input v-model="password" type="password" autocomplete="current-password" placeholder="至少 8 位" required />
      <p v-if="authError" class="err">{{ authError }}</p>
      <button class="primary" type="submit" :disabled="authBusy">
        {{ authBusy ? '请稍候…' : authMode === 'login' ? '登录' : '注册并登录' }}
      </button>
    </form>
  </div>

  <div v-else class="layout">
    <header>
      <h1>ACP Copilot</h1>
      <nav>
        <button :class="{ on: view === 'chat' }" @click="view = 'chat'">对话</button>
        <button v-if="isAdmin" :class="{ on: view === 'admin' }" @click="view = 'admin'">知识库管理</button>
      </nav>
      <div class="who">
        <span class="role">{{ isAdmin ? '管理员' : '学员' }} · {{ user && user.username }}</span>
        <button class="ghost" @click="logout">退出</button>
      </div>
    </header>

    <main v-if="view === 'chat'" class="chat">
      <div ref="chatBox" class="messages">
        <div v-if="!messages.length" class="empty">
          输入你的问题开始对话。支持上传附件（PDF / Word / 图片），Agent 会主动检索课程知识库并管理长期记忆。
        </div>
        <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
          <div class="bubble">
            <div v-if="m.files && m.files.length" class="chips">
              <span v-for="f in m.files" :key="f" class="chip">📎 {{ f }}</span>
            </div>
            <div class="text">{{ m.text }}</div>
            <div v-if="m.steps && m.steps.length" class="steps">
              <div v-for="s in m.steps" :key="s" class="step">{{ s }}</div>
            </div>
            <div v-if="m.sources && m.sources.length" class="sources">
              <div class="src-title">引用来源</div>
              <div v-for="(s, j) in m.sources" :key="j" class="src">
                {{ s.source }} · {{ s.header_path }}
              </div>
            </div>
            <div v-if="m.error" class="err">{{ m.error }}</div>
          </div>
        </div>
        <div v-if="streaming" class="msg assistant"><div class="bubble dim">思考中…</div></div>
      </div>

      <div class="composer">
        <div v-if="files.length" class="chips">
          <span v-for="f in files" :key="f.name" class="chip">
            {{ f.name }}（{{ fmtSize(f.size) }}）
          </span>
        </div>
        <div class="row">
          <input ref="fileInput" type="file" multiple accept=".pdf,.docx,.doc,.txt,.md,.png,.jpg,.jpeg" @change="pickFiles" />
          <textarea
            v-model="input"
            rows="2"
            placeholder="输入问题，回车发送，Shift+回车换行"
            @keydown.enter.exact.prevent="send"
          ></textarea>
          <button class="primary" :disabled="streaming || !input.trim()" @click="send">
            {{ streaming ? '回复中…' : '发送' }}
          </button>
        </div>
      </div>
    </main>

    <main v-else-if="isAdmin" class="admin">
      <section class="card">
        <h2>重灌课程知识库</h2>
        <p>清空并重建 Qdrant 中的课程知识库，重新分块、向量化 /app/data/docs 下的全部文档。</p>
        <button class="primary" :disabled="adminBusy" @click="adminReindex">开始重灌</button>
      </section>
      <section class="card">
        <h2>添加知识库文档</h2>
        <p>上传 PDF / Word / Markdown，worker 解析后经 gRPC 写入课程知识库。</p>
        <input type="file" multiple accept=".pdf,.docx,.doc,.txt,.md" @change="pickAdminFiles" />
        <div v-if="adminFiles.length" class="chips">
          <span v-for="f in adminFiles" :key="f.name" class="chip">{{ f.name }}</span>
        </div>
        <button class="primary" :disabled="adminBusy || !adminFiles.length" @click="adminUpload">上传入库</button>
      </section>
      <p v-if="adminMsg" class="admin-msg">{{ adminMsg }}</p>
    </main>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }
.app, .auth, .layout { font-family: system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
.auth { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #0f172a; color: #e2e8f0; }
.card { background: #1e293b; padding: 32px; border-radius: 14px; width: 340px; display: flex; flex-direction: column; gap: 10px; }
.card h1 { margin: 0; font-size: 22px; }
.card .sub { margin: 0 0 8px; color: #94a3b8; font-size: 13px; }
.card label { font-size: 13px; color: #94a3b8; }
.card input { padding: 10px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; }
.tabs { display: flex; gap: 8px; }
.tabs button { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid #334155; background: transparent; color: #94a3b8; cursor: pointer; }
.tabs button.on { background: #2563eb; color: #fff; border-color: #2563eb; }
.layout { display: flex; flex-direction: column; height: 100vh; background: #f1f5f9; color: #0f172a; }
header { display: flex; align-items: center; gap: 20px; padding: 12px 20px; background: #0f172a; color: #fff; }
header h1 { font-size: 18px; margin: 0; }
nav { display: flex; gap: 8px; }
nav button, .ghost { padding: 7px 14px; border-radius: 8px; border: 1px solid #334155; background: transparent; color: #cbd5e1; cursor: pointer; }
nav button.on { background: #2563eb; border-color: #2563eb; color: #fff; }
.who { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.role { font-size: 13px; color: #94a3b8; }
.chat { flex: 1; display: flex; flex-direction: column; min-height: 0; max-width: 900px; width: 100%; margin: 0 auto; padding: 16px; }
.messages { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; padding-bottom: 8px; }
.empty { color: #64748b; text-align: center; margin-top: 40px; font-size: 14px; }
.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.bubble { max-width: 78%; padding: 12px 16px; border-radius: 12px; white-space: pre-wrap; word-break: break-word; font-size: 15px; line-height: 1.6; }
.msg.user .bubble { background: #2563eb; color: #fff; border-bottom-right-radius: 4px; }
.msg.assistant .bubble { background: #fff; color: #0f172a; border: 1px solid #e2e8f0; border-bottom-left-radius: 4px; }
.bubble.dim { color: #94a3b8; }
.text { white-space: pre-wrap; }
.err { color: #dc2626; font-size: 13px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.chip { font-size: 12px; padding: 3px 9px; border-radius: 999px; background: rgba(148, 163, 184, 0.2); }
.steps { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
.step { font-size: 12px; color: #64748b; }
.steps .step::before { content: "⚙ "; }
.sources { margin-top: 10px; border-top: 1px dashed #e2e8f0; padding-top: 8px; }
.src-title { font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 4px; }
.src { font-size: 12px; color: #64748b; }
.composer { border-top: 1px solid #e2e8f0; padding-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.composer .row { display: flex; gap: 10px; align-items: flex-end; }
.composer input[type="file"] { font-size: 12px; color: #64748b; max-width: 260px; }
.composer textarea { flex: 1; padding: 10px 12px; border-radius: 10px; border: 1px solid #cbd5e1; resize: none; font: inherit; font-size: 15px; }
.primary { padding: 10px 20px; border-radius: 10px; border: none; background: #2563eb; color: #fff; cursor: pointer; font-weight: 600; }
.primary:disabled { background: #93c5fd; cursor: not-allowed; }
.admin { flex: 1; overflow-y: auto; max-width: 900px; width: 100%; margin: 0 auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.admin .card { width: 100%; }
.admin h2 { margin: 0 0 8px; font-size: 17px; }
.admin p { color: #64748b; font-size: 14px; margin: 0 0 12px; }
.admin input[type="file"] { margin-bottom: 10px; font-size: 13px; }
.admin-msg { padding: 12px; border-radius: 8px; background: #fff; border: 1px solid #e2e8f0; }
</style>
