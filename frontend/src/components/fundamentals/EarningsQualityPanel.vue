<template>
  <div class="eqp-root">
    <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />

    <div class="eqp-chart-wrap">
      <div ref="chartEl" class="eqp-chart"></div>
    </div>

    <div v-if="rows.length" class="eqp-table-wrap">
      <table class="eqp-table">
        <thead>
          <tr>
            <th>报告期</th>
            <th>净现比</th>
            <th>核现比</th>
            <th>OCF(亿)</th>
            <th>净利润(亿)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.end_date">
            <td>{{ row.end_date }}</td>
            <td>{{ fmtNum(row.ocf_to_np ?? row.ocf_to_np_ratio) }}</td>
            <td>{{ fmtNum(row.cash_sales_ratio) }}</td>
            <td>{{ fmtBig(row.ocf) }}</td>
            <td>{{ fmtBig(row.net_profit_parent ?? row.net_profit) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="reasons.length" class="eqp-reasons">
      <span v-for="r in reasons" :key="r" class="eqp-reason">{{ r }}</span>
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
  { key: 'ocf_to_np',        label: '净现比' },   // tool field: ocf_to_np (was ocf_to_np_ratio)
  { key: 'cash_sales_ratio', label: '核现比' },
  { key: 'ocf_vs_np',        label: 'OCF vs净利润' },
]

const activeMetric = ref('ocf_to_np')
const chartEl = ref(null)
let chartInstance = null
let ro = null
let _ecCache = null

const rows = computed(() => props.envelope?.data?.rows || [])
const reasons = computed(() => props.envelope?.data?.reasons || [])
const displayRows = computed(() => rows.value.slice().reverse().slice(0, 10))

function fmtNum(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2)
}

function fmtBig(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return (n / 1e8).toFixed(2)
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

  let series = []
  if (activeMetric.value === 'ocf_vs_np') {
    series = [
      {
        name: 'OCF(亿)',
        type: 'bar',
        data: sorted.map(r => r.ocf != null ? +(r.ocf / 1e8).toFixed(2) : null),
        itemStyle: { color: '#1a73e8' },
      },
      {
        name: '净利润(亿)',
        type: 'bar',
        data: sorted.map(r => { const v = r.net_profit_parent ?? r.net_profit; return v != null ? +(v / 1e8).toFixed(2) : null }),
        itemStyle: { color: '#e8503a' },
      },
    ]
  } else {
    const tab = metricTabs.find(t => t.key === activeMetric.value)
    series = [{
      name: tab?.label || activeMetric.value,
      type: 'line',
      data: sorted.map(r => r[activeMetric.value] != null ? Number(r[activeMetric.value]) : null),
      smooth: true,
      connectNulls: false,
      lineStyle: { color: '#1a73e8', width: 2 },
      itemStyle: { color: '#1a73e8' },
      symbol: 'circle',
      symbolSize: 5,
      areaStyle: { color: 'rgba(26,115,232,0.07)' },
    }]
  }

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: series.length > 1 ? { data: series.map(s => s.name), top: 0, textStyle: { fontSize: 11 } } : undefined,
    grid: { left: 50, right: 20, top: series.length > 1 ? 30 : 10, bottom: 45 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 11 } },
    series,
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
.eqp-root { display: flex; flex-direction: column; gap: 12px; }
.eqp-chart-wrap { width: 100%; }
.eqp-chart { width: 100%; height: 220px; }
.eqp-table-wrap { overflow-x: auto; }
.eqp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.eqp-table th, .eqp-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.eqp-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.eqp-table td:first-child, .eqp-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.eqp-reasons { display: flex; flex-direction: column; gap: 4px; }
.eqp-reason { font-size: 12px; color: #92400e; background: #fffbeb; border-radius: 4px; padding: 4px 8px; }
</style>
