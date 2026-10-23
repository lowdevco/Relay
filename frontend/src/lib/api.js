// Thin fetch wrapper. Auth = Django session cookie (HttpOnly) + CSRF header.
// No tokens or API keys are ever stored in the browser.

let workspaceId = null

export function setWorkspaceId(id) {
  workspaceId = id
  if (id) localStorage.setItem('relay.workspace', String(id))
  else localStorage.removeItem('relay.workspace')
}

export function storedWorkspaceId() {
  return localStorage.getItem('relay.workspace')
}

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[2]) : null
}

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

// Flatten DRF error payloads ({field: ["msg"]}, {detail: "..."}) into one sentence.
export function errorMessage(data, fallback = 'Something went wrong.') {
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.detail) return String(data.detail)
  const parts = []
  for (const [key, value] of Object.entries(data)) {
    if (key === 'code' || key === 'test') continue
    const text = Array.isArray(value) ? value.join(' ') : typeof value === 'object' ? errorMessage(value, '') : String(value)
    if (text) parts.push(key === 'non_field_errors' ? text : `${key.replaceAll('_', ' ')}: ${text}`)
  }
  return parts.join(' ') || fallback
}

let csrfPromise = null
async function ensureCsrf() {
  if (getCookie('csrftoken')) return
  csrfPromise ??= fetch('/api/auth/csrf/', { credentials: 'same-origin' }).finally(() => (csrfPromise = null))
  await csrfPromise
}

export async function api(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' }
  const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(method)
  if (unsafe) {
    await ensureCsrf()
    headers['X-CSRFToken'] = getCookie('csrftoken') || ''
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (workspaceId) headers['X-Workspace-ID'] = String(workspaceId)

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
    signal,
  })
  let data = null
  const text = await res.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    if (res.status === 403 && data?.detail?.includes?.('CSRF')) {
      // Token rotated (e.g. after login). Retry once with a fresh one.
      document.cookie = 'csrftoken=; Max-Age=0; path=/'
    }
    throw new ApiError(errorMessage(data, `Request failed (${res.status})`), res.status, data)
  }
  return data
}

export const get = (path, opts) => api(path, opts)
export const post = (path, body, opts) => api(path, { ...opts, method: 'POST', body: body ?? {} })
export const put = (path, body) => api(path, { method: 'PUT', body })
export const patch = (path, body) => api(path, { method: 'PATCH', body })
export const del = (path) => api(path, { method: 'DELETE' })
