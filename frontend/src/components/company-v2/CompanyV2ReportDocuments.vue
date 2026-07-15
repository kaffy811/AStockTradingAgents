<template>
  <div class="cv2-report-docs">
    <!-- 头部状态 -->
    <div class="cv2-rd-header">
      <div class="cv2-rd-status-row">
        <span :class="['cv2-rd-badge', statusBadgeClass]">{{ statusBadgeText }}</span>
        <span v-if="reportSummary.report_count > 0" class="cv2-rd-summary">
          {{ summaryText }}
        </span>
        <span v-if="reportSummary.rag_status === 'indexed'" class="cv2-rd-rag-badge">已可分析</span>
        <span v-if="debugMode && reportSummary.report_count > 0" class="cv2-rd-count">
          chunks {{ reportSummary.chunk_count }}
        </span>
      </div>
      <p class="cv2-rd-hint">{{ statusHint }}</p>
    </div>

    <CompanyV2ReportTimeline
      :reports="reports"
      :discovering="discovering"
      :view-state="reportState"
      :default-show="defaultShow"
      :market="market"
      :symbol="symbol"
      :debug-mode="debugMode"
      @discover="triggerDiscover"
      @manual="showManual = !showManual"
      @download-parse="downloadAndParse"
      @verify="verifyReport"
      @ai-verify="aiVerifyReport"
    />

    <!-- 操作按钮 -->
    <div v-if="debugMode" class="cv2-rd-toolbar">
      <button
        class="cv2-rd-discover-btn"
        :disabled="discovering"
        @click="triggerDiscover(false)"
      >
        {{ discovering ? '发现中...' : '发现年报' }}
      </button>
      <button
        class="cv2-rd-discover-btn secondary"
        :disabled="discovering"
        @click="triggerDiscover(true)"
      >
        强制刷新
      </button>
      <button class="cv2-rd-discover-btn secondary" @click="showManual = !showManual">
        手动录入 URL
      </button>
      <button class="cv2-rd-discover-btn secondary" data-testid="report-rag-manager-toggle" @click="showIndexManager = !showIndexManager">
        索引管理
      </button>
      <button class="cv2-rd-discover-btn secondary" data-testid="report-compare-toggle" @click="showComparison = !showComparison">
        比较报告
      </button>
      <button class="cv2-rd-discover-btn secondary" data-testid="report-fusion-toggle" @click="showFusion = !showFusion">
        证据融合
      </button>
    </div>

    <div v-if="showNormalManualEntry" class="cv2-rd-normal-actions">
      <button class="cv2-rd-discover-btn secondary" @click="triggerDiscover(false)">
        重新获取
      </button>
      <button class="cv2-rd-discover-btn secondary" @click="showManual = !showManual">
        手动添加官方 PDF 链接
      </button>
    </div>

    <CompanyV2ReportRagIndexManager
      v-if="debugMode && showIndexManager"
      :market="market"
      :symbol="symbol"
      @build="actionMessage = '请在对应报告的 Report QA 面板中建立索引。'"
    />

    <CompanyV2ReportComparisonPanel
      v-if="debugMode && showComparison"
      :market="market"
      :symbol="symbol"
      :reports="reports"
    />

    <CompanyV2FinancialEvidenceFusionPanel
      v-if="debugMode && showFusion"
      :market="market"
      :symbol="symbol"
      :reports="reports"
    />

    <!-- 手动录入面板 -->
    <div v-if="(debugMode || showNormalManualEntry) && showManual" class="cv2-rd-manual">
      <h4>手动录入年报 PDF URL</h4>
      <p class="cv2-rd-hint">仅支持 static.cninfo.com.cn 域名的 PDF 链接。</p>
      <div class="cv2-rd-manual-row">
        <input v-model="manualUrl" placeholder="https://static.cninfo.com.cn/finalpage/..." class="cv2-rd-input" />
        <input v-model="manualYear" type="number" placeholder="年份（如 2024）" class="cv2-rd-input short" />
        <button class="cv2-rd-action-btn primary" @click="submitManual">提交</button>
      </div>
      <p v-if="manualError" class="cv2-rd-error">{{ manualError }}</p>
      <p v-if="manualSuccess" class="cv2-rd-success">{{ manualSuccess }}</p>
    </div>

    <!-- 发现错误 -->
    <div v-if="discoverErrors.length" class="cv2-rd-errors">
      <details v-if="debugMode">
        <summary>发现日志（{{ discoverErrors.length }} 条）</summary>
        <ul>
          <li v-for="e in discoverErrors" :key="e">{{ e }}</li>
        </ul>
      </details>
      <p v-else>报告发现暂时失败，其他财务数据不受影响。</p>
    </div>
    <p v-if="actionMessage" class="cv2-rd-success">{{ actionMessage }}</p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  addManualReport,
  aiVerifyCompanyV2Report,
  discoverCompanyV2Reports,
  downloadCompanyV2Report,
  getCompanyV2Reports,
  parseCompanyV2Report,
  verifyCompanyV2Report,
} from '../../api/companyV2.js'
import CompanyV2ReportTimeline from './CompanyV2ReportTimeline.vue'
import CompanyV2ReportRagIndexManager from './reports/CompanyV2ReportRagIndexManager.vue'
import CompanyV2ReportComparisonPanel from './reports/CompanyV2ReportComparisonPanel.vue'
import CompanyV2FinancialEvidenceFusionPanel from './reports/CompanyV2FinancialEvidenceFusionPanel.vue'

