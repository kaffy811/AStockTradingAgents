<template>
  <!-- 营运能力：分组柱状图（自动处理量级差异） -->
  <div>
    <div v-if="hasScaleWarning" class="cv2-op-warning">
      应收账款周转率与其他指标量级差异较大，已使用对数坐标轴。
    </div>
    <div class="cv2-chart-wrap">
      <div ref="el" class="cv2-chart" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { classifyRowsPeriod, extractXLabels, sortedRows } from '../../../utils/companyV2PeriodClassifier.js'

const props = defineProps({ rows: { type: Array, default: () => [] } })
const el = ref(null)
let ec = null; let ro = null; let _ec = null

const metrics = [
  { key: 'asset_turnover', label: '总资产周转率' },
  { key: 'inventory_turnover', label: '存货周转率' },
  { key: 'receivable_turnover', label: '应收账款周转率' },
  { key: 'total_asset_turnover', label: '资产周转率(合并)' },
]

const _maxVal = computed(() => {
  let max = 0
  for (const r of props.rows) {
    for (const m of metrics) {
      const v = Number(r[m.key])
      if (!isNaN(v) && v > max) max = v
    }
  }
  return max
})

// 若最大值 > 100 则使用 log scale
const hasScaleWarning = computed(() => _maxVal.value > 100)

async function init() {
  if (!el.value) return
  if (!_ec) _ec = await import('echarts')
  if (ec) ec.dispose()
  ec = _ec.init(el.value)
  render()
}

function render() {
  if (!ec || !props.rows.length) return
  const pt = classifyRowsPeriod(props.rows)
  const sorted = sortedRows(props.rows)
  const xData = extractXLabels(sorted, pt)
  const colors = ['#6366f1', '#10b981', '#f59e0b', '#3b82f6']
  const useLog = hasScaleWarning.value
  ec.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: metrics.map(m => m.label), top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: 20, top: 35, bottom: 50 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: useLog ? 'log' : 'value', logBase: 10, scale: true, axisLabel: { fontSize: 10 } },
    series: metrics.map((m, i) => ({
      name: m.label, type: 'bar',
      data: sorted.map(r => r[m.key] != null ? +Number(r[m.key]).toFixed(4) : null),
      barMaxWidth: 22,
      itemStyle: { color: colors[i % colors.length] },
    })),
  }, true)
}

watch(() => props.rows, render)
onMounted(async () => {
  await init()
  if (el.value) { ro = new ResizeObserver(() => ec?.resize()); ro.observe(el.value) }
})
onUnmounted(() => { ro?.disconnect(); ec?.dispose() })
</script>
<style scoped>
.cv2-chart-wrap { width: 100%; }
.cv2-chart { width: 100%; height: 240px; }
.cv2-op-warning { font-size: 11px; color: #92400e; background: #fef3c7; border-radius: 5px; padding: 4px 8px; margin-bottom: 6px; }
</style>
