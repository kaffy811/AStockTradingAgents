<template>
  <section class="cv2-section">
    <header class="cv2-section-head">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ statusText }}</p>
      </div>
      <span :class="['cv2-status', statusClass]">{{ primaryIssue }}</span>
    </header>

    <div class="cv2-quality-row">
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

    <div class="cv2-source-chain">
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
      该行业下以下指标不适用（N/A）：{{ notApplicableFields.map(f => fieldLabel(f)).join('、') }}
    </p>

    <CompanyV2MetricCards v-if="metricItems.length" :items="metricItems" />

    <!-- 报告文件模块：时间线 -->
    <CompanyV2ReportDocuments
      v-if="props.moduleKey === 'report_documents'"
      :envelope="envelope"
      :market="props.market"
      :symbol="props.symbol"
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
      v-else-if="tableRenderable && props.moduleKey !== 'report_documents'"
      :rows="tableRows"
      :columns="tableColumns"
    />
    <CompanyV2UnavailablePanel v-else-if="props.moduleKey !== 'report_documents'" :reason="envelope.render?.reason" />

    <div class="cv2-field-row">
      <span>diagnosis: {{ primaryIssue }}</span>
      <span>raw_rows_count: {{ diagnosis.raw_rows_count ?? 0 }}</span>
      <span>normalized_rows_count: {{ diagnosis.normalized_rows_count ?? tableRows.length }}</span>
      <span>valid_fields_count: {{ diagnosis.valid_fields_count ?? metricItems.length }}</span>
      <span>coverage: {{ coverage.filled_fields ?? filledFields.length }}/{{ coverage.required_fields ?? '—' }}</span>
    </div>
    <details v-if="missingFields.length" class="cv2-missing-fields">
      <summary>missing fields {{ missingFields.length }}</summary>
      <span>{{ missingFields.join(', ') }}</span>
    </details>
    <details v-if="Object.keys(fieldTrace).length" class="cv2-trace">
      <summary>field_trace {{ Object.keys(fieldTrace).length }}</summary>
      <pre>{{ JSON.stringify(fieldTrace, null, 2) }}</pre>
    </details>
    <details v-if="validationChecks.length" class="cv2-validation-checks">
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
    <p v-if="diagnosisMessage" class="cv2-diagnosis-message">{{ diagnosisMessage }}</p>
    <CompanyV2RawJsonDrawer :data="envelope" label="复制模块 JSON" />
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
})

const fields = computed(() => props.envelope.normalized?.fields || {})
const firstRow = computed(() => props.envelope.normalized?.rows?.[0] || {})
const metricItems = computed(() => Object.entries(fields.value).map(([field, item]) => ({
  field,
  label: fieldLabel(field),
  value: item?.value,
  displayValue: item?.display_value,
  rawValue: item?.raw_value ?? item?.value,
  source: item?.source || 'provider',
  provider: item?.provider,
  rawField: item?.raw_field,
  computedFormula: item?.computed_formula,
  computed: !!item?.computed,
  accuracyVerdict: props.envelope.accuracy_audit?.field_verdicts?.[field],
  verificationStatus: props.envelope.official_verification?.fields?.[field]?.status,
})))
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
const tableColumns = computed(() => {
  const visible = props.envelope.render?.visible_fields || []
  if (visible.length) return visible
  return Object.keys(tableRows.value[0] || {}).filter(key => !key.endsWith('_source')).slice(0, 8)
})
const tableRenderable = computed(() => props.envelope.render?.table_renderable && tableRows.value.length && tableColumns.value.length)

// Chart decision: use chart if multiple rows and chart-able module
const periodType = computed(() => classifyRowsPeriod(tableRows.value))
const chartType = computed(() => suggestChartType(periodType.value, props.moduleKey))
const CHART_MODULES = new Set(['growth', 'profitability', 'dupont', 'cashflow_quality', 'solvency', 'operation_capability', 'valuation', 'quote_overview'])
const showChart = computed(() => (
  CHART_MODULES.has(props.moduleKey) &&
  tableRows.value.length >= 1 &&
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
const statusText = computed(() => {
  if (primaryIssue.value === 'REPORT_PDF_NOT_FOUND') return '暂未接入可确认报告文件，可尝试发现、手动录入 PDF URL 或上传 PDF。'
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
    recent_close: '最近收盘价',
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
    net_profit_yoy: '归母净利润同比',
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
  })[field] || field
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
