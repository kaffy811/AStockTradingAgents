<template>
  <section class="cv2-section">
    <header class="cv2-section-head">
      <div>
        <h2>{{ title }}</h2>
        <p v-if="debugMode || impactStatus?.description">{{ debugMode ? statusText : impactStatus.description }}</p>
      </div>
      <span v-if="debugMode || impactStatus" :class="['cv2-status', debugMode ? statusClass : impactStatus.class]">
        {{ debugMode ? statusLabel : impactStatus.text }}
      </span>
    </header>

    <div v-if="debugMode || latestPeriodLabel" class="cv2-quality-row">
      <span v-if="debugMode && userQuality.text" :class="['cv2-user-quality', userQuality.class]">{{ userQuality.text }}</span>
      <span v-if="latestPeriodLabel" class="cv2-period-label">数据截至 {{ latestPeriodLabel }}</span>
    </div>

    <div v-if="debugMode" class="cv2-quality-row">
      <span class="cv2-coverage">coverage {{ coverage.coverage_pct ?? 0 }}%</span>
      <span
        v-if="validationSummary.checks_total !== undefined"
        :class="['cv2-validation-pill', validationStatusClass]"
      >
        quality {{ validationSummary.data_quality_score ?? '—' }} · {{ validationSummary.status }}
      </span>
      <span
        v-for="tag in diagnosisTags"
        :key="tag"
        :class="['cv2-tag', tagClass(tag)]"
      >{{ tag }}</span>
    </div>

    <div v-if="debugMode" class="cv2-source-chain">
      <span
        v-for="source in envelope.source_chain || []"
        :key="`${source.provider}-${source.endpoint}`"
        :class="sourceClass(source)"
      >
        {{ source.provider }} / {{ source.endpoint }} / {{ source.success ? 'success' : (source.error_code || 'empty') }}
      </span>
    </div>

    <!-- Phase 6T-E: 金融行业不适用指标提示（中性样式，不计为数据错误） -->
    <p v-if="notApplicableFields.length" class="cv2-na-hint" data-testid="metric-na-hint">
      该行业不适用这些指标：{{ notApplicableFields.map(f => fieldLabel(f)).join('、') }}
    </p>
    <p v-if="recommendedIndustryMetrics.length" class="cv2-na-hint" data-testid="industry-recommended-metrics">
      该行业更适合关注：{{ recommendedIndustryMetrics.map(f => fieldLabel(f)).join('、') }}
    </p>
    <p v-if="outlierWarning" class="cv2-business-warning">{{ outlierWarning }}</p>

    <CompanyV2MetricCards v-if="metricItems.length" :items="metricItems" :debug-mode="debugMode" />

    <p v-if="cashflowWarning" class="cv2-business-warning">{{ cashflowWarning }}</p>
    <p v-if="dupontMismatch" class="cv2-business-warning">指标口径或期间不一致，暂不进行杜邦拆解。</p>

    <!-- 报告文件模块：时间线 -->
    <CompanyV2ReportDocuments
      v-if="props.moduleKey === 'report_documents'"
      :envelope="envelope"
      :market="props.market"
      :symbol="props.symbol"
      :debug-mode="debugMode"
    />

    <!-- 财务图表（有多行时优先图表，否则表格） -->
    <template v-else-if="showChart">
      <CompanyV2GrowthComboChart v-if="props.moduleKey === 'growth'" :rows="tableRows" />
      <CompanyV2ProfitabilityTrendChart v-else-if="props.moduleKey === 'profitability'" :rows="tableRows" />
      <CompanyV2DupontChart v-else-if="props.moduleKey === 'dupont'" :rows="tableRows" />
      <CompanyV2CashflowQualityChart v-else-if="props.moduleKey === 'cashflow_quality'" :rows="tableRows" />
      <CompanyV2SolvencyChart v-else-if="props.moduleKey === 'solvency'" :rows="tableRows" />
      <CompanyV2OperationChart v-else-if="props.moduleKey === 'operation_capability'" :rows="tableRows" />
      <CompanyV2ValuationTrendChart v-else-if="props.moduleKey === 'valuation' || props.moduleKey === 'quote_overview'" :rows="tableRows" :fields="fields" />
      <CompanyV2FallbackTable v-else :rows="tableRows" :columns="tableColumns" />
    </template>

    <CompanyV2FallbackTable
      v-else-if="showFallbackTable"
      :rows="tableRows"
      :columns="tableColumns"
    />
    <CompanyV2UnavailablePanel v-else-if="props.moduleKey !== 'report_documents'" :reason="envelope.render?.reason" />

    <div v-if="debugMode" class="cv2-field-row">
      <span>diagnosis: {{ primaryIssue }}</span>
      <span>raw_rows_count: {{ diagnosis.raw_rows_count ?? 0 }}</span>
      <span>normalized_rows_count: {{ diagnosis.normalized_rows_count ?? tableRows.length }}</span>
      <span>valid_fields_count: {{ diagnosis.valid_fields_count ?? metricItems.length }}</span>
      <span>coverage: {{ coverage.filled_fields ?? filledFields.length }}/{{ coverage.required_fields ?? '—' }}</span>
    </div>
    <details v-if="debugMode && missingFields.length" class="cv2-missing-fields">
      <summary>missing fields {{ missingFields.length }}</summary>
      <span>{{ missingFields.join(', ') }}</span>
    </details>
    <details v-if="debugMode && Object.keys(fieldTrace).length" class="cv2-trace">
      <summary>field_trace {{ Object.keys(fieldTrace).length }}</summary>
      <pre>{{ JSON.stringify(fieldTrace, null, 2) }}</pre>
    </details>
    <details v-if="debugMode && validationChecks.length" class="cv2-validation-checks">
      <summary>validation_checks {{ validationChecks.length }}</summary>
      <p>数据质量校验，仅用于字段一致性和口径提示，不构成投资建议。</p>
      <p v-if="hasWeakFormulaWarning" class="cv2-formula-warning">
        该指标存在口径差异，可能来自报告期间、累计/单季或供应商定义差异，不代表数据一定错误。
      </p>
      <p v-if="hasDupontProviderWarning" class="cv2-formula-warning">
        杜邦拆解字段来自供应商定义口径，与简单乘积公式可能存在差异。
      </p>
      <p v-if="hasNetMarginContextWarning" class="cv2-formula-warning">
        净利率校验需要营收、净利润和净利率处于同一期间与同一口径。
      </p>
      <pre>{{ JSON.stringify(validationChecks, null, 2) }}</pre>
    </details>
    <p v-if="debugMode && diagnosisMessage" class="cv2-diagnosis-message">{{ diagnosisMessage }}</p>
    <CompanyV2RawJsonDrawer v-if="debugMode" :data="envelope" label="复制模块 JSON" />
  </section>
