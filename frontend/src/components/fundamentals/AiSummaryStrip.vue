<template>
  <div class="ai-strip" :class="{ 'ai-strip--unavailable': isUnavailable }">
    <!-- Unavailable placeholder -->
    <div v-if="isUnavailable" class="ai-strip__placeholder">
      <span class="ai-strip__icon">🤖</span>
      <span class="ai-strip__placeholder-text">AI 分析暂不可用，当前展示确定性财务数据</span>
    </div>

    <!-- Loading skeleton -->
    <div v-else-if="loading" class="ai-strip__skeleton">
      <div class="ai-strip__skel-line ai-strip__skel-line--short"></div>
      <div class="ai-strip__skel-line"></div>
      <div class="ai-strip__skel-line ai-strip__skel-line--medium"></div>
    </div>

    <!-- Content -->
    <details v-else class="ai-strip__details" :open="expanded">
      <summary class="ai-strip__summary-row" @click.prevent="expanded = !expanded">
        <!-- Score badge -->
        <span class="ai-strip__score-badge" :class="scoreBadgeClass">
          {{ scoreDisplay }}
        </span>
        <!-- Summary text -->
        <span class="ai-strip__summary-text">{{ analysis.summary }}</span>
        <!-- Review status badge -->
        <span class="ai-strip__review-badge" :class="reviewBadgeClass">
          {{ reviewLabel }}
        </span>
        <!-- Toggle arrow -->
        <span class="ai-strip__toggle" :class="{ 'ai-strip__toggle--open': expanded }">▾</span>
        <!-- Refresh button -->
        <button class="ai-strip__refresh" :disabled="loading" @click.stop="$emit('refresh')" title="刷新 AI 摘要">
          <span :class="{ 'ai-strip__refresh--spinning': loading }">↻</span>
        </button>
      </summary>

      <div class="ai-strip__body">
        <!-- Top 2 highlights -->
        <div v-if="topHighlights.length" class="ai-strip__section">
          <div class="ai-strip__section-title ai-strip__section-title--positive">亮点</div>
          <ul class="ai-strip__list">
            <li v-for="h in topHighlights" :key="h.title" class="ai-strip__list-item ai-strip__list-item--positive">
              <strong>{{ h.title }}</strong>
              <span v-if="h.detail"> — {{ h.detail }}</span>
            </li>
          </ul>
        </div>

        <!-- Top 2 risks -->
        <div v-if="topRisks.length" class="ai-strip__section">
          <div class="ai-strip__section-title ai-strip__section-title--negative">风险</div>
          <ul class="ai-strip__list">
            <li v-for="r in topRisks" :key="r.title" class="ai-strip__list-item ai-strip__list-item--negative">
              <strong>{{ r.title }}</strong>
              <span v-if="r.detail"> — {{ r.detail }}</span>
            </li>
          </ul>
        </div>

        <!-- Disclaimer -->
        <div class="ai-strip__disclaimer">{{ disclaimer }}</div>

        <!-- View full button -->
        <button class="ai-strip__full-btn" @click="$emit('view-full')">
          查看完整 AI 分析 →
        </button>
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  envelope: { type: Object, default: null },
  loading:  { type: Boolean, default: false },
})

defineEmits(['view-full', 'refresh'])

const expanded = ref(false)

const analysis = computed(() => {
  return props.envelope?.data?.ai_analysis || null
})

const isUnavailable = computed(() => {
  if (props.loading) return false
  if (!props.envelope) return true
  if (props.envelope.partial && !analysis.value?.summary) return true
  if (!analysis.value?.summary) return true
  if (analysis.value?.review?.review_status === 'rejected') return true
  return false
})

const scoreDisplay = computed(() => {
  const s = analysis.value?.overall_score
  return s != null ? String(s) : '—'
})

const scoreBadgeClass = computed(() => {
  const s = analysis.value?.overall_score
  if (s == null) return 'ai-strip__score-badge--neutral'
  if (s >= 80) return 'ai-strip__score-badge--high'
  if (s >= 60) return 'ai-strip__score-badge--medium'
  return 'ai-strip__score-badge--low'
})

const reviewLabel = computed(() => {
  const status = analysis.value?.review?.review_status
  if (status === 'approved') return '已审核'
  if (status === 'revised') return '已修订'
  if (status === 'rejected') return '审核未通过'
  return ''
})

