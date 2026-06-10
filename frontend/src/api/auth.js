const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

/**
 * Login API call — uses raw fetch (no auth token needed).
 *
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{ access_token: string }>}
 */
export async function loginApi(username, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  const data = await res.json()

  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`)
  }

  return data
}