const props = defineProps({
  envelope: { type: Object, default: null },
  market:   { type: String, required: true },
  symbol:   { type: String, required: true },
  debugMode: { type: Boolean, default: false },
})
const debugMode = computed(() => props.debugMode)

const defaultShow = 5
const reports = ref([])
const reportState = ref('idle')
const discovering = ref(false)
const discoverErrors = ref([])
const showManual = ref(false)
const showIndexManager = ref(false)
const showComparison = ref(false)
const showFusion = ref(false)
const manualUrl = ref('')
const manualYear = ref('')
const manualError = ref('')
const manualSuccess = ref('')
const actionMessage = ref('')
const autoDiscoverKey = ref('')
let reportRequestSeq = 0

const reportSummary = computed(() => {
  const list = reports.value || []
  const annual = list.filter(item => (item.report_type || 'annual') === 'annual').length
  const chunkCount = list.reduce((sum, item) => sum + (Number(item.chunk_count) || 0), 0)
  const readyCount = list.filter(item => ['rag_ready', 'indexed', 'partial'].includes(item.rag_status) || ['indexed', 'partial'].includes(item.rag_index_status)).length
  return {
    report_count: list.length,
    annual_count: annual,
    chunk_count: chunkCount,
    ready_count: readyCount,
    rag_status: readyCount > 0 ? 'indexed' : (list.length ? 'pending' : 'empty'),
  }
})
const summaryText = computed(() => (
  `已发现 ${reportSummary.value.report_count} 份官方报告，其中 ${reportSummary.value.ready_count} 份可分析`
))

const statusBadgeClass = computed(() => {
  if (reportSummary.value.rag_status === 'indexed') return 'green'
  if (reportSummary.value.report_count > 0) return 'yellow'
  if (reportState.value === 'error') return 'yellow'
  return 'grey'
})
const statusBadgeText = computed(() => {
  if (['loading_persisted', 'discovering'].includes(reportState.value)) return '正在获取官方报告'
  if (reportSummary.value.rag_status === 'indexed') return '报告已可分析'
  if (reportSummary.value.report_count > 0) return '已发现官方报告'
  if (reportState.value === 'error') return '报告获取失败'
  return '暂无已发现的官方财务报告'
})
const statusHint = computed(() => {
  if (['loading_persisted', 'discovering'].includes(reportState.value)) return '正在获取官方报告...'
  if (reportState.value === 'error') return '报告获取失败，请稍后重试。'
  if (reportSummary.value.report_count === 0) return '暂无已发现的官方财务报告。'
  if (reportSummary.value.ready_count === 0) return '已发现官方报告，正在等待解析或索引。'
  return '报告已解析，可用于报告问答。'
})
const showNormalManualEntry = computed(() => !debugMode.value && ['empty', 'error'].includes(reportState.value))

async function loadReports() {
  const seq = ++reportRequestSeq
  const key = `${props.market}:${props.symbol}`
  reportState.value = 'loading_persisted'
  try {
    const res = await getCompanyV2Reports(props.market, props.symbol)
    if (seq !== reportRequestSeq || key !== `${props.market}:${props.symbol}`) return
    if (res.ok && res.reports) {
      reports.value = res.reports
      reportState.value = reports.value.length ? 'persisted_found' : 'empty'
      if (!reports.value.length) scheduleAutoDiscover()
    }
  } catch (e) {
    if (seq !== reportRequestSeq || key !== `${props.market}:${props.symbol}`) return
    reports.value = []
    reportState.value = 'error'
    discoverErrors.value = [e.message || '报告获取失败']
    scheduleAutoDiscover()
  }
}

