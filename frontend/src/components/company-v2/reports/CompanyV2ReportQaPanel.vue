<template>
  <div class="cv2-report-qa" data-testid="report-qa-panel">
    <div class="cv2-report-qa-head">
      <span class="cv2-report-qa-title">Report QA</span>
      <CompanyV2ReportRagStatus :status="ragStatus.status" :chunk-count="ragStatus.chunk_count || 0" />
    </div>

    <label class="cv2-report-qa-selector">
      <span>报告</span>
      <select v-model="selectedReportId" data-testid="report-rag-selector" @change="handleReportSwitch">
        <option
          v-for="item in selectableReports"
          :key="item.id || item.report_id"
          :value="String(item.id || item.report_id)"
        >
          {{ item.report_year }} · {{ reportTypeLabel(item.report_type) }} · {{ item.title || item.report_title || '报告' }}
        </option>
      </select>
    </label>

    <div class="cv2-report-qa-actions">
      <button
        class="cv2-report-qa-btn"
        type="button"
        :disabled="indexing || ragStatus.status === 'indexing'"
        data-testid="report-rag-index-btn"
        @click="buildIndex"
      >
        {{ indexing ? '索引中' : '建立报告问答索引' }}
      </button>
      <span v-if="statusMessage" class="cv2-report-qa-note">{{ statusMessage }}</span>
    </div>

    <form v-if="canQuery" class="cv2-report-qa-form" data-testid="report-rag-query-form" @submit.prevent="submitQuestion">
      <input
        v-model="question"
        class="cv2-report-qa-input"
        maxlength="500"
        placeholder="输入报告原文问题"
        data-testid="report-rag-question"
      />
      <button class="cv2-report-qa-btn primary" type="submit" :disabled="querying || !question.trim()">
        {{ querying ? '检索中' : '提问' }}
      </button>
    </form>

    <div v-if="answer" :class="['cv2-report-qa-answer', answer.status]" data-testid="report-rag-answer">
      <p>{{ answer.answer }}</p>
      <CompanyV2ReportCitationList :citations="answer.citations || []" />
    </div>

    <p v-if="errorMessage" class="cv2-report-qa-error" data-testid="report-rag-error">{{ errorMessage }}</p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  getCompanyV2ReportRagStatus,
  getCompanyV2ReportRagJob,
  indexCompanyV2ReportRag,
  queryCompanyV2ReportRag,
} from '../../../api/companyV2.js'
import CompanyV2ReportCitationList from './CompanyV2ReportCitationList.vue'
import CompanyV2ReportRagStatus from './CompanyV2ReportRagStatus.vue'

const props = defineProps({
  market: { type: String, required: true },
  symbol: { type: String, required: true },
  report: { type: Object, required: true },
  reports: { type: Array, default: () => [] },
})

const ragStatus = ref({ status: 'pending', chunk_count: 0 })
const question = ref('')
const answer = ref(null)
const indexing = ref(false)
const querying = ref(false)
const errorMessage = ref('')
const selectedReportId = ref(String(props.report.id || props.report.report_id || ''))
const activeJobId = ref('')

const selectableReports = computed(() => {
  const rows = props.reports?.length ? props.reports : [props.report]
  return rows.filter(item => item.id || item.report_id)
})
const selectedReport = computed(() => selectableReports.value.find(item => String(item.id || item.report_id) === String(selectedReportId.value)) || props.report)
const reportId = computed(() => selectedReport.value.id || selectedReport.value.report_id)
const canQuery = computed(() => ['indexed', 'partial'].includes(ragStatus.value.status))
const statusMessage = computed(() => {
  if (ragStatus.value.status === 'pending') return '索引不会自动建立。'
  if (ragStatus.value.status === 'failed') return ragStatus.value.last_error || '索引失败。'
  if (ragStatus.value.status === 'stale') return ragStatus.value.stale_reason || '索引已过期。'
  if (ragStatus.value.status === 'indexed') return ragStatus.value.embedding_model || ''
  return ''
})

