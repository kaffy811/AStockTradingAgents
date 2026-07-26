import { describe, expect, it } from 'vitest'
import companyV2Raw from '../views/CompanyV2View.vue?raw'
import stockDetailRaw from '../views/StockDetailView.vue?raw'
import debugPanelRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'

const forbidden = 'DATA_MODE=free：BaoStock 和 AkShare 均未返回数据，请检查 ENABLE_BAOSTOCK / ENABLE_AKSHARE 配置。'

describe('CompanyV2 replacement gate', () => {
  it('renders bottom sentinel and avoids locked vertical page scroll', () => {
    expect(companyV2Raw).toContain('data-testid="company-v2-bottom-sentinel"')
    expect(companyV2Raw).not.toContain('height: 100vh')
    expect(companyV2Raw).not.toContain('overflow: hidden')
  })

  it('supports query and env gate without removing legacy route', () => {
    expect(stockDetailRaw).toContain('VITE_COMPANY_TAB_VERSION')
    expect(stockDetailRaw).toContain("companyV2Query.value !== '0'")
    expect(stockDetailRaw).toContain('CompanyFundamentalsPanel')
    expect(stockDetailRaw).toContain('CompanyV2View')
  })

  it('does not use forbidden legacy DATA_MODE message in CompanyV2', () => {
    expect(companyV2Raw).not.toContain(forbidden)
    expect(debugPanelRaw).not.toContain(forbidden)
    expect(debugPanelRaw).toContain('已展示当前可用的公开数据')
  })
})
