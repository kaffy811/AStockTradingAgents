import { describe, expect, it } from 'vitest'

describe('CompanyV2ReportRagIndexManager', () => {
  it('has report selector in QA panel and clears answer on switch', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    expect(raw.default).toContain('report-rag-selector')
    expect(raw.default).toContain('handleReportSwitch')
    expect(raw.default).toContain('answer.value = null')
    expect(raw.default).toContain('question.value =')
  })

  it('uses selected report id for query/index/status/job', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    expect(raw.default).toContain('selectedReport')
    expect(raw.default).toContain('reportId.value')
    expect(raw.default).toContain('getCompanyV2ReportRagJob')
  })

  it('has index manager operations and delete confirmation', async () => {
    const raw = await import('../components/company-v2/reports/CompanyV2ReportRagIndexManager.vue?raw')
    expect(raw.default).toContain('报告索引管理')
    expect(raw.default).toContain('refreshCompanyV2ReportRagIndex')
    expect(raw.default).toContain('deleteCompanyV2ReportRagIndex')
    expect(raw.default).toContain('window.confirm')
  })

  it('index manager is not mounted by default', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(raw.default).toContain('showIndexManager = ref(false)')
    expect(raw.default).toContain('v-if="showIndexManager"')
    expect(raw.default).toContain('report-rag-manager-toggle')
  })

  it('api supports multi-report index management paths', async () => {
    const raw = await import('../api/companyV2.js?raw')
    expect(raw.default).toContain('/reports/rag/indexes')
    expect(raw.default).toContain('/rag/refresh')
    expect(raw.default).toContain("method: 'DELETE'")
    expect(raw.default).toContain('/rag/job')
  })

  it('does not show local_path or batch index all reports', async () => {
    const manager = await import('../components/company-v2/reports/CompanyV2ReportRagIndexManager.vue?raw')
    const panel = await import('../components/company-v2/reports/CompanyV2ReportQaPanel.vue?raw')
    expect(manager.default).not.toContain('local_path')
    expect(panel.default).not.toContain('local_path')
    expect(manager.default).not.toContain('batch')
  })
})
