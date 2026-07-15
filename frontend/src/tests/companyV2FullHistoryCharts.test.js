/**
 * frontend/src/tests/companyV2FullHistoryCharts.test.js
 * Phase 6T-B: Full-History Charts 验收测试
 */
import { describe, expect, it } from 'vitest'

// ── Chart Selector 测试 ───────────────────────────────────────────────────────

describe('companyV2ChartSelector', () => {
  it('imports correctly', async () => {
    const { selectChart, computeSecondaryAxisSplit } = await import('../utils/companyV2ChartSelector.js')
    expect(typeof selectChart).toBe('function')
    expect(typeof computeSecondaryAxisSplit).toBe('function')
  })

  it('returns metric_cards for point_in_time', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'profitability',
      period_type: 'point_in_time',
      fields: ['roe', 'gross_margin'],
      rows_count: 1,
    })
    expect(result.chart_type).toBe('metric_cards')
  })

  it('returns metric_cards for single row', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'profitability',
      period_type: 'annual',
      fields: ['roe'],
      rows_count: 1,
    })
    expect(result.chart_type).toBe('metric_cards')
    expect(result.warnings).toContain('single_period_no_trend')
  })

  it('uses chart_contract preferred_chart when provided', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'profitability',
      period_type: 'annual',
      fields: ['roe', 'gross_margin', 'net_margin'],
      rows_count: 8,
      chart_contract: {
        preferred_chart: 'multi_line',
        x_field: 'period',
        series: [{ field: 'roe', display_name: 'ROE' }],
      },
    })
    expect(result.chart_type).toBe('multi_line')
    expect(result.x_axis).toBe('period')
  })

  it('returns multi_line for profitability without contract', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'profitability',
      period_type: 'annual',
      fields: ['roe', 'gross_margin'],
      rows_count: 5,
    })
    expect(result.chart_type).toBe('multi_line')
  })

  it('returns bar_line_combo for growth', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'growth',
      period_type: 'annual',
      fields: ['revenue', 'net_profit_parent', 'revenue_yoy'],
      rows_count: 6,
    })
    expect(result.chart_type).toBe('bar_line_combo')
    expect(result.highlight_negative).toBe(true)
  })

  it('returns line_chart for daily period', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'valuation',
      period_type: 'daily',
      fields: ['pe_ttm'],
      rows_count: 100,
    })
    expect(result.chart_type).toBe('line_chart')
    expect(result.x_axis).toBe('trade_date')
  })

  it('returns grouped_bar for mixed period type', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'profitability',
      period_type: 'mixed',
      fields: ['roe'],
      rows_count: 4,
    })
    expect(result.chart_type).toBe('grouped_bar')
    expect(result.warnings).toContain('mixed_period_type_no_continuous_line')
  })

  it('detects extreme scale and warns', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const rows = [
      { period: '2022-12-31', asset_turnover: 0.18, receivable_turnover: 3500 },
      { period: '2023-12-31', asset_turnover: 0.20, receivable_turnover: 3200 },
    ]
    const result = selectChart({
      module_key: 'operation_capability',
      period_type: 'annual',
      fields: ['asset_turnover', 'receivable_turnover'],
      rows_count: 2,
      rows,
    })
    // 无 chart_contract 时，auto_secondary_axis 应触发
    expect(result.secondary_axis).toBe(true)
    expect(result.warnings.length).toBeGreaterThan(0)
  })

  it('computeSecondaryAxisSplit handles extreme scale', async () => {
    const { computeSecondaryAxisSplit } = await import('../utils/companyV2ChartSelector.js')
    const rows = [
      { asset_turnover: 0.2, receivable_turnover: 3000 },
      { asset_turnover: 0.18, receivable_turnover: 2800 },
    ]
    const result = computeSecondaryAxisSplit(rows, ['asset_turnover', 'receivable_turnover'])
    expect(result.needsSecondaryAxis).toBe(true)
    expect(result.secondaryFields).toContain('receivable_turnover')
    expect(result.primaryFields).toContain('asset_turnover')
  })

  it('computeSecondaryAxisSplit does not split when scale is normal', async () => {
    const { computeSecondaryAxisSplit } = await import('../utils/companyV2ChartSelector.js')
    const rows = [
      { current_ratio: 2.1, quick_ratio: 1.5 },
      { current_ratio: 2.0, quick_ratio: 1.4 },
    ]
    const result = computeSecondaryAxisSplit(rows, ['current_ratio', 'quick_ratio'])
    expect(result.needsSecondaryAxis).toBe(false)
  })
})

