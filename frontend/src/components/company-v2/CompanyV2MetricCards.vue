<template>
  <div class="cv2-metrics">
    <div v-for="item in items" :key="item.field" class="cv2-metric">
      <span class="cv2-metric-label">{{ item.label }}</span>
      <strong :title="debugMode ? tooltip(item) : ''">{{ item.displayValue || formatValue(item.value) }}</strong>
      <small v-if="item.periodEnd">{{ item.periodEnd }}</small>
      <small v-if="debugMode">{{ item.source }}<template v-if="item.rawField"> · {{ item.rawField }}</template></small>
      <span v-if="debugMode" :class="['cv2-source-badge', sourceBadgeClass(item)]">{{ sourceBadgeLabel(item) }}</span>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  items: { type: Array, default: () => [] },
  debugMode: { type: Boolean, default: false },
})
const debugMode = props.debugMode

function formatValue(value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(value)) return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(2)}亿`
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(2)}万`
  return n.toFixed(2)
}

function formatRaw(value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(value)) return '—'
  return String(value)
}

function tooltip(item) {
  return [
    `raw_value: ${formatRaw(item.rawValue)}`,
    `provider: ${item.provider || item.source || '—'}`,
    `raw_field: ${item.rawField || '—'}`,
    `computed_formula: ${item.computedFormula || '—'}`,
  ].join('\n')
}

function sourceBadgeLabel(item) {
  if (item.verificationStatus === 'conflict' || item.accuracyVerdict === 'official_disclosure_conflict') return 'Conflict'
  if (item.verificationStatus === 'verified' || item.accuracyVerdict === 'official_disclosure_verified') return 'CNINFO verified'
  if (item.computed || String(item.source || '').includes('computed')) return 'Computed'
  if (item.provider || item.source === 'baostock_aggregate' || item.source === 'public_provider') return 'Public provider'
  return 'Unverified'
}

function sourceBadgeClass(item) {
  const label = sourceBadgeLabel(item)
  if (label === 'CNINFO verified') return 'verified'
  if (label === 'Conflict') return 'conflict'
  if (label === 'Computed') return 'computed'
  if (label === 'Public provider') return 'public'
  return 'unverified'
}
</script>

<style scoped>
.cv2-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin-top: 14px;
}
.cv2-metric {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  background: #fafafa;
}
.cv2-metric-label,
.cv2-metric small {
  display: block;
  color: #6b7280;
  font-size: 12px;
}
.cv2-metric strong {
  display: block;
  margin: 6px 0;
  font-size: 18px;
}
.cv2-source-badge {
  display: inline-flex;
  margin-top: 6px;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
}
.cv2-source-badge.verified { background: #dcfce7; color: #166534; }
.cv2-source-badge.public { background: #eff6ff; color: #1d4ed8; }
.cv2-source-badge.computed { background: #f5f3ff; color: #6d28d9; }
.cv2-source-badge.unverified { background: #f3f4f6; color: #6b7280; }
.cv2-source-badge.conflict { background: #fee2e2; color: #991b1b; }
</style>
