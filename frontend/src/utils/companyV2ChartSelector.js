/**
 * frontend/src/utils/companyV2ChartSelector.js
 * Phase 6T-B: 图表类型选择逻辑
 *
 * 根据模块特征（period_type、字段、行数、量级差距）决定最佳图表类型。
 *
 * 输入：
 *   - module_key
 *   - period_type
 *   - fields (series 字段列表)
 *   - rows_count
 *   - value_scale_profile (optional)
 *
 * 输出：
 *   - chart_type
 *   - x_axis
 *   - y_axis
 *   - series
 *   - warnings
 *
 * 规则：
 *   1. point_in_time → metric_cards（不画趋势图）
 *   2. rows_count == 1 → metric_cards（单行不可趋势）
 *   3. annual / quarterly → trend charts
 *   4. daily → line_chart
 *   5. mixed → grouped（不强行连线）
 *   6. 有绝对值 + yoy → bar_line_combo
 *   7. 全部百分比 → multi_line
 *   8. 指标量级差 > 100 倍 → secondary_axis 或 log_scale
 */

// ── 模块默认图表配置 ──────────────────────────────────────────────────────────

const MODULE_CHART_DEFAULTS = {
  profitability: {
    chart_type: 'multi_line',
    series_types: 'percent_only',
    description: 'ROE/毛利率/净利率多折线',
  },
  growth: {
    chart_type: 'bar_line_combo',
    series_types: 'absolute_plus_yoy',
    description: '营收/净利润柱 + 同比增速折线',
    highlight_negative: true,
  },
  cashflow_quality: {
    chart_type: 'positive_negative_bar',
    series_types: 'mixed',
    description: '正负柱状图，0轴突出',
    highlight_zero: true,
  },
  solvency: {
    chart_type: 'multi_line',
    series_types: 'ratio_and_percent',
    description: '流动/速动/现金比率折线 + 资产负债率副轴',
  },
  operation_capability: {
    chart_type: 'grouped_bar',
    series_types: 'ratio',
    description: '分组柱状，量级差距大时启用副轴',
    auto_secondary_axis: true,
    scale_threshold: 100,
  },
  dupont: {
    chart_type: 'dual_axis_line',
    series_types: 'mixed',
    description: 'ROE/净利率主轴 + 周转率/权益乘数副轴',
    formula_hint: 'ROE ≈ 净利率 × 总资产周转率 × 权益乘数',
  },
  valuation: {
    chart_type: 'metric_cards',
    series_types: 'ratio',
    description: '估值指标卡（无历史序列时）',
  },
  quote_overview: {
    chart_type: 'metric_cards',
    series_types: 'mixed',
    description: '行情指标卡',
  },
}

// ── 量级检测 ──────────────────────────────────────────────────────────────────

/**
 * 检测一组值的量级差距
 * @param {Array} values - 数值数组（可含 null）
 * @returns {number} max/min 比值（绝对值非零最小值）
 */
function detectScaleRange(values) {
  const nums = values.filter(v => v != null && !isNaN(v) && Math.abs(v) > 1e-10)
  if (nums.length < 2) return 1
  const maxAbs = Math.max(...nums.map(Math.abs))
  const minAbs = Math.min(...nums.map(Math.abs))
  if (minAbs === 0) return Infinity
  return maxAbs / minAbs
}

/**
 * 从 history rows 中提取某字段的所有值
 * @param {Array} rows
 * @param {string} field
 * @returns {Array<number|null>}
 */
function extractFieldValues(rows, field) {
  return rows.map(r => {
    const v = r[field]
    if (v == null || v === '') return null
    const n = Number(v)
    return isNaN(n) ? null : n
  })
}

// ── 主函数 ────────────────────────────────────────────────────────────────────

/**
 * 根据模块特征选择图表类型
 *
 * @param {object} params
 * @param {string} params.module_key
 * @param {string} params.period_type - "annual" | "quarterly" | "daily" | "point_in_time" | "mixed" | "unknown"
 * @param {Array}  params.fields       - 字段名列表
 * @param {number} params.rows_count
 * @param {Array}  [params.rows]        - 原始数据行（用于量级检测）
 * @param {object} [params.chart_contract] - 后端提供的 chart_contract（优先使用）
 *
 * @returns {object} {
 *   chart_type: string,
 *   x_axis: string,
 *   series: Array,
 *   secondary_axis: boolean,
 *   log_scale: boolean,
 *   warnings: string[],
 *   description: string,
 * }
 */
