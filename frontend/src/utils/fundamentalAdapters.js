/**
 * src/utils/fundamentalAdapters.js
 * Converts DataEnvelope.data → normalized chart/table view models.
 *
 * Return shape:
 * {
 *   metrics: [{label, value, unit, raw}],   // for metric_cards
 *   xAxis:   [string],                       // chart x-axis labels
 *   series:  [{name, data, type}],           // chart series
 *   rows:    [object],                       // table rows
 *   columns: [string],                       // table column keys
 *   insight: string | null,                  // comment/summary text
 * }
 */

/**
 * Phase 6N-8B: Check if any row contains at least one valid core field value.
 *
 * Rules:
 *   - null / undefined / "" / "—" / NaN → empty
 *   - 0 is VALID
 *   - At least one row must have at least one valid core field to return true
 *
 * @param {Array<object>} rows
 * @param {string[]} [coreFields] — if omitted, checks all non-meta fields
 * @returns {boolean}
 */
export function hasDisplayableData(rows, coreFields) {
  if (!Array.isArray(rows) || rows.length === 0) return false
  const checkFields = Array.isArray(coreFields) && coreFields.length > 0
    ? coreFields
    : null
  const EMPTY_VALUES = new Set([null, undefined, '', '—', NaN])
  for (const row of rows) {
    const keys = checkFields || Object.keys(row).filter(k => !k.startsWith('_') &&
      k !== 'source' && k !== 'ts_code' && k !== 'symbol' && k !== 'end_date' &&
      k !== 'trade_date' && k !== 'ann_date')
    for (const k of keys) {
      const v = row[k]
      // 0 is valid; NaN check via Number comparison
      if (!EMPTY_VALUES.has(v) && !(typeof v === 'number' && isNaN(v))) return true
    }
  }
  return false
}

// null/NaN safe float
function sf(v) {
  if (v === null || v === undefined || v === '' || !Number.isFinite(Number(v))) return null
  return Number(v)
}

// Format value with unit hint
export function fmtVal(v, field, unitHints = {}) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const unit = unitHints[field] || ''
  if (unit === '%') return n.toFixed(2) + '%'
  if (unit === '元' || unit === '万元') {
    if (Math.abs(n) >= 100000000) return (n / 100000000).toFixed(2) + '亿'
    if (Math.abs(n) >= 10000) return (n / 10000).toFixed(2) + '万'
    return n.toFixed(2)
  }
  if (unit === '倍' || unit === '次/年') return n.toFixed(2) + (unit ? ' ' + unit : '')
  if (unit === '天') return Math.round(n) + ' 天'
  if (unit === '万股' || unit === '万元') return n.toFixed(2) + ' ' + unit
  if (/pct$|_ratio_pct$|_yoy$|margin$|percentile$/.test(field)) return n.toFixed(2) + '%'
  if (Math.abs(n) >= 100000000) return (n / 100000000).toFixed(2) + '亿'
  if (Math.abs(n) >= 10000 && unit === '') return (n / 10000).toFixed(2) + '万'
  return n.toFixed(2)
}

// Generic series extractor
function extractSeries(data) {
  if (Array.isArray(data?.series)) return data.series
  if (Array.isArray(data?.records)) return data.records
  if (Array.isArray(data?.rankings)) return data.rankings
  if (Array.isArray(data?.holder_num_series)) return data.holder_num_series
  return []
}

// Generic adapter (fallback for any module)
function genericAdapter(data, moduleMeta) {
  const fieldLabels = moduleMeta?.field_labels || {}
  const unitHints = moduleMeta?.unit_hints || {}
  const primaryKey = moduleMeta?.table_primary_key || 'end_date'
  const rows = extractSeries(data)
  const dateFields = new Set(['end_date','trade_date','ann_date','ex_date','pay_date'])

  // Build columns: all keys from first row, excluding internal/long-text
  const exclude = new Set(['source','ts_code','symbol','curr_type','_partial_errors'])
  const columns = rows.length > 0
    ? Object.keys(rows[0]).filter(k => !k.startsWith('_') && !exclude.has(k) && typeof rows[0][k] !== 'object')
    : []

  // Numeric columns for chart (excluding date/id columns)
  const numericCols = columns.filter(col => {
    if (dateFields.has(col) || col === primaryKey) return false
    const v = rows[0]?.[col]
    return v != null && Number.isFinite(Number(v))
  })

  const xAxis = rows.map(r => r[primaryKey] || r.end_date || r.trade_date || r.ann_date || '—').reverse()
  const series = numericCols.slice(0, 4).map(col => ({
    name: fieldLabels[col] || col,
    type: 'line',
    data: [...rows].reverse().map(r => sf(r[col])),
    connectNulls: false,
  }))

  // Metrics from scalars in data (non-array, non-object top-level fields)
  const metrics = []
  if (data) {
    Object.entries(data).forEach(([k, v]) => {
      if (k.startsWith('_') || exclude.has(k)) return
      if (Array.isArray(v) || (typeof v === 'object' && v !== null)) return
      if (fieldLabels[k]) {
        metrics.push({ label: fieldLabels[k], value: fmtVal(v, k, unitHints), raw: v, field: k })
      }
    })
  }

  return { metrics, xAxis, series, rows, columns, insight: data?.comment || null }
}

