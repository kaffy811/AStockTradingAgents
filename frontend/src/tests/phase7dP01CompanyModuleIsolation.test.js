import { describe, expect, it } from 'vitest'

describe('Phase 7D-P0.1 company page module isolation', () => {
  it('keeps profile display data independent from history and debug modules', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    expect(view.default).toContain('Object.keys(stockBasic.value || {}).length > 0')
    expect(view.default).toContain("historyResult.status === 'fulfilled'")
    expect(view.default).toContain("debugResult.status === 'fulfilled'")
    expect(view.default).not.toContain('throw debugResult.reason')
  })

  it('shows an explicit empty history state without hiding the profile', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    expect(view.default).toContain('data-testid="history-unavailable"')
    expect(view.default).toContain('暂缺历史财务数据')
    expect(view.default).toContain('CompanyV2CompanyProfileCard')
  })

  it('contains quote failure within the quote module', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    expect(view.default).toContain('data-testid="quote-unavailable"')
    expect(view.default).toContain('不影响公司资料与其他模块')
  })

  it('preserves the existing quote, kline and news card boundaries', async () => {
    const detail = await import('../views/StockDetailView.vue?raw')
    expect(detail.default).toContain(':quote-error="quoteError"')
    expect(detail.default).toContain('<TechnicalChartPanel')
    expect(detail.default).toContain(':error="newsError"')
    expect(detail.default).toContain('Promise.allSettled')
  })

  it('renders allowlisted history fields and keeps module unavailable states independent', async () => {
    const publicHistory = {
      ok: true,
      modules: {
        profitability: {
          history: [{ period: '2025-12-31', roe: 0.12, gross_margin: null }],
          latest: { period: '2025-12-31', roe: 0.12, gross_margin: null },
          field_availability: { period: true, roe: true },
          data_success: true,
        },
        cashflow_quality: {
          history: [],
          latest: {},
          field_availability: {},
          data_success: false,
          reason_code: 'DATA_NOT_AVAILABLE',
        },
      },
    }
    expect(publicHistory.modules.profitability.latest.roe).toBe(0.12)
    expect(publicHistory.modules.cashflow_quality.data_success).toBe(false)
    expect(publicHistory.modules.cashflow_quality.reason_code).toBe('DATA_NOT_AVAILABLE')

    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(section.default).toContain('props.historyData?.latest')
    expect(section.default).toContain('props.historyData?.data_success')
    expect(section.default).toContain("return { text: '暂无数据', class: 'warn' }")
  })
})
