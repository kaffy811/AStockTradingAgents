/**
 * src/api/fundamentals.js — Fundamentals API client
 * Supports mock mode: VITE_USE_MOCK=true reads from frontend/mock/fundamentals/
 */

import { baseFetch } from './http.js'
import { cachedRequest, buildKey, clearFundamentalsCache } from '../utils/requestCache.js'

export { clearFundamentalsCache }

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

// Vite glob import for mock data (only bundled when needed)
const _mockFiles = import.meta.glob('../../mock/fundamentals/*.json', { eager: true })

function _getMock(filename) {
  const key = `../../mock/fundamentals/${filename}.json`
  const mod = _mockFiles[key]
  return mod ? (mod.default ?? mod) : null
}

/**
 * Normalize any fetch/API error into a safe frontend shape.
 * Never throws — always returns an object.
 * @param {unknown} error
 * @returns {{ type: string, message: string, status: number|null }}
 */
export function normalizeFundamentalError(error) {
  if (!error) return { type: 'unknown', message: '未知错误', status: null }

  // Network error (fetch failed entirely)
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return { type: 'network', message: '网络请求失败，请检查网络连接或后端服务是否启动', status: null }
  }

  // HTTP error with status
  const status = error?.status ?? error?.statusCode ?? null
  if (status === 404) return { type: 'not_found', message: '模块不存在（404）', status: 404 }
  if (status === 503) return { type: 'unavailable', message: '数据源暂不可用（TUSHARE_TOKEN 未配置或配额不足）', status: 503 }
  if (status >= 500) return { type: 'server_error', message: `后端错误（${status}），请查看后端日志`, status }
  if (status === 401 || status === 403) return { type: 'auth', message: '认证失败，请重新登录', status }

  // Malformed envelope
  if (error?.type === 'malformed') return { type: 'malformed', message: '响应格式异常', status: null }

  const msg = error?.message || error?.detail || String(error) || '未知错误'
  return { type: 'error', message: msg, status }
}

/**
 * Validate that a response is a valid DataEnvelope.
 * Returns normalized error if invalid, null if valid.
 */
function _validateEnvelope(data) {
  if (!data || typeof data !== 'object') return { type: 'malformed', message: '响应格式异常' }
  return null
}

/**
 * GET /api/v1/modules → list of module descriptors
 */
export async function getFundamentalModules() {
  if (USE_MOCK) {
    return _getMock('modules') || []
  }
  try {
    return await baseFetch('/modules')
  } catch (e) {
    console.warn('[fundamentals] getFundamentalModules error:', e)
    return []
  }
}

/**
 * GET /api/v1/stock/{code}/overview → { snapshot: envelope, financial_summary: envelope }
 */
export async function getFundamentalOverview(code) {
  if (USE_MOCK) {
    return {
      snapshot: _getMock('snapshot'),
      financial_summary: _getMock('financial_summary'),
    }
  }
  try {
    const data = await baseFetch(`/stock/${code}/overview`)
    const err = _validateEnvelope(data)
    if (err) throw err
    return data
  } catch (e) {
    throw normalizeFundamentalError(e)
  }
}

/**
 * GET /api/v1/stock/{code}/modules/{moduleKey} → DataEnvelope
 * @param {string} code - stock code
 * @param {string} moduleKey - module key
 * @param {Object} options - optional { period, limit, mode, force_refresh }
 */
export async function getFundamentalModule(code, moduleKey, options = {}) {
  if (USE_MOCK) {
    return _getMock(moduleKey) || null
  }
  const { period, limit, mode, force_refresh = false } = options
  const cacheParams = {}
  if (period) cacheParams.period = period
  if (limit)  cacheParams.limit  = String(limit)
  if (mode)   cacheParams.mode   = mode
  const key = buildKey(`/api/v1/stock/${code}/modules/${moduleKey}`, cacheParams)
  return cachedRequest(key, () => _fetchModule(code, moduleKey, options), { forceRefresh: force_refresh })
}

/**
 * GET /api/v1/stock/{code}/fundamentals/diagnostics
 * Returns module data availability diagnostics for free mode visibility decisions.
 * Never throws — returns null on error.
 */
export async function getFundamentalDiagnostics(code) {
  if (USE_MOCK) {
    // Mock: all ALWAYS_SHOW visible, others hidden
    return {
      visibility: {
        overview: true, 'highlight-risk': true, 'ai-analysis': true,
        'report-documents': true, valuation: false, dividend: false,
        'main-business': false, industry: false, growth: false,
        profitability: false, 'earnings-quality': false, 'asset-structure': false,
        solvency: false, capital: false, operations: false, dupont: false,
        shareholders: false,
      },
      unavailable_sections: [
        'valuation', 'dividend', 'main-business', 'industry', 'growth',
        'profitability', 'earnings-quality', 'asset-structure', 'solvency',
        'capital', 'operations', 'dupont', 'shareholders',
      ],
      modules: [],
      summary: { ok: 0, partial: 0, empty: 13, failed: 0 },
    }
  }
  try {
    return await baseFetch(`/stock/${code}/fundamentals/diagnostics`)
  } catch (e) {
    console.warn('[fundamentals] diagnostics error:', e)
    return null
  }
}

/** Private: actual network fetch for a module. */
async function _fetchModule(code, moduleKey, options = {}) {
  const { period, limit, mode, force_refresh = false } = options
  const params = new URLSearchParams()
  if (period) params.set('period', period)
  if (limit)  params.set('limit',  String(limit))
  if (mode)   params.set('mode',   mode)
  if (force_refresh) params.set('force_refresh', 'true')
  const qs = params.toString()
  const url = `/stock/${code}/modules/${moduleKey}${qs ? '?' + qs : ''}`
  try {
    const data = await baseFetch(url)
    const err = _validateEnvelope(data)
    if (err) throw err
    return data
  } catch (e) {
    throw normalizeFundamentalError(e)
  }
}
