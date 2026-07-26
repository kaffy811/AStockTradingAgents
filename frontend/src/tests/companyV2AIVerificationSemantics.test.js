import { describe, expect, it } from 'vitest'

describe('CompanyV2 AI verification semantics UI', () => {
  it('true conflict uses conflict label', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('同期同口径数据存在差异')
    expect(raw.default).toContain("status === 'conflict'")
    expect(raw.default).toContain("return 'conflict'")
  })

  it('period mismatch uses warning label', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('period_basis_mismatch')
    expect(raw.default).toContain('数据期间或时点不同')
    expect(raw.default).toContain("return 'warning'")
  })

  it('definition mismatch uses warning label', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('definition_mismatch')
    expect(raw.default).toContain('字段口径不同')
  })

  it('definition mismatch uses field-specific wording', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('营业收入字段口径不同')
    expect(raw.default).toContain('净利润与归母净利润口径不同')
    expect(raw.default).toContain('ROE 与加权平均 ROE 口径不同')
    expect(raw.default).not.toContain('数据错误')
  })

  it('missing field uses neutral label', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('structured_field_missing')
    expect(raw.default).toContain('结构化数据缺少该字段')
    expect(raw.default).toContain('official_field_not_found')
    expect(raw.default).toContain("return 'neutral'")
  })

  it('human review count renders through queue list', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('human_review_queue')
    expect(raw.default).toContain('以下字段建议人工抽检')
    expect(raw.default).toContain('slice(0, 4)')
  })

  it('non-blocking findings render lightly', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('non_blocking_findings')
    expect(raw.default).toContain('非阻断发现')
    expect(raw.default).toContain('cv2-rt-ai-findings')
  })

  it('does not render local_path', async () => {
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(timeline.default).not.toContain('local_path')
    expect(docs.default).not.toContain('local_path')
  })
})
