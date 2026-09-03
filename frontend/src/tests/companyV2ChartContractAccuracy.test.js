/**
 * frontend/src/tests/companyV2ChartContractAccuracy.test.js
 * Phase 6T-E: 图表契约与数据特征一致性
 */
import { describe, expect, it } from 'vitest'

describe('Phase 6T-E chart contract accuracy', () => {
  it('profitability percent axis converts ratio to percentage points (no 1050% bug)', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2ProfitabilityTrendChart.vue?raw')
    // 图表内应有明确的 percent 转换（×100 formatter）或原生百分点数据
    expect(raw.default).toMatch(/\*\s*100|toFixed/)
  })

  it('growth chart contract from backend uses real fields', async () => {
    // 后端契约（series 字段）不包含 provider 不存在的 revenue_yoy
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const contract = {
      preferred_chart: 'bar_line_combo',
      x_field: 'period',
      series: [
        { field: 'main_business_revenue', display_name: '主营业务收入', chart_type: 'bar' },
        { field: 'net_profit_yoy', display_name: '净利润同比', chart_type: 'line', axis: 'secondary' },
      ],
    }
    const result = selectChart({
      module_key: 'growth', period_type: 'annual',
      fields: ['main_business_revenue', 'net_profit_yoy'],
      rows_count: 5, chart_contract: contract,
    })
    expect(result.chart_type).toBe('bar_line_combo')
    expect(result.series.map(s => s.field)).toContain('main_business_revenue')
  })

  it('cashflow chart highlights zero baseline', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2CashflowQualityChart.vue?raw')
    // 有 0 轴基线（markLine/0基线/正负着色任一形式）
    expect(raw.default).toMatch(/markLine|zero|0 ?轴|baseline|itemStyle/)
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'cashflow_quality', period_type: 'annual',
      fields: ['ocf_to_np'], rows_count: 4,
    })
    expect(result.highlight_zero).toBe(true)
  })

  it('operation extreme scale uses secondary axis / split panels', async () => {
    const { computeSecondaryAxisSplit } = await import('../utils/companyV2ChartSelector.js')
    const rows = [
      { asset_turnover: 0.1, receivable_turnover: 500 },
      { asset_turnover: 0.12, receivable_turnover: 480 },
    ]
    const split = computeSecondaryAxisSplit(rows, ['asset_turnover', 'receivable_turnover'])
    expect(split.needsSecondaryAxis).toBe(true)
    expect(split.secondaryFields).toContain('receivable_turnover')
  })

  it('missing values are not rendered as 0', async () => {
    const rawGrowth = await import('../components/company-v2/charts/CompanyV2GrowthComboChart.vue?raw')
    // null 保持 null（ECharts 断点），不得 || 0
    expect(rawGrowth.default).toContain('return null')
    expect(rawGrowth.default).not.toMatch(/\?\?\s*0[,)\s]/)
  })

  it('valuation without daily history uses metric cards, no fake quantiles', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'valuation', period_type: 'annual',
      fields: ['pe_ttm', 'pb'], rows_count: 1,
    })
    expect(result.chart_type).toBe('metric_cards')
    const rawVal = await import('../components/company-v2/charts/CompanyV2ValuationTrendChart.vue?raw')
    // 不显示"历史估值分位"字样（前端未实现分位，避免用少量年度点伪造）
    expect(rawVal.default).not.toContain('分位')
  })

  it('dupont shows formula as hint (口径提示), not as verified fact', async () => {
    const { selectChart } = await import('../utils/companyV2ChartSelector.js')
    const result = selectChart({
      module_key: 'dupont', period_type: 'annual',
      fields: ['roe', 'net_margin'], rows_count: 5,
    })
    expect(result.formula_hint).toContain('≈')
    const rawDupont = await import('../components/company-v2/charts/CompanyV2DupontChart.vue?raw')
    expect(rawDupont.default).not.toContain('公式已验证')
  })

  it('ECharts instances are disposed on unmount in all chart components', async () => {
    // ValuationTrendChart 为纯指标卡（无 ECharts 实例），不在 dispose 检查范围
    const charts = [
      'CompanyV2GrowthComboChart', 'CompanyV2ProfitabilityTrendChart',
      'CompanyV2DupontChart', 'CompanyV2CashflowQualityChart',
      'CompanyV2SolvencyRadarOrBars', 'CompanyV2OperationBarChart',
    ]
    for (const name of charts) {
      const raw = await import(`../components/company-v2/charts/${name}.vue?raw`)
      expect(raw.default, `${name} must dispose ECharts`).toContain('dispose')
      expect(raw.default, `${name} must use onUnmounted`).toContain('onUnmounted')
    }
  })
})
