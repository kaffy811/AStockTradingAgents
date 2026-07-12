import { describe, expect, it } from 'vitest'

describe('CompanyV2FinancialFusion Phase 6T-K job UX', () => {
  it('uses manual async jobs and cleans up polling', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue?raw')
    expect(raw.default).toContain('核验官方报告')
    expect(raw.default).toContain('createCompanyV2FinancialFusionJob')
    expect(raw.default).toContain('pollJob')
    expect(raw.default).toContain('stopPolling')
    expect(raw.default).toContain('onBeforeUnmount')
    expect(raw.default).toContain('cancelFusion')
    expect(raw.default).toContain('activeJob.terminal')
    expect(raw.default).toContain('cached')
    expect(raw.default).not.toContain('onMounted(runFusion)')
  })

  it('keeps PDF viewing independent from fusion job state', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue?raw')
    expect(raw.default).toContain('官方报告查看')
    expect(raw.default).toContain('fusion-view-report')
    expect(raw.default).toContain('report_view_ready')
    expect(raw.default).toContain('href="')
    expect(raw.default).toContain('rel="noopener noreferrer"')
  })

  it('exposes job API helpers without local paths', async () => {
    const api = await import('../api/companyV2.js?raw')
    expect(api.default).toContain('createCompanyV2FinancialFusionJob')
    expect(api.default).toContain('getCompanyV2FinancialFusionJobResult')
    expect(api.default).toContain('cancelCompanyV2FinancialFusionJob')
    expect(api.default).not.toContain('local_path')
  })
})
