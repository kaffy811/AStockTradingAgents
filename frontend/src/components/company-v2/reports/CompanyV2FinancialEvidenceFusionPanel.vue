<template>
  <div class="cv2-fusion-panel" data-testid="financial-evidence-fusion-panel">
    <div class="cv2-fusion-head">
      <div>
        <span class="cv2-fusion-title">Financial Evidence Fusion</span>
        <p class="cv2-fusion-note">结构化财务与年报证据按所选报告逐字段核验。</p>
      </div>
      <div class="cv2-fusion-actions">
        <select v-model="selectedReportId" class="cv2-fusion-select" data-testid="fusion-report-select" @change="handleReportChange">
          <option v-for="item in reportOptions" :key="reportKey(item)" :value="String(reportId(item))">
            {{ item.report_year }} · {{ reportTypeLabel(item.report_type) }} · {{ item.title || item.report_title || '报告' }}
          </option>
        </select>
        <button class="cv2-fusion-btn secondary" type="button" data-testid="fusion-status-load" @click="loadStatus">
          查看状态
        </button>
        <button class="cv2-fusion-btn secondary" type="button" data-testid="fusion-eligibility-load" @click="loadEligibility">
          资格
        </button>
        <button class="cv2-fusion-btn secondary" type="button" data-testid="fusion-health-load" @click="loadHealth">
          健康
        </button>
        <button class="cv2-fusion-btn primary" type="button" data-testid="fusion-run" :disabled="running || !canRunFusionJob" @click="runFusion(false)">
          {{ running ? '核验中' : '核验官方报告' }}
        </button>
        <button class="cv2-fusion-btn primary" type="button" data-testid="fusion-refresh" :disabled="running || !canRunFusionJob" @click="runFusion(true)">
          重新核验
        </button>
        <button v-if="activeJob && !activeJob.terminal" class="cv2-fusion-btn secondary" type="button" data-testid="fusion-cancel" @click="cancelFusion">
          取消
        </button>
      </div>
    </div>

    <p v-if="helperText" class="cv2-fusion-hint">{{ helperText }}</p>
    <p v-if="errorMessage" class="cv2-fusion-error">{{ errorMessage }}</p>

    <div v-if="activeJob" class="cv2-fusion-summary" data-testid="fusion-job-status">
      <span class="cv2-fusion-badge info">{{ activeJob.status }}</span>
      <span class="cv2-fusion-badge idle">{{ jobStageText(activeJob.current_stage) }}</span>
      <span class="cv2-fusion-badge idle">{{ Math.round((activeJob.progress || 0) * 100) }}%</span>
      <span v-if="activeJob.cache_hit" class="cv2-fusion-badge info">cached</span>
      <span v-if="activeJob.terminal" class="cv2-fusion-badge ok">terminal</span>
    </div>

    <div v-if="selectedReadiness" class="cv2-report-view">
      <span class="cv2-fusion-badge info">官方报告查看</span>
      <a
        v-if="selectedReadiness.report_view_ready && selectedReadiness.source_url"
        class="cv2-report-link"
        :href="selectedReadiness.source_url"
        target="_blank"
        rel="noopener noreferrer"
        data-testid="fusion-view-report"
      >
        PDF
      </a>
      <span v-else class="cv2-fusion-badge idle">官方报告链接暂不可用</span>
      <span class="cv2-fusion-badge idle">{{ selectedReadiness.canonical_report ? 'canonical' : 'non-canonical' }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedReadiness.url_whitelist_valid ? 'url_ok' : 'url_blocked' }}</span>
    </div>

    <div v-if="selectedReadiness" class="cv2-fusion-summary">
      <span class="cv2-fusion-badge info">实验性官方证据核验</span>
      <span class="cv2-fusion-badge idle">需手动运行</span>
      <span :class="['cv2-fusion-badge', selectedReadiness.fusion_ready ? 'ok' : 'warn']">
        {{ readinessStatusLabel(selectedReadiness.status) }}
      </span>
      <span class="cv2-fusion-badge idle">{{ selectedReadiness.next_manual_action || 'run_fusion' }}</span>
    </div>

    <div v-if="eligibility" class="cv2-fusion-summary">
      <span :class="['cv2-fusion-badge', eligibility.eligible ? 'ok' : 'idle']">
        {{ eligibility.eligible ? 'eligible' : 'ineligible' }}
      </span>
      <span class="cv2-fusion-badge idle">{{ eligibility.reason }}</span>
      <span v-if="eligibility.cached" class="cv2-fusion-badge info">cached</span>
      <CompanyV2FinancialFusionHealthBadge :health="health" />
      <CompanyV2FinancialFusionReviewBadge :count="reviewCount" />
    </div>

    <div v-if="snapshot" class="cv2-fusion-summary">
      <span class="cv2-fusion-badge ok">{{ snapshot.summary.verified }} verified</span>
      <span class="cv2-fusion-badge info">{{ snapshot.summary.definition_mismatch }} definition mismatch</span>
      <span class="cv2-fusion-badge warn">{{ snapshot.summary.period_basis_mismatch }} period mismatch</span>
      <span class="cv2-fusion-badge idle">{{ snapshot.summary.insufficient_evidence }} insufficient</span>
      <span class="cv2-fusion-badge idle">{{ snapshot.cache_hit ? 'cached' : 'newly computed' }}</span>
    </div>

    <div v-if="selectedReadiness && !selectedReadiness.fusion_ready" class="cv2-fusion-actions cv2-fusion-readiness-actions">
      <div class="cv2-fusion-stepper" data-testid="fusion-prep-stepper">
        <button
          v-for="step in ['download', 'parse', 'index', 'fusion']"
          :key="step"
          class="cv2-fusion-step"
          type="button"
          :disabled="!canRunStep(step) || running"
          :data-testid="`fusion-prepare-${step}`"
          @click="step === 'fusion' ? runFusion(false) : prepareStep(step)"
        >
          <span>{{ stepLabel(step) }}</span>
          <small>{{ stepStatusLabel(selectedPrepareStatus?.steps?.find(item => item.step === step)?.status) }}</small>
        </button>
      </div>
    </div>

    <div v-if="selectedPrepareStatus" class="cv2-fusion-summary">
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.report_view_ready ? 'report_view_ready' : 'report_view_blocked' }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.pdf_url_ready ? 'pdf_url_ready' : 'pdf_url_blocked' }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.next_manual_action_for_view || 'view_ready' }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.discovery_status }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.download_status }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.parse_status }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.rag_index_status || selectedPrepareStatus.index_status }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.next_manual_action_for_rag || selectedPrepareStatus.next_manual_action || 'run_fusion' }}</span>
      <span class="cv2-fusion-badge idle">{{ selectedPrepareStatus.next_manual_action_for_fusion || 'fusion_ready' }}</span>
      <span v-if="selectedPrepareStatus.current_job?.status" class="cv2-fusion-badge info">
        {{ selectedPrepareStatus.current_job.status }}
      </span>
    </div>

    <div v-if="snapshot?.fields?.length" class="cv2-fusion-table">
      <div class="cv2-fusion-row head">
        <span>字段</span>
        <span>结构化值</span>
        <span>官方值</span>
        <span>状态</span>
        <span>证据</span>
      </div>
      <div v-for="item in snapshot.fields" :key="item.field_name" class="cv2-fusion-row">
        <span class="cv2-fusion-field">{{ fieldLabel(item.field_name) }}</span>
        <span>{{ formatValue(item.provider_value, item.provider_unit) }}</span>
        <span>{{ formatValue(item.official_value, item.official_unit) }}</span>
        <span :class="['cv2-fusion-status', toneClass(item.fusion_status)]">{{ statusLabel(item.fusion_status) }}</span>
        <button class="cv2-fusion-citation" type="button" :disabled="!item.official_page" @click="selectedCitation = item">
          {{ item.official_page ? `第 ${item.official_page} 页` : '无页码' }}
        </button>
      </div>
    </div>

    <div v-if="selectedCitation" class="cv2-fusion-citation-detail" data-testid="fusion-citation-detail">
      <div class="cv2-fusion-citation-head">
        <strong>{{ fieldLabel(selectedCitation.field_name) }}</strong>
        <span>{{ selectedReportLabel }}</span>
      </div>
      <p class="cv2-fusion-citation-page">
        {{ selectedCitation.official_page ? `第 ${selectedCitation.official_page} 页` : '无页码' }}
      </p>
      <p v-if="snapshot?.cache_hit !== undefined" class="cv2-fusion-citation-page">
        {{ snapshot.cache_hit ? 'cache_hit' : 'newly_computed' }} · {{ snapshot.computed_at || snapshot.generated_at }}
      </p>
      <p class="cv2-fusion-citation-excerpt">{{ selectedCitation.official_excerpt }}</p>
      <a v-if="selectedCitation.source_trace_json?.official?.source_url" :href="selectedCitation.source_trace_json.official.source_url" target="_blank" rel="noopener noreferrer">
        CNINFO PDF
      </a>
      <details class="cv2-fusion-trace">
        <summary>Source Trace</summary>
        <pre>{{ JSON.stringify(selectedCitation.source_trace_json, null, 2) }}</pre>
      </details>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  cancelCompanyV2FinancialFusionJob,
  createCompanyV2FinancialFusionJob,
  getCompanyV2FinancialFusion,
  getCompanyV2FinancialFusionEligibility,
  getCompanyV2FinancialFusionHealth,
  getCompanyV2FinancialFusionJob,
  getCompanyV2FinancialFusionJobResult,
  getCompanyV2FinancialFusionReadiness,
  getCompanyV2FinancialFusionPrepareStatus,
  prepareCompanyV2FinancialFusionStep,
} from '../../../api/companyV2.js'
import CompanyV2FinancialFusionHealthBadge from './CompanyV2FinancialFusionHealthBadge.vue'
import CompanyV2FinancialFusionReviewBadge from './CompanyV2FinancialFusionReviewBadge.vue'