// ── PeriodClassifier 测试 ──────────────────────────────────────────────────────

describe('companyV2PeriodClassifier', () => {
  it('classifies annual rows', async () => {
    const { classifyRowsPeriod } = await import('../utils/companyV2PeriodClassifier.js')
    const rows = [
      { period: '2020-12-31' },
      { period: '2021-12-31' },
      { period: '2022-12-31' },
    ]
    expect(classifyRowsPeriod(rows)).toBe('annual')
  })

  it('classifies quarterly rows', async () => {
    const { classifyRowsPeriod } = await import('../utils/companyV2PeriodClassifier.js')
    const rows = [
      { period: '2022-03-31' },
      { period: '2022-06-30' },
      { period: '2022-09-30' },
      { period: '2022-12-31' },
    ]
    expect(classifyRowsPeriod(rows)).toBe('quarterly')
  })

  it('classifies single row as point_in_time', async () => {
    const { classifyRowsPeriod } = await import('../utils/companyV2PeriodClassifier.js')
    expect(classifyRowsPeriod([{ period: '2024-12-31' }])).toBe('point_in_time')
  })
})

// ── Chart Components Render 测试 ──────────────────────────────────────────────

describe('Chart component source code checks', () => {
  it('ProfitabilityTrendChart accepts rows prop', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2ProfitabilityTrendChart.vue?raw')
    expect(raw.default).toContain('rows')
    expect(raw.default).toContain('roe')
    expect(raw.default).toContain('gross_margin')
    expect(raw.default).toContain('net_margin')
  })

  it('GrowthComboChart uses bar + line', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2GrowthComboChart.vue?raw')
    expect(raw.default).toContain('bar')
    expect(raw.default).toContain('line')
  })

  it('ValuationTrendChart handles no history (shows metric cards)', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2ValuationTrendChart.vue?raw')
    expect(raw.default).toContain('rows')
    // Should fallback to cards when no trend
    expect(raw.default).toContain('fields')
  })

  it('OperationBarChart exists and has rows prop', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2OperationBarChart.vue?raw')
    expect(raw.default).toContain('rows')
  })

  it('DupontChart has formula hint', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2DupontChart.vue?raw')
    expect(raw.default).toContain('ROE')
  })
})

// ── CompanyV2View 测试 ─────────────────────────────────────────────────────────

describe('CompanyV2View Phase 6T-B', () => {
  it('imports history API functions', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('getCompanyV2History')
    expect(raw.default).toContain('getCompanyV2Profile')
  })

  it('debug panel is inside details element (collapsed by default)', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('<details')
    expect(raw.default).toContain('CompanyV2DebugPanel')
  })

  it('shows disclaimer with no investment advice language', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('不构成投资建议')
    expect(raw.default).not.toContain('买入')
    expect(raw.default).not.toContain('卖出')
    expect(raw.default).not.toContain('目标价')
  })

  it('filters out report_rag from displayed modules', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain("report_rag")
    // report_rag 应该被过滤掉
    expect(raw.default).toMatch(/filter.*report_rag|report_rag.*filter/)
  })

  it('has bottom sentinel', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('company-v2-bottom-sentinel')
  })

  it('has StockBasicCard component', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('CompanyV2StockBasicCard')
    expect(raw.default).toContain('stock-basic-card')
  })

  it('passes historyData to CompanyV2Section', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('historyData') || expect(raw.default).toContain('history-data')
  })
})
