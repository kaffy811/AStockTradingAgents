/**
 * Phase 6T-C: Official disclosure verification UI tests.
 */
import { describe, expect, it } from 'vitest'

describe('CompanyV2 official verification UI', () => {
  it('report timeline shows PDF status', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('cv2-rt-pdf-status')
    expect(raw.default).toContain('PDF discovered')
    expect(raw.default).toContain('PDF parsed')
  })

  it('report timeline renders verification badge', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('cv2-rt-verification-badge')
    expect(raw.default).toContain('年年度报告核验部分字段')
    expect(raw.default).toContain('结构化数据与年报字段存在差异')
  })

  it('report documents exposes parse and verify actions', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(raw.default).toContain('downloadCompanyV2Report')
    expect(raw.default).toContain('parseCompanyV2Report')
    expect(raw.default).toContain('verifyCompanyV2Report')
    expect(raw.default).toContain('下载/解析')
  })

  it('API client has report verification endpoints', async () => {
    const raw = await import('../api/companyV2.js?raw')
    expect(raw.default).toContain('/download')
    expect(raw.default).toContain('/parse')
    expect(raw.default).toContain('/verify')
    expect(raw.default).toContain('/verification')
  })

  it('metric cards render CNINFO verified and conflict badges', async () => {
    const raw = await import('../components/company-v2/CompanyV2MetricCards.vue?raw')
    expect(raw.default).toContain('CNINFO verified')
    expect(raw.default).toContain('Conflict')
    expect(raw.default).toContain('cv2-source-badge')
  })

  it('metric cards do not render local path', async () => {
    const raw = await import('../components/company-v2/CompanyV2MetricCards.vue?raw')
    expect(raw.default).not.toContain('local_path')
  })

  it('report timeline does not render local path', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).not.toContain('local_path')
  })

  it('does not include actionable investment wording', async () => {
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    const cards = await import('../components/company-v2/CompanyV2MetricCards.vue?raw')
    const text = `${timeline.default}\n${cards.default}`
    for (const word of ['买入', '卖出', '目标价', '保证上涨']) {
      expect(text).not.toContain(word)
    }
  })
})