</template>

<script setup>
import { computed } from 'vue'
import CompanyV2MetricCards from './CompanyV2MetricCards.vue'
import CompanyV2FallbackTable from './CompanyV2FallbackTable.vue'
import CompanyV2UnavailablePanel from './CompanyV2UnavailablePanel.vue'
import CompanyV2RawJsonDrawer from './CompanyV2RawJsonDrawer.vue'
import CompanyV2ReportDocuments from './CompanyV2ReportDocuments.vue'
import CompanyV2GrowthComboChart from './charts/CompanyV2GrowthComboChart.vue'
import CompanyV2ProfitabilityTrendChart from './charts/CompanyV2ProfitabilityTrendChart.vue'
import CompanyV2DupontChart from './charts/CompanyV2DupontChart.vue'
import CompanyV2CashflowQualityChart from './charts/CompanyV2CashflowQualityChart.vue'
import CompanyV2SolvencyChart from './charts/CompanyV2SolvencyChart.vue'
import CompanyV2OperationChart from './charts/CompanyV2OperationChart.vue'
import CompanyV2ValuationTrendChart from './charts/CompanyV2ValuationTrendChart.vue'
import { classifyRowsPeriod, suggestChartType } from '../../utils/companyV2PeriodClassifier.js'

const props = defineProps({
  title: { type: String, required: true },
  envelope: { type: Object, required: true },
  moduleKey: { type: String, default: '' },
  market: { type: String, default: '' },
  symbol: { type: String, default: '' },
  // Phase 6T-B: 全历史数据（来自 /history 接口）
  historyData: { type: Object, default: () => null },
  debugMode: { type: Boolean, default: false },
})
const debugMode = computed(() => props.debugMode)

