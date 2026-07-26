import { describe, expect, it } from 'vitest'

describe('CompanyV2ReportQaPanel', () => {
  it('has unindexed and indexing states', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    const status = await import('../components/company-v2/reports/CompanyV2ReportRagStatus.vue?raw')
    expect(status.default).toContain('未索引')
    expect(raw.default).toContain('索引中')
    expect(raw.default).toContain('建立报告问答索引')
  })

  it('does not auto index on mount', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    expect(raw.default).toContain('onMounted(refreshStatus)')
    expect(raw.default).not.toContain('onMounted(buildIndex)')
  })

  it('uses report scoped API paths and report id from selected report only', async () => {
    const api = await import('../api/companyV2.js?raw')
    expect(api.default).toContain('/reports/${reportId}/rag/index')
    expect(api.default).toContain('/reports/${reportId}/rag/status')
    expect(api.default).toContain('/reports/${reportId}/rag/query')
  })

  it('renders query success, insufficient evidence, and citations', async () => {
    const panel = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    const citations = await import('../components/company-v2/reports/CompanyV2ReportCitationList.vue?raw')
    expect(panel.default).toContain('report-rag-answer')
    expect(panel.default).toContain('insufficient_evidence')
    expect(citations.default).toContain('第 {{ citation.page }} 页')
    expect(citations.default).toContain('source_url')
  })

  it('does not show local_path or full PDF text', async () => {
    const panel = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    const citations = await import('../components/company-v2/reports/CompanyV2ReportCitationList.vue?raw')
    expect(panel.default).not.toContain('local_path')
    expect(citations.default).not.toContain('local_path')
    expect(panel.default).not.toContain('text_pages')
  })

  it('timeline has explicit report analysis toggle and is not default expanded', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('分析此报告')
    expect(raw.default).toContain('report-qa-toggle-btn')
    expect(raw.default).toContain('qaOpenId === reportId(item)')
    expect(raw.default).not.toContain('qaOpenId = reportId')
  })

  it('API query body is constrained by top_k and answer_style', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    expect(raw.default).toContain('top_k: 6')
    expect(raw.default).toContain("answer_style: 'concise'")
    expect(raw.default).toContain('maxlength="500"')
  })

  it('investment advice refusal can be displayed as a normal answer without citations', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    expect(raw.default).toContain('answer.answer')
    expect(raw.default).toContain('answer.citations || []')
  })
})
