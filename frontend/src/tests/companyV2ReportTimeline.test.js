/**
 * frontend/src/tests/companyV2ReportTimeline.test.js
 * Phase 6T-B: Report Timeline 验收测试
 */
import { describe, expect, it } from 'vitest'

describe('CompanyV2ReportTimeline', () => {
  it('component source has filter tabs', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('filterTabs')
    expect(raw.default).toContain('activeFilter')
  })

  it('has annual filter tab', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('annual')
    expect(raw.default).toContain('年报')
  })

  it('has semi_annual filter tab', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('semi_annual')
    expect(raw.default).toContain('半年报')
  })

  it('has q1 and q3 filter tabs', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('q1')
    expect(raw.default).toContain('q3')
    expect(raw.default).toContain('一季报')
    expect(raw.default).toContain('三季报')
  })

  it('has open PDF button', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('打开 PDF')
    expect(raw.default).toContain('open-pdf-btn')
  })

  it('has copy URL button', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('复制链接')
    expect(raw.default).toContain('copyUrl')
  })

  it('has expand/collapse for showing all reports', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('expanded')
    expect(raw.default).toContain('查看全部')
  })

  it('shows RAG status as badge only (not independent module)', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('rag_status')
    expect(raw.default).toContain('cv2-rt-rag-badge')
    // Should not have 'report_rag' as independent section
    expect(raw.default).not.toContain('<section')
  })

  it('renders year label per report', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('report_year')
    expect(raw.default).toContain('cv2-rt-year')
  })

  it('has discover and force refresh buttons', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('发现报告')
    expect(raw.default).toContain('强制刷新')
  })

  it('has manual URL input button', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('手动录入')
  })

  it('shows disclaimer about not being investment advice', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('不构成投资建议')
  })

  it('has data-testid attributes for testing', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('data-testid="report-timeline"')
    expect(raw.default).toContain('data-testid="report-empty"')
  })

  it('uses is_correction badge for corrected reports', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('is_correction')
    expect(raw.default).toContain('更正版')
  })
})