const fields = computed(() => props.envelope.normalized?.fields || {})
const firstRow = computed(() => props.envelope.normalized?.rows?.[0] || {})
const BUSINESS_FIELDS = {
  quote_overview: ['latest_price', 'pct_chg', 'turnover', 'market_cap'],
  valuation: ['pe_ttm', 'pb', 'ps_ttm', 'pcf_ncf_ttm'],
  profitability: ['roe', 'gross_margin', 'net_margin', 'net_profit'],
  growth: ['main_business_revenue', 'net_profit', 'net_profit_yoy', 'parent_net_profit_yoy', 'equity_yoy', 'asset_yoy', 'eps_yoy'],
  operation_capability: ['asset_turnover', 'inventory_turnover', 'receivable_turnover'],
  solvency: ['current_ratio', 'quick_ratio', 'cash_ratio', 'debt_ratio', 'equity_multiplier'],
  cashflow_quality: ['ocf_to_np', 'ocf_to_revenue'],
  dupont: ['roe', 'net_margin', 'asset_turnover', 'equity_multiplier'],
  report_documents: ['documents_count', 'chunks_count', 'embedding_count'],
}
const latestRow = computed(() => props.historyData?.latest || firstRow.value || {})
const latestPeriodLabel = computed(() => latestRow.value.period || latestRow.value.period_end || fields.value[Object.keys(fields.value)[0]]?.period_end || '')
const metricItems = computed(() => {
  if (props.moduleKey === 'report_documents' && !debugMode.value) return []
  const preferred = BUSINESS_FIELDS[props.moduleKey] || props.envelope.render?.visible_fields || Object.keys(fields.value)
  const row = latestRow.value
  return preferred
    .filter(field => !['cashflow_revenue_ratio', 'dupont_npi', 'dupont_nitogr', 'dupont_net_profit_factor', 'dupont_income_margin'].includes(field))
    .map(field => {
      const item = fields.value[field] || {}
      const value = row[field] ?? item.value
      if (value === null || value === undefined || value === '') return null
      return {
        field,
        label: fieldLabel(field),
        value,
        displayValue: item.display_value && row[field] === undefined ? item.display_value : formatBusinessValue(field, value),
        rawValue: item?.raw_value ?? value,
        periodEnd: row.period || item.period_end,
        source: item?.source || 'provider',
        provider: item?.provider,
        rawField: item?.raw_field,
        computedFormula: item?.computed_formula,
        computed: !!item?.computed,
        accuracyVerdict: props.envelope.accuracy_audit?.field_verdicts?.[field],
        verificationStatus: props.envelope.official_verification?.fields?.[field]?.status,
      }
    })
    .filter(Boolean)
})
// Phase 6T-B: 优先使用 history 数据（全量历史序列）；historyData 不存在时回退到 snapshot rows
const historyRows = computed(() => {
  if (props.historyData && Array.isArray(props.historyData.history) && props.historyData.history.length > 0) {
    return props.historyData.history
  }
  return null
})
const tableRows = computed(() => historyRows.value || props.envelope.normalized?.rows || [])
// Phase 6T-E: 行业不适用字段（银行/保险等），N/A 不计入缺失
const notApplicableFields = computed(() => (
  props.historyData?.metric_applicability?.not_applicable_fields || []
))
const recommendedIndustryMetrics = computed(() => (
  props.historyData?.metric_applicability?.recommended_metrics || []
).slice(0, 6))
const tableColumns = computed(() => {
  const visible = props.envelope.render?.visible_fields || []
  if (visible.length) return visible
  return Object.keys(tableRows.value[0] || {}).filter(key => !key.endsWith('_source')).slice(0, 8)
})
const tableRenderable = computed(() => props.envelope.render?.table_renderable && tableRows.value.length && tableColumns.value.length)
const showFallbackTable = computed(() => (
  tableRenderable.value &&
  props.moduleKey !== 'report_documents' &&
  (debugMode.value || metricItems.value.length === 0)
))

