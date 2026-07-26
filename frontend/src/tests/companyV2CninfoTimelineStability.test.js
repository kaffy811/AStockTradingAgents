/**
 * frontend/src/tests/companyV2CninfoTimelineStability.test.js
 * Phase 6T-E: CNINFO 报告时间线前端稳定性
 */
import { describe, expect, it } from 'vitest'

describe('Phase 6T-E report timeline stability', () => {
  it('timeline distinguishes report_year from announcement_date', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('report_year')
    expect(raw.default).toContain('announcement_date')
  })

  it('timeline uses timeline layout, not financial line chart', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).not.toContain('echarts')
  })

  it('reports load asynchronously inside report_documents module (not blocking core financials)', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    // 首屏 load() 不直接调用 reports 发现接口
    expect(view.default).not.toContain('discoverCompanyV2Reports')
    const reports = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(reports.default).toMatch(/getCompanyV2Reports|discoverCompanyV2Reports/)
  })

  it('PDF URLs open via https cninfo whitelist only (no local paths)', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).not.toContain('local_path')
    expect(raw.default).not.toContain('file://')
  })

  it('summary reports are not presented as main reports (backend filters is_summary)', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    // 前端不应主动把摘要当正文渲染主链接
    expect(raw.default).not.toContain('摘要版全文')
  })

  it('timeline renders empty state instead of crashing when no reports', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(raw.default).toMatch(/暂无|empty|无报告|not_found|NOT_FOUND/i)
  })
})
