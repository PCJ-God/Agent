// 统一 API 客户端。所有路径均为相对路径：生产由 nginx 反代、开发由 vite proxy 转发。

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function postJson(path, body, token) {
  const resp = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(body),
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`)
  return data
}

export function register(username, password) {
  return postJson('/api/auth/register', { username, password })
}

export function login(username, password) {
  return postJson('/api/auth/login', { username, password })
}

export function uploadFile(token, file) {
  const form = new FormData()
  form.append('file', file)
  return fetch('/api/files/upload', {
    method: 'POST',
    headers: authHeaders(token),
    body: form,
  }).then(async (resp) => {
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`)
    return data
  })
}

// 以 POST + fetch 流式读取 SSE；每解析出一个 data 事件就回调 onEvent(obj)。
// 事件对象形如：{delta} {sources} {steps} {answer} {profile} {done} {error}
export async function chatStream(path, body, token, onEvent) {
  const resp = await fetch(path, {
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