// Chart decision: use chart if multiple rows and chart-able module
const periodType = computed(() => classifyRowsPeriod(tableRows.value))
const chartType = computed(() => suggestChartType(periodType.value, props.moduleKey))
const CHART_MODULES = new Set(['growth', 'profitability', 'dupont', 'cashflow_quality', 'solvency', 'operation_capability', 'valuation', 'quote_overview'])
const showChart = computed(() => (
  CHART_MODULES.has(props.moduleKey) &&
  tableRows.value.length >= 2 &&
  !dupontMismatch.value &&
  chartType.value !== 'none'
))
const filledFields = computed(() => Object.keys(props.envelope.completion?.filled_fields || {}))
const missingFields = computed(() => Object.keys(props.envelope.completion?.still_missing_fields || {}))
const diagnosis = computed(() => props.envelope.diagnosis || {})
const diagnosisTags = computed(() => diagnosis.value.tags || [primaryIssue.value])
const coverage = computed(() => props.envelope.coverage || {})
const fieldTrace = computed(() => props.envelope.field_trace || {})
const validationSummary = computed(() => props.envelope.validation_summary || {})
const validationChecks = computed(() => props.envelope.validation_checks || [])
const dupontMismatch = computed(() => (
  props.moduleKey === 'dupont' &&
  (latestRow.value.dupont_formula_status === 'mismatch' || props.historyData?.chart_contract?.formula_status === 'mismatch')
))
const cashflowWarning = computed(() => {
  if (props.moduleKey !== 'cashflow_quality') return ''
  const warnings = latestRow.value.warnings || props.historyData?.warnings || []
  const hit = warnings.find(w => w?.code === 'CFO_TO_NP_DENOMINATOR_SENSITIVE')
  return hit?.message || ''
})
const outlierWarning = computed(() => {
  const warnings = [
    ...(latestRow.value.warnings || []),
    ...(props.historyData?.warnings || []),
  ]
  const hit = warnings.find(w => w?.code === 'OUTLIER_REQUIRES_REVIEW')
  return hit ? '部分历史指标口径待确认，图表已避免误导性连接。' : ''
})
const moduleCompletenessStatus = computed(() => props.historyData?.completeness_status || props.historyData?.metric_applicability?.module_status || '')
const moduleSemanticStatus = computed(() => props.historyData?.semantic_status || '')
const moduleOutlierStatus = computed(() => props.historyData?.outlier_status || '')
const moduleFormulaStatus = computed(() => props.historyData?.formula_status || '')
const moduleUserMessage = computed(() => props.historyData?.user_message || '')
const hasDisplayableData = computed(() => Boolean(
  props.envelope.render?.has_displayable_data ||
  props.historyData?.data_success ||
  metricItems.value.length ||
  tableRows.value.length
))
const hasHistoryLimited = computed(() => {
  const count = Number(props.historyData?.history_coverage?.periods_count ?? tableRows.value.length)
  return Number.isFinite(count) && count > 0 && count <= 2
})
const impactStatus = computed(() => {
  if (moduleFormulaStatus.value === 'mismatch' || dupontMismatch.value) {
    return { text: '指标口径待确认', description: '指标口径或期间不一致，暂不进行拆解。', class: 'warn' }
  }
  if (moduleSemanticStatus.value === 'conflict') {
    return { text: '指标口径待确认', description: '不同来源的指标口径存在差异。', class: 'warn' }
  }
  if (moduleSemanticStatus.value === 'warning' || moduleOutlierStatus.value === 'extreme' || cashflowWarning.value) {
    return { text: '极端值可能受低基数影响', description: moduleUserMessage.value || cashflowWarning.value || '极端值可能受低基数影响。', class: 'warn' }
  }
  if (outlierWarning.value) return { text: '指标口径待确认', description: outlierWarning.value, class: 'warn' }
  if (props.historyData?.metric_applicability?.module_status === 'not_applicable') {
    return { text: '该行业不适用', class: 'muted' }
  }
  if (hasHistoryLimited.value && hasDisplayableData.value) {
    return { text: '历史数据不足', description: '历史覆盖有限，趋势仅供辅助参考。', class: 'warn' }
  }
  if (primaryIssue.value === 'REPORT_NOT_INGESTED') return { text: '报告正在处理', description: '报告正在解析或索引，完成后可用于分析。', class: 'warn' }
  if (primaryIssue.value === 'PROVIDER_TIMEOUT' || primaryIssue.value === 'PROVIDER_TIMEOUT_WITH_STALE_CACHE') return { text: '报告获取失败', description: '报告获取暂时失败，请稍后重试。', class: 'warn' }
  if (primaryIssue.value === 'REPORT_PDF_NOT_FOUND') return { text: '当前无正式报告', description: '当前未发现可用的正式年度报告。', class: 'warn' }
  return null
})
const userQuality = computed(() => {
  if (impactStatus.value) return impactStatus.value
  if (props.historyData?.metric_applicability?.module_status === 'not_applicable') return { text: '该行业不适用', class: 'muted' }
  if (dupontMismatch.value) return { text: '指标口径待确认', class: 'warn' }
  if (outlierWarning.value) return { text: '指标口径待确认', class: 'warn' }
  if (!props.envelope.render?.has_displayable_data && !props.historyData?.data_success) return { text: '暂无数据', class: 'warn' }
  const pct = Number(coverage.value.coverage_pct)
  if (Number.isFinite(pct)) {
    if (pct >= 100 && !hasSemanticWarning.value) return { text: '数据完整', class: 'ok' }
    if (pct >= 60) return { text: '部分指标缺失', class: 'warn' }
    return { text: '数据覆盖有限', class: 'warn' }
  }
  if (props.historyData?.history_coverage?.periods_count <= 2) return { text: '历史覆盖有限', class: 'warn' }
  return { text: '', class: 'ok' }
})
const hasSemanticWarning = computed(() => validationChecks.value.some(check => (
  check.status === 'warning' || check.status === 'fail' || (check.tags || []).some(tag => ['DUPONT_FORMULA_MISMATCH', 'CFO_TO_NP_DENOMINATOR_SENSITIVE'].includes(tag))
)))
const hasWeakFormulaWarning = computed(() => validationChecks.value.some(check => check.check_strength === 'weak'))
const hasDupontProviderWarning = computed(() => validationChecks.value.some(check => (check.tags || []).includes('DUPONT_PROVIDER_DEFINED')))
const hasNetMarginContextWarning = computed(() => validationChecks.value.some(check => check.check_id === 'net_margin_formula' && check.status === 'warning'))
const validationStatusClass = computed(() => {
  if (validationSummary.value.status === 'pass') return 'pass'
  if (validationSummary.value.status === 'fail') return 'fail'
  if (validationSummary.value.status === 'warning') return 'warning'
  return 'skipped'
})
const primaryIssue = computed(() => diagnosis.value.primary_issue || (props.envelope.ok ? 'OK' : 'PROVIDER_EMPTY'))
const statusLabel = computed(() => {
  if (debugMode.value) return primaryIssue.value
  return {
    OK: '数据正常',
    OK_WITH_FALLBACK: '部分数据来自备用来源',
    PARTIAL_DATA: '部分指标缺失',
    LOW_COVERAGE: '数据覆盖有限',
    VERY_LOW_COVERAGE: '数据覆盖有限',
    ALL_NULL_ROWS: '暂无可用数据',
    OUTLIER_REQUIRES_REVIEW: '指标口径待确认',
    FIELD_CONFLICT: '指标口径待确认',
    NOT_APPLICABLE_FOR_INDUSTRY: '该行业不适用',
    REPORT_PDF_NOT_FOUND: '暂无可用财报',
    REPORT_NOT_INGESTED: '财报待解析',
    PROVIDER_EMPTY: '暂无数据',
    PROVIDER_TIMEOUT: '数据源超时',
    PROVIDER_TIMEOUT_WITH_STALE_CACHE: '显示缓存数据',
    MAPPING_ERROR: '数据暂不可用',
  }[primaryIssue.value] || userQuality.value.text
})
const statusText = computed(() => {
  if (!debugMode.value) return userQuality.value.text
  if (primaryIssue.value === 'REPORT_PDF_NOT_FOUND') return '暂未接入可确认报告文件。'
  if (primaryIssue.value === 'REPORT_NOT_INGESTED') return '尚未接入可检索的年报片段，暂无法进行基于年报的 RAG 分析。'
  if (props.envelope.render?.reason) return props.envelope.render.reason
  const pct = coverage.value.coverage_pct
  if (pct !== undefined && pct !== null) return `coverage ${pct}% · ${coverage.value.filled_fields ?? filledFields.value.length}/${coverage.value.required_fields ?? '—'}`
  return `${filledFields.value.length} fields filled`
})
const statusClass = computed(() => {
  if (primaryIssue.value === 'OK_WITH_FALLBACK') return 'fallback'
  if (primaryIssue.value === 'LOW_COVERAGE') return 'low'
  if (primaryIssue.value === 'VERY_LOW_COVERAGE') return 'low'
  if (props.envelope.render?.has_displayable_data) return 'ok'
  if (primaryIssue.value === 'PROVIDER_TIMEOUT' || primaryIssue.value === 'PROVIDER_TIMEOUT_WITH_STALE_CACHE') return 'timeout'
  if (primaryIssue.value === 'MAPPING_ERROR' || primaryIssue.value === 'AGGREGATE_REUSE_MISSING' || primaryIssue.value === 'MAPPING_OR_RENDER_ERROR') return 'mapping'
  if (primaryIssue.value === 'REPORT_PDF_NOT_FOUND' || primaryIssue.value === 'REPORT_NOT_INGESTED') return 'warn'
  return 'warn'
})
const diagnosisMessage = computed(() => {
  if (primaryIssue.value === 'MAPPING_ERROR') return '原始数据已返回，但字段映射为空，请检查 normalizer。'
  if (primaryIssue.value === 'PROVIDER_TIMEOUT_WITH_STALE_CACHE') return '数据源超时，已展示缓存快照。'
  if (primaryIssue.value === 'AGGREGATE_REUSE_MISSING') return '聚合数据已返回，但模块未复用。'
  if (primaryIssue.value === 'REPORT_PDF_NOT_FOUND') return '暂未接入可确认报告文件，可尝试发现、手动录入 PDF URL 或上传 PDF。'
  if (primaryIssue.value === 'REPORT_NOT_INGESTED') return '尚未接入可检索的年报片段，暂无法进行基于年报的 RAG 分析。'
  return ''
})

