<template>
  <div class="hrp-root">
    <!-- AI unavailable -->
    <div v-if="isUnavailable" class="hrp-unavailable">
      <span class="hrp-unavail-icon">🤖</span>
      <p class="hrp-unavail-text">AI 分析暂不可用</p>
    </div>

    <div v-else class="hrp-columns">
      <!-- Highlights -->
      <div class="hrp-col hrp-col--highlights">
        <div class="hrp-col-header hrp-col-header--positive">✨ 投资亮点</div>
        <div v-if="highlights.length" class="hrp-items">
          <div v-for="(h, i) in highlights" :key="i" class="hrp-item hrp-item--highlight">
            <div class="hrp-item-title">{{ h.title }}</div>
            <div v-if="h.detail" class="hrp-item-detail">{{ h.detail }}</div>
            <div v-if="h.source_modules?.length" class="hrp-item-tags">
              <span v-for="src in h.source_modules" :key="src" class="hrp-tag">{{ src }}</span>
            </div>
          </div>
        </div>
        <div v-else class="hrp-empty-col">暂无亮点数据</div>
      </div>

      <!-- Risks -->
      <div class="hrp-col hrp-col--risks">
        <div class="hrp-col-header hrp-col-header--negative">⚠️ 主要风险</div>
        <div v-if="risks.length" class="hrp-items">
          <div v-for="(r, i) in risks" :key="i" :class="['hrp-item', 'hrp-item--risk', 'hrp-item--' + (r.severity || 'low')]">
            <div class="hrp-item-title-row">
              <span class="hrp-item-title">{{ r.title }}</span>
              <span v-if="r.severity" :class="['hrp-severity', r.severity]">{{ severityLabel(r.severity) }}</span>
            </div>
            <div v-if="r.detail" class="hrp-item-detail">{{ r.detail }}</div>
            <div v-if="r.source_modules?.length" class="hrp-item-tags">
              <span v-for="src in r.source_modules" :key="src" class="hrp-tag">{{ src }}</span>
            </div>
          </div>
        </div>
        <div v-else class="hrp-empty-col">暂无风险数据</div>
      </div>
    </div>

    <!-- Always-visible disclaimer -->
    <div class="hrp-disclaimer">
      ⚠️ {{ disclaimer }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  envelope: { type: Object, default: null },
  loading:  { type: Boolean, default: false },
})

const analysis = computed(() => props.envelope?.data?.ai_analysis || null)

const isUnavailable = computed(() => {
  if (!props.envelope || !analysis.value) return true
  if (analysis.value?.review?.review_status === 'rejected') return true
  return false
})

const highlights = computed(() => analysis.value?.highlights || [])
const risks      = computed(() => analysis.value?.risks      || [])

const disclaimer = computed(() => {
  return analysis.value?.disclaimer ||
    '本内容由 AI 基于公开财务数据生成，仅供参考，不构成投资建议。'
})

function severityLabel(sev) {
  return { low: '低风险', medium: '中风险', high: '高风险' }[sev] || sev
}
</script>

<style scoped>
.hrp-root {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hrp-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 640px) {
  .hrp-columns { grid-template-columns: 1fr; }
}

.hrp-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hrp-col-header {
  font-size: 13px;
  font-weight: 700;
  padding-bottom: 6px;
  border-bottom: 2px solid;
}

.hrp-col-header--positive {
  color: #16a34a;
  border-color: #86efac;
}

.hrp-col-header--negative {
  color: #dc2626;
  border-color: #fca5a5;
}

.hrp-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hrp-item {
  border-radius: 8px;
  padding: 10px 12px;
  background: #f9fafb;
  border-left: 3px solid #e5e7eb;
}

.hrp-item--highlight { border-left-color: #22c55e; background: #f0fdf4; }
.hrp-item--risk { border-left-color: #ef4444; background: #fff5f5; }
.hrp-item--medium { border-left-color: #f59e0b; background: #fffbeb; }
.hrp-item--high   { border-left-color: #dc2626; background: #fff2f0; }

.hrp-item-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.hrp-item-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary, #1a2540);
}

.hrp-item-detail {
  font-size: 12px;
  color: var(--color-text-secondary, #555);
  line-height: 1.5;
  margin-top: 4px;
}

.hrp-item-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.hrp-tag {
  font-size: 10px;
  background: #e5e7eb;
  color: #6b7280;
  border-radius: 3px;
  padding: 1px 5px;
}

.hrp-severity {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
}

.hrp-severity.low    { background: #dcfce7; color: #16a34a; }
.hrp-severity.medium { background: #fef3c7; color: #92400e; }
.hrp-severity.high   { background: #fee2e2; color: #991b1b; }

.hrp-empty-col {
  font-size: 13px;
  color: var(--color-text-secondary, #aaa);
  padding: 8px 0;
}

.hrp-unavailable {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 0;
  text-align: center;
}

.hrp-unavail-icon { font-size: 28px; }
.hrp-unavail-text { font-size: 13px; color: var(--color-text-secondary, #888); margin: 0; }

.hrp-disclaimer {
  font-size: 11px;
  color: #92400e;
  background: #fffbeb;
  border-radius: 6px;
  padding: 8px 12px;
  line-height: 1.5;
}
</style>
