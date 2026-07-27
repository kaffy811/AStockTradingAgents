const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

/**
 * Login API call — uses raw fetch (no auth token needed).
 * Accepts username OR email in the `username` field.
 *
 * @param {string} username  username or email
 * @param {string} password
 * @returns {Promise<{ access_token: string, refresh_token: string }>}
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

/**
 * Register a new user with an invite code.
 *
 * @param {string} username
 * @param {string} email
 * @param {string} password
 * @param {string} inviteCode
 * @returns {Promise<UserPublic>}
 */
export async function registerApi(username, email, password, inviteCode) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      email,
      password,
      invite_code: inviteCode,
    }),
  })

  const data = await res.json()

  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`)
  }

  return data
}

/**
 * Fetch current user info (requires valid access token).
 *
 * @param {string} accessToken
 * @returns {Promise<UserPublic>}  includes is_admin
 */
export async function meApi(accessToken) {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
  })

  const data = await res.json()

  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`)
  }

  return data
}
