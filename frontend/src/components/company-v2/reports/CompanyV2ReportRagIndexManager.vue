<template>
  <div class="cv2-rag-manager" data-testid="report-rag-index-manager">
    <div class="cv2-rag-manager-head">
      <span>报告索引管理</span>
      <button class="cv2-rag-manager-btn" type="button" @click="loadIndexes">刷新列表</button>
    </div>
    <div v-if="rows.length" class="cv2-rag-manager-list">
      <div v-for="row in rows" :key="row.report_id" class="cv2-rag-manager-row">
        <div class="cv2-rag-manager-main">
          <strong>{{ row.report_year }} · {{ reportTypeLabel(row.report_type) }}</strong>
          <span>{{ row.report_title || '报告' }}</span>
          <CompanyV2ReportRagStatus :status="row.status" :chunk-count="row.chunk_count || 0" />
          <em v-if="row.stale_reason">{{ row.stale_reason }}</em>
        </div>
        <div class="cv2-rag-manager-actions">
          <button class="cv2-rag-manager-btn" type="button" @click="emitBuild(row)">建立</button>
          <button class="cv2-rag-manager-btn" type="button" @click="refreshIndex(row)">刷新</button>
          <button class="cv2-rag-manager-btn danger" type="button" @click="deleteIndex(row)">删除</button>
        </div>
      </div>
    </div>
    <p v-else class="cv2-rag-manager-empty">暂无报告问答索引。</p>
    <p v-if="message" class="cv2-rag-manager-note">{{ message }}</p>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import {
  deleteCompanyV2ReportRagIndex,
  listCompanyV2ReportRagIndexes,
  refreshCompanyV2ReportRagIndex,
} from '../../../api/companyV2.js'
import CompanyV2ReportRagStatus from './CompanyV2ReportRagStatus.vue'

const props = defineProps({
  market: { type: String, required: true },
  symbol: { type: String, required: true },
})

const emit = defineEmits(['build'])
const rows = ref([])
const message = ref('')

function reportTypeLabel(type) {
  return { annual: '年报', semiannual: '半年报', semi_annual: '半年报', q1: '一季报', q3: '三季报' }[type] || type || '报告'
}

async function loadIndexes() {
  const result = await listCompanyV2ReportRagIndexes(props.market, props.symbol)
  rows.value = result.indexes || []
}

function emitBuild(row) {
  emit('build', row)
}

async function refreshIndex(row) {
  message.value = ''
  const result = await refreshCompanyV2ReportRagIndex(props.market, props.symbol, row.report_id)
  message.value = result.job_id ? '刷新任务已提交。' : (result.message || '刷新请求已提交。')
  await loadIndexes()
}

async function deleteIndex(row) {
  if (!window.confirm('删除该报告问答索引？原 PDF 和解析文本不会删除。')) return
  const result = await deleteCompanyV2ReportRagIndex(props.market, props.symbol, row.report_id)
  message.value = result.ok ? '索引已删除。' : (result.message || '删除失败。')
  await loadIndexes()
}

onMounted(loadIndexes)
</script>

<style scoped>
.cv2-rag-manager {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cv2-rag-manager-head,
.cv2-rag-manager-row,
.cv2-rag-manager-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cv2-rag-manager-head { justify-content: space-between; font-size: 13px; font-weight: 600; color: #111827; }
.cv2-rag-manager-list { display: flex; flex-direction: column; gap: 8px; }
.cv2-rag-manager-row { justify-content: space-between; border-top: 1px solid #f3f4f6; padding-top: 8px; }
.cv2-rag-manager-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12px; color: #4b5563; }
.cv2-rag-manager-main strong { color: #111827; }
.cv2-rag-manager-main em { color: #92400e; font-style: normal; }
.cv2-rag-manager-btn {
  min-height: 28px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  background: #fff;
  color: #374151;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}
.cv2-rag-manager-btn.danger { color: #b91c1c; border-color: #fecaca; }
.cv2-rag-manager-empty,
.cv2-rag-manager-note { margin: 0; font-size: 12px; color: #6b7280; }
</style>
