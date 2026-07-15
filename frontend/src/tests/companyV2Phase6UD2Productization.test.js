describe('CompanyV2 Phase 6U-D2 productization', () => {
  it('hides diagnostics in normal mode and gates them with debugMode', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(view.default).toContain('VITE_COMPANY_V2_DEBUG')
    expect(view.default).toContain('v-if="debugMode" class="cv2-debug-details"')
    expect(section.default).toContain('v-if="debugMode" class="cv2-source-chain"')
    expect(section.default).toContain('v-if="debugMode" :data="envelope"')
  })

  it('does not duplicate valuation ratios in the quote summary', async () => {
    const stock = await import('../components/company-v2/CompanyV2StockBasicCard.vue?raw')
    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(stock.default).not.toContain('pe_ttm')
    expect(stock.default).not.toContain('pcf_ncf_ttm')
    expect(section.default).toContain("valuation: ['pe_ttm', 'pb', 'ps_ttm', 'pcf_ncf_ttm']")
  })

  it('uses Chinese business labels and avoids internal duplicate fields', async () => {
    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(section.default).toContain("parent_net_profit_yoy: '归母净利润同比'")
    expect(section.default).toContain("cashflow_quality: ['ocf_to_np', 'ocf_to_revenue']")
    expect(section.default).toContain("!['cashflow_revenue_ratio', 'dupont_npi'")
  })

  it('auto loads reports and gates admin controls', async () => {
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(docs.default).toContain('scheduleAutoDiscover')
    expect(docs.default).toContain('autoDiscoverKey')
    expect(docs.default).toContain('v-if="debugMode" class="cv2-rd-toolbar"')
    expect(timeline.default).toContain('分析此报告')
    expect(timeline.default).toContain('v-if="debugMode" class="cv2-rt-toolbar"')
  })

  it('downgrades unsafe charts for single point and dupont mismatch', async () => {
    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(section.default).toContain('tableRows.value.length >= 2')
    expect(section.default).toContain('!dupontMismatch.value')
    expect(section.default).toContain('指标口径或期间不一致，暂不进行杜邦拆解')
  })
})
