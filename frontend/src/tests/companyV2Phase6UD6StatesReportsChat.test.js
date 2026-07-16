import { describe, expect, it } from 'vitest'

describe('CompanyV2 Phase 6U-D6 states, reports, and contextual chat', () => {
  it('hides normal status badges in normal mode', async () => {
    const raw = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(raw.default).toContain('v-if="debugMode || impactStatus"')
    expect(raw.default).toContain('debugMode ? statusLabel : impactStatus.text')
    expect(raw.default).toContain('return null')
  })

  it('uses concise empty module copy instead of internal unavailable labels', async () => {
    const raw = await import('../components/company-v2/CompanyV2UnavailablePanel.vue?raw')
    expect(raw.default).toContain('当前暂无该类数据。')
    expect(raw.default).not.toContain('暂无可展示字段')
  })

  it('shows extreme outlier warning as impactful status', async () => {
    const raw = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(raw.default).toContain('moduleOutlierStatus.value ===')
    expect(raw.default).toContain('极端值可能受低基数影响')
    expect(raw.default).toContain('cashflowWarning')
  })

  it('filters non-full annual announcements in normal report timeline', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('visibleReports')
    expect(raw.default).toContain("item.report_document_kind === 'annual_full'")
    expect(raw.default).toContain('if (debugMode.value) return props.reports')
  })

  it('keeps comparison answer as a rendered financial table path', async () => {
    const raw = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(raw.default).toContain('分析此报告')
  })
})
