<template>
  <div class="pgp-root">
    <div class="pgp-controls">
      <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />
      <FundamentalPeriodFilter :period="period" :limit="limit" @update:period="period = $event" @update:limit="limit = $event" />
    </div>

    <div class="pgp-chart-wrap">
      <div ref="chartEl" class="pgp-chart"></div>
    </div>

    <div v-if="tableRows.length" class="pgp-table-wrap">
      <table class="pgp-table">
        <thead>
          <tr>
            <th>报告期</th>
            <th>{{ activeTab.label }}</th>
            <th>同比增速(%)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.end_date">
            <td>{{ row.end_date }}</td>
            <td>{{ fmtValue(row[activeTab.valueKey]) }}</td>
            <td>{{ fmtPct(row[activeTab.yoyKey]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="reasons.length" class="pgp-reasons">
      <span v-for="r in reasons" :key="r" class="pgp-reason">{{ r }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import FundamentalMetricTabs from './FundamentalMetricTabs.vue'
import FundamentalPeriodFilter from './FundamentalPeriodFilter.vue'

const props = defineProps({
  envelope: { type: Object, default: null },
  loading:  { type: Boolean, default: false },
})

const metricTabs = [
  { key: 'revenue',        label: '营收及增速',     valueKey: 'revenue',           yoyKey: 'revenue_yoy_pct' },
  { key: 'net_profit',     label: '归母净利润及增速', valueKey: 'net_profit_parent',  yoyKey: 'net_profit_yoy_pct' },
  { key: 'deduct_profit',  label: '扣非净利润增速',  valueKey: 'deduct_net_profit',  yoyKey: 'deduct_net_profit_yoy_pct' },
  { key: 'roe',            label: 'ROE',            valueKey: 'roe_pct',           yoyKey: null },
]

const activeMetric = ref('revenue')
const period = ref('annual')
const limit  = ref(5)

const chartEl = ref(null)
let chartInstance = null
let ro = null
let _ecCache = null

const allRows = computed(() => props.envelope?.data?.rows || [])
const reasons = computed(() => props.envelope?.data?.reasons || [])

const activeTab = computed(() => {
  const tab = metricTabs.find(t => t.key === activeMetric.value)
  return tab || metricTabs[0]
})

const tableRows = computed(() => {
  let rows = allRows.value
  if (period.value === 'annual') {
    rows = rows.filter(r => r.end_date && r.end_date.endsWith('12-31'))
  } else if (period.value === 'quarterly') {
    rows = rows.filter(r => r.end_date && (r.end_date.endsWith('06-30') || r.end_date.endsWith('09-30')))
  }
  return rows.slice(-limit.value).reverse()
})

function fmtValue(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(2)
}

function fmtPct(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2) + '%'
}

async function initChart() {
  if (!chartEl.value) return
  if (!_ecCache) _ecCache = await import('echarts')
  const echarts = _ecCache
  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartEl.value)
  renderChart()
}

function renderChart() {
  if (!chartInstance) return
  const tab = activeTab.value
  const rows = tableRows.value.slice().reverse()
  const xData = rows.map(r => r.end_date)
  const barData = rows.map(r => r[tab.valueKey] != null ? Number(r[tab.valueKey]) : null)
  const lineData = tab.yoyKey ? rows.map(r => r[tab.yoyKey] != null ? Number(r[tab.yoyKey]) : null) : []

  const series = [{
    name: tab.label,
    type: 'bar',
    data: barData,
    itemStyle: { color: '#1a73e8' },
    yAxisIndex: 0,
  }]

  const yAxes = [{ type: 'value', scale: true, axisLabel: { fontSize: 11 } }]

  if (lineData.length) {
    series.push({
      name: '同比增速(%)',
      type: 'line',
      data: lineData,
      smooth: true,
      yAxisIndex: 1,
      lineStyle: { color: '#e8503a', width: 2 },
      itemStyle: { color: '#e8503a' },
      symbol: 'circle',
      symbolSize: 4,
    })
    yAxes.push({
      type: 'value',
      scale: true,
      axisLabel: { fontSize: 11, formatter: v => v + '%' },
      splitLine: { show: false },
    })
  }

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: series.map(s => s.name), top: 0, right: 10, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: lineData.length ? 55 : 20, top: 30, bottom: 45 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: yAxes,
    series,
  }, true)
}

watch([activeMetric, period, limit], renderChart)
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
.pgp-root { display: flex; flex-direction: column; gap: 12px; }
.pgp-controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-start; }
.pgp-chart-wrap { width: 100%; }
.pgp-chart { width: 100%; height: 240px; }
.pgp-table-wrap { overflow-x: auto; }
.pgp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.pgp-table th, .pgp-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.pgp-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.pgp-table td:first-child, .pgp-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.pgp-reasons { display: flex; flex-direction: column; gap: 4px; }
.pgp-reason { font-size: 12px; color: #92400e; background: #fffbeb; border-radius: 4px; padding: 4px 8px; }
</style>
