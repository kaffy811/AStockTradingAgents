/**
 * Phase 6T-C1: live annual-history official verification UI tests.
 */
import { describe, expect, it } from 'vitest'

describe('CompanyV2 live official verification UI', () => {
  it('verified badge message renders', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('已按')
    expect(raw.default).toContain('年年度报告核验部分字段')
  })

  it('partial badge message renders', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('部分字段已核验，其余字段缺少可靠抽取结果')
  })

  it('period mismatch message renders', async () => {
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(timeline.default).toContain('当前年报年份与结构化数据期间不一致，已跳过强核验')
    expect(docs.default).toContain('当前年报年份与结构化数据期间不一致，已跳过强核验')
  })

  it('conflict badge renders', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('结构化数据与年报字段存在差异')
    expect(raw.default).toContain('verificationClass')
  })

  it('local path is not rendered', async () => {
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(timeline.default).not.toContain('local_path')
    expect(docs.default).not.toContain('local_path')
  })

  it('does not include actionable investment wording', async () => {
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    const text = `${timeline.default}\n${docs.default}`
    for (const word of ['买入', '卖出', '目标价', '保证上涨']) {
      expect(text).not.toContain(word)
    }
  })
})
