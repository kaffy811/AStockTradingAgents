/**
 * frontend/src/tests/companyV2CompanyProfile.test.js
 * Phase 6T-B: CompanyProfileCard + StockBasicCard 验收测试
 */
import { describe, expect, it } from 'vitest'

describe('CompanyV2CompanyProfileCard', () => {
  it('component source renders company_name', async () => {
    const raw = await import('../components/company-v2/CompanyV2CompanyProfileCard.vue?raw')
    expect(raw.default).toContain('company_name')
    expect(raw.default).toContain('companyName')
  })

  it('shows stock code and exchange', async () => {
    const raw = await import('../components/company-v2/CompanyV2CompanyProfileCard.vue?raw')
    expect(raw.default).toContain('symbol')
    expect(raw.default).toContain('exchange')
  })

  it('shows list_date', async () => {
    const raw = await import('../components/company-v2/CompanyV2CompanyProfileCard.vue?raw')
    expect(raw.default).toContain('list_date')
    expect(raw.default).toContain('上市日期')
  })

  it('shows industry and area', async () => {
    const raw = await import('../components/company-v2/CompanyV2CompanyProfileCard.vue?raw')
    expect(raw.default).toContain('industry')
    expect(raw.default).toContain('area')
    expect(raw.default).toContain('行业')
    expect(raw.default).toContain('地区')
  })

  it('marks seed data with badge', async () => {
    const raw = await import('../components/company-v2/CompanyV2CompanyProfileCard.vue?raw')
    expect(raw.default).toContain('listDateStatus')
    expect(raw.default).toContain('seed')
  })

  it('shows data source label', async () => {
    const raw = await import('../components/company-v2/CompanyV2CompanyProfileCard.vue?raw')
    expect(raw.default).toContain('数据来源')
    expect(raw.default).toContain('sourceLabel')
  })

  it('does not contain investment advice language', async () => {
    const raw = await import('../components/company-v2/CompanyV2CompanyProfileCard.vue?raw')
    const src = raw.default
    expect(src).not.toContain('买入')
    expect(src).not.toContain('卖出')
    expect(src).not.toContain('目标价')
  })
})

describe('CompanyV2StockBasicCard', () => {
  it('renders price from quoteRow', async () => {
    const raw = await import('../components/company-v2/CompanyV2StockBasicCard.vue?raw')
    expect(raw.default).toContain('quoteRow')
    expect(raw.default).toContain('latest_price')
    expect(raw.default).toContain('recent_close')
  })

  it('keeps valuation ratios out of top quote summary', async () => {
    const raw = await import('../components/company-v2/CompanyV2StockBasicCard.vue?raw')
    expect(raw.default).not.toContain('pe_ttm')
    expect(raw.default).not.toContain('ps_ttm')
    expect(raw.default).not.toContain('pcf_ncf_ttm')
    expect(raw.default).toContain('turnover')
    expect(raw.default).not.toContain("key: 'amount'")
  })

  it('renders total market cap without duplicating float market cap', async () => {
    const raw = await import('../components/company-v2/CompanyV2StockBasicCard.vue?raw')
    expect(raw.default).toContain('market_cap')
    expect(raw.default).toContain('总市值')
    expect(raw.default).not.toContain('流通市值')
  })

  it('has non-realtime price handling', async () => {
    const raw = await import('../components/company-v2/CompanyV2StockBasicCard.vue?raw')
    // Should not say "实时" - only non-realtime language
    expect(raw.default).not.toContain('"实时"')
    expect(raw.default).not.toContain("'实时'")
  })

  it('has positive/negative color classes for A-stock convention (red up/green down)', async () => {
    const raw = await import('../components/company-v2/CompanyV2StockBasicCard.vue?raw')
    // A股：涨红跌绿
    expect(raw.default).toContain('cv2-positive')
    expect(raw.default).toContain('cv2-negative')
  })

  it('does not contain investment advice', async () => {
    const raw = await import('../components/company-v2/CompanyV2StockBasicCard.vue?raw')
    const src = raw.default
    expect(src).not.toContain('买入')
    expect(src).not.toContain('卖出')
    expect(src).not.toContain('保证')
  })
})

// ── CompanyV2Section historyData prop 测试 ────────────────────────────────────

describe('CompanyV2Section with historyData prop', () => {
  it('accepts historyData prop', async () => {
    const raw = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(raw.default).toContain('historyData')
  })

  it('uses history.history rows when available', async () => {
    const raw = await import('../components/company-v2/CompanyV2Section.vue?raw')
    // historyRows or historyData should be referenced for tableRows
    expect(raw.default).toContain('historyData') || expect(raw.default).toContain('historyRows')
  })
})

// ── aicaibao 安全测试 ─────────────────────────────────────────────────────────

describe('No aicaibao data usage', () => {
  it('CompanyV2View does not access aicaibao', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).not.toContain('aicaibao')
  })

  it('CompanyV2Section does not access aicaibao', async () => {
    const raw = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(raw.default).not.toContain('aicaibao')
  })

  it('companyV2.js API client does not access aicaibao', async () => {
    const raw = await import('../api/companyV2.js?raw')
    expect(raw.default).not.toContain('aicaibao')
  })
})
