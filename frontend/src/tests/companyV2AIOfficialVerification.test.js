import { describe, expect, it } from 'vitest'

describe('CompanyV2 AI official verification UI', () => {
  it('renders AI verify button hook', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('AI 校对')
    expect(raw.default).toContain('ai-verify-report-btn')
  })

  it('renders AI badge text and class', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('cv2-rt-ai-badge')
    expect(raw.default).toContain('AI 校对通过，无需人工复核')
  })

  it('renders human review queue and evidence excerpt', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('human_review_queue')
    expect(raw.default).toContain('以下字段建议人工抽检')
    expect(raw.default).toContain('evidence_excerpt')
    expect(raw.default).toContain('shortEvidence')
  })

  it('does not render local_path', async () => {
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(timeline.default).not.toContain('local_path')
    expect(docs.default).not.toContain('local_path')
  })

  it('does not include prohibited advice wording', async () => {
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    const text = `${timeline.default}\n${docs.default}`
    for (const word of ['买入', '卖出', '目标价', '保证上涨']) {
      expect(text).not.toContain(word)
    }
  })
})
