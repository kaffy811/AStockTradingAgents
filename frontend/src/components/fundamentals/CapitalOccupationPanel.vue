<template>
  <div class="cop-root">
    <div v-if="isUnavailable" class="cop-empty">
      <span class="cop-empty-icon">📭</span>
      <p class="cop-empty-text">{{ emptyReason }}</p>
    </div>
    <template v-else>
      <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />
      <div class="cop-chart-wrap">
        <div ref="chartEl" class="cop-chart"></div>
      </div>
      <div v-if="tableRows.length" class="cop-table-wrap">
        <table class="cop-table">
          <thead>
            <tr>
              <th>报告期</th>
              <th>{{ activeTabDef.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableRows" :key="row.end_date">
              <td>{{ row.end_date }}</td>
              <td>{{ fmtCell(row, activeMetric) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="comment" class="cop-comment">{{ comment }}</div>
    </template>
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
  { key: 'occupation_power',         label: '资金占用力',         unit: 'x' },
  { key: 'receivable_to_revenue_pct',label: '应收/营收',          unit: '%' },
  { key: 'payable_to_revenue_pct',   label: '应付/营收',          unit: '%' },
  { key: 'advance_to_revenue_pct',   label: '预收款/营收',        unit: '%' },
]

const activeMetric = ref('occupation_power')
const chartEl = ref(null)
let chartInstance = null
let ro = null
let _ecCache = null

const rows = computed(() => props.envelope?.data?.rows || [])
const reasons = computed(() => props.envelope?.data?.reasons || [])
const comment = computed(() => props.envelope?.data?.comment || '')

const isUnavailable = computed(() => !props.loading && rows.value.length === 0)
const emptyReason = computed(() => {
  if (reasons.value.length) return reasons.value[0]
  const e = props.envelope?.errors
  if (Array.isArray(e) && e.length) return e[0]
  return '暂无数据'
})

const tableRows = computed(() =>
  rows.value.slice().sort((a, b) => (b.end_date || '').localeCompare(a.end_date || '')).slice(0, 8)
)

const activeTabDef = computed(() => metricTabs.find(t => t.key === activeMetric.value) || metricTabs[0])

function fmtCell(row, key) {
  const tab = metricTabs.find(t => t.key === key)
  const v = row[key]
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (tab?.unit === '%') return n.toFixed(2) + '%'
  return n.toFixed(2) + (tab?.unit === 'x' ? 'x' : '')
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
  const sorted = rows.value.slice().sort((a, b) => (a.end_date || '').localeCompare(b.end_date || ''))
  const xData = sorted.map(r => r.end_date)
  const metric = activeMetric.value
  const tab = activeTabDef.value

  const series = [{
    name: tab.label,
    type: 'line',
    data: sorted.map(r => r[metric] != null ? Number(r[metric]) : null),
    smooth: true,
    connectNulls: false,
    symbol: 'circle',
    symbolSize: 5,
    lineStyle: { color: '#1a73e8', width: 2 },
    itemStyle: { color: '#1a73e8' },
    areaStyle: { color: 'rgba(26,115,232,0.08)' },
  }]

  const yAxisFormatter = tab.unit === '%' ? v => v + '%' : undefined

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, top: 16, bottom: 45 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
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
.cop-root { display: flex; flex-direction: column; gap: 12px; }
.cop-chart-wrap { width: 100%; }
.cop-chart { width: 100%; height: 240px; }
.cop-table-wrap { overflow-x: auto; }
.cop-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cop-table th, .cop-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.cop-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.cop-table td:first-child, .cop-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.cop-comment { font-size: 12px; color: #555; background: #f0f4ff; border-radius: 6px; padding: 8px 12px; line-height: 1.6; }
.cop-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px 0; text-align: center; }
.cop-empty-icon { font-size: 28px; }
.cop-empty-text { font-size: 13px; color: #888; margin: 0; max-width: 320px; }
</style>