const reviewBadgeClass = computed(() => {
  const status = analysis.value?.review?.review_status
  if (status === 'approved') return 'ai-strip__review-badge--approved'
  if (status === 'revised') return 'ai-strip__review-badge--revised'
  if (status === 'rejected') return 'ai-strip__review-badge--rejected'
  return ''
})

const topHighlights = computed(() => (analysis.value?.highlights || []).slice(0, 2))
const topRisks = computed(() => (analysis.value?.risks || []).slice(0, 2))

const disclaimer = computed(() => {
  return analysis.value?.disclaimer || '本内容由 AI 基于公开财务数据生成，仅供参考，不构成投资建议。'
})
</script>

<style scoped>
.ai-strip {
  background: #f0f6ff;
  border: 1px solid #c8deff;
  border-radius: 10px;
  overflow: hidden;
  font-size: 13px;
}

.ai-strip--unavailable {
  background: #f8f9fa;
  border-color: #e0e0e0;
}

/* Placeholder */
.ai-strip__placeholder {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  color: var(--color-text-secondary, #888);
}

.ai-strip__icon {
  font-size: 16px;
  flex-shrink: 0;
}

.ai-strip__placeholder-text {
  font-size: 13px;
}

/* Skeleton */
.ai-strip__skeleton {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-strip__skel-line {
  height: 12px;
  background: linear-gradient(90deg, #e8eef8 25%, #d0ddf5 50%, #e8eef8 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
  border-radius: 6px;
  width: 100%;
}

.ai-strip__skel-line--short { width: 40%; }
.ai-strip__skel-line--medium { width: 65%; }

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Summary row (always visible) */
.ai-strip__details {
  cursor: default;
}

.ai-strip__summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.ai-strip__summary-row::-webkit-details-marker {
  display: none;
}

.ai-strip__score-badge {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
  color: #fff;
}

.ai-strip__score-badge--high   { background: #22c55e; }
.ai-strip__score-badge--medium { background: #f59e0b; }
.ai-strip__score-badge--low    { background: #ef4444; }
.ai-strip__score-badge--neutral { background: #94a3b8; }

.ai-strip__summary-text {
  flex: 1;
  color: var(--color-text-primary, #1a2540);
  line-height: 1.4;
  font-weight: 500;
}

.ai-strip__review-badge {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  font-weight: 600;
}

.ai-strip__review-badge--approved { background: #d1fae5; color: #065f46; }
.ai-strip__review-badge--revised  { background: #fef3c7; color: #92400e; }
.ai-strip__review-badge--rejected { background: #fee2e2; color: #991b1b; }

.ai-strip__toggle {
  flex-shrink: 0;
  font-size: 14px;
  color: #64748b;
  transition: transform 0.2s;
  display: inline-block;
}

.ai-strip__toggle--open {
  transform: rotate(180deg);
}

/* Expanded body */
.ai-strip__body {
  padding: 0 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-top: 1px solid #dbeafe;
}

.ai-strip__section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ai-strip__section-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.ai-strip__section-title--positive { color: #16a34a; }
.ai-strip__section-title--negative { color: #dc2626; }

.ai-strip__list {
  margin: 0;
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ai-strip__list-item {
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-text-primary, #1a2540);
}

.ai-strip__list-item--positive::marker { color: #22c55e; }
.ai-strip__list-item--negative::marker { color: #ef4444; }

.ai-strip__disclaimer {
  font-size: 11px;
  color: var(--color-text-secondary, #888);
  line-height: 1.4;
  margin-top: 4px;
}

.ai-strip__full-btn {
  align-self: flex-start;
  background: #3b82f6;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.ai-strip__full-btn:hover {
  background: #2563eb;
}

/* Refresh button */
.ai-strip__refresh {
  flex-shrink: 0;
  background: none;
  border: 1px solid #c8deff;
  border-radius: 6px;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #1a73e8;
  cursor: pointer;
  padding: 0;
  transition: background 0.15s, opacity 0.15s;
  line-height: 1;
}

.ai-strip__refresh:hover:not(:disabled) {
  background: #e8f0fe;
}

.ai-strip__refresh:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

.ai-strip__refresh--spinning {
  display: inline-block;
  animation: spin 1s linear infinite;
}
</style>