// ── Specific adapters ─────────────────────────────────────────────────────────

function adaptValuation(data, meta) {
  const rows = data?.series || []
  const uh = meta?.unit_hints || {}
  const fl = meta?.field_labels || {}
  const reversed = [...rows].reverse()
  const xAxis = reversed.map(r => (r.trade_date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
  const metrics = []
  if (rows[0]) {
    const r = rows[0]
    ;['pe_ttm','pb','ps_ttm','pe_percentile','pb_percentile'].forEach(k => {
      if (r[k] != null) metrics.push({ label: fl[k] || k, value: fmtVal(r[k], k, uh), raw: r[k], field: k })
    })
  }
  const series = [
    { name: fl.pe_ttm || 'PE(TTM)', type: 'line', data: reversed.map(r => sf(r.pe_ttm)), connectNulls: false },
    { name: fl.pb || 'PB', type: 'line', data: reversed.map(r => sf(r.pb)), connectNulls: false },
  ]
  return { metrics, xAxis, series, rows, columns: ['trade_date','pe_ttm','pb','ps_ttm','pe_percentile','pb_percentile'], insight: null }
}

function adaptGrowth(data, meta) {
  const rows = data?.series || data?.rows || []
  const uh = meta?.unit_hints || {}
  const fl = meta?.field_labels || {}
  const reversed = [...rows].reverse()
  const xAxis = reversed.map(r => (r.end_date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
  const series = [
    { name: fl.revenue_yoy_pct || '营收同比(%)', type: 'bar', data: reversed.map(r => sf(r.revenue_yoy_pct)), connectNulls: false },
    { name: fl.net_profit_yoy_pct || '净利润同比(%)', type: 'bar', data: reversed.map(r => sf(r.net_profit_yoy_pct)), connectNulls: false },
    { name: fl.deduct_net_profit_yoy_pct || '扣非净利同比(%)', type: 'bar', data: reversed.map(r => sf(r.deduct_net_profit_yoy_pct)), connectNulls: false },
  ]
  const columns = ['end_date','revenue','revenue_yoy_pct','net_profit_parent','net_profit_yoy_pct','deduct_net_profit_yoy_pct','roe_pct','eps']
  return { metrics: [], xAxis, series, rows, columns, insight: data?.comment || null }
}

function adaptProfitability(data, meta) {
  const rows = data?.series || data?.rows || []
  const fl = meta?.field_labels || {}
  const reversed = [...rows].reverse()
  const xAxis = reversed.map(r => (r.end_date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
  // BaoStock returns _pct suffix; Tushare returns same _pct suffix; support both
  const series = [
    { name: fl.gross_margin_pct || '毛利率(%)', type: 'line', data: reversed.map(r => sf(r.gross_margin_pct ?? r.gross_margin)), connectNulls: false },
    { name: fl.net_margin_pct || '净利率(%)', type: 'line', data: reversed.map(r => sf(r.net_margin_pct ?? r.net_margin)), connectNulls: false },
    { name: fl.roe_pct || 'ROE(%)', type: 'line', data: reversed.map(r => sf(r.roe_pct ?? r.roe)), connectNulls: false },
    { name: fl.roa_pct || 'ROA(%)', type: 'line', data: reversed.map(r => sf(r.roa_pct ?? r.roa)), connectNulls: false },
  ]
  return { metrics: [], xAxis, series, rows, columns: ['end_date','gross_margin_pct','net_margin_pct','roe_pct','roa_pct','roic_pct'], insight: null }
}

function adaptCashflowQuality(data, meta) {
  // Tushare and BaoStock both return `periods`; fall back to series/rows for safety
  const rows = data?.periods || data?.series || data?.rows || []
  const fl = meta?.field_labels || {}
  const uh = meta?.unit_hints || {}
  const reversed = [...rows].reverse()
  const xAxis = reversed.map(r => (r.end_date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
  const metrics = []
  if (rows[0]) {
    const r = rows[0]
    ;['cash_cover_ratio'].forEach(k => {
      if (r[k] != null) metrics.push({ label: fl[k] || k, value: fmtVal(r[k], k, uh), raw: r[k], field: k })
    })
  }
  const series = [
    { name: fl.ocf || '经营现金流', type: 'bar', data: reversed.map(r => sf(r.ocf)), connectNulls: false },
    { name: fl.net_profit || '净利润', type: 'bar', data: reversed.map(r => sf(r.net_profit)), connectNulls: false },
    { name: fl.free_cashflow || '自由现金流', type: 'bar', data: reversed.map(r => sf(r.free_cashflow)), connectNulls: false },
  ]
  return { metrics, xAxis, series, rows, columns: ['end_date','ocf','net_profit','cash_cover_ratio','free_cashflow'], insight: data?.comment || null }
}

function adaptDupont(data, meta) {
  const rows = data?.series || data?.rows || []
  const fl = meta?.field_labels || {}
  const reversed = [...rows].reverse()
  const xAxis = reversed.map(r => (r.end_date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
  // BaoStock returns roe_pct/net_margin_pct/assets_turn; Tushare same _pct suffix
  const series = [
    { name: fl.roe_pct || 'ROE(%)', type: 'line', data: reversed.map(r => sf(r.roe_pct ?? r.roe)), connectNulls: false },
    { name: fl.net_margin_pct || '净利率(%)', type: 'bar', data: reversed.map(r => sf(r.net_margin_pct ?? r.net_margin)), connectNulls: false },
    { name: fl.assets_turn || '资产周转率', type: 'bar', data: reversed.map(r => sf(r.assets_turn ?? r.asset_turnover)), connectNulls: false },
  ]
  return {
    metrics: [],
    xAxis, series,
    rows,
    columns: ['end_date','roe_pct','net_margin_pct','assets_turn','equity_multiplier','factor_product_pct'],
    insight: '注意：三因子乘积与披露ROE可能因平均净资产口径不同存在小幅差异，仅供趋势参考。'
  }
}

function adaptAssetStructure(data, meta) {
  const rows = data?.series || []
  const fl = meta?.field_labels || {}
  const uh = meta?.unit_hints || {}
  const reversed = [...rows].reverse()
  const xAxis = reversed.map(r => (r.end_date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
  const metrics = []
  if (rows[0]) {
    const r = rows[0]
    ;['current_asset_ratio_pct'].forEach(k => {
      if (r[k] != null) metrics.push({ label: fl[k] || '流动资产比例', value: fmtVal(r[k], k, uh), raw: r[k], field: k })
    })
  }
  const series = [
    { name: fl.current_assets || '流动资产', type: 'bar', data: reversed.map(r => sf(r.current_assets)), connectNulls: false, stack: 'assets' },
    { name: fl.non_current_assets || '非流动资产', type: 'bar', data: reversed.map(r => sf(r.non_current_assets)), connectNulls: false, stack: 'assets' },
  ]
  return { metrics, xAxis, series, rows, columns: ['end_date','total_assets','current_assets','non_current_assets','current_asset_ratio_pct','goodwill','intangible_assets'], insight: null }
}

function adaptMainBusiness(data, meta) {
  const periods = data?.periods || []
  if (!periods.length) return genericAdapter(data, meta)
  const latest = periods[0]
  const items = latest?.items || []
  // Pie series for donut
  const series = [{
    name: '主营收入占比',
    type: 'pie',
    radius: ['40%', '70%'],
    data: items.filter(i => i.bz_sales != null).map(i => ({
      name: i.bz_item || '其他',
      value: sf(i.bz_sales),
    })),
    connectNulls: false,
  }]
  return {
    metrics: [],
    xAxis: [],
    series,
    rows: items.map(i => ({ ...i, end_date: latest.end_date })),
    columns: ['bz_item','bz_sales','sales_ratio_pct','bz_profit','bz_cost'],
    insight: null,
  }
}

function adaptDividendHistory(data, meta) {
  const rows = data?.records || []
  const fl = meta?.field_labels || {}
  const reversed = [...rows].reverse()
  const xAxis = reversed.map(r => (r.end_date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
  const series = [
    { name: fl.cash_div || '每股现金分红(元)', type: 'bar', data: reversed.map(r => sf(r.cash_div)), connectNulls: false },
  ]
  const metrics = []
  if (data?.summary) {
    const s = data.summary
    if (s.latest_cash_div != null) metrics.push({ label: '最新每股分红', value: (s.latest_cash_div || 0).toFixed(4) + ' 元', raw: s.latest_cash_div, field: 'latest_cash_div' })
    if (s.years_count != null) metrics.push({ label: '分红年数', value: s.years_count + ' 年', raw: s.years_count, field: 'years_count' })
  }
  return { metrics, xAxis, series, rows, columns: ['end_date','ex_date','pay_date','cash_div','cash_div_tax','stk_div','div_proc'], insight: data?.comment || null }
}

function adaptMajorHolders(data, meta) {
  const holderNumRows = data?.holder_num_series || []
  const top10 = data?.top10_float_holders || []
  const fl = meta?.field_labels || {}
  const reversed = [...holderNumRows].reverse()
  const xAxis = reversed.map(r => (r.end_date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))
  const series = holderNumRows.length > 0
    ? [{ name: fl.holder_num || '股东户数', type: 'line', data: reversed.map(r => sf(r.holder_num)), connectNulls: false }]
    : []
  return {
    metrics: [],
    xAxis, series,
    rows: top10,
    columns: ['holder_name','hold_amount','hold_ratio_pct'],
    insight: data?.comment || null,
    extra: { holder_num_rows: holderNumRows },
  }
}

function adaptIndustryRank(data, meta) {
  const rankings = data?.rankings || []
  const fl = meta?.field_labels || {}
  // Radar: each metric is a dimension, value=percentile
  const radarIndicators = rankings.map(r => ({ name: fl[r.metric] || r.metric, max: 100 }))
  const radarValues = rankings.map(r => sf(r.percentile) != null ? Math.round(sf(r.percentile) * 100) : null)
  const series = radarValues.some(v => v != null) ? [{
    name: '行业分位(%)',
    type: 'radar',
    data: [{ value: radarValues, name: '分位数' }],
    connectNulls: false,
  }] : []
  return { metrics: [], xAxis: [], series, rows: rankings, columns: ['metric','value','rank','peer_count','percentile'], insight: null, radarIndicators }
}

// ── Registry ─────────────────────────────────────────────────────────────────

function adaptAiAnalysis(data, meta) {
  // data = { ai_analysis: { dimensions: [...], ... } }
  const ai = data?.ai_analysis || {}
  const dims = ai.dimensions || []
  // Build radar chart data
  const radarIndicators = dims.map(d => ({ name: d.name, max: 100 }))
  const series = dims.length ? [{
    name: '基本面评分',
    type: 'radar',
    data: [{ value: dims.map(d => d.score ?? 0), name: '评分' }],
    connectNulls: false,
  }] : []
  // No table rows for ai_analysis
  return {
    metrics: ai.overall_score != null ? [{ label: '综合评分', value: String(ai.overall_score), raw: ai.overall_score, field: 'overall_score' }] : [],
    xAxis: [],
    series,
    rows: [],
    columns: [],
    insight: ai.summary || null,
    radarIndicators,
  }
}

const ADAPTERS = {
  valuation:           adaptValuation,
  growth:              adaptGrowth,
  profitability:       adaptProfitability,
  cashflow_quality:    adaptCashflowQuality,
  dupont:              adaptDupont,
  asset_structure:     adaptAssetStructure,
  main_business:       adaptMainBusiness,
  dividend_history:    adaptDividendHistory,
  major_holders:       adaptMajorHolders,
  industry_rank:       adaptIndustryRank,
  ai_analysis:         adaptAiAnalysis,
}

/**
 * Main entry point.
 * @param {string} moduleKey - e.g. "valuation"
 * @param {object} data - DataEnvelope.data
 * @param {object} moduleMeta - MODULE_CATALOG entry
 * @returns {object} view model
 */
export function adaptModuleData(moduleKey, data, moduleMeta) {
  if (!data) return { metrics: [], xAxis: [], series: [], rows: [], columns: [], insight: null }
  const adapter = ADAPTERS[moduleKey] || genericAdapter
  return adapter(data, moduleMeta)
}
