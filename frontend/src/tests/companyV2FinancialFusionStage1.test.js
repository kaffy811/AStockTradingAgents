import { describe, expect, it } from 'vitest'

describe('CompanyV2FinancialEvidenceFusionPanel Stage 1', () => {
  it('shows explicit pilot labels and readiness controls', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue?raw')
    expect(raw.default).toContain('实验性官方证据核验')
    expect(raw.default).toContain('需手动运行')
    expect(raw.default).toContain('readinessStatusLabel')
    expect(raw.default).toContain('getCompanyV2FinancialFusionReadiness')
    expect(raw.default).toContain('prepareCompanyV2FinancialFusionStep')
    expect(raw.default).toContain('cached')
    expect(raw.default).toContain('newly computed')
  })

  it('exposes readiness states and one-step prepare buttons without auto action', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue?raw')
    expect(raw.default).toContain('report_not_discovered')
    expect(raw.default).toContain('pdf_not_downloaded')
    expect(raw.default).toContain('parse_pending')
    expect(raw.default).toContain('rag_not_indexed')
    expect(raw.default).toContain('structured_data_missing')
    // One prepare button per step with a dynamic testid binding:
    // :data-testid="`fusion-prepare-${step}`" covers download/parse/index.
    expect(raw.default).toContain('fusion-prepare-${step}')
    expect(raw.default).toContain('prepareStep(step)')
    expect(raw.default).not.toContain('onMounted(runFusion)')
    expect(raw.default).not.toContain('auto_run')
    expect(raw.default).not.toContain('local_path')
  })
})
