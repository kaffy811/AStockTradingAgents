<template>
  <div class="cv2-report-compare" data-testid="report-comparison-panel">
    <div class="cv2-report-compare-head">
      <span class="cv2-report-compare-title">Report Compare</span>
      <button class="cv2-report-compare-btn" type="button" @click="loadIndexes">刷新列表</button>
    </div>

    <div class="cv2-report-compare-list">
      <label
        v-for="item in selectableReports"
        :key="reportKey(item)"
        :class="['cv2-report-compare-row', !item.selectable && 'disabled']"
      >
        <input
          v-model="selectedReportIds"
          type="checkbox"
          :value="String(reportId(item))"
          :disabled="!item.selectable || selectedReportIds.length >= 4 && !selectedReportIds.includes(String(reportId(item)))"
          data-testid="report-compare-checkbox"
        />
        <span class="cv2-report-compare-meta">
          <strong>{{ item.report_year }} · {{ reportTypeLabel(item.report_type) }}</strong>
          <span>{{ item.report_title || item.title || '报告' }}</span>
          <CompanyV2ReportRagStatus :status="item.index_status" :chunk-count="item.chunk_count || 0" />
        </span>
      </label>
    </div>

    <div class="cv2-report-compare-actions">
      <label class="cv2-report-compare-field">
        <span>比较模式</span>
        <select v-model="comparisonMode" data-testid="report-compare-mode">
          <option value="generic_comparison">通用比较</option>
          <option value="metric_change">指标变化</option>
          <option value="business_change">业务变化</option>
          <option value="risk_change">风险变化</option>
          <option value="management_discussion_change">管理层讨论变化</option>
        </select>
      </label>
      <label class="cv2-report-compare-field grow">
        <span>比较问题</span>
        <input
          v-model="question"
          class="cv2-report-compare-input"
          maxlength="500"
          placeholder="例如：比较 2023 和 2024 年营业收入变化"
          data-testid="report-compare-question"
        />
      </label>
      <button
        class="cv2-report-compare-btn primary"
        type="button"
        :disabled="querying || selectedReportIds.length < 2"
        data-testid="report-compare-submit"
        @click="submitComparison"
      >
        {{ querying ? '比较中' : '开始比较' }}
      </button>
    </div>

    <p v-if="helperText" class="cv2-report-compare-note">{{ helperText }}</p>
    <p v-if="errorMessage" class="cv2-report-compare-error">{{ errorMessage }}</p>

    <div v-if="result" class="cv2-report-compare-result" data-testid="report-compare-result">
      <p class="cv2-report-compare-answer">{{ result.answer }}</p>

      <div v-if="result.comparison_items?.length" class="cv2-report-compare-items">
        <article v-for="item in result.comparison_items" :key="item.topic" class="cv2-report-compare-item">
          <div class="cv2-report-compare-item-head">
            <strong>{{ item.topic }}</strong>
            <span v-if="item.change?.warnings?.length" class="cv2-report-compare-warning">
              {{ item.change.warnings.join(' / ') }}
            </span>
          </div>
          <div class="cv2-report-compare-item-body">
            <div v-for="row in item.reports" :key="`${item.topic}-${row.report_id}`" class="cv2-report-compare-report">
              <span>{{ row.report_year }} 年 {{ row.report_type }} · 第 {{ row.evidence_pages?.[0] || '?' }} 页</span>
              <span>{{ row.value || 'N/A' }}</span>
            </div>
          </div>
        </article>
      </div>

      <div v-if="result.citations?.length" class="cv2-report-compare-citations">
        <button
          v-for="citation in result.citations"
          :key="`${citation.report_id}-${citation.page}`"
          class="cv2-report-compare-citation"
          type="button"
          @click="selectedCitation = selectedCitation === citation ? null : citation"
        >
          {{ citation.report_year }} · {{ reportTypeLabel(citation.report_type) }} · 第 {{ citation.page }} 页
        </button>
      </div>
      <div v-if="selectedCitation" class="cv2-report-compare-citation-detail" data-testid="report-compare-citation-detail">
        <div class="cv2-report-compare-citation-head">
          {{ selectedCitation.report_year }} · {{ reportTypeLabel(selectedCitation.report_type) }} · 第 {{ selectedCitation.page }} 页
        </div>
        <p>{{ selectedCitation.excerpt }}</p>
        <a v-if="selectedCitation.source_url" :href="selectedCitation.source_url" target="_blank" rel="noopener noreferrer">CNINFO PDF</a>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { compareCompanyV2ReportRag, listCompanyV2ReportRagIndexes } from '../../../api/companyV2.js'
import CompanyV2ReportRagStatus from './CompanyV2ReportRagStatus.vue'

const props = defineProps({
  market: { type: String, required: true },
  symbol: { type: String, required: true },
  reports: { type: Array, default: () => [] },
})

const selectedReportIds = ref([])
const comparisonMode = ref('generic_comparison')
const question = ref('')
const querying = ref(false)
const errorMessage = ref('')
const result = ref(null)
const selectedCitation = ref(null)
const indexRows = ref([])

