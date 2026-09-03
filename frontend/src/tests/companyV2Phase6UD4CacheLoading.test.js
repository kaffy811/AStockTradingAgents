describe('CompanyV2 Phase 6U-D4 cache and progressive loading', () => {
  it('removes normal report metric cards while keeping debug diagnostics available', async () => {
    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')

    expect(section.default).toContain("props.moduleKey === 'report_documents' && !debugMode.value")
    expect(section.default).toContain("report_documents: ['documents_count', 'chunks_count', 'embedding_count']")
    expect(docs.default).toContain('debugMode && reportSummary.report_count > 0')
    expect(docs.default).toContain('chunks {{ reportSummary.chunk_count }}')
  })

  it('uses a single report list summary for discovered and analyzable counts', async () => {
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')

    expect(docs.default).toContain('summaryText')
    expect(docs.default).toContain('已发现 ${reportSummary.value.report_count} 份官方报告')
    expect(docs.default).toContain('ready_count')
    expect(docs.default).toContain('reportSummary.value.ready_count === 0')
  })

  it('does not duplicate quote valuation or amount fields in the normal quote summary', async () => {
    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    const stock = await import('../components/company-v2/CompanyV2StockBasicCard.vue?raw')

    expect(section.default).toContain("quote_overview: ['latest_price', 'pct_chg', 'turnover', 'market_cap']")
    expect(stock.default).toContain("label: '最新价'")
    expect(stock.default).not.toContain("key: 'amount'")
    expect(stock.default).not.toContain("label: '成交额'")
  })

  it('renders progressive skeletons and timeout retry instead of blocking the whole page', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')

    expect(view.default).toContain('profile-skeleton')
    expect(view.default).toContain('quote-skeleton')
    expect(view.default).toContain('financial-module-skeletons')
    expect(view.default).toContain('pageTimedOut')
    expect(view.default).toContain('加载超时，可重试')
    expect(view.default).toContain('setTimeout')
  })

  it('updates profile and history independently before full envelope completes', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')

    expect(view.default).toContain('const basicPromise = getCompanyV2Profile')
    expect(view.default).toContain('stockBasic.value = { ...(stockBasic.value || {}), ...(data || {}) }')
    expect(view.default).toContain('const historyPromise = getCompanyV2History')
    expect(view.default).toContain('historyData.value = data || {}')
  })
})
