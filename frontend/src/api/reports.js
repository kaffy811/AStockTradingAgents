import { baseFetch } from './http.js'

/**
 * Save a comprehensive analysis result as a report.
 * Maps frontend result structure → backend API fields.
 */
export async function createReport(result) {
  return baseFetch('/reports/', {
    method: 'POST',
    body: JSON.stringify({
      market:          result.market,
      symbol:          result.symbol,
      report_type:     'comprehensive',
      stock_name:      result.stock_name || null,
      auto_saved:      result.auto_saved ?? false,
      analysis_scope:  result.analysis_scope || result.metadata?.analysis_scope || 'comprehensive',
      output_language: result.output_language || result.metadata?.output_language || 'zh-CN',
      report_md:       result.report,
      sections:        result.sections,
      report_metadata: result.metadata,
      warnings:        result.metadata?.warnings  || [],
      agents:          result.metadata?.agents    || {},
    }),
  })
}

/**
 * List the current user's historical reports.
 * @param {{ market?: string, symbol?: string, analysis_scope?: string, auto_saved?: boolean,
 *           start_date?: string, end_date?: string, limit?: number, offset?: number }} params
 */
export async function listReports({
  market, symbol, analysis_scope, auto_saved,
  start_date, end_date,
  limit = 20, offset = 0,
} = {}) {
  const q = new URLSearchParams({ limit, offset })
  if (market)         q.set('market', market)
  if (symbol)         q.set('symbol', symbol)
  if (analysis_scope) q.set('analysis_scope', analysis_scope)
  if (auto_saved != null) q.set('auto_saved', String(auto_saved))
  if (start_date)     q.set('start_date', start_date)
  if (end_date)       q.set('end_date', end_date)
  return baseFetch(`/reports/?${q}`)
}

/**
 * Fetch a single report detail and remap to the same structure as getComprehensive().
 * Callers can feed the returned object directly into AgentStatusBar / MarkdownReport etc.
 */
export async function getReport(reportId) {
  const data = await baseFetch(`/reports/${reportId}`)
  return {
    id:              data.id,
    market:          data.market,
    symbol:          data.symbol,
    stock_name:      data.stock_name || null,
    auto_saved:      data.auto_saved ?? false,
    analysis_scope:  data.analysis_scope || 'comprehensive',
    output_language: data.output_language || 'zh-CN',
    report:          data.report_md,          // ← remap
    sections:        data.sections,
    metadata:        data.report_metadata,    // ← remap
    warnings:        data.warnings,
    agents:          data.agents,
    created_at:      data.created_at,
    updated_at:      data.updated_at,
  }
}

/**
 * Delete a report. Returns null (204 No Content).
 */
export async function deleteReport(reportId) {
  return baseFetch(`/reports/${reportId}`, { method: 'DELETE' })
}
