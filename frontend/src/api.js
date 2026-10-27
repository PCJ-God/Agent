// 统一 API 客户端。所有路径均为相对路径：生产由 nginx 反代、开发由 vite proxy 转发。

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function parseJson(resp) {
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`)
  return data
}

async function postJson(path, body, token) {
  const resp = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(body),
  })
  return parseJson(resp)
}

async function getJson(path, token) {
  const resp = await fetch(path, { headers: authHeaders(token) })
  return parseJson(resp)
}

export const register = (u, p) => postJson('/api/auth/register', { username: u, password: p })
export const login = (u, p) => postJson('/api/auth/login', { username: u, password: p })
export const me = (t) => getJson('/api/auth/me', t)
export const logout = (t) => postJson('/api/auth/logout', {}, t)

// 多文件上传。task_type：chat=附件（进对话上下文）；ingest=写入知识库（管理员）。
export function uploadFiles(token, files, taskType = 'chat') {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const q = taskType && taskType !== 'chat' ? `?task_type=${taskType}` : ''
  return fetch(`/api/files/upload${q}`, {
    method: 'POST',
    headers: authHeaders(token),
    body: form,
  }).then(parseJson)
}

// 轮询解析任务状态，返回 { statuses: { task_id: 'pending'|'done'|'failed' } }
export function getFileStatus(token, taskIds) {
  const q = taskIds.map((id) => `task_id=${encodeURIComponent(id)}`).join('&')
  return getJson(`/api/files/status?${q}`, token)
}

// 管理员：重灌课程知识库
export const reindex = (t) => postJson('/api/admin/reindex', {}, t)

// 飞书绑定
export const feishuBindStatus = (t) => getJson('/api/bind/feishu/status', t)
export const bindFeishu = (t, code) => postJson('/api/bind/feishu', { code }, t)
export const unbindFeishu = (t) => postJson('/api/bind/feishu/unbind', {}, t)

// 统一对话入口：SSE 流式。事件对象形如
// {type:'step', text} / {type:'delta', text} / {type:'sources', sources} / {type:'done'} / {type:'error', text}
export async function chatStream(token, body, onEvent) {
  const resp = await fetch('/api/assistant', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(body),
  })
  if (!resp.ok || !resp.body) {
    let msg = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      if (data.error) msg = data.error
    } catch {
      /* 忽略非 JSON 响应体 */
    }
    throw new Error(msg)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data:')) continue
        const payload = line.slice(5).trim()
        if (!payload) continue
        try {
          onEvent(JSON.parse(payload))
        } catch {
          /* 忽略无法解析的行 */
        }
      }
    }
  }
}
