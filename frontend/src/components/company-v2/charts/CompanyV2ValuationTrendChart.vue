<template>
  <!-- 估值模块：指标卡展示 PE/PB/PS/PCF/市值 -->
  <div class="cv2-val-cards">
    <div v-for="m in valuationMetrics" :key="m.key" class="cv2-val-card">
      <span class="cv2-val-label">{{ m.label }}</span>
      <span class="cv2-val-value">{{ fmtVal(latestRow[m.key], m.fmt) }}</span>
      <span v-if="m.unit" class="cv2-val-unit">{{ m.unit }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  fields: { type: Object, default: () => ({}) },
})

const valuationMetrics = [
  { key: 'pe_ttm', label: 'PE TTM', fmt: 'ratio' },
  { key: 'pb', label: 'PB', fmt: 'ratio' },
  { key: 'ps_ttm', label: 'PS TTM', fmt: 'ratio' },
  { key: 'pcf_ncf_ttm', label: 'PCF TTM', fmt: 'ratio' },
  { key: 'market_cap', label: '总市值', fmt: 'cap', unit: '亿' },
  { key: 'float_market_cap', label: '流通市值', fmt: 'cap', unit: '亿' },
]

const latestRow = computed(() => {
  if (props.rows.length) return props.rows[0]
  // Fall back to fields values
  const out = {}
  for (const [k, v] of Object.entries(props.fields)) {
    out[k] = v?.value
  }
  return out
})

function fmtVal(v, fmt) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (fmt === 'cap') return (n / 1e8).toFixed(2)
  if (fmt === 'ratio') return n.toFixed(2)
  return n.toFixed(2)
}
</script>

<style scoped>
.cv2-val-cards { display: flex; flex-wrap: wrap; gap: 10px; }
.cv2-val-card { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 14px; min-width: 100px; text-align: center; flex: 1; max-width: 160px; }
.cv2-val-label { display: block; font-size: 11px; color: #6b7280; margin-bottom: 4px; }
.cv2-val-value { display: block; font-size: 18px; font-weight: 600; color: #111827; }
.cv2-val-unit { display: block; font-size: 10px; color: #9ca3af; }
</style>
