import { describe, expect, it } from 'vitest'

describe('CompanyV2FinancialEvidenceFusionPanel stage2 viewing split', () => {
  it('renders a direct official PDF link separate from RAG actions', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue?raw')
    expect(raw.default).toContain('官方报告查看')
    expect(raw.default).toContain('fusion-view-report')
    expect(raw.default).toContain('href="')
    expect(raw.default).toContain('target="_blank"')
    expect(raw.default).toContain('rel="noopener noreferrer"')
    expect(raw.default).toContain('download')
    expect(raw.default).toContain('parse')
    expect(raw.default).toContain('index')
    expect(raw.default).toContain('fusion')
  })

  it('keeps report view readiness separate from RAG readiness', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue?raw')
    expect(raw.default).toContain('report_view_ready')
    expect(raw.default).toContain('pdf_url_ready')
    expect(raw.default).toContain('next_manual_action_for_view')
    expect(raw.default).toContain('next_manual_action_for_rag')
    expect(raw.default).toContain('next_manual_action_for_fusion')
    expect(raw.default).toContain('官方报告链接暂不可用')
  })
})
