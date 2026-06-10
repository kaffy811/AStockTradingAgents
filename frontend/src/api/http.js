import { useAuthStore } from '../stores/auth.js'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

/**
 * Base fetch wrapper.
 * - Automatically injects Authorization: Bearer <token> header.
 * - On 401: calls authStore.logout() and throws with a user-facing message.
 * - On non-2xx: throws Error with data.detail or HTTP status.
 */
export async function baseFetch(path, options = {}) {
  const authStore = useAuthStore()

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (authStore.token) {
    headers['Authorization'] = `Bearer ${authStore.token}`
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (res.status === 401) {
    authStore.logout()
    const err = new Error('登录已过期，请重新登录')
    err.status = 401
    throw err
  }

  if (res.status === 204) {
    return null
  }

  const data = await res.json()

  if (!res.ok) {
    const err = new Error(data.detail || `HTTP ${res.status}`)
    err.status = res.status
    throw err
  }

  return data
}