function fieldLabel(field) {
  if (field === 'latest_price') return firstRow.value.price_label || '最新价'
  return ({
    recent_close: '前收盘价',
    open: '开盘价',
    high: '最高价',
    low: '最低价',
    volume: '成交量',
    amount: '成交额',
    pct_chg: '涨跌幅',
    turnover: '换手率',
    pe_ttm: '市盈率 TTM',
    pb: '市净率',
    ps_ttm: '市销率 TTM',
    pcf_ncf_ttm: '市现率 TTM',
    market_cap: '总市值',
    float_market_cap: '流通市值',
    roe: '净资产收益率',
    gross_margin: '毛利率',
    net_margin: '净利率',
    roa: '总资产收益率',
    roic: '投入资本回报率',
    revenue: '营业收入',
    revenue_yoy: '营收同比',
    net_profit_parent: '归母净利润',
    net_profit_yoy: '净利润同比',
    parent_net_profit_yoy: '归母净利润同比',
    main_business_revenue: '主营业务收入',
    net_profit: '净利润',
    equity_yoy: '净资产同比',
    asset_yoy: '总资产同比',
    eps_yoy: '每股收益同比',
    eps_basic: '基本每股收益',
    operating_cashflow: '经营现金流',
    ocf_to_np: '经营现金流/净利润',
    ocf_to_revenue: '经营现金流/营收',
    cashflow_revenue_ratio: '现金流收入比',
    current_ratio: '流动比率',
    quick_ratio: '速动比率',
    cash_ratio: '现金比率',
    debt_ratio: '资产负债率',
    equity_multiplier: '权益乘数',
    asset_turnover: '资产周转率',
    inventory_turnover: '存货周转率',
    receivable_turnover: '应收账款周转率',
    total_asset_turnover: '总资产周转率',
    documents_count: '报告文件数',
    chunks_count: '年报片段数',
    embedding_count: '向量片段数',
    summary: '摘要状态',
    net_interest_margin: '净息差',
    net_interest_spread: '净利差',
    non_performing_loan_ratio: '不良贷款率',
    provision_coverage_ratio: '拨备覆盖率',
    loan_provision_ratio: '贷款拨备率',
    capital_adequacy_ratio: '资本充足率',
    tier1_capital_adequacy_ratio: '一级资本充足率',
    core_tier1_capital_adequacy_ratio: '核心一级资本充足率',
    cost_income_ratio: '成本收入比',
    deposit_balance_yoy: '存款余额及增长',
    loan_balance_yoy: '贷款余额及增长',
    special_mention_loan_ratio: '关注类贷款比例',
    overdue_loan_ratio: '逾期贷款比例',
  })[field] || '指标'
}

