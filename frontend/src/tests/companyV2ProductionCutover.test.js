import { describe, expect, it } from 'vitest'
import stockDetailRaw from '../views/StockDetailView.vue?raw'
import companyV2Raw from '../views/CompanyV2View.vue?raw'
import debugPanelRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'
import sectionRaw from '../components/company-v2/CompanyV2Section.vue?raw'
import apiRaw from '../api/companyV2.js?raw'

const forbidden = 'DATA_MODE=free：BaoStock 和 AkShare 均未返回数据，请检查 ENABLE_BAOSTOCK / ENABLE_AKSHARE 配置。'

describe('CompanyV2 production cutover preparation', () => {
  it('keeps production default controlled by env with safe code fallback', () => {
    expect(stockDetailRaw).toContain("import.meta.env.PROD ? 'legacy' : 'v2'")
    expect(stockDetailRaw).toContain('VITE_COMPANY_TAB_VERSION')
  })

  it('supports force v2 and force legacy URL switches', () => {
    expect(stockDetailRaw).toContain("companyV2Query.value === '1'")
    expect(stockDetailRaw).toContain("companyV2Query.value !== '0'")
  })

  it('keeps fallback-to-legacy path for embedded CompanyV2 errors', () => {
    expect(companyV2Raw).toContain("defineEmits(['load-error'])")
    expect(companyV2Raw).toContain("emit('load-error', e)")
    expect(stockDetailRaw).toContain('companyV2TabFailed')
    expect(stockDetailRaw).toContain('CompanyFundamentalsPanel')
  })

  it('does not include legacy DATA_MODE message or advice wording in v2 UI/client', () => {
    const source = [companyV2Raw, debugPanelRaw, sectionRaw, apiRaw].join('\n')
    expect(source).not.toContain(forbidden)
    expect(source).not.toContain('target_price')
    expect(source).not.toContain('analyst_rating')
    expect(source).not.toContain('建议买入')
    expect(source).not.toContain('建议卖出')
    expect(source).not.toContain('保证上涨')
  })

  it('passes request options needed for production diagnostics without secrets', () => {
    expect(apiRaw).toContain('include_raw')
    expect(apiRaw).toContain('force_refresh')
    expect(apiRaw).toContain('max_raw_chars')
    expect(apiRaw).not.toContain('SECRET')
    expect(apiRaw).not.toContain('local_path')
  })
})
