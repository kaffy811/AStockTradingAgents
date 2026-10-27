import { readJsonResponse } from './response.js'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

async function authFetch(path, options = {}) {
  let res
  try {
    res = await fetch(`${API_BASE}/auth${path}`, { credentials: 'include', ...options })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    const err = new Error('无法连接登录服务，请检查网络后重试。')
    err.errorCode = 'AUTH_NETWORK_ERROR'
    throw err
  }
  const data = await readJsonResponse(res)
  if (!res.ok) {
    const detail = data?.detail
    const err = new Error((typeof detail === 'string' ? detail : detail?.message) || data?.message || '登录服务暂不可用，请稍后重试。')
    err.status = res.status
    err.errorCode = detail?.error_code || data?.error_code || null
    throw err
  }
  return data
}

export function meApi(accessToken) {
  return authFetch('/me', { headers: { Authorization: `Bearer ${accessToken}` } })
}

export function googleConfigApi(options = {}) {
  return authFetch('/google/config', { cache: 'no-store', signal: options.signal })
}

export function googleLoginApi(credential, options = {}) {
  return authFetch('/google', {
    method: 'POST', signal: options.signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  })
}

export function refreshApi(refreshToken, options = {}) {
  return authFetch('/refresh', {
    method: 'POST', signal: options.signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
}