function formatBusinessValue(field, value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(value)) return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  if (['roe', 'gross_margin', 'net_margin', 'net_profit_yoy', 'parent_net_profit_yoy', 'equity_yoy', 'asset_yoy', 'eps_yoy', 'ocf_to_np', 'ocf_to_revenue', 'debt_ratio'].includes(field)) {
    return `${(n * 100).toFixed(2)}%`
  }
  if (['pct_chg', 'turnover'].includes(field)) return `${n.toFixed(2)}%`
  if (['market_cap', 'float_market_cap', 'amount', 'revenue', 'main_business_revenue', 'net_profit'].includes(field)) {
    if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(2)}亿`
    if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(2)}万`
  }
  return n.toFixed(2)
}

function sourceClass(source) {
  if (source?.success) return 'source-ok'
  if (source?.error_code === 'PROVIDER_TIMEOUT' || source?.status === 'timeout') return 'source-timeout'
  if (source?.error_code === 'MAPPING_ERROR' || source?.status === 'schema_error' || source?.error_code === 'PROVIDER_SCHEMA_CHANGED') return 'source-mapping'
  return 'source-warn'
}

function tagClass(tag) {
  if (tag === 'OK' || tag === 'COMPUTED_FIELDS') return 'ok'
  if (tag === 'OK_WITH_FALLBACK') return 'fallback'
  if (tag === 'PARTIAL_DATA') return 'partial'
  if (tag === 'LOW_COVERAGE' || tag === 'MISSING_COMPUTABLE_FIELDS') return 'low'
  if (tag === 'REPORT_PDF_NOT_FOUND' || tag === 'REPORT_NOT_INGESTED') return 'neutral'
  return 'warn'
}
</script>

