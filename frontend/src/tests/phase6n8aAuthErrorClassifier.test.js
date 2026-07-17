/**
 * phase6n8aAuthErrorClassifier.test.js — Phase 6N-8A
 *
 * Covers:
 *   A. apiErrorClassifier 分类
 *   B. 401 绝不归因为 BaoStock/AkShare provider 失败
 *   C. requestCache 不缓存错误、走同一 fetcher（API client）
 *   D. baseFetch 附带 Authorization header；401 触发 logout(expired)
 *   E. DataSourceBanner / LoginCard 源码契约（auth 文案存在、auth 抑制 provider 文案）
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  classifyApiError,
  isAuthError,
  AUTH_REQUIRED_MESSAGE,
  PROVIDER_EMPTY_MESSAGE,
  PARTIAL_DATA_MESSAGE,
} from '../utils/apiErrorClassifier.js'
import { cachedRequest, clearAllCache } from '../utils/requestCache.js'

// ── A. 分类 ───────────────────────────────────────────────────────────────────

describe('classifyApiError', () => {
  it('401 → auth_required', () => {
    const r = classifyApiError({ status: 401, message: 'Unauthorized' })
    expect(r.category).toBe('auth_required')
    expect(r.message).toBe(AUTH_REQUIRED_MESSAGE)
  })

  it('error_code=AUTH_REQUIRED → auth_required（无 status 也可识别）', () => {
    expect(classifyApiError({ errorCode: 'AUTH_REQUIRED' }).category).toBe('auth_required')
    expect(classifyApiError({ error_code: 'AUTH_REQUIRED' }).category).toBe('auth_required')
  })

  it('403 → forbidden', () => {
    expect(classifyApiError({ status: 403 }).category).toBe('forbidden')
  })

  it('429 → rate_limited', () => {
    expect(classifyApiError({ status: 429 }).category).toBe('rate_limited')
  })

  it('5xx → server_error', () => {
    expect(classifyApiError({ status: 500 }).category).toBe('server_error')
    expect(classifyApiError({ status: 503 }).category).toBe('server_error')
  })

  it('DATA_SOURCE_UNAVAILABLE → provider_unavailable', () => {
    const r = classifyApiError({ errorCode: 'DATA_SOURCE_UNAVAILABLE' })
    expect(r.category).toBe('provider_unavailable')
  })

  it('DATA_SOURCE_EMPTY → provider_empty，文案为免费数据源提示', () => {
    const r = classifyApiError({ errorCode: 'DATA_SOURCE_EMPTY' })
    expect(r.category).toBe('provider_empty')
    expect(r.message).toBe(PROVIDER_EMPTY_MESSAGE)
  })

  it('失败 envelope（ok=false 网络类 reason）→ provider_unavailable', () => {
    const r = classifyApiError({ ok: false, reason: 'AkShare timeout after 20s' })
    expect(r.category).toBe('provider_unavailable')
  })

  it('失败 envelope（ok=false 空数据 reason）→ provider_empty', () => {
    const r = classifyApiError({ ok: false, reason: 'income 和 fina_indicator 均无数据' })
    expect(r.category).toBe('provider_empty')
  })

  it('partial=true → partial_data', () => {
    const r = classifyApiError({ partial: true })
    expect(r.category).toBe('partial_data')
    expect(r.message).toBe(PARTIAL_DATA_MESSAGE)
  })

  it('fetch 网络失败（TypeError）→ provider_unavailable', () => {
    const r = classifyApiError(new TypeError('Failed to fetch'))
    expect(r.category).toBe('provider_unavailable')
  })

  it('无法识别 → unknown_error', () => {
    expect(classifyApiError({ weird: true }).category).toBe('unknown_error')
  })
})

// ── B. 401 不得归因为 provider 失败 ──────────────────────────────────────────

describe('401 never misclassified as provider failure', () => {
  it('401 且 envelope 同时带 reason，仍归类为 auth_required', () => {
    const r = classifyApiError({ status: 401, ok: false, reason: 'BaoStock 未返回数据' })
    expect(r.category).toBe('auth_required')
  })

  it('auth_required 文案不包含 BaoStock/AkShare', () => {
    const r = classifyApiError({ status: 401 })
    expect(r.message).not.toMatch(/BaoStock|AkShare|数据源/)
    expect(r.message).toMatch(/登录/)
  })

  it('isAuthError 识别 401 / AUTH_REQUIRED / 登录已过期 message / type=auth', () => {
    expect(isAuthError({ status: 401 })).toBe(true)
    expect(isAuthError({ errorCode: 'AUTH_REQUIRED' })).toBe(true)
    expect(isAuthError(new Error('登录已过期，请重新登录'))).toBe(true)
    expect(isAuthError({ type: 'auth', status: 403 })).toBe(true)
    expect(isAuthError({ status: 503 })).toBe(false)
    expect(isAuthError({ ok: false, reason: 'BaoStock 均未返回数据' })).toBe(false)
  })
})

// ── C. requestCache 行为 ─────────────────────────────────────────────────────

describe('requestCache (Phase 6N-8A contract)', () => {
  beforeEach(() => clearAllCache())

  it('错误（含 401）不进缓存 — 第二次调用重新执行 fetcher', async () => {
    let calls = 0
    const fetcher = () => {
      calls += 1
      const err = new Error('登录已过期，请重新登录')
      err.status = 401
      return Promise.reject(err)
    }
    await expect(cachedRequest('k1', fetcher)).rejects.toMatchObject({ status: 401 })
    await expect(cachedRequest('k1', fetcher)).rejects.toMatchObject({ status: 401 })
    expect(calls).toBe(2)   // not cached
  })

  it('成功结果缓存 — 第二次调用不再执行 fetcher（cache-first 保持）', async () => {
    let calls = 0
    const fetcher = () => { calls += 1; return Promise.resolve({ ok: true }) }
    await cachedRequest('k2', fetcher)
    await cachedRequest('k2', fetcher)
    expect(calls).toBe(1)
  })
})

// ── D. baseFetch：Authorization header + 401 → logout(expired) ────────────────

describe('baseFetch auth propagation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('已登录时请求带 Authorization: Bearer <token>', async () => {
    localStorage.setItem('ta_token', 'tok-123')
    const { baseFetch } = await import('../api/http.js')
    let captured = null
    vi.stubGlobal('fetch', vi.fn(async (url, opts) => {
      captured = opts.headers
      return new Response(JSON.stringify({ ok: true }), { status: 200 })
    }))
    await baseFetch('/stocks/CN/601686/quote')
    expect(captured['Authorization']).toBe('Bearer tok-123')
    vi.unstubAllGlobals()
  })

  it('401 → authStore.logout(expired) + 抛出 AUTH_REQUIRED 错误', async () => {
    localStorage.setItem('ta_token', 'expired-tok')
    const { baseFetch } = await import('../api/http.js')
    const { useAuthStore } = await import('../stores/auth.js')
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'Invalid or expired token', error_code: 'AUTH_REQUIRED' }), { status: 401 })
    ))
    const store = useAuthStore()
    let thrown = null
    try { await baseFetch('/watchlist/') } catch (e) { thrown = e }
    expect(thrown.status).toBe(401)
    expect(thrown.errorCode).toBe('AUTH_REQUIRED')
    expect(store.token).toBe('')
    expect(store.sessionExpired).toBe(true)
    vi.unstubAllGlobals()
  })

  it('非 401 错误透传后端 error_code（如 DATA_SOURCE_EMPTY）', async () => {
    const { baseFetch } = await import('../api/http.js')
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'no data', error_code: 'DATA_SOURCE_EMPTY' }), { status: 502 })
    ))
    let thrown = null
    try { await baseFetch('/stock/601686/modules/growth') } catch (e) { thrown = e }
    expect(thrown.errorCode).toBe('DATA_SOURCE_EMPTY')
    expect(classifyApiError(thrown).category).not.toBe('auth_required')
    vi.unstubAllGlobals()
  })

  it('503 AUTH_DATABASE_UNAVAILABLE 不清除登录状态，提示可重试', async () => {
    localStorage.setItem('ta_token', 'tok-keep')
    const { baseFetch } = await import('../api/http.js')
    const { useAuthStore } = await import('../stores/auth.js')
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({
        detail: {
          status: 'failed',
          error_code: 'AUTH_DATABASE_UNAVAILABLE',
          message: '服务暂时无法验证账户状态，请稍后重试。',
        },
      }), { status: 503, headers: { 'Retry-After': '3' } })
    ))
    const store = useAuthStore()
    let thrown = null
    try { await baseFetch('/chat/sessions') } catch (e) { thrown = e }
    expect(thrown.status).toBe(503)
    expect(thrown.errorCode).toBe('AUTH_DATABASE_UNAVAILABLE')
    expect(store.token).toBe('tok-keep')
    expect(store.sessionExpired).toBe(false)
    vi.unstubAllGlobals()
  })
})

// ── E. 组件源码契约（无 @vue/test-utils，用 ?raw 校验关键逻辑存在）────────────

import dataSourceBannerRaw from '../components/fundamentals/DataSourceBanner.vue?raw'
import loginCardRaw from '../components/LoginCard.vue?raw'
import stockDetailRaw from '../views/StockDetailView.vue?raw'

describe('component source contracts', () => {
  it('DataSourceBanner：auth_required 类型存在且返回登录文案', () => {
    expect(dataSourceBannerRaw).toMatch(/auth_required/)
    expect(dataSourceBannerRaw).toMatch(/登录已过期，请重新登录后查看行情、新闻和财报数据。/)
  })

  it('DataSourceBanner：auth 错误抑制 provider 类型（return 早退）', () => {
    expect(dataSourceBannerRaw).toMatch(/if \(hasAuthError\.value\) return \['auth_required'\]/)
  })

  it('DataSourceBanner：auth 错误不展示 provider 错误详情列表', () => {
    expect(dataSourceBannerRaw).toMatch(/sanitizedErrors\.length && !hasAuthError/)
  })

  it('LoginCard：sessionExpired 时显示登录过期提示', () => {
    expect(loginCardRaw).toMatch(/sessionExpired/)
    expect(loginCardRaw).toMatch(/登录已过期，请重新登录后查看行情、新闻和财报数据。/)
  })

  it('StockDetailView：未登录跳过受保护请求批次 + 登录后自动重试', () => {
    expect(stockDetailRaw).toMatch(/if \(!authStore\.token\) return/)
    expect(stockDetailRaw).toMatch(/authStore\.token,\s*\n\s*\(t, old\) => \{\s*\n\s*if \(t && !old\) loadAll\(\)/)
  })
})
