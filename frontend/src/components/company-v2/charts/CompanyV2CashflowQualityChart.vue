<template>
  <!-- 现金流质量：正负柱状图（OCF/净利润、OCF/营收） -->
  <div class="cv2-chart-wrap">
    <p v-if="scaleNotice" class="cv2-chart-scale-note">{{ scaleNotice }}</p>
    <div ref="el" class="cv2-chart" />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { sortedRows, extractXLabels, classifyRowsPeriod } from '../../../utils/companyV2PeriodClassifier.js'
import { computeSecondaryAxisSplit } from '../../../utils/companyV2ChartSelector.js'

const props = defineProps({ rows: { type: Array, default: () => [] } })
const el = ref(null)
const scaleNotice = ref('')
let ec = null; let ro = null; let _ec = null

const _n = v => v == null ? null : +Number(v).toFixed(4)
const _median = values => {
  const nums = values.map(v => Math.abs(Number(v))).filter(v => Number.isFinite(v) && v > 0).sort((a, b) => a - b)
  if (!nums.length) return 0
  const mid = Math.floor(nums.length / 2)
  return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2
}
function detectCashflowOutliers(seriesValues) {
  const median = _median(seriesValues)
  if (!median) return { enabled: false, median, outliers: new Set() }
  const threshold = Math.max(median * 6, 3)
  const outliers = new Set()
  seriesValues.forEach((v, index) => {
    if (v != null && Math.abs(Number(v)) > threshold) outliers.add(index)
  })
  return { enabled: outliers.size > 0, median, threshold, outliers }
}
function symlogValue(value, enabled) {
  if (value == null || !enabled) return value
  const n = Number(value)
  if (!Number.isFinite(n)) return value
  return Math.sign(n) * Math.log10(1 + Math.abs(n))
}
function pct(v) {
  return v == null ? '—' : `${(Number(v) * 100).toFixed(2)}%`
}

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
  const rawOcfToNp = sorted.map(r => _n(r.ocf_to_np))
  const rawOcfToRev = sorted.map(r => _n(r.ocf_to_revenue ?? r.cashflow_revenue_ratio))
  const outlierCheck = detectCashflowOutliers(rawOcfToNp)
  const useSymlog = outlierCheck.enabled
  scaleNotice.value = useSymlog
    ? '经营现金流/净利润存在极端值，图表使用对称对数尺度展示；tooltip 保留原始值。'
    : ''
  const ocfToNp = rawOcfToNp.map(v => symlogValue(v, useSymlog))
  const ocfToRev = rawOcfToRev.map(v => symlogValue(v, useSymlog))
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
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const rows = Array.isArray(params) ? params : [params]
        const index = rows[0]?.dataIndex ?? 0
        const title = xData[index] || ''
        return [
          title,
          `OCF/净利润：${pct(rawOcfToNp[index])}${outlierCheck.outliers.has(index) ? '（异常点）' : ''}`,
          `OCF/营收：${pct(rawOcfToRev[index])}`,
        ].join('<br/>')
      },
    },
    legend: { data: ['OCF/净利润', 'OCF/营收'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: split.needsSecondaryAxis ? 55 : 20, top: 35, bottom: 50 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: Array.isArray(yAxis)
      ? yAxis.map(axis => ({ ...axis, name: useSymlog ? '对称对数尺度' : axis.name }))
      : { ...yAxis, name: useSymlog ? '对称对数尺度' : yAxis.name },
    series: [
      {
        name: 'OCF/净利润', type: 'bar', data: ocfToNp, barMaxWidth: 28, yAxisIndex: npAxisIndex,
        markLine: zeroMark,
        markPoint: useSymlog ? {
          data: [...outlierCheck.outliers].map(index => ({
            coord: [xData[index], ocfToNp[index]],
            value: pct(rawOcfToNp[index]),
            name: '异常点',
          })),
          label: { fontSize: 10 },
        } : undefined,
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
.cv2-chart-scale-note {
  margin: 0 0 6px;
  font-size: 12px;
  color: #92400e;
  background: #fef3c7;
  border-radius: 6px;
  padding: 6px 8px;
}
.cv2-chart { width: 100%; height: 240px; }
</style>
