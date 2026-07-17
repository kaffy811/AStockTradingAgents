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

  it('D6.4 strips body disclaimer and keeps footer as the single owner', async () => {
    const listRaw = await import('../components/chat/ChatMessageList.vue?raw')
    const viewRaw = await import('../views/ChatCopilotView.vue?raw')
    expect(listRaw.default).toContain('stripStandardDisclaimer(msg.content)')
    expect(listRaw.default).toContain('仅供研究参考，不构成投资建议')
    expect(viewRaw.default).toContain('chat-disclaimer')
  })

  it('D6.4 report chat source evidence is collapsed by default', async () => {
    const raw = await import('../components/fundamentals/ReportChatPanel.vue?raw')
    expect(raw.default).toContain('<details v-if="result.source_chunks?.length"')
    expect(raw.default).toContain('查看数据来源')
    expect(raw.default).toContain('isDebugMode && result.review_audit?.source_chunks_checked')
  })

  it('D6.4 normal thinking trace hides internal agent and skill names', async () => {
    const raw = await import('../components/chat/ChatThinkingMiniPanel.vue?raw')
    expect(raw.default).toContain('sanitizeTraceContent')
    expect(raw.default).toContain('ReportChatCopilotAgent|MultiCompanyFinancialComparisonAgent')
    expect(raw.default).toContain("agent:   ''")
  })
})
