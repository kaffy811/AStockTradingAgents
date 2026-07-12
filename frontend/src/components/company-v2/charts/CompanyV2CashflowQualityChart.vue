<template>
  <!-- 现金流质量：正负柱状图（OCF/净利润、OCF/营收） -->
  <div class="cv2-chart-wrap">
    <div ref="el" class="cv2-chart" />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { sortedRows, extractXLabels, classifyRowsPeriod } from '../../../utils/companyV2PeriodClassifier.js'
import { computeSecondaryAxisSplit } from '../../../utils/companyV2ChartSelector.js'

const props = defineProps({ rows: { type: Array, default: () => [] } })
const el = ref(null)
let ec = null; let ro = null; let _ec = null

const _n = v => v == null ? null : +Number(v).toFixed(4)

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
  const ocfToNp = sorted.map(r => _n(r.ocf_to_np))
  const ocfToRev = sorted.map(r => _n(r.ocf_to_revenue ?? r.cashflow_revenue_ratio))
  // Phase 6T-E1: 两个比率真实量级差可 >100x（601686 实测 124x），量级差大时启用副轴
  const splitRows = sorted.map(r => ({
    ...r,
    ocf_to_revenue_effective: r.ocf_to_revenue ?? r.cashflow_revenue_ratio,
  }))
  const split = computeSecondaryAxisSplit(splitRows, ['ocf_to_np', 'ocf_to_revenue_effective'], 100)
  const zeroMark = { data: [{ yAxis: 0, lineStyle: { color: '#374151', width: 1 } }] }
  const yAxisBase = {
    type: 'value', scale: true,
    axisLine: { show: true },
    axisLabel: { fontSize: 10 },
  }
  const yAxis = split.needsSecondaryAxis
    ? [yAxisBase, { ...yAxisBase, splitLine: { show: false } }]
    : { ...yAxisBase, splitLine: { show: true, lineStyle: { color: '#e5e7eb', width: 1 } } }
  const npAxisIndex = split.needsSecondaryAxis && split.secondaryFields.includes('ocf_to_np') ? 1 : 0
  const revAxisIndex = split.needsSecondaryAxis && split.secondaryFields.includes('ocf_to_revenue_effective') ? 1 : 0
  ec.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['OCF/净利润', 'OCF/营收'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: split.needsSecondaryAxis ? 55 : 20, top: 35, bottom: 50 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis,
    series: [
      {
        name: 'OCF/净利润', type: 'bar', data: ocfToNp, barMaxWidth: 28, yAxisIndex: npAxisIndex,
        markLine: zeroMark,
        itemStyle: { color: params => (params.value ?? 0) >= 0 ? '#34d399' : '#f87171' },
      },
      {
        name: 'OCF/营收', type: 'bar', data: ocfToRev, barMaxWidth: 28, yAxisIndex: revAxisIndex,
        itemStyle: { color: params => (params.value ?? 0) >= 0 ? '#60a5fa' : '#fbbf24' },
      },
    ],
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
</style>
