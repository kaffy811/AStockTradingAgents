/**
 * frontend/src/utils/companyV2PeriodClassifier.js
 * 识别 CompanyV2 模块 rows 的数据周期类型。
 *
 * period_type:
 *   - "point_in_time"  → 只有一行，无时间序列
 *   - "daily"          → 有 trade_date 且多行
 *   - "quarterly"      → 有 period 字段，季度末日期
 *   - "annual"         → 有 period 字段，年末 12-31
 *   - "mixed"          → 年度和季度混合
 *   - "unknown"        → 无法识别
 */

const RE_ANNUAL_END = /\d{4}-12-31$/
const RE_QUARTER_END = /\d{4}-(03-31|06-30|09-30|12-31)$/

/**
 * 识别单行的期间类型
 * @param {object} row
 * @returns {"annual"|"quarterly"|"daily"|"point_in_time"|"unknown"}
 */
export function classifyRowPeriod(row) {
  if (!row || typeof row !== 'object') return 'unknown'
  const period = row.period || row.stat_date || row.end_date || ''
  const tradeDate = row.trade_date || row.date || ''
  if (tradeDate && !period) return 'daily'
  if (!period) return 'unknown'
  if (RE_ANNUAL_END.test(period)) return 'annual'
  if (RE_QUARTER_END.test(period)) return 'quarterly'
  return 'unknown'
}

/**
 * 识别 rows 数组的整体周期类型
 * @param {Array} rows
 * @returns {"point_in_time"|"daily"|"annual"|"quarterly"|"mixed"|"unknown"}
 */
export function classifyRowsPeriod(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return 'unknown'
  if (rows.length === 1) return 'point_in_time'

  const hasTradeDates = rows.every(r => !!(r.trade_date || r.date))
  if (hasTradeDates) return 'daily'

  const periods = rows
    .map(r => r?.period || r?.stat_date || r?.end_date || '')
    .filter(Boolean)
  if (periods.length === rows.length) {
    const allQuarterEnds = periods.every(p => RE_QUARTER_END.test(p))
    const allAnnualEnds = periods.every(p => RE_ANNUAL_END.test(p))
    if (allQuarterEnds && !allAnnualEnds) return 'quarterly'
    if (allAnnualEnds) return 'annual'
  }

  const types = new Set(rows.map(r => classifyRowPeriod(r)).filter(t => t !== 'unknown'))
  if (types.size === 0) return 'unknown'
  if (types.size === 1) return [...types][0]
  if (types.has('annual') && types.has('quarterly')) return 'mixed'
  return 'mixed'
}

/**
 * 根据周期类型建议图表类型
 * @param {string} periodType
 * @param {string} moduleKey
 * @returns {"line"|"bar"|"combo"|"metric_card"|"radar"|"none"}
 */
export function suggestChartType(periodType, moduleKey) {
  if (periodType === 'point_in_time') return 'metric_card'
  if (periodType === 'unknown') return 'metric_card'
  // Phase 6T-E: mixed 周期不得连成同一条趋势线，使用分组柱状
  if (periodType === 'mixed') return 'bar'
  if (moduleKey === 'quote_overview' || moduleKey === 'valuation') return 'metric_card'
  if (moduleKey === 'growth') return 'combo'          // 柱（绝对值）+ 折线（同比）
  if (moduleKey === 'profitability') return 'line'     // 多折线
  if (moduleKey === 'dupont') return 'line'            // 双轴折线
  if (moduleKey === 'cashflow_quality') return 'bar'   // 正负柱
  if (moduleKey === 'solvency') return periodType === 'point_in_time' ? 'metric_card' : 'line'
  if (moduleKey === 'operation_capability') return 'bar'
  return periodType === 'annual' || periodType === 'quarterly' ? 'line' : 'metric_card'
}

/**
 * 提取 rows 中的有序 X 轴时间标签
 * @param {Array} rows
 * @param {string} periodType
 * @returns {string[]}
 */
export function extractXLabels(rows, periodType) {
  if (!Array.isArray(rows)) return []
  const sorted = [...rows].sort((a, b) => {
    const da = a.period || a.stat_date || a.end_date || a.trade_date || ''
    const db = b.period || b.stat_date || b.end_date || b.trade_date || ''
    return da.localeCompare(db)
  })
  return sorted.map(r => {
    const d = r.period || r.stat_date || r.end_date || r.trade_date || ''
    if (periodType === 'annual') return d.slice(0, 4)  // "2024"
    if (periodType === 'quarterly') {
      // "2024-09-30" → "2024Q3"
      const mo = d.slice(5, 7)
      const q = mo === '03' ? 'Q1' : mo === '06' ? 'Q2' : mo === '09' ? 'Q3' : 'Q4'
      return d.slice(0, 4) + q
    }
    return d
  })
}

/**
 * 获取排序后的 rows
 */
export function sortedRows(rows) {
  return [...(rows || [])].sort((a, b) => {
    const da = a.period || a.stat_date || a.end_date || a.trade_date || ''
    const db = b.period || b.stat_date || b.end_date || b.trade_date || ''
    return da.localeCompare(db)
  })
}
