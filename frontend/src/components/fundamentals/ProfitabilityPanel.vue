<template>
  <div class="pp-root">
    <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />

    <div class="pp-chart-wrap">
      <div ref="chartEl" class="pp-chart"></div>
    </div>

    <div v-if="rows.length" class="pp-table-wrap">
      <table class="pp-table">
        <thead>
          <tr>
            <th>报告期</th>
            <th v-for="tab in metricTabs" :key="tab.key">{{ tab.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.end_date">
            <td>{{ row.end_date }}</td>
            <td v-for="tab in metricTabs" :key="tab.key">{{ fmtPct(row[tab.key]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="reasons.length" class="pp-reasons">
      <span v-for="r in reasons" :key="r" class="pp-reason">{{ r }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import FundamentalMetricTabs from './FundamentalMetricTabs.vue'

const props = defineProps({
  envelope: { type: Object, default: null },
  loading:  { type: Boolean, default: false },
})

const metricTabs = [
  { key: 'gross_margin_pct', label: '毛利率' },
  { key: 'net_margin_pct',   label: '净利率' },
  { key: 'roe_pct',          label: 'ROE' },
  { key: 'roa_pct',          label: 'ROA' },
  { key: 'roic_pct',         label: 'ROIC' },
]

const activeMetric = ref('gross_margin_pct')
const chartEl = ref(null)
let chartInstance = null
let ro = null
let _ecCache = null

const rows = computed(() => props.envelope?.data?.rows || [])
const reasons = computed(() => props.envelope?.data?.reasons || [])
const displayRows = computed(() => rows.value.slice().reverse().slice(0, 10))

function fmtPct(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2) + '%'
}

async function initChart() {
  if (!chartEl.value) return
  if (!_ecCache) _ecCache = await import('echarts')
  if (chartInstance) chartInstance.dispose()
  chartInstance = _ecCache.init(chartEl.value)
  renderChart()
}

function renderChart() {
  if (!chartInstance) return
  const sorted = rows.value.slice().sort((a, b) => (a.end_date || '').localeCompare(b.end_date || ''))
  const xData = sorted.map(r => r.end_date)

  const series = metricTabs.map(tab => ({
    name: tab.label,
    type: 'line',
    data: sorted.map(r => r[tab.key] != null ? Number(r[tab.key]) : null),
    smooth: true,
    connectNulls: false,
    symbol: 'circle',
    symbolSize: 4,
    visible: tab.key === activeMetric.value,
  }))

  // Only show active metric as bold, others dimmed
  const visibleSeries = series.map(s => ({
    ...s,
    lineStyle: {
      width: metricTabs.find(t => t.label === s.name)?.key === activeMetric.value ? 2.5 : 1,
      opacity: metricTabs.find(t => t.label === s.name)?.key === activeMetric.value ? 1 : 0.3,
    },
    itemStyle: {
      opacity: metricTabs.find(t => t.label === s.name)?.key === activeMetric.value ? 1 : 0.3,
    },
  }))

  chartInstance.setOption({
    tooltip: { trigger: 'axis', valueFormatter: v => v != null ? v.toFixed(2) + '%' : '—' },
    legend: { data: metricTabs.map(t => t.label), top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 50, right: 20, top: 30, bottom: 45 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 11, formatter: v => v + '%' } },
    series: visibleSeries,
  }, true)
}

watch(activeMetric, renderChart)
watch(() => props.envelope, () => renderChart())

onMounted(async () => {
  await initChart()
  if (chartEl.value) {
    ro = new ResizeObserver(() => chartInstance?.resize())
    ro.observe(chartEl.value)
  }
})

onUnmounted(() => {
  ro?.disconnect()
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.pp-root { display: flex; flex-direction: column; gap: 12px; }
.pp-chart-wrap { width: 100%; }
.pp-chart { width: 100%; height: 220px; }
.pp-table-wrap { overflow-x: auto; }
.pp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.pp-table th, .pp-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.pp-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.pp-table td:first-child, .pp-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.pp-reasons { display: flex; flex-direction: column; gap: 4px; }
.pp-reason { font-size: 12px; color: #92400e; background: #fffbeb; border-radius: 4px; padding: 4px 8px; }
</style>
