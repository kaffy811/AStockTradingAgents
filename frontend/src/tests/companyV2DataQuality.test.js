import { describe, expect, it } from 'vitest'
import sectionRaw from '../components/company-v2/CompanyV2Section.vue?raw'
import cardsRaw from '../components/company-v2/CompanyV2MetricCards.vue?raw'
import tableRaw from '../components/company-v2/CompanyV2FallbackTable.vue?raw'
import debugRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'
import stockDetailRaw from '../views/StockDetailView.vue?raw'
import companyV2Raw from '../views/CompanyV2View.vue?raw'

describe('CompanyV2 data quality UI', () => {
  it('renders backend display_value and keeps raw_value in tooltip', () => {
    expect(cardsRaw).toContain('item.displayValue')
    expect(cardsRaw).toContain('raw_value')
    expect(cardsRaw).toContain('computed_formula')
    expect(tableRaw).toContain('display_fields')
  })

  it('renders coverage badge and diagnosis tags', () => {
    expect(sectionRaw).toContain('coverage.coverage_pct')
    expect(sectionRaw).toContain('diagnosisTags')
    expect(sectionRaw).toContain('OK_WITH_FALLBACK')
    expect(sectionRaw).toContain('PARTIAL_DATA')
    expect(sectionRaw).toContain('LOW_COVERAGE')
  })

  it('exposes field_trace and provider_summary in debug UI', () => {
    expect(sectionRaw).toContain('field_trace')
    expect(debugRaw).toContain('provider_summary')
    expect(debugRaw).toContain('providers_data_success')
    expect(debugRaw).toContain('overall_coverage')
  })

  it('keeps report empty states distinct from OK', () => {
    expect(sectionRaw).toContain('REPORT_PDF_NOT_FOUND')
    expect(sectionRaw).toContain('REPORT_NOT_INGESTED')
    expect(sectionRaw).toContain('暂未接入可确认报告文件')
    expect(sectionRaw).toContain('尚未接入可检索的年报片段')
  })

  it('keeps legacy switch and bottom sentinel available', () => {
    expect(stockDetailRaw).toContain("companyV2Query.value !== '0'")
    expect(companyV2Raw).toContain('company-v2-bottom-sentinel')
  })
})
