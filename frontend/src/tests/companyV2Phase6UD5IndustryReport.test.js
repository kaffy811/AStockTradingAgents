import { describe, expect, it } from 'vitest'

describe('CompanyV2 Phase 6U-D5 industry-aware UI', () => {
  it('renders bank not-applicable fields as industry-specific hints', async () => {
    const raw = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(raw.default).toContain('该行业不适用这些指标')
    expect(raw.default).toContain('industry-recommended-metrics')
    expect(raw.default).toContain("net_interest_margin: '净息差'")
    expect(raw.default).toContain("non_performing_loan_ratio: '不良贷款率'")
  })

  it('hides internal error codes in normal unavailable panel', async () => {
    const raw = await import('../components/company-v2/CompanyV2UnavailablePanel.vue?raw')
    expect(raw.default).toContain('当前暂无该类数据。')
    expect(raw.default).toContain("OUTLIER_REQUIRES_REVIEW: '指标口径待确认'")
    expect(raw.default).not.toContain("{{ reason || 'ALL_NULL_ROWS' }}")
  })

  it('surfaces outlier review as friendly warning', async () => {
    const raw = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(raw.default).toContain('outlierWarning')
    expect(raw.default).toContain('部分历史指标口径待确认')
  })
})
