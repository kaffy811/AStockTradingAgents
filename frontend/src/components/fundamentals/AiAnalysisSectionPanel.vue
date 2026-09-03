<template>
  <div class="aasp-root">
    <!-- Header with refresh button and review status -->
    <div class="aasp-header">
      <div class="aasp-badges">
        <span v-if="reviewStatus" :class="['aasp-review-badge', 'aasp-review-badge--' + reviewStatus]">
          {{ reviewLabel }}
        </span>
        <span v-if="isStale" class="aasp-stale-badge">数据来自缓存</span>
      </div>
      <button
        class="aasp-refresh-btn"
        :disabled="refreshing"
        @click="handleRefresh"
      >
        <span v-if="refreshing">刷新中…</span>
        <span v-else>重新生成</span>
      </button>
    </div>

    <!-- Delegate to AiAnalysisCard -->
    <AiAnalysisCard
      :envelope="envelope"
      :loading="loading"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import AiAnalysisCard from './AiAnalysisCard.vue'

const props = defineProps({
  envelope:  { type: Object, default: null },
  loading:   { type: Boolean, default: false },
  onRefresh: { type: Function, default: null },
})

const refreshing = ref(false)

const analysis     = computed(() => props.envelope?.data?.ai_analysis || null)
const isStale      = computed(() => props.envelope?.stale === true)
const reviewStatus = computed(() => analysis.value?.review?.review_status || '')

const reviewLabel = computed(() => {
  const s = reviewStatus.value
  if (s === 'approved') return '已审核'
  if (s === 'revised')  return '已修订'
  if (s === 'rejected') return '审核未通过'
  return ''
})

async function handleRefresh() {
  if (!props.onRefresh || refreshing.value) return
  refreshing.value = true
  try {
    await props.onRefresh()
  } finally {
    refreshing.value = false
  }
}
</script>

<style scoped>
.aasp-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.aasp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.aasp-badges {
  display: flex;
  align-items: center;
  gap: 8px;
}

.aasp-review-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

.aasp-review-badge--approved { background: #d1fae5; color: #065f46; }
.aasp-review-badge--revised  { background: #fef3c7; color: #92400e; }
.aasp-review-badge--rejected { background: #fee2e2; color: #991b1b; }

.aasp-stale-badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 4px;
  background: #fff8e1;
  color: #856404;
  border: 1px solid #ffc107;
}

.aasp-refresh-btn {
  background: #f0f4fd;
  border: 1px solid #c8deff;
  color: #1a73e8;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  padding: 5px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.aasp-refresh-btn:hover:not(:disabled) {
  background: #e8f0fe;
}

.aasp-refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