const props = defineProps({
  market: { type: String, required: true },
  symbol: { type: String, required: true },
  reports: { type: Array, default: () => [] },
})

const selectedReportId = ref('')
const snapshot = ref(null)
const selectedCitation = ref(null)
const running = ref(false)
const errorMessage = ref('')
const eligibility = ref(null)
const health = ref(null)
const readiness = ref(null)
const prepareStatus = ref(null)
const reviewCount = ref(0)
const activeJob = ref(null)
let pollTimer = null
let pollStartedAt = 0

const fieldOrder = [
  'revenue',
  'net_profit',
  'net_profit_parent',
  'operating_cashflow',
  'total_assets',
  'equity_parent',
  'eps_basic',
  'roe_weighted',
  'total_share',
  'float_share',
]

const reportOptions = computed(() => (props.reports || []).filter(Boolean))

const selectedReport = computed(() => reportOptions.value.find(item => String(reportId(item)) === String(selectedReportId.value)) || null)

const selectedReportLabel = computed(() => {
  const item = selectedReport.value
  if (!item) return ''
  return `${item.report_year} · ${reportTypeLabel(item.report_type)} · ${item.title || item.report_title || '报告'}`
})

const selectedReadiness = computed(() => {
  if (!readiness.value) return null
  const selectedId = Number(selectedReportId.value || 0)
  return readiness.value.reports?.find(item => Number(item.report_id) === selectedId) || readiness.value
})

