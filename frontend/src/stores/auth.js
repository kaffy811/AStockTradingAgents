import { defineStore } from 'pinia'
import { ref } from 'vue'
import { loginApi } from '../api/auth.js'

export const useAuthStore = defineStore('auth', () => {
  const token       = ref(localStorage.getItem('ta_token') || '')
  const currentUser = ref(localStorage.getItem('ta_user')  || '')

  /**
   * Login and persist token + username to localStorage.
   * Throws on failure — caller handles the error.
   */
  async function login(username, password) {
    const data = await loginApi(username, password)
    token.value       = data.access_token
    currentUser.value = username
    localStorage.setItem('ta_token', data.access_token)
    localStorage.setItem('ta_user',  username)
  }

  /** Clear session state and localStorage. */
  function logout() {
    token.value       = ''
    currentUser.value = ''
    localStorage.removeItem('ta_token')
    localStorage.removeItem('ta_user')
  }

  return { token, currentUser, login, logout }
})
