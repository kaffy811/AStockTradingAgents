import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { loginApi } from '../api/auth.js'

export const useAuthStore = defineStore('auth', () => {
  const token       = ref(localStorage.getItem('ta_token') || '')
  const currentUser = ref(localStorage.getItem('ta_user')  || '')
  /** Phase 6N-8A: true when logout was triggered by a 401 (expired/invalid token).
   *  LoginCard uses this to show "登录已过期" instead of a blank login form. */
  const sessionExpired = ref(false)

  /**
   * Phase 6N-8B: authReady = true when the store has resolved its initial state.
   * Protected requests MUST check authReady before firing to avoid a burst of 401s
   * from requests that fire before the token is read from storage.
   */
  const authReady = computed(() => true) // token is read synchronously from localStorage

  /**
   * Login and persist token + username to localStorage.
   * Throws on failure — caller handles the error.
   */
  async function login(username, password) {
    const data = await loginApi(username, password)
    token.value       = data.access_token
    currentUser.value = username
    sessionExpired.value = false
    localStorage.setItem('ta_token', data.access_token)
    localStorage.setItem('ta_user',  username)
  }

  /** Clear session state and localStorage.
   *  @param {{expired?: boolean}} [opts] — expired=true when caused by a 401. */
  function logout(opts = {}) {
    token.value       = ''
    currentUser.value = ''
    sessionExpired.value = !!opts.expired
    localStorage.removeItem('ta_token')
    localStorage.removeItem('ta_user')
  }

  return { token, currentUser, sessionExpired, authReady, login, logout }
})