function scheduleAutoDiscover() {
  const key = `${props.market}:${props.symbol}`
  if (autoDiscoverKey.value === key || discovering.value) return
  autoDiscoverKey.value = key
  triggerDiscover(false)
}

async function triggerDiscover(forceRefresh = false) {
  const seq = ++reportRequestSeq
  const key = `${props.market}:${props.symbol}`
  discovering.value = true
  reportState.value = 'discovering'
  discoverErrors.value = []
  try {
    const res = await discoverCompanyV2Reports(props.market, props.symbol, {
      force_refresh: forceRefresh,
    })
    if (seq !== reportRequestSeq || key !== `${props.market}:${props.symbol}`) return
    if (res.ok) {
      reports.value = res.reports || []
      discoverErrors.value = res.errors || []
      reportState.value = reports.value.length ? 'discovered' : 'empty'
    }
  } catch (e) {
    if (seq !== reportRequestSeq || key !== `${props.market}:${props.symbol}`) return
    discoverErrors.value = [e.message || '发现失败']
    reportState.value = 'error'
  } finally {
    if (seq === reportRequestSeq) discovering.value = false
  }
}

async function submitManual() {
  manualError.value = ''
  manualSuccess.value = ''
  const url = manualUrl.value.trim()
  if (!url) { manualError.value = '请输入 PDF URL'; return }
  try {
    const res = await addManualReport(props.market, props.symbol, {
      pdf_url: url,
      report_year: Number(manualYear.value) || 0,
    })
    if (res.ok) {
      manualSuccess.value = '已接受手动录入的 PDF URL。'
      manualUrl.value = ''
      manualYear.value = ''
      await loadReports()
    } else {
      manualError.value = res.message || '提交失败'
    }
  } catch (e) {
    manualError.value = e.data?.message || e.message || '提交失败'
  }
}

async function downloadAndParse(item) {
  const reportId = item.id || item.report_id
  if (!reportId) {
    discoverErrors.value = ['该报告尚未入库，无法下载/解析。']
    return
  }
  actionMessage.value = '下载/解析中...'
  const downloadResult = await downloadCompanyV2Report(props.market, props.symbol, reportId)
  const parseResult = await parseCompanyV2Report(props.market, props.symbol, reportId)
  item.download_status = parseResult.status || downloadResult.status
  item.pdf_status = parseResult.ok ? 'parsed' : (downloadResult.status || 'download_failed')
  actionMessage.value = parseResult.ok ? 'PDF 已解析。' : 'PDF 解析未完成。'
}

async function verifyReport(item) {
  const reportId = item.id || item.report_id
  if (!reportId) {
    discoverErrors.value = ['该报告尚未入库，无法核验。']
    return
  }
  actionMessage.value = '核验中...'
  const result = await verifyCompanyV2Report(props.market, props.symbol, reportId)
  item.official_verification = result.official_verification || { status: result.status || 'unverified' }
  if (item.official_verification.period_mismatch_count > 0) {
    actionMessage.value = '当前年报年份与结构化数据期间不一致，已跳过强核验。'
    return
  }
  actionMessage.value = item.official_verification.status === 'conflict'
    ? '结构化数据与年报字段存在差异。'
    : item.official_verification.status === 'partial'
      ? '部分字段已核验，其余字段缺少可靠抽取结果。'
      : '核验结果已更新。'
}

async function aiVerifyReport(item) {
  const reportId = item.id || item.report_id
  if (!reportId) {
    discoverErrors.value = ['该报告尚未入库，无法 AI 校对。']
    return
  }
  actionMessage.value = 'AI 校对中...'
  const result = await aiVerifyCompanyV2Report(props.market, props.symbol, reportId, {
    report_year: item.report_year,
    report_type: item.report_type || 'annual',
  })
  item.ai_verification = result
  if (result.human_review_queue?.length) {
    actionMessage.value = 'AI 校对完成：以下字段建议人工抽检。'
  } else if (result.ai_verification_status === 'verified') {
    actionMessage.value = 'AI 校对通过，无需人工复核。'
  } else if (result.ai_verification_status === 'conflict') {
    actionMessage.value = 'AI 校对完成：同期同口径数据存在差异。'
  } else if (result.non_blocking_findings?.length) {
    actionMessage.value = 'AI 校对完成：存在非阻断发现。'
  } else {
    actionMessage.value = 'AI 校对完成。'
  }
}

