import { createApp, nextTick } from 'vue'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import LoginView from '../views/LoginView.vue'
import { googleConfigApi } from '../api/auth.js'

const mocks = vi.hoisted(() => ({
  store: { sessionExpired: false, loginGoogle: vi.fn() },
  router: { replace: vi.fn() },
  load: vi.fn(),
}))
vi.mock('../stores/auth.js', () => ({ useAuthStore: () => mocks.store }))
vi.mock('vue-router', () => ({ useRouter: () => mocks.router }))
vi.mock('../api/auth.js', () => ({ googleConfigApi: vi.fn() }))
vi.mock('../utils/googleIdentity.js', () => ({ loadGoogleIdentity: () => mocks.load() }))

let callback, click, app, el, gis
async function flush() {
  for (let n = 0; n < 8; n++) await Promise.resolve()
  await nextTick()
}
async function mount() {
  el = document.createElement('div')
  document.body.appendChild(el)
  app = createApp(LoginView)
  app.mount(el)
  await flush()
}
function button(label) { return [...el.querySelectorAll('button')].find(b => b.textContent.includes(label)) }

beforeEach(() => {
  vi.clearAllMocks()
  mocks.store.sessionExpired = false
  mocks.store.loginGoogle.mockResolvedValue(undefined)
  mocks.load.mockResolvedValue(undefined)
  googleConfigApi.mockResolvedValue({ enabled: true, client_id: 'test-client', nonce: 'new-nonce' })
  gis = {
    initialize: vi.fn(config => { callback = config.callback }),
    renderButton: vi.fn((target, options) => {
      click = options.click_listener
      const b = document.createElement('button')
      b.textContent = '使用 Google 登录'
      b.addEventListener('click', click)
      target.appendChild(b)
    }),
    cancel: vi.fn(),
  }
  vi.stubGlobal('google', { accounts: { id: gis } })
})
afterEach(() => {
  app?.unmount()
  app = null
  el?.remove()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('Google-only login', () => {
  it('has a Google button and no password, invite, or registration inputs/links', async () => {
    await mount()
    expect(button('Google 登录')).toBeTruthy()
    expect(el.querySelector('input')).toBeNull()
    expect(el.querySelector('form')).toBeNull()
    expect(el.querySelector('a[href="/register"]')).toBeNull()
    expect(el.textContent).toContain('首次登录将自动创建普通账户')
    expect(gis.initialize).toHaveBeenCalledWith(expect.objectContaining({ nonce: 'new-nonce', auto_select: false }))
  })

  it('shows loading and allows stopping a pending configuration request', async () => {
    googleConfigApi.mockReturnValue(new Promise(() => {}))
    await mount()
    expect(el.textContent).toContain('正在加载 Google 登录')
    button('停止等待').click()
    await flush()
    expect(el.textContent).toContain('已停止等待')
    expect(button('重新尝试 Google 登录')).toBeTruthy()
  })

  it('shows Google configuration failure without offering another auth method', async () => {
    googleConfigApi.mockResolvedValue({ enabled: false })
    await mount()
    expect(el.textContent).toContain('Google 登录暂未配置')
    expect(gis.renderButton).not.toHaveBeenCalled()
    expect(button('重新尝试 Google 登录')).toBeTruthy()
  })

  it('handles script load failure and explicitly retries with a fresh nonce', async () => {
    mocks.load.mockRejectedValueOnce(new Error('无法加载 Google 登录，请检查网络后重试。'))
    await mount()
    expect(el.textContent).toContain('无法加载 Google 登录')
    googleConfigApi.mockResolvedValueOnce({ enabled: true, client_id: 'test-client', nonce: 'retry-nonce' })
    button('重新尝试 Google 登录').click()
    await flush()
    expect(gis.initialize).toHaveBeenLastCalledWith(expect.objectContaining({ nonce: 'retry-nonce' }))
  })

  it('signs in without invite/password fields and navigates on success', async () => {
    await mount()
    button('使用 Google 登录').click()
    await flush()
    expect(el.textContent).toContain('若已关闭窗口，可停止等待后重试')
    await callback({ credential: 'signed-token' })
    expect(mocks.store.loginGoogle).toHaveBeenCalledWith('signed-token', { signal: expect.any(AbortSignal) })
    expect(mocks.router.replace).toHaveBeenCalledWith('/')
  })

  it('shows migration/failure message and retries without reusing a consumed session', async () => {
    mocks.store.loginGoogle.mockRejectedValueOnce(new Error('请联系管理员核实身份并办理账户迁移。'))
    await mount()
    await callback({ credential: 'signed-token' })
    await flush()
    expect(el.textContent).toContain('联系管理员')
    expect(mocks.router.replace).not.toHaveBeenCalled()
    button('重新尝试 Google 登录').click()
    await flush()
    expect(googleConfigApi).toHaveBeenCalledTimes(2)
  })

  it('ignores a popup credential delivered after the user stops waiting', async () => {
    await mount()
    const stale = callback
    button('使用 Google 登录').click()
    await flush()
    button('停止等待').click()
    await flush()
    await stale({ credential: 'late-token' })
    expect(mocks.store.loginGoogle).not.toHaveBeenCalled()
    expect(mocks.router.replace).not.toHaveBeenCalled()
  })

  it('aborts a slow login HTTP response with an understandable retry message', async () => {
    vi.useFakeTimers()
    mocks.store.loginGoogle.mockImplementation((_credential, { signal }) => new Promise((resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    }))
    await mount()
    const work = callback({ credential: 'signed-token' })
    await flush()
    expect(el.textContent).toContain('正在验证身份')
    await vi.advanceTimersByTimeAsync(15000)
    await work
    await flush()
    expect(el.textContent).toContain('登录响应等待超时')
    expect(mocks.router.replace).not.toHaveBeenCalled()
  })

  it('ignores callbacks after unmount and keeps the session-expired explanation', async () => {
    mocks.store.sessionExpired = true
    await mount()
    expect(el.textContent).toContain('登录已过期')
    const stale = callback
    app.unmount()
    app = null
    await stale({ credential: 'late-token' })
    expect(mocks.store.loginGoogle).not.toHaveBeenCalled()
  })
})