async function refreshStatus() {
  if (!reportId.value) return
  try {
    ragStatus.value = await getCompanyV2ReportRagStatus(props.market, props.symbol, reportId.value)
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '状态读取失败'
  }
}

function reportTypeLabel(type) {
  return {
    annual: '年报',
    semiannual: '半年报',
    semi_annual: '半年报',
    quarterly: '季报',
    q1: '一季报',
    q3: '三季报',
  }[type] || type || '报告'
}

async function handleReportSwitch() {
  answer.value = null
  question.value = ''
  errorMessage.value = ''
  activeJobId.value = ''
  ragStatus.value = { status: 'pending', chunk_count: 0 }
  await refreshStatus()
}

async function refreshJobOnce() {
  if (!activeJobId.value || !reportId.value) return
  const job = await getCompanyV2ReportRagJob(props.market, props.symbol, reportId.value, activeJobId.value)
  if (job.status === 'succeeded') {
    await refreshStatus()
  } else if (job.status === 'failed') {
    ragStatus.value = { ...ragStatus.value, status: 'failed', last_error: job.last_error }
    errorMessage.value = job.last_error || '索引失败'
  } else {
    ragStatus.value = { ...ragStatus.value, status: 'indexing' }
  }
}

async function buildIndex() {
  if (!reportId.value) return
  indexing.value = true
  errorMessage.value = ''
  answer.value = null
  try {
    const result = await indexCompanyV2ReportRag(props.market, props.symbol, reportId.value)
    activeJobId.value = result.job_id || ''
    ragStatus.value = {
      status: ['queued', 'running'].includes(result.status) ? 'indexing' : result.status,
      chunk_count: result.chunk_count,
      embedding_model: result.embedding_model,
      last_error: result.message,
    }
    await refreshJobOnce()
  } catch (error) {
    const data = error.data || {}
    ragStatus.value = { ...ragStatus.value, status: 'failed', last_error: data.message || error.message }
    errorMessage.value = data.message || error.message || '索引失败'
  } finally {
    indexing.value = false
  }
}

async function submitQuestion() {
  if (!reportId.value || !question.value.trim()) return
  querying.value = true
  errorMessage.value = ''
  answer.value = null
  try {
    answer.value = await queryCompanyV2ReportRag(props.market, props.symbol, reportId.value, {
      question: question.value.trim(),
      top_k: 6,
      answer_style: 'concise',
    })
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '问答请求失败'
  } finally {
    querying.value = false
  }
}

onMounted(refreshStatus)
</script>

<style scoped>
.cv2-report-qa {
  margin-top: 10px;
  border-top: 1px solid #e5e7eb;
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cv2-report-qa-head,
.cv2-report-qa-actions,
.cv2-report-qa-form {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cv2-report-qa-title { font-size: 13px; font-weight: 600; color: #111827; }
.cv2-report-qa-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #4b5563;
}
.cv2-report-qa-selector select {
  min-height: 30px;
  max-width: min(100%, 520px);
  border: 1px solid #d1d5db;
  border-radius: 5px;
  background: #fff;
  padding: 4px 8px;
  font-size: 12px;
}
.cv2-report-qa-btn {
  min-height: 30px;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #374151;
  border-radius: 5px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
}
.cv2-report-qa-btn.primary { border-color: #2563eb; background: #2563eb; color: #fff; }
.cv2-report-qa-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.cv2-report-qa-note { font-size: 12px; color: #6b7280; }
.cv2-report-qa-input {
  min-width: min(100%, 320px);
  flex: 1;
  min-height: 32px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  padding: 5px 8px;
  font-size: 13px;
}
.cv2-report-qa-answer {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  padding: 10px;
  font-size: 13px;
  color: #111827;
}
.cv2-report-qa-answer.insufficient_evidence { background: #f9fafb; color: #4b5563; }
.cv2-report-qa-answer p { margin: 0 0 8px; line-height: 1.65; }
.cv2-report-qa-error { margin: 0; color: #b91c1c; font-size: 12px; }
</style>
