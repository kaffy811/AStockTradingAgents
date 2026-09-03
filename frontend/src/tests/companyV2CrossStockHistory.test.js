/**
 * frontend/src/tests/companyV2CrossStockHistory.test.js
 * Phase 6T-E: 跨股票历史数据前端行为验收
 */
import { describe, expect, it } from 'vitest'

describe('Phase 6T-E history ordering & tabs', () => {
  it('sortedRows sorts multi-year annual history ascending', async () => {
    const { sortedRows } = await import('../utils/companyV2PeriodClassifier.js')
    const rows = [
      { period: '2023-12-31' },
      { period: '2019-12-31' },
      { period: '2021-12-31' },
    ]
    const sorted = sortedRows(rows)
    expect(sorted.map(r => r.period)).toEqual(['2019-12-31', '2021-12-31', '2023-12-31'])
  })

  it('sortedRows sorts quarterly history ascending', async () => {
    const { sortedRows, extractXLabels } = await import('../utils/companyV2PeriodClassifier.js')
    const rows = [
      { period: '2024-09-30' },
      { period: '2024-03-31' },
      { period: '2024-06-30' },
    ]
    const sorted = sortedRows(rows)
    expect(extractXLabels(sorted, 'quarterly')).toEqual(['2024Q1', '2024Q2', '2024Q3'])
  })

  it('CompanyV2View has annual/quarterly period tabs (annual default, quarterly lazy)', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('period-tabs')
    expect(raw.default).toContain("periodTab = ref('annual')")
    expect(raw.default).toContain('displayHistoryModules')
    // Phase 6T-E1: 季度懒加载，已缓存不重复请求
    expect(raw.default).toContain('switchToQuarterly')
    expect(raw.default).toContain('quarterlyHistoryData')
  })

  it('mixed rows are not rendered as a continuous line', async () => {
    const { classifyRowsPeriod, suggestChartType } = await import('../utils/companyV2PeriodClassifier.js')
    const mixedRows = [
      { period: '2023-12-31' },
      { period: '2024-05-15' },   // 日频混入
      { period: '2024-06-30' },
    ]
    const pt = classifyRowsPeriod(mixedRows)
    // mixed 数据必须使用非连线图表
    if (pt === 'mixed') {
      expect(suggestChartType(pt, 'profitability')).not.toBe('line')
    }
    expect(suggestChartType('mixed', 'profitability')).toBe('bar')
    expect(suggestChartType('mixed', 'dupont')).toBe('bar')
  })

  it('single period uses metric card, no fake trend', async () => {
    const { classifyRowsPeriod, suggestChartType } = await import('../utils/companyV2PeriodClassifier.js')
    expect(classifyRowsPeriod([{ period: '2024-12-31' }])).toBe('point_in_time')
    expect(suggestChartType('point_in_time', 'profitability')).toBe('metric_card')
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'growth', period_type: 'annual',
      fields: ['net_profit_yoy'], rows_count: 1,
    })
    expect(result.chart_type).toBe('metric_cards')
  })

  it('history range label is displayed from backend semantics', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('history-range-label')
    expect(raw.default).toContain('history_range_label')
    // 不允许无条件硬编码"上市以来"
    expect(raw.default).not.toContain('上市以来全部数据')
  })
})

describe('Phase 6T-E growth field semantics', () => {
  it('GrowthComboChart uses provider-real field names (not 营业收入/归母净利润 mislabels)', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2GrowthComboChart.vue?raw')
    expect(raw.default).toContain('main_business_revenue')
    expect(raw.default).toContain('net_profit_yoy')
    expect(raw.default).toContain('net_profit_parent_yoy')
    expect(raw.default).toContain('主营收入')
    // 不得把净利润同比标注为营收同比
    expect(raw.default).not.toContain("'营收同比%'")
  })

  it('growth combo uses bar for absolute values and line for yoy with dual axis', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2GrowthComboChart.vue?raw')
    expect(raw.default).toContain("type: 'bar'")
    expect(raw.default).toContain("type: 'line'")
    expect(raw.default).toContain('yAxisIndex: 1')
  })
})

describe('Phase 6T-E financial industry N/A', () => {
  it('CompanyV2Section renders neutral N/A hint for not-applicable fields', async () => {
    const raw = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(raw.default).toContain('metric-na-hint')
    expect(raw.default).toContain('not_applicable_fields')
    expect(raw.default).toContain('N/A')
  })
})