<style scoped>
.cv2-section {
  margin-top: 16px;
  padding: 18px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}
.cv2-section-head,
.cv2-field-row,
.cv2-source-chain,
.cv2-quality-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.cv2-section h2 {
  margin: 0;
  font-size: 18px;
}
.cv2-section p,
.cv2-field-row,
.cv2-missing-fields {
  color: #6b7280;
  font-size: 13px;
}
.cv2-status {
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  background: #fef3c7;
  color: #92400e;
}
.cv2-user-quality,
.cv2-period-label {
  font-size: 12px;
  color: #4b5563;
}
.cv2-user-quality {
  border-radius: 999px;
  padding: 3px 8px;
  background: #f3f4f6;
}
.cv2-user-quality.ok {
  background: #dcfce7;
  color: #166534;
}
.cv2-user-quality.warn {
  background: #fef3c7;
  color: #92400e;
}
.cv2-business-warning {
  margin: 10px 0 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fffbeb;
  color: #92400e;
}
.cv2-status.ok {
  background: #dcfce7;
  color: #166534;
}
.cv2-status.fallback {
  background: #dbeafe;
  color: #1d4ed8;
}
.cv2-status.low {
  background: #ffedd5;
  color: #9a3412;
}
.cv2-status.timeout {
  background: #fef3c7;
  color: #92400e;
}
.cv2-status.mapping {
  background: #ffedd5;
  color: #9a3412;
}
.cv2-source-chain {
  justify-content: flex-start;
  margin-top: 12px;
}
.cv2-quality-row {
  justify-content: flex-start;
  margin-top: 12px;
}
.cv2-coverage,
.cv2-tag,
.cv2-validation-pill {
  padding: 4px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #4b5563;
  font-size: 12px;
}
.cv2-tag.ok {
  background: #dcfce7;
  color: #166534;
}
.cv2-tag.fallback {
  background: #dbeafe;
  color: #1d4ed8;
}
.cv2-tag.partial {
  background: #fef3c7;
  color: #92400e;
}
.cv2-tag.low {
  background: #ffedd5;
  color: #9a3412;
}
.cv2-tag.neutral {
  background: #f3f4f6;
  color: #4b5563;
}
.cv2-validation-pill.pass {
  background: #dcfce7;
  color: #166534;
}
.cv2-validation-pill.warning {
  background: #fef3c7;
  color: #92400e;
}
.cv2-validation-pill.fail {
  background: #fee2e2;
  color: #991b1b;
}
.cv2-validation-pill.skipped {
  background: #f3f4f6;
  color: #4b5563;
}
.cv2-source-chain span {
  padding: 5px 8px;
  border-radius: 6px;
  background: #f3f4f6;
  color: #4b5563;
  font-size: 12px;
}
.cv2-source-chain .source-ok {
  background: #dcfce7;
  color: #166534;
}
.cv2-source-chain .source-timeout {
  background: #fef3c7;
  color: #92400e;
}
.cv2-source-chain .source-mapping {
  background: #ffedd5;
  color: #9a3412;
}
.cv2-field-row,
.cv2-missing-fields,
.cv2-trace,
.cv2-validation-checks {
  margin-top: 12px;
}
.cv2-missing-fields summary,
.cv2-trace summary,
.cv2-validation-checks summary {
  cursor: pointer;
  color: #374151;
}
.cv2-trace pre,
.cv2-validation-checks pre {
  max-width: 100%;
  overflow-x: auto;
  padding: 10px;
  border-radius: 8px;
  background: #f9fafb;
  font-size: 12px;
}
.cv2-validation-checks p {
  margin: 8px 0;
}
.cv2-formula-warning {
  color: #92400e;
}
.cv2-diagnosis-message {
  margin-top: 10px;
}
.cv2-na-hint {
  margin-top: 10px;
  padding: 6px 10px;
  border-radius: 6px;
  background: #f3f4f6;
  color: #4b5563;
  font-size: 12px;
}
</style>