const selectedPrepareStatus = computed(() => {
  if (!prepareStatus.value) return null
  return prepareStatus.value
})

const helperText = computed(() => {
  if (!selectedReportId.value) return '请选择一份已解析报告后运行融合。'
  if (activeJob.value && !activeJob.value.terminal) return '正在核验官方报告，通常需要约 30–60 秒。'
  if (selectedReadiness.value && !selectedReadiness.value.fusion_ready) return readinessStatusText(selectedReadiness.value)
  return '点击后才会创建核验任务；页面加载不会自动运行融合。'
})

const canRunFusionJob = computed(() => Boolean(selectedReportId.value && eligibility.value?.eligible && selectedReadiness.value?.fusion_ready))

function reportId(item) {
  return item.id || item.report_id
}

function reportKey(item) {
  return `${reportId(item)}-${item.report_year}-${item.report_type}`
}

function reportTypeLabel(type) {
  return {
    annual: '年报',
    semiannual: '半年报',
    quarterly: '季报',
    q1: '一季报',
    q3: '三季报',
  }[type] || type || '报告'
}

function fieldLabel(field) {
  return {
    revenue: '营业收入',
    net_profit: '净利润',
    net_profit_parent: '归母净利润',
    operating_cashflow: '经营活动现金流净额',
    total_assets: '总资产',
    equity_parent: '归母净资产',
    eps_basic: '基本每股收益',
    roe_weighted: '加权平均净资产收益率',
    total_share: '总股本',
    float_share: '流通股本',
  }[field] || field
}

function formatValue(value, unit) {
  if (value === null || value === undefined || value === '') return 'N/A'
  return unit ? `${value} ${unit}` : String(value)
}

