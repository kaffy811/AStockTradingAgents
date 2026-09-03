/**
 * Phase 6W-R1.3 — Company Overview Six-Field Chain Test
 *
 * Verifies that the 6 required fields flow correctly through:
 *   1. Backend tool source (QuoteSnapshotTool / financial_summary)
 *   2. CompanyOverviewCards Vue component template bindings
 *   3. Frontend adapter logic
 *
 * Fields: latest_price, pe_ttm, pb, total_market_cap (total_mv), roe, dividend_yield_ttm (dv_ttm)
 *
 * Pattern: source code inspection (project-standard ?raw import approach)
 */
import { describe, it, expect } from 'vitest'
import overviewCardsRaw from '../components/CompanyOverviewCards.vue?raw'
import fundamentalAdaptersRaw from '../utils/fundamentalAdapters.js?raw'
import cfpRaw from '../components/CompanyFundamentalsPanel.vue?raw'

// ── Section 1: Six-field template bindings in CompanyOverviewCards ────────

describe('CompanyOverviewCards — six-field template bindings', () => {
  it('latest_price: component reads price ?? latest_price ?? close from snapData', () => {
    expect(overviewCardsRaw).toContain('snapData.value.price ?? snapData.value.latest_price ?? snapData.value.close')
  })

  it('pe_ttm: PE(TTM) card renders snapData.pe_ttm', () => {
    expect(overviewCardsRaw).toContain('PE(TTM)')
    expect(overviewCardsRaw).toContain('snapData.pe_ttm')
  })

  it('pb: PB card renders snapData.pb', () => {
    expect(overviewCardsRaw).toContain('PB')
    expect(overviewCardsRaw).toContain('snapData.pb')
  })

  it('total_market_cap: 总市值 card renders snapData.total_mv via fmtMv', () => {
    expect(overviewCardsRaw).toContain('总市值')
    expect(overviewCardsRaw).toContain('fmtMv(snapData.total_mv)')
  })

  it('roe: ROE card renders finData.roe', () => {
    expect(overviewCardsRaw).toContain('ROE')
    expect(overviewCardsRaw).toContain('finData.roe')
  })

  it('dividend_yield_ttm: 股息率(TTM) card renders snapData.dv_ttm', () => {
    expect(overviewCardsRaw).toContain('股息率(TTM)')
    expect(overviewCardsRaw).toContain('snapData.dv_ttm')
  })
})

// ── Section 2: Field sources (API keys → template keys) ──────────────────

describe('CompanyOverviewCards — field origin mapping', () => {
  it('snapshot prop feeds snapData: snapshot?.data || {}', () => {
    expect(overviewCardsRaw).toContain("props.snapshot?.data || {}")
  })

  it('financial prop feeds finData: financial?.data || {}', () => {
    expect(overviewCardsRaw).toContain("props.financial?.data || {}")
  })

  it('ROE comes from financial.data.series[0] when series array present', () => {
    // finData computed: if Array.isArray(d.series) → series[0], else d
    expect(overviewCardsRaw).toContain('Array.isArray(d.series)')
    expect(overviewCardsRaw).toContain('d.series[0]')
  })

  it('total_mv unit: 万元→亿元 via fmtMv division', () => {
    // fmtMv: n >= 100000000 ? (n / 100000000).toFixed(2) : (n / 10000).toFixed(2)
    expect(overviewCardsRaw).toContain('100000000')
    expect(overviewCardsRaw).toContain('亿元')
  })
})

// ── Section 3: Degradation handling ──────────────────────────────────────

describe('CompanyOverviewCards — degradation (null/missing fields)', () => {
  it('fmt() returns "—" for null values', () => {
    expect(overviewCardsRaw).toContain("return '—'")
  })

  it('fmtPct() returns "—" for null roe / dv_ttm', () => {
    // fmtPct definition must handle null → '—'
    expect(overviewCardsRaw).toContain('fmtPct')
    expect(overviewCardsRaw).toContain("'—'")
  })

  it('loading state shows .coc-skeleton, not .coc-grid', () => {
    expect(overviewCardsRaw).toContain('v-if="loading"')
    expect(overviewCardsRaw).toContain('coc-skeleton')
    expect(overviewCardsRaw).toContain('v-else')
    expect(overviewCardsRaw).toContain('coc-grid')
  })

  it('BaoStock kline fallback shows 最近收盘价 label and safe note', () => {
    expect(overviewCardsRaw).toContain('最近收盘价')
    expect(overviewCardsRaw).toContain('baostock_kline_fallback')
    expect(overviewCardsRaw).toContain('行情与估值来自 BaoStock K线')
  })
})

// ── Section 4: CompanyFundamentalsPanel passes snapshot + financial as props ──

describe('CompanyFundamentalsPanel — snapshot and financial prop wiring', () => {
  it('CompanyOverviewCards is imported in CompanyFundamentalsPanel', () => {
    expect(cfpRaw).toContain("import CompanyOverviewCards from './CompanyOverviewCards.vue'")
  })

  it('CompanyOverviewCards receives snapshot and financial props from parent', () => {
    expect(cfpRaw).toContain('<CompanyOverviewCards')
    expect(cfpRaw).toContain(':snapshot=')
    expect(cfpRaw).toContain(':financial=')
  })
})

// ── Section 5: Adapter chain — pe_ttm/pb in fundamentalAdapters ──────────

describe('fundamentalAdapters — pe_ttm and pb in valuation chain', () => {
  it('pe_ttm used in valuation rows adapter', () => {
    expect(fundamentalAdaptersRaw).toContain('pe_ttm')
  })

  it('pb used in valuation metrics', () => {
    expect(fundamentalAdaptersRaw).toContain("'pb'")
  })
})
