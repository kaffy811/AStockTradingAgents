<template>
  <div class="vpp-root">
    <!-- Metric tabs -->
    <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />

    <!-- Chart -->
    <div class="vpp-chart-wrap">
      <div ref="chartEl" class="vpp-chart"></div>
    </div>

    <!-- Table -->
    <div v-if="rows.length" class="vpp-table-wrap">
      <table class="vpp-table">
        <thead>
          <tr>
            <th>报告期</th>
            <th v-for="tab in metricTabs" :key="tab.key">{{ tab.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.end_date">
            <td>{{ row.end_date }}</td>
            <td v-for="tab in metricTabs" :key="tab.key">{{ fmtNum(row[tab.key]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Reasons -->
    <div v-if="reasons.length" class="vpp-reasons">
      <span v-for="r in reasons" :key="r" class="vpp-reason">{{ r }}</span>
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
  { key: 'pe_ttm',    label: '市盈率TTM' },
  { key: 'pb',        label: '市净率' },
  { key: 'ps_ttm',    label: '市销率' },
  { key: 'dv_ttm',    label: '股息率' },
  { key: 'total_mv',  label: '总市值' },
]

const activeMetric = ref('pe_ttm')
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
  const metric = activeMetric.value
  const sorted = rows.value.slice().sort((a, b) => (a.end_date || '').localeCompare(b.end_date || ''))
  const xData = sorted.map(r => r.end_date)
  const yData = sorted.map(r => r[metric] != null ? Number(r[metric]) : null)

  const tab = metricTabs.find(t => t.key === metric)
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 11 } },
    series: [{
      name: tab?.label || metric,
      type: 'line',
      data: yData,
      smooth: true,
      connectNulls: false,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color: '#1a73e8', width: 2 },
      itemStyle: { color: '#1a73e8' },
      areaStyle: { color: 'rgba(26,115,232,0.08)' },
    }],
  }, true)
}

watch(activeMetric, renderChart)
watch(() => props.envelope, () => { renderChart() })

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
.vpp-root { display: flex; flex-direction: column; gap: 12px; }

.vpp-chart-wrap {
  width: 100%;
}

.vpp-chart {
  width: 100%;
  height: 220px;
}

.vpp-table-wrap { overflow-x: auto; }

.vpp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.vpp-table th, .vpp-table td {
  border: 1px solid #e5e7eb;
  padding: 5px 8px;
  text-align: right;
  white-space: nowrap;
}

.vpp-table th {
  background: #f8fafc;
  font-weight: 600;
  color: var(--color-text-secondary, #666);
  text-align: center;
}

.vpp-table td:first-child, .vpp-table th:first-child {
  text-align: left;
  position: sticky;
  left: 0;
  background: #fff;
}

.vpp-reasons {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.vpp-reason {
  font-size: 12px;
  color: #92400e;
  background: #fffbeb;
  border-radius: 4px;
  padding: 4px 8px;
}
</style>
