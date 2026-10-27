import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '../stores/auth.js'
import { googleConfigApi, googleLoginApi } from '../api/auth.js'

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })
const json = (body) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })

it.each([() => googleConfigApi(), () => googleLoginApi('signed')])('explains network failures without exposing browser internals', async (call) => {
  fetch.mockRejectedValueOnce(new TypeError('Failed to fetch: private-network-details'))
  const error = await call().catch(e => e)
  expect(error.message).toBe('无法连接登录服务，请检查网络后重试。')
  expect(error.errorCode).toBe('AUTH_NETWORK_ERROR')
  expect(error.message).not.toContain('private-network-details')
})

it('posts only Google credential and uses the existing authenticated user profile', async () => {
  fetch.mockResolvedValueOnce(json({ access_token: 'access', refresh_token: 'refresh' }))
    .mockResolvedValueOnce(json({ id: 'existing-id', username: 'existing-owner', is_admin: true }))
  const store = useAuthStore()
  await store.loginGoogle('signed-credential')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ credential: 'signed-credential' })
  expect(store.currentUser).toBe('existing-owner')
  expect(store.isAdmin).toBe(true)
  expect(store.token).toBe('access')
  expect(store.refreshToken).toBe('refresh')
  expect(store.login).toBeUndefined()
  expect(store.register).toBeUndefined()
  expect(store.requestEmailVerification).toBeUndefined()
})

it('never grants admin from stale local storage after a new ordinary login', async () => {
  localStorage.setItem('ta_is_admin', 'true')
  fetch.mockResolvedValueOnce(json({ access_token: 'ordinary' }))
    .mockResolvedValueOnce(json({ username: 'ordinary-user', is_admin: false }))
  const store = useAuthStore()
  await store.loginGoogle('signed')
  expect(store.isAdmin).toBe(false)
  expect(localStorage.getItem('ta_is_admin')).toBe('false')
})

it('does not install a late session response after cancellation', async () => {
  const controller = new AbortController()
  fetch.mockImplementationOnce(async () => {
    controller.abort()
    return json({ access_token: 'late-token' })
  })
  const store = useAuthStore()
  await expect(store.loginGoogle('signed', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
  expect(store.token).toBe('')
  expect(localStorage.getItem('ta_token')).toBeNull()
})

it('refreshes the existing session and preserves Google sign-out behavior', async () => {
  localStorage.setItem('ta_refresh_token', 'old-refresh')
  fetch.mockResolvedValueOnce(json({ access_token: 'new-access', refresh_token: 'new-refresh' }))
    .mockResolvedValueOnce(json({ username: 'same-user', is_admin: false }))
  const disableAutoSelect = vi.fn()
  vi.stubGlobal('google', { accounts: { id: { disableAutoSelect } } })
  const store = useAuthStore()
  await store.refreshSession()
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ refresh_token: 'old-refresh' })
  expect(store.token).toBe('new-access')
  store.logout()
  expect(store.token).toBe('')
  expect(store.refreshToken).toBe('')
  expect(disableAutoSelect).toHaveBeenCalledOnce()
})
