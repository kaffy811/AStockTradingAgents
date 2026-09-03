import { describe, expect, it } from 'vitest'

describe('CompanyV2ReportComparisonPanel', () => {
  it('renders explicit comparison entry and does not auto compare', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportComparisonPanel.vue?raw')
    expect(raw.default).toContain('report-comparison-panel')
    expect(raw.default).toContain('report-compare-checkbox')
    expect(raw.default).toContain('report-compare-submit')
    expect(raw.default).toContain('compareCompanyV2ReportRag')
    expect(raw.default).not.toContain('onMounted(compare')
  })

  it('supports 2 to 4 selected reports only and resets on symbol switch', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportComparisonPanel.vue?raw')
    expect(raw.default).toContain('selectedReportIds.length < 2')
    expect(raw.default).toContain('selectedReportIds.length >= 4')
    expect(raw.default).toContain('watch(() => props.symbol')
    expect(raw.default).toContain("comparisonMode.value = 'generic_comparison'")
  })

  it('shows report year, type, page citations and no local_path', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportComparisonPanel.vue?raw')
    expect(raw.default).toContain('report_year')
    expect(raw.default).toContain('report_type')
    expect(raw.default).toContain('第 {{ citation.page }} 页')
    expect(raw.default).not.toContain('local_path')
  })

  it('documents view exposes explicit comparison entry', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(raw.default).toContain('report-compare-toggle')
    expect(raw.default).toContain('showComparison = ref(false)')
    expect(raw.default).toContain('CompanyV2ReportComparisonPanel')
  })

  it('api exposes compare endpoint with report_ids body', async () => {
    const api = await import('../api/companyV2.js?raw')
    expect(api.default).toContain('/reports/rag/compare')
    expect(api.default).toContain('report_ids')
  })
})
