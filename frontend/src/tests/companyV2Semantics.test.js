import { describe, expect, it } from 'vitest'
import stockDetailRaw from '../views/StockDetailView.vue?raw'
import companyV2Raw from '../views/CompanyV2View.vue?raw'
import sectionRaw from '../components/company-v2/CompanyV2Section.vue?raw'
import cardsRaw from '../components/company-v2/CompanyV2MetricCards.vue?raw'
import tableRaw from '../components/company-v2/CompanyV2FallbackTable.vue?raw'
import debugPanelRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'

const forbidden = 'DATA_MODE=free：BaoStock 和 AkShare 均未返回数据，请检查 ENABLE_BAOSTOCK / ENABLE_AKSHARE 配置。'

describe('CompanyV2 semantics polish', () => {
  it('defaults to v2 outside production and keeps query legacy fallback', () => {
    expect(stockDetailRaw).toContain("import.meta.env.PROD ? 'legacy' : 'v2'")
    expect(stockDetailRaw).toContain("companyV2Query.value !== '0'")
    expect(stockDetailRaw).toContain('CompanyFundamentalsPanel')
  })

  it('shows report and RAG empty states without OK wording', () => {
    expect(companyV2Raw).toContain("statusPanelModules = new Set(['report_documents', 'ai_analysis_status'])")
    expect(companyV2Raw).toContain("key !== 'report_rag'")
    expect(sectionRaw).toContain('暂未接入可确认报告文件')
    expect(sectionRaw).toContain('尚未接入可检索的年报片段')
    expect(sectionRaw).toContain('REPORT_PDF_NOT_FOUND')
    expect(sectionRaw).toContain('REPORT_NOT_INGESTED')
  })

  it('uses display metadata and source tags while preserving raw value access', () => {
    expect(cardsRaw).toContain('displayValue')
    expect(cardsRaw).toContain('raw_value')
    expect(tableRaw).toContain('display_fields')
    expect(tableRaw).toContain('raw_value')
    expect(sectionRaw).toContain('fieldLabel(field)')
    expect(sectionRaw).toContain('firstRow.value.price_label')
  })

  it('does not include forbidden legacy or advice wording in CompanyV2 UI', () => {
    const source = [companyV2Raw, sectionRaw, cardsRaw, tableRaw, debugPanelRaw].join('\n')
    expect(source).not.toContain(forbidden)
    expect(source).not.toContain('target_price')
    expect(source).not.toContain('analyst_rating')
    expect(source).not.toContain('建议买入')
    expect(source).not.toContain('建议卖出')
    expect(source).not.toContain('保证上涨')
  })
})
