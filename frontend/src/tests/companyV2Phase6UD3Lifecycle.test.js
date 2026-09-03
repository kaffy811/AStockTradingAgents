describe('CompanyV2 Phase 6U-D3 lifecycle and report states', () => {
  it('uses schema-scoped page cache and request generation for re-entry', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('COMPANY_V2_SCHEMA_VERSION')
    expect(raw.default).toContain('companyV2PageCache')
    expect(raw.default).toContain('requestGeneration')
    expect(raw.default).toContain('seq !== _loadSeq')
    expect(raw.default).toContain('onActivated')
  })

  it('resets state on symbol changes and keeps the company tab visited when visible', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    const stockDetail = await import('../views/StockDetailView.vue?raw')
    expect(view.default).toContain('resetViewState')
    expect(view.default).toContain('watch([market, symbol]')
    expect(stockDetail.default).toContain("companyTabVisited.value = activeDetailTab.value === 'company'")
  })

  it('renders company overview fields and expandable long text', async () => {
    const profile = await import('../components/company-v2/CompanyV2CompanyProfileCard.vue?raw')
    expect(profile.default).toContain('shortName')
    expect(profile.default).toContain('registeredAddress')
    expect(profile.default).toContain('officeAddress')
    expect(profile.default).toContain('-webkit-line-clamp: 4')
    expect(profile.default).toContain('展开')
  })

  it('normal mode maps internal status enums and hides raw tables when cards exist', async () => {
    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(section.default).toContain('statusLabel')
    expect(section.default).toContain("OK_WITH_FALLBACK: '部分数据来自备用来源'")
    expect(section.default).toContain("LOW_COVERAGE: '数据覆盖有限'")
    expect(section.default).toContain("REPORT_PDF_NOT_FOUND: '暂无可用财报'")
    expect(section.default).toContain('debugMode.value || metricItems.value.length === 0')
  })

  it('uses unified coverage labels without showing coverage in normal mode', async () => {
    const section = await import('../components/company-v2/CompanyV2Section.vue?raw')
    expect(section.default).toContain("pct >= 100 && !hasSemanticWarning.value")
    expect(section.default).toContain("pct >= 60")
    expect(section.default).toContain("数据覆盖有限")
    expect(section.default).toContain('v-if="debugMode" class="cv2-quality-row"')
  })

  it('reports use a persisted-first state machine and summary from the same list', async () => {
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(docs.default).toContain("reportState = ref('idle')")
    expect(docs.default).toContain("reportState.value = 'loading_persisted'")
    expect(docs.default).toContain("reportState.value = reports.value.length ? 'persisted_found' : 'empty'")
    expect(docs.default).toContain('reportSummary')
    expect(docs.default).toContain('reportRequestSeq')
  })

  it('reports expose loading empty error and manual official PDF states', async () => {
    const docs = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(timeline.default).toContain('report-loading')
    expect(timeline.default).toContain('正在获取官方报告')
    expect(timeline.default).toContain('暂无已发现的官方财务报告')
    expect(timeline.default).toContain('报告获取失败，请稍后重试')
    expect(docs.default).toContain('手动添加官方 PDF 链接')
    expect(docs.default).toContain('showNormalManualEntry')
  })

  it('normal report cards avoid raw English PDF status labels', async () => {
    const timeline = await import('../components/company-v2/CompanyV2ReportTimeline.vue?raw')
    expect(timeline.default).toContain("discovered: '已发现'")
    expect(timeline.default).toContain("parsed: '可分析'")
    expect(timeline.default).toContain("download_failed: '处理失败'")
    expect(timeline.default).not.toContain('PDF discovered')
    expect(timeline.default).not.toContain('Unverified')
  })

  it('cashflow chart marks outliers and uses symlog display with raw tooltip values', async () => {
    const chart = await import('../components/company-v2/charts/CompanyV2CashflowQualityChart.vue?raw')
    expect(chart.default).toContain('detectCashflowOutliers')
    expect(chart.default).toContain('symlogValue')
    expect(chart.default).toContain('对称对数尺度')
    expect(chart.default).toContain('异常点')
    expect(chart.default).toContain('tooltip 保留原始值')
  })
})