function statusLabel(status) {
  return {
    verified: 'verified',
    normalized_match: 'normalized_match',
    likely_match: 'likely_match',
    definition_mismatch: 'definition_mismatch',
    period_basis_mismatch: 'period_basis_mismatch',
    unit_mismatch: 'unit_mismatch',
    value_conflict: 'value_conflict',
    structured_field_missing: 'structured_field_missing',
    official_field_not_found: 'official_field_not_found',
    insufficient_evidence: 'insufficient_evidence',
    not_applicable: 'not_applicable',
    failed: 'failed',
  }[status] || status || 'pending'
}

function readinessStatusLabel(status) {
  return {
    ready: 'ready',
    report_not_discovered: '未发现报告',
    report_discovered: '报告已发现',
    pdf_not_downloaded: '报告尚未下载',
    pdf_downloaded: '报告已下载',
    parse_pending: '报告尚未解析',
    parsed: '报告已解析',
    rag_not_indexed: '报告尚未建立索引',
    indexed: '报告已建立索引',
    structured_data_missing: '结构化数据不完整',
    failed: '准备失败',
  }[status] || status || 'pending'
}

function readinessStatusText(item) {
  const text = {
    report_not_discovered: '未发现可用报告链接。',
    report_discovered: '已发现可用报告链接。',
    pdf_not_downloaded: item?.report_view_ready ? '官方报告可查看，RAG 链路尚未下载 PDF。' : '官方报告链接暂不可用，RAG 链路尚未下载 PDF。',
    pdf_downloaded: item?.report_view_ready ? '官方报告可查看，PDF 已下载，下一步可解析。' : '官方报告链接暂不可用，PDF 已下载，下一步可解析。',
    parse_pending: item?.report_view_ready ? '官方报告可查看，PDF 已下载，尚未解析。' : '官方报告链接暂不可用，PDF 已下载，尚未解析。',
    parsed: item?.report_view_ready ? '官方报告可查看，PDF 已解析，下一步可建立索引。' : '官方报告链接暂不可用，PDF 已解析，下一步可建立索引。',
    rag_not_indexed: item?.report_view_ready ? '官方报告可查看，RAG 尚未建立索引。' : '官方报告链接暂不可用，RAG 尚未建立索引。',
    indexed: item?.report_view_ready ? '官方报告可查看，RAG 已建立索引，但融合仍未完成。' : '官方报告链接暂不可用，RAG 已建立索引，但融合仍未完成。',
    structured_data_missing: item?.report_view_ready ? '官方报告可查看，结构化融合数据不完整。' : '官方报告链接暂不可用，结构化融合数据不完整。',
    ready: '当前报告已具备融合条件。',
    failed: '准备流程失败。',
  }[item?.status] || '当前报告尚未准备完成。'
  return `${text}${item?.next_manual_action ? ` 下一步：${item.next_manual_action}` : ''}`
}

function stepLabel(step) {
  return {
    download: '下载',
    parse: '解析',
    index: '建索引',
    fusion: '融合',
  }[step] || step
}

function stepStatusLabel(status) {
  return {
    pending: '待执行',
    blocked: '已阻塞',
    done: '已完成',
  }[status] || status || '待执行'
}

function canRunStep(step) {
  const status = selectedPrepareStatus.value
  if (!status) return false
  return status.steps?.find(item => item.step === step)?.status === 'pending'
}

function toneClass(status) {
  if (status === 'verified' || status === 'normalized_match') return 'ok'
  if (status === 'likely_match') return 'info'
  if (status === 'definition_mismatch' || status === 'period_basis_mismatch' || status === 'unit_mismatch') return 'warn'
  if (status === 'value_conflict') return 'fail'
  if (status === 'structured_field_missing' || status === 'insufficient_evidence' || status === 'official_field_not_found') return 'idle'
  return 'idle'
}

function clearResult() {
  snapshot.value = null
  selectedCitation.value = null
  errorMessage.value = ''
}

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function jobStageText(stage) {
  return {
    queued: '等待核验',
    validating_readiness: '正在检查报告状态',
    cache_lookup: '正在读取缓存',
    structured_data_load: '正在读取结构化数据',
    rag_retrieval: '正在检索官方报告',
    official_evidence_extract: '正在核验字段口径',
    unit_normalization: '正在归一化单位',
    field_alignment: '正在比对字段',
    classification: '正在分类结果',
    citation_validation: '正在生成引用',
    result_persistence: '正在保存结果',
    completed: '已完成',
    cancelled: '已取消',
    failed: '已失败',
    timed_out: '已超时',
    running: '正在处理',
  }[stage] || '正在处理'
}

