import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { loginApi, registerApi, meApi } from '../api/auth.js'

export const useAuthStore = defineStore('auth', () => {
  const token        = ref(localStorage.getItem('ta_token')         || '')
  const refreshToken = ref(localStorage.getItem('ta_refresh_token') || '')
  const currentUser  = ref(localStorage.getItem('ta_user')          || '')
  const isAdmin      = ref(localStorage.getItem('ta_is_admin') === 'true')

  /** true when logout was triggered by a 401 (expired/invalid token) */
  const sessionExpired = ref(false)

  /** Synchronously resolved — token is read from localStorage at store init */
  const authReady = computed(() => true)

  const isAuthenticated = computed(() => !!token.value)

  /** Fetch /auth/me and populate isAdmin. Called after login. */
  async function fetchMe() {
    if (!token.value) return
    try {
      const user = await meApi(token.value)
      if (user.is_admin !== undefined) {
        isAdmin.value = !!user.is_admin
        localStorage.setItem('ta_is_admin', String(!!user.is_admin))
      }
      if (user.username) {
        currentUser.value = user.username
        localStorage.setItem('ta_user', user.username)
      }
    } catch {
      // non-fatal — isAdmin stays false
    }
  }

  /**
   * Login and persist tokens + username to localStorage.
   * Throws on failure — caller handles the error.
   */
  async function login(username, password) {
    const data = await loginApi(username, password)
    token.value        = data.access_token
    refreshToken.value = data.refresh_token || ''
    currentUser.value  = username
    sessionExpired.value = false
    localStorage.setItem('ta_token',         data.access_token)
    localStorage.setItem('ta_refresh_token', data.refresh_token || '')
    localStorage.setItem('ta_user',          username)
    await fetchMe()
  }

  /**
   * Register a new user with an invite code.
   * Throws on failure — caller handles the error.
   */
  async function register(username, email, password, inviteCode) {
    await registerApi(username, email, password, inviteCode)
  }

  /** Clear session state and localStorage.
   *  @param {{expired?: boolean}} [opts] — expired=true when caused by a 401. */
  function logout(opts = {}) {
    token.value        = ''
    refreshToken.value = ''
    currentUser.value  = ''
    isAdmin.value      = false
    sessionExpired.value = !!opts.expired
    localStorage.removeItem('ta_token')
    localStorage.removeItem('ta_refresh_token')
    localStorage.removeItem('ta_user')
    localStorage.removeItem('ta_is_admin')
  }

  return {
    token, refreshToken, currentUser, isAdmin,
    sessionExpired, authReady, isAuthenticated,
    login, register, fetchMe, logout,
  }
})
