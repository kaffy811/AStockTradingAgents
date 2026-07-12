import { useAuthStore } from '../stores/auth.js'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'
const API_ROOT = API_BASE.replace(/\/api\/v1\/?$/, '')

async function v2Fetch(path, options = {}) {
  const authStore = useAuthStore()
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }
  if (authStore.token) headers.Authorization = `Bearer ${authStore.token}`
  // Phase 6T-E: 支持 AbortSignal（股票快速切换时取消旧请求）
  const res = await fetch(`${API_ROOT}${path}`, { ...options, headers })
  const contentType = res.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await res.json() : { ok: false, error_code: 'RENDER_ERROR', message: await res.text() }
  if (!res.ok) {
    const err = new Error(data.message || data.detail || `HTTP ${res.status}`)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export function getCompanyV2FullDebug(market, symbol, options = {}) {
  const params = new URLSearchParams()
  if (options.include_raw) params.set('include_raw', 'true')
  if (options.providers) params.set('providers', options.providers)
  if (options.force_refresh) params.set('force_refresh', 'true')
  if (options.max_raw_chars) params.set('max_raw_chars', String(options.max_raw_chars))
  if (options.history) params.set('history', 'true')
  if (options.period) params.set('period', options.period)
  if (options.start_year) params.set('start_year', String(options.start_year))
  if (options.end_year) params.set('end_year', String(options.end_year))
  // Phase 6T-E: profile=page（轻量生产展示）| debug（完整诊断）
  if (options.profile) params.set('profile', options.profile)
  const qs = params.toString()
  return v2Fetch(`/api/v2/company/${market}/${symbol}/debug/full${qs ? '?' + qs : ''}`, { signal: options.signal })
}

export function refreshCompanyV2Debug(market, symbol) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/debug/refresh`, { method: 'POST' })
}

export function getCompanyV2Reports(market, symbol, options = {}) {
  const params = new URLSearchParams()
  if (options.start_year) params.set('start_year', String(options.start_year))
  if (options.end_year) params.set('end_year', String(options.end_year))
  const qs = params.toString()
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports${qs ? '?' + qs : ''}`)
}

export function discoverCompanyV2Reports(market, symbol, options = {}) {
  const params = new URLSearchParams()
  if (options.start_year) params.set('start_year', String(options.start_year))
  if (options.end_year) params.set('end_year', String(options.end_year))
  if (options.force_refresh) params.set('force_refresh', 'true')
  const qs = params.toString()
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/discover${qs ? '?' + qs : ''}`, { method: 'POST' })
}

export function addManualReport(market, symbol, body) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/manual`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function downloadCompanyV2Report(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/download`, { method: 'POST' })
}

export function parseCompanyV2Report(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/parse`, { method: 'POST' })
}

export function verifyCompanyV2Report(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/verify`, { method: 'POST' })
}

export function aiVerifyCompanyV2Report(market, symbol, reportId, options = {}) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/ai-verify`, {
    method: 'POST',
    body: JSON.stringify(options),
  })
}

export function getCompanyV2ReportVerification(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/verification`)
}

export function indexCompanyV2ReportRag(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/rag/index`, { method: 'POST' })
}

export function listCompanyV2ReportRagIndexes(market, symbol) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/rag/indexes`)
}

export function refreshCompanyV2ReportRagIndex(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/rag/refresh`, { method: 'POST' })
}

export function deleteCompanyV2ReportRagIndex(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/rag/index`, { method: 'DELETE' })
}

export function getCompanyV2ReportRagJob(market, symbol, reportId, jobId) {
  const qs = jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/rag/job${qs}`)
}

export function getCompanyV2ReportRagStatus(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/rag/status`)
}

export function queryCompanyV2ReportRag(market, symbol, reportId, body) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/rag/query`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function compareCompanyV2ReportRag(market, symbol, body) {
  const { report_ids, ...rest } = body || {}
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/rag/compare`, {
    method: 'POST',
    body: JSON.stringify({ report_ids, ...rest }),
  })
}

export function runCompanyV2FinancialFusion(market, symbol, reportId, body = {}) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/financial-fusion/run`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function createCompanyV2FinancialFusionJob(market, symbol, body = {}) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/financial-fusion/jobs`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getCompanyV2FinancialFusionJob(market, symbol, jobId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/financial-fusion/jobs/${encodeURIComponent(jobId)}`)
}

export function getCompanyV2FinancialFusionJobResult(market, symbol, jobId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/financial-fusion/jobs/${encodeURIComponent(jobId)}/result`)
}

export function cancelCompanyV2FinancialFusionJob(market, symbol, jobId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/financial-fusion/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' })
}

export function getCompanyV2FinancialFusion(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/financial-fusion`)
}

export function getCompanyV2FinancialFusionField(market, symbol, reportId, fieldName) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/financial-fusion/${fieldName}`)
}

export function getCompanyV2FinancialFusionEligibility(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/financial-fusion/eligibility`)
}

export function getCompanyV2FinancialFusionHealth(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/financial-fusion/health`)
}

export function getCompanyV2FinancialFusionReadiness(market, symbol) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/financial-fusion/readiness`)
}

export function getCompanyV2FinancialFusionPrepareStatus(market, symbol, reportId) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/prepare-status`)
}

export function prepareCompanyV2FinancialFusionStep(market, symbol, reportId, step) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/reports/${reportId}/prepare-step`, {
    method: 'POST',
    body: JSON.stringify({ step }),
  })
}

// ── Phase 6T-B: Full-History Financial Dashboard ──────────────────────────

/**
 * 获取股票全历史财务仪表盘（上市以来全量数据）
 * @param {string} market
 * @param {string} symbol
 * @param {object} options - { period: 'annual'|'quarterly'|'all', start_year, end_year, force_refresh }
 */
export function getCompanyV2History(market, symbol, options = {}) {
  const params = new URLSearchParams()
  if (options.period) params.set('period', options.period)
  if (options.start_year) params.set('start_year', String(options.start_year))
  if (options.end_year) params.set('end_year', String(options.end_year))
  if (options.force_refresh) params.set('force_refresh', 'true')
  const qs = params.toString()
  return v2Fetch(`/api/v2/company/${market}/${symbol}/history${qs ? '?' + qs : ''}`, { signal: options.signal })
}

/**
 * 获取单个财务模块的全历史数据
 */
export function getCompanyV2ModuleHistory(market, symbol, moduleKey, options = {}) {
  const params = new URLSearchParams()
  if (options.period) params.set('period', options.period)
  if (options.start_year) params.set('start_year', String(options.start_year))
  if (options.end_year) params.set('end_year', String(options.end_year))
  const qs = params.toString()
  return v2Fetch(`/api/v2/company/${market}/${symbol}/history/module/${moduleKey}${qs ? '?' + qs : ''}`)
}

/**
 * 获取股票/公司基本信息
 */
export function getCompanyV2StockBasic(market, symbol) {
  return v2Fetch(`/api/v2/company/${market}/${symbol}/stock_basic`)
}
