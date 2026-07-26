import { describe, expect, it } from 'vitest'
import stockDetailRaw from '../views/StockDetailView.vue?raw'
import companyV2Raw from '../views/CompanyV2View.vue?raw'
import debugRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'

describe('CompanyV2 staged cutover', () => {
  it('keeps env controlled v2 default and query rollback precedence', () => {
    expect(stockDetailRaw).toContain('VITE_COMPANY_TAB_VERSION')
    expect(stockDetailRaw).toContain("companyV2Query.value !== '0'")
    expect(stockDetailRaw).toContain("companyV2Query.value === '1'")
    expect(stockDetailRaw).toContain('useCompanyV2Tab')
    expect(stockDetailRaw).toContain('CompanyFundamentalsPanel')
  })

  it('shows cutover debug note without affecting page sentinel', () => {
    expect(debugRaw).toContain('Company Tab Version')
    expect(debugRaw).toContain('Rollback company_v2=0')
    expect(debugRaw).toContain('Schema Version')
    expect(debugRaw).toContain('semantic_warning_count')
    expect(companyV2Raw).toContain('company-v2-bottom-sentinel')
  })

  it('does not include forbidden legacy message or restricted wording', () => {
    const raw = `${stockDetailRaw}\n${companyV2Raw}\n${debugRaw}`
    expect(raw).not.toContain('DATA_MODE=free：BaoStock 和 AkShare 均未返回数据')
    expect(raw).not.toContain('目标价')
    expect(raw).not.toContain('保证上涨')
    expect(raw).not.toContain('建议买入')
    expect(raw).not.toContain('建议卖出')
  })
})
