import { describe, expect, it } from 'vitest'
import stockDetailRaw from '../views/StockDetailView.vue?raw'
import companyV2Raw from '../views/CompanyV2View.vue?raw'
import debugPanelRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'
import sectionRaw from '../components/company-v2/CompanyV2Section.vue?raw'

const forbidden = 'DATA_MODE=free：BaoStock 和 AkShare 均未返回数据，请检查 ENABLE_BAOSTOCK / ENABLE_AKSHARE 配置。'

describe('CompanyV2 rollout gate', () => {
  it('keeps env-controlled production default and dev/staging v2 fallback', () => {
    expect(stockDetailRaw).toContain("import.meta.env.PROD ? 'legacy' : 'v2'")
    expect(stockDetailRaw).toContain('VITE_COMPANY_TAB_VERSION')
  })

  it('supports URL force v2 and force legacy overrides', () => {
    expect(stockDetailRaw).toContain("companyV2Query.value === '1'")
    expect(stockDetailRaw).toContain("companyV2Query.value !== '0'")
  })

  it('keeps legacy accessible and falls back when embedded CompanyV2 load fails', () => {
    expect(stockDetailRaw).toContain('CompanyFundamentalsPanel')
    expect(stockDetailRaw).toContain('companyV2TabFailed')
    expect(stockDetailRaw).toContain('@load-error="onCompanyV2LoadError"')
  })

  it('does not include forbidden legacy DATA_MODE or advice wording in CompanyV2 UI', () => {
    const source = [companyV2Raw, debugPanelRaw, sectionRaw].join('\n')
    expect(source).not.toContain(forbidden)
    expect(source).not.toContain('target_price')
    expect(source).not.toContain('analyst_rating')
    expect(source).not.toContain('建议买入')
    expect(source).not.toContain('建议卖出')
    expect(source).not.toContain('保证上涨')
  })
})