function nextPollDelay(job) {
  if (job?.poll_after_ms) return job.poll_after_ms
  const elapsed = Date.now() - pollStartedAt
  if (elapsed > 20000) return 4000
  if (elapsed > 5000) return 2000
  return 1000
}

async function pollJob(jobId) {
  stopPolling()
  if (!jobId) return
  try {
    const job = await getCompanyV2FinancialFusionJob(props.market, props.symbol, jobId)
    activeJob.value = job
    if (job.terminal) {
      running.value = false
      if (['completed', 'partial'].includes(job.status)) {
        const resultPayload = await getCompanyV2FinancialFusionJobResult(props.market, props.symbol, jobId)
        snapshot.value = resultPayload.result || null
        selectedCitation.value = snapshot.value?.fields?.[0] || null
        reviewCount.value = snapshot.value?.fields?.filter(item => ['value_conflict', 'likely_match', 'unit_mismatch'].includes(item.fusion_status)).length || 0
        await loadEligibility()
        await loadHealth()
      }
      return
    }
    if (Date.now() - pollStartedAt < 120000) {
      pollTimer = setTimeout(() => pollJob(jobId), nextPollDelay(job))
    } else {
      running.value = false
      errorMessage.value = '核验任务仍在运行，请稍后手动查看状态。'
    }
  } catch (error) {
    running.value = false
    errorMessage.value = error.data?.message || error.message || '任务状态读取失败'
  }
}

async function handleReportChange() {
  stopPolling()
  clearResult()
  activeJob.value = null
  prepareStatus.value = null
  await loadEligibility()
  await loadHealth()
  await loadReadiness()
  await loadPrepareStatus()
}

async function loadStatus() {
  if (!selectedReportId.value) return
  errorMessage.value = ''
  try {
    snapshot.value = await getCompanyV2FinancialFusion(props.market, props.symbol, Number(selectedReportId.value))
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '状态读取失败'
  }
}

async function loadEligibility() {
  if (!selectedReportId.value) return
  try {
    eligibility.value = await getCompanyV2FinancialFusionEligibility(props.market, props.symbol, Number(selectedReportId.value))
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '资格读取失败'
  }
}

async function loadHealth() {
  if (!selectedReportId.value) return
  try {
    health.value = await getCompanyV2FinancialFusionHealth(props.market, props.symbol, Number(selectedReportId.value))
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '健康状态读取失败'
  }
}

async function loadReadiness() {
  try {
    readiness.value = await getCompanyV2FinancialFusionReadiness(props.market, props.symbol)
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '准备状态读取失败'
  }
}

async function loadPrepareStatus() {
  if (!selectedReportId.value) return
  try {
    prepareStatus.value = await getCompanyV2FinancialFusionPrepareStatus(props.market, props.symbol, Number(selectedReportId.value))
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '准备进度读取失败'
  }
}

async function prepareStep(step) {
  if (!selectedReportId.value) return
  running.value = true
  errorMessage.value = ''
  try {
    await prepareCompanyV2FinancialFusionStep(props.market, props.symbol, Number(selectedReportId.value), step)
    await loadReadiness()
    await loadPrepareStatus()
    await loadEligibility()
    await loadHealth()
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '准备步骤失败'
  } finally {
    running.value = false
  }
}

async function runFusion(refresh = false) {
  if (!selectedReportId.value) return
  running.value = true
  errorMessage.value = ''
  try {
    const job = await createCompanyV2FinancialFusionJob(props.market, props.symbol, {
      report_id: Number(selectedReportId.value),
      fields: fieldOrder,
      refresh,
    })
    if (!job.job_id) {
      running.value = false
      errorMessage.value = job.error_code || job.reason || '当前报告暂不能核验'
      return
    }
    activeJob.value = job
    pollStartedAt = Date.now()
    pollTimer = setTimeout(() => pollJob(job.job_id), job.poll_after_ms || 1000)
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '融合失败'
    running.value = false
  }
}

async function cancelFusion() {
  if (!activeJob.value?.job_id) return
  try {
    const job = await cancelCompanyV2FinancialFusionJob(props.market, props.symbol, activeJob.value.job_id)
    activeJob.value = job
    stopPolling()
  } finally {
    running.value = false
  }
}