export function selectChart({
  module_key,
  period_type,
  fields = [],
  rows_count = 0,
  rows = [],
  chart_contract = null,
}) {
  const warnings = []

  // 1. 单行或 point_in_time → metric_cards
  if (period_type === 'point_in_time' || rows_count <= 1) {
    return {
      chart_type: 'metric_cards',
      x_axis: 'period',
      series: fields.map(f => ({ field: f })),
      secondary_axis: false,
      log_scale: false,
      warnings: rows_count === 1 ? ['single_period_no_trend'] : [],
      description: '单期指标卡（无趋势序列）',
    }
  }

  // 2. 如果后端提供了 chart_contract，优先使用
  if (chart_contract && chart_contract.preferred_chart) {
    const contractType = chart_contract.preferred_chart
    // 验证量级问题（operation_capability 特殊处理）
    let secondary_axis = false
    let log_scale = false
    if (module_key === 'operation_capability' && rows.length > 0) {
      const allValues = fields.flatMap(f => extractFieldValues(rows, f))
      const scaleRange = detectScaleRange(allValues)
      if (scaleRange > 100) {
        secondary_axis = true
        warnings.push(`scale_range_${Math.round(scaleRange)}x_uses_secondary_axis`)
      }
    }
    return {
      chart_type: contractType,
      x_axis: chart_contract.x_field || 'period',
      series: chart_contract.series || fields.map(f => ({ field: f })),
      secondary_axis,
      log_scale,
      warnings,
      description: `后端 chart_contract: ${contractType}`,
    }
  }

  // 3. 没有 chart_contract，根据规则推断
  const defaults = MODULE_CHART_DEFAULTS[module_key] || {}

  // daily → line chart
  if (period_type === 'daily') {
    return {
      chart_type: 'line_chart',
      x_axis: 'trade_date',
      series: fields.map(f => ({ field: f })),
      secondary_axis: false,
      log_scale: false,
      warnings: [],
      description: '日频折线图',
    }
  }

  // mixed → grouped，不强行连线
  if (period_type === 'mixed') {
    warnings.push('mixed_period_type_no_continuous_line')
    return {
      chart_type: 'grouped_bar',
      x_axis: 'period',
      series: fields.map(f => ({ field: f })),
      secondary_axis: false,
      log_scale: false,
      warnings,
      description: '混合周期分组柱状（不连线）',
    }
  }

  // annual / quarterly → 使用模块默认
  const base_type = defaults.chart_type || 'line_chart'

  // 检测量级差距
  let secondary_axis = false
  let log_scale = false
  if (defaults.auto_secondary_axis && rows.length > 0) {
    const allValues = fields.flatMap(f => extractFieldValues(rows, f))
    const scaleRange = detectScaleRange(allValues)
    if (scaleRange > (defaults.scale_threshold || 100)) {
      secondary_axis = true
      warnings.push(`extreme_scale_ratio_${Math.round(scaleRange)}x_secondary_axis_enabled`)
    }
  }

  return {
    chart_type: base_type,
    x_axis: 'period',
    series: fields.map(f => ({ field: f })),
    secondary_axis,
    log_scale,
    warnings,
    description: defaults.description || base_type,
    formula_hint: defaults.formula_hint || null,
    highlight_negative: defaults.highlight_negative || false,
    highlight_zero: defaults.highlight_zero || false,
  }
}

/**
 * 从 history rows 和 chart_contract 计算副轴建议
 * 主要用于 operation_capability：应收账款周转率可能远高于其他指标
 *
 * @param {Array} rows
 * @param {Array} seriesFields - 字段名列表
 * @param {number} threshold - 量级差距阈值（默认 100）
 * @returns {{ needsSecondaryAxis: boolean, primaryFields: string[], secondaryFields: string[] }}
 */
export function computeSecondaryAxisSplit(rows, seriesFields, threshold = 100) {
  if (!rows || !rows.length || !seriesFields || !seriesFields.length) {
    return { needsSecondaryAxis: false, primaryFields: seriesFields, secondaryFields: [] }
  }

  const means = {}
  for (const field of seriesFields) {
    const vals = extractFieldValues(rows, field).filter(v => v != null)
    if (vals.length > 0) {
      means[field] = vals.reduce((a, b) => a + Math.abs(b), 0) / vals.length
    }
  }

  const meanValues = Object.values(means).filter(v => v > 0)
  if (meanValues.length < 2) {
    return { needsSecondaryAxis: false, primaryFields: seriesFields, secondaryFields: [] }
  }

  const maxMean = Math.max(...meanValues)
  const minMean = Math.min(...meanValues)
  if (maxMean / minMean <= threshold) {
    return { needsSecondaryAxis: false, primaryFields: seriesFields, secondaryFields: [] }
  }

  // 按均值分组：大的放副轴
  const median = (maxMean + minMean) / 2
  const primaryFields = []
  const secondaryFields = []
  for (const field of seriesFields) {
    if (means[field] != null && means[field] > median) {
      secondaryFields.push(field)
    } else {
      primaryFields.push(field)
    }
  }

  return { needsSecondaryAxis: true, primaryFields, secondaryFields }
}