const indexMap = computed(() => {
  const map = new Map()
  for (const row of indexRows.value) map.set(String(row.report_id), row)
  return map
})

const selectableReports = computed(() => {
  return (props.reports || []).map(item => {
    const reportId = reportIdOf(item)
    const indexRow = indexMap.value.get(String(reportId))
    const indexStatus = indexRow?.status || item.rag_status || 'pending'
    const selectable = Boolean(indexRow ? (indexRow.active_index && !indexRow.deleted_at && ['indexed', 'partial'].includes(indexStatus)) : ['indexed', 'partial', 'rag_ready'].includes(indexStatus))
    return {
      ...item,
      report_id: reportId,
      index_status: indexStatus,
      selectable,
      chunk_count: indexRow?.chunk_count ?? item.chunk_count ?? 0,
    }
  })
})

const helperText = computed(() => {
  if (selectedReportIds.value.length < 2) return '请显式选择 2 到 4 份已索引报告。'
  if (selectedReportIds.value.length > 4) return '最多只能选择 4 份报告。'
  return '比较模式只会使用所选报告。'
})

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

function reportIdOf(item) {
  return item.id || item.report_id
}

function reportKey(item) {
  return `${reportIdOf(item)}-${item.report_year}-${item.report_type}`
}

async function loadIndexes() {
  const payload = await listCompanyV2ReportRagIndexes(props.market, props.symbol)
  indexRows.value = payload.indexes || []
}

async function submitComparison() {
  errorMessage.value = ''
  result.value = null
  selectedCitation.value = null
  if (selectedReportIds.value.length < 2 || selectedReportIds.value.length > 4) {
    errorMessage.value = '比较模式必须选择 2 到 4 份报告。'
    return
  }
  querying.value = true
  try {
    result.value = await compareCompanyV2ReportRag(props.market, props.symbol, {
      report_ids: selectedReportIds.value.map(id => Number(id)),
      question: question.value.trim(),
      comparison_mode: comparisonMode.value,
      top_k_per_report: 4,
      answer_style: 'concise',
    })
  } catch (error) {
    errorMessage.value = error.data?.message || error.message || '比较请求失败'
  } finally {
    querying.value = false
  }
}

watch(() => props.symbol, async () => {
  selectedReportIds.value = []
  question.value = ''
  comparisonMode.value = 'generic_comparison'
  result.value = null
  errorMessage.value = ''
  selectedCitation.value = null
  await loadIndexes()
})

onMounted(loadIndexes)
</script>

<style scoped>
.cv2-report-compare {
  margin-top: 12px;
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cv2-report-compare-head,
.cv2-report-compare-actions,
.cv2-report-compare-item-head,
.cv2-report-compare-report {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cv2-report-compare-head { justify-content: space-between; }
.cv2-report-compare-title { font-size: 13px; font-weight: 600; color: #111827; }
.cv2-report-compare-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cv2-report-compare-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.cv2-report-compare-row.disabled { opacity: 0.55; cursor: not-allowed; }
.cv2-report-compare-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: #4b5563;
}
.cv2-report-compare-meta strong { color: #111827; }
.cv2-report-compare-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #4b5563;
}
.cv2-report-compare-field.grow { flex: 1; min-width: min(100%, 320px); }
.cv2-report-compare-input,
.cv2-report-compare-field select {
  min-height: 32px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  padding: 5px 8px;
  font-size: 13px;
  background: #fff;
}
.cv2-report-compare-btn {
  min-height: 32px;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #374151;
  border-radius: 5px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
}
.cv2-report-compare-btn.primary { border-color: #1d4ed8; background: #1d4ed8; color: #fff; }
.cv2-report-compare-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.cv2-report-compare-note,
.cv2-report-compare-error {
  margin: 0;
  font-size: 12px;
}
.cv2-report-compare-note { color: #6b7280; }
.cv2-report-compare-error { color: #b91c1c; }
.cv2-report-compare-result {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cv2-report-compare-answer { margin: 0; font-size: 13px; line-height: 1.65; color: #111827; }
.cv2-report-compare-items { display: flex; flex-direction: column; gap: 8px; }
.cv2-report-compare-item {
  border-top: 1px solid #f3f4f6;
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cv2-report-compare-item-head { justify-content: space-between; font-size: 12px; }
.cv2-report-compare-warning { color: #92400e; }
.cv2-report-compare-report { font-size: 12px; color: #4b5563; justify-content: space-between; }
.cv2-report-compare-report span:last-child { color: #111827; }
.cv2-report-compare-citations {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cv2-report-compare-citation {
  min-height: 26px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}
.cv2-report-compare-citation-detail {
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 6px;
  padding: 10px;
  font-size: 12px;
  color: #374151;
}
.cv2-report-compare-citation-detail p { margin: 4px 0 6px; line-height: 1.6; }
.cv2-report-compare-citation-detail a { color: #2563eb; text-decoration: none; }
.cv2-report-compare-citation-head { font-weight: 600; color: #111827; }
</style>
