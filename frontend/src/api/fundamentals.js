/**
 * src/api/fundamentals.js — Fundamentals API client
 * Supports mock mode: VITE_USE_MOCK=true reads from frontend/mock/fundamentals/
 */

import { baseFetch } from './http.js'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

// Vite glob import for mock data (only bundled when needed)
const _mockFiles = import.meta.glob('../../mock/fundamentals/*.json', { eager: true })

function _getMock(filename) {
  const key = `../../mock/fundamentals/${filename}.json`
  const mod = _mockFiles[key]
  return mod ? (mod.default ?? mod) : null
}

/**
 * GET /api/v1/modules → list of module descriptors
 */
export async function getFundamentalModules() {
  if (USE_MOCK) {
    return _getMock('modules') || []
  }
  return baseFetch('/modules')
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
  return baseFetch(`/stock/${code}/overview`)
}

/**
 * GET /api/v1/stock/{code}/modules/{moduleKey} → DataEnvelope
 * @param {string} code - stock code
 * @param {string} moduleKey - module key
 * @param {Object} options - optional { period, limit }
 */
export async function getFundamentalModule(code, moduleKey, options = {}) {
  if (USE_MOCK) {
    return _getMock(moduleKey) || null
  }
  const params = new URLSearchParams()
  if (options.period) params.set('period', options.period)
  if (options.limit)  params.set('limit',  String(options.limit))
  const qs = params.toString()
  const url = `/stock/${code}/modules/${moduleKey}${qs ? '?' + qs : ''}`
  return baseFetch(url)
}
