<template>
  <!-- 盈利能力：ROE / 毛利率 / 净利率多折线 -->
  <div class="cv2-chart-wrap">
    <div ref="el" class="cv2-chart" />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { sortedRows, extractXLabels, classifyRowsPeriod } from '../../../utils/companyV2PeriodClassifier.js'

const props = defineProps({ rows: { type: Array, default: () => [] } })
const el = ref(null)
let ec = null; let ro = null; let _ec = null

const _pct = v => v == null ? null : +(Number(v) * 100).toFixed(2)

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
  // Phase 6T-E: BaoStock profit 表无 roa，不渲染空 ROA 序列
  const metrics = [
    { key: 'roe', label: 'ROE', color: '#6366f1' },
    { key: 'gross_margin', label: '毛利率', color: '#10b981' },
    { key: 'net_margin', label: '净利率', color: '#f59e0b' },
  ]
  ec.setOption({
    tooltip: { trigger: 'axis', valueFormatter: v => v != null ? v.toFixed(2) + '%' : '—' },
    legend: { data: metrics.map(m => m.label), top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 50, right: 20, top: 35, bottom: 50 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 10, formatter: v => v + '%' } },
    series: metrics.map(m => ({
      name: m.label, type: 'line',
      data: sorted.map(r => _pct(r[m.key] ?? r[m.key + '_pct'])),
      smooth: true, symbol: 'circle', symbolSize: 4,
      lineStyle: { width: 2 }, itemStyle: { color: m.color },
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
.cv2-chart { width: 100%; height: 260px; }
</style>
