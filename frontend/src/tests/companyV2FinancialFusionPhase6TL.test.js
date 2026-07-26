import { describe, expect, it } from 'vitest'

describe('CompanyV2FinancialEvidenceFusionPanel Phase 6T-L', () => {
  it('keeps polling and result hydration separated', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue?raw')
    expect(raw.default).toContain('getCompanyV2FinancialFusionJob(')
    expect(raw.default).toContain('getCompanyV2FinancialFusionJobResult(')
    expect(raw.default).toContain('if (job.terminal)')
    expect(raw.default).toContain('pollTimer = setTimeout(() => pollJob(job.job_id)')
    expect(raw.default).toContain('getCompanyV2FinancialFusionReadiness')
    expect(raw.default).not.toContain('onMounted(runFusion)')
  })
})