onMounted(() => loadReports())
watch(() => [props.market, props.symbol], () => {
  reports.value = []
  reportState.value = 'idle'
  discovering.value = false
  discoverErrors.value = []
  showManual.value = false
  manualError.value = ''
  manualSuccess.value = ''
  actionMessage.value = ''
  autoDiscoverKey.value = ''
  reportRequestSeq += 1
  loadReports()
})
</script>

<style scoped>
.cv2-report-docs { display: flex; flex-direction: column; gap: 16px; }
.cv2-rd-header { display: flex; flex-direction: column; gap: 6px; }
.cv2-rd-status-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cv2-rd-badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; font-weight: 500; }
.cv2-rd-badge.green { background: #d1fae5; color: #065f46; }
.cv2-rd-badge.yellow { background: #fef3c7; color: #92400e; }
.cv2-rd-badge.grey { background: #f3f4f6; color: #6b7280; }
.cv2-rd-count, .cv2-rd-summary { font-size: 12px; color: #6b7280; }
.cv2-rd-rag-badge { font-size: 11px; background: #ede9fe; color: #5b21b6; padding: 2px 6px; border-radius: 4px; }
.cv2-rd-hint { font-size: 12px; color: #6b7280; margin: 0; }
.cv2-rd-timeline { display: flex; flex-direction: column; gap: 4px; }
.cv2-rd-year-node { display: flex; gap: 12px; align-items: flex-start; }
.cv2-rd-year-label { font-size: 13px; font-weight: 600; color: #374151; min-width: 42px; padding-top: 10px; }
.cv2-rd-card { flex: 1; display: flex; gap: 10px; align-items: flex-start; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 12px; }
.cv2-rd-card.no-pdf { opacity: 0.6; }
.cv2-rd-icon { font-size: 20px; line-height: 1; margin-top: 2px; }
.cv2-rd-icon.muted { opacity: 0.4; }
.cv2-rd-card-body { flex: 1; min-width: 0; }
.cv2-rd-title { font-size: 13px; color: #111827; margin: 0 0 4px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cv2-rd-title.muted { color: #9ca3af; }
.cv2-rd-meta { font-size: 11px; color: #6b7280; margin: 0 0 6px; display: flex; gap: 8px; flex-wrap: wrap; }
.cv2-rd-source { background: #eff6ff; color: #1d4ed8; padding: 1px 5px; border-radius: 3px; font-size: 10px; }
.cv2-rd-full { background: #f0fdf4; color: #166534; padding: 1px 5px; border-radius: 3px; font-size: 10px; }
.cv2-rd-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.cv2-rd-action-btn { font-size: 12px; padding: 3px 10px; border-radius: 5px; cursor: pointer; border: 1px solid #d1d5db; background: #fff; color: #374151; text-decoration: none; display: inline-flex; align-items: center; }
.cv2-rd-action-btn.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
.cv2-rd-action-btn.primary:hover { background: #1d4ed8; }
.cv2-rd-expand-btn { font-size: 12px; color: #2563eb; background: none; border: none; cursor: pointer; padding: 6px 0; text-align: left; }
.cv2-rd-empty { padding: 16px; background: #f9fafb; border-radius: 8px; font-size: 13px; color: #6b7280; }
.cv2-rd-toolbar { display: flex; gap: 8px; flex-wrap: wrap; }
.cv2-rd-discover-btn { font-size: 12px; padding: 6px 14px; border-radius: 6px; cursor: pointer; border: 1px solid #2563eb; background: #2563eb; color: #fff; }
.cv2-rd-discover-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.cv2-rd-discover-btn.secondary { background: #fff; color: #374151; border-color: #d1d5db; }
.cv2-rd-manual { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.cv2-rd-manual h4 { margin: 0; font-size: 13px; }
.cv2-rd-manual-row { display: flex; gap: 8px; flex-wrap: wrap; }
.cv2-rd-input { font-size: 12px; padding: 5px 8px; border: 1px solid #d1d5db; border-radius: 5px; flex: 1; min-width: 200px; }
.cv2-rd-input.short { max-width: 100px; flex: none; }
.cv2-rd-error { color: #dc2626; font-size: 12px; margin: 0; }
.cv2-rd-success { color: #059669; font-size: 12px; margin: 0; }
.cv2-rd-errors { font-size: 11px; color: #6b7280; }
.cv2-rd-errors ul { margin: 4px 0 0; padding-left: 16px; }
</style>
