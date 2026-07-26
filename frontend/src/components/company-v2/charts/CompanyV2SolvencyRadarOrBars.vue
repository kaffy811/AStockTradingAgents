<template>
  <!-- 偿债能力：多折线（多期）或指标卡（单期） -->
  <div class="cv2-chart-wrap" v-if="showChart">
    <div ref="el" class="cv2-chart" />
  </div>
  <div v-else class="cv2-solvency-cards">
    <div v-for="m in solvencyMetrics" :key="m.key" class="cv2-sol-card">
      <span class="cv2-sol-label">{{ m.label }}</span>
      <span class="cv2-sol-value">{{ fmtVal(firstRow[m.key], m.unit) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { classifyRowsPeriod, extractXLabels, sortedRows } from '../../../utils/companyV2PeriodClassifier.js'

const props = defineProps({ rows: { type: Array, default: () => [] } })
const el = ref(null)
let ec = null; let ro = null; let _ec = null

const solvencyMetrics = [
  { key: 'current_ratio', label: '流动比率', unit: 'x' },
  { key: 'quick_ratio', label: '速动比率', unit: 'x' },
  { key: 'cash_ratio', label: '现金比率', unit: 'x' },
  { key: 'debt_ratio', label: '资产负债率', unit: '%' },
  { key: 'equity_multiplier', label: '权益乘数', unit: 'x' },
]

const periodType = computed(() => classifyRowsPeriod(props.rows))
const showChart = computed(() => props.rows.length >= 2 && periodType.value !== 'point_in_time')
const firstRow = computed(() => props.rows[0] || {})

function fmtVal(v, unit) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (unit === '%') return (n * 100).toFixed(2) + '%'
  return n.toFixed(2) + ' ' + unit
}

async function init() {
  if (!el.value || !showChart.value) return
  if (!_ec) _ec = await import('echarts')
  if (ec) ec.dispose()
  ec = _ec.init(el.value)
  render()
}

function render() {
  if (!ec || !props.rows.length) return
  const sorted = sortedRows(props.rows)
  const xData = extractXLabels(sorted, periodType.value)
  const colors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#3b82f6']
  ec.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: solvencyMetrics.map(m => m.label), top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: 20, top: 35, bottom: 50 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 10 } },
    series: solvencyMetrics.map((m, i) => ({
      name: m.label, type: 'line',
      data: sorted.map(r => r[m.key] != null ? +Number(r[m.key]).toFixed(4) : null),
      smooth: true, symbol: 'circle', symbolSize: 4,
      itemStyle: { color: colors[i % colors.length] },
    })),
  }, true)
}

watch([() => props.rows, showChart], async () => {
  if (showChart.value) { await init() } else { ec?.dispose(); ec = null }
})
onMounted(() => init().then(() => {
  if (el.value && showChart.value) { ro = new ResizeObserver(() => ec?.resize()); ro.observe(el.value) }
}))
onUnmounted(() => { ro?.disconnect(); ec?.dispose() })
</script>
<style scoped>
.cv2-chart-wrap { width: 100%; }
.cv2-chart { width: 100%; height: 240px; }
.cv2-solvency-cards { display: flex; flex-wrap: wrap; gap: 10px; }
.cv2-sol-card { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 14px; min-width: 110px; text-align: center; }
.cv2-sol-label { display: block; font-size: 11px; color: #6b7280; margin-bottom: 4px; }
.cv2-sol-value { display: block; font-size: 18px; font-weight: 600; color: #111827; }
</style>