watch(
  () => props.reports,
  () => {
    if (!selectedReportId.value && reportOptions.value.length) {
      selectedReportId.value = String(reportId(reportOptions.value[0]))
      loadEligibility()
      loadHealth()
      loadReadiness()
      loadPrepareStatus()
    }
  },
  { immediate: true },
)

watch(
  () => props.symbol,
  () => {
    stopPolling()
    selectedReportId.value = reportOptions.value.length ? String(reportId(reportOptions.value[0])) : ''
    clearResult()
    activeJob.value = null
    eligibility.value = null
    health.value = null
    readiness.value = null
    prepareStatus.value = null
    reviewCount.value = 0
  },
)

onBeforeUnmount(() => {
  stopPolling()
})

onMounted(() => {
  if (!selectedReportId.value && reportOptions.value.length) {
    selectedReportId.value = String(reportId(reportOptions.value[0]))
  }
  if (selectedReportId.value) {
    loadEligibility()
    loadHealth()
    loadReadiness()
    loadPrepareStatus()
  }
})
</script>

<style scoped>
.cv2-fusion-panel {
  margin-top: 12px;
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cv2-fusion-head,
.cv2-fusion-actions,
.cv2-fusion-summary,
.cv2-fusion-row,
.cv2-fusion-citation-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cv2-report-view {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cv2-fusion-head { justify-content: space-between; }
.cv2-fusion-title { font-size: 13px; font-weight: 600; color: #111827; }
.cv2-fusion-note,
.cv2-fusion-hint,
.cv2-fusion-error,
.cv2-fusion-citation-page,
.cv2-fusion-citation-excerpt {
  margin: 0;
  font-size: 12px;
  color: #4b5563;
}
.cv2-fusion-select,
.cv2-fusion-btn {
  min-height: 28px;
  border-radius: 6px;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #111827;
  font-size: 12px;
  padding: 0 10px;
}
.cv2-fusion-btn.primary { background: #111827; color: #fff; border-color: #111827; }
.cv2-fusion-btn.secondary { background: #fff; }
.cv2-fusion-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.cv2-report-link {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  border: 1px solid #93c5fd;
  background: #eff6ff;
  color: #1d4ed8;
  text-decoration: none;
  font-size: 12px;
}
.cv2-fusion-summary { gap: 6px; }
.cv2-fusion-badge {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #4b5563;
}
.cv2-fusion-badge.ok { border-color: #86efac; background: #f0fdf4; color: #166534; }
.cv2-fusion-badge.info { border-color: #bfdbfe; background: #eff6ff; color: #1d4ed8; }
.cv2-fusion-badge.warn { border-color: #fde68a; background: #fffbeb; color: #92400e; }
.cv2-fusion-badge.idle { border-color: #e5e7eb; background: #f9fafb; color: #6b7280; }
.cv2-fusion-table {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cv2-fusion-row {
  display: grid;
  grid-template-columns: minmax(110px, 1.2fr) minmax(150px, 1fr) minmax(150px, 1fr) minmax(150px, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  font-size: 12px;
}
.cv2-fusion-row.head {
  background: #f9fafb;
  font-weight: 600;
  color: #374151;
}
.cv2-fusion-field { font-weight: 600; color: #111827; }
.cv2-fusion-status {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid #d1d5db;
  background: #fff;
}
.cv2-fusion-status.ok { border-color: #86efac; background: #f0fdf4; color: #166534; }
.cv2-fusion-status.info { border-color: #bfdbfe; background: #eff6ff; color: #1d4ed8; }
.cv2-fusion-status.warn { border-color: #fde68a; background: #fffbeb; color: #92400e; }
.cv2-fusion-status.fail { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.cv2-fusion-status.idle { border-color: #e5e7eb; background: #f9fafb; color: #6b7280; }
.cv2-fusion-citation {
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #fff;
  color: #111827;
  min-height: 24px;
  padding: 0 8px;
  font-size: 12px;
}
.cv2-fusion-citation-detail {
  border-top: 1px solid #e5e7eb;
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cv2-fusion-trace pre {
  margin: 0;
  white-space: pre-wrap;
  font-size: 11px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px;
}
.cv2-fusion-readiness-actions {
  margin-top: -2px;
}
.cv2-fusion-stepper {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}
.cv2-fusion-step {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-height: 46px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #111827;
  font-size: 12px;
}
.cv2-fusion-step small {
  color: #6b7280;
  font-size: 11px;
}
.cv2-fusion-step:disabled {
  opacity: 0.55;
}
</style>
