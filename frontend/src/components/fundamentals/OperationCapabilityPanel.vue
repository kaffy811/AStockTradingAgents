<template>
  <div class="ocp-root">
    <div v-if="isUnavailable" class="ocp-empty">
      <span class="ocp-empty-icon">📭</span>
      <p class="ocp-empty-text">{{ emptyReason }}</p>
    </div>
    <template v-else>
      <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />
      <div class="ocp-chart-wrap">
        <div ref="chartEl" class="ocp-chart"></div>
      </div>
      <div v-if="tableRows.length" class="ocp-table-wrap">
        <table class="ocp-table">
          <thead>
            <tr>
              <th>报告期</th>
              <th>{{ activeTabDef.label }}</th>
              <th v-if="activeTabDef.daysKey">天数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableRows" :key="row.end_date">
              <td>{{ row.end_date }}</td>
              <td>{{ fmtNum(row[activeTabDef.valueKey]) }}</td>
              <td v-if="activeTabDef.daysKey">{{ fmtDays(row[activeTabDef.daysKey]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="comment" class="ocp-comment">{{ comment }}</div>
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
  { key: 'inv_turn',      label: '存货周转率',      valueKey: 'inv_turn',       daysKey: 'inventory_days' },
  { key: 'ar_turn',       label: '应收账款周转率',   valueKey: 'ar_turn',        daysKey: 'receivable_days' },
  { key: 'assets_turn',   label: '总资产周转率',     valueKey: 'assets_turn',    daysKey: null },
  { key: 'fa_turn',       label: '固定资产周转率',   valueKey: 'fa_turn',        daysKey: null },
  { key: 'cash_cycle',    label: '现金循环周期',     valueKey: 'cash_conversion_cycle', daysKey: null, unit: '天' },
]

const activeMetric = ref('inv_turn')
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

function fmtNum(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2)
}

function fmtDays(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(0) + '天'
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
  const tab = activeTabDef.value
  const sorted = rows.value.slice().sort((a, b) => (a.end_date || '').localeCompare(b.end_date || ''))
  const xData = sorted.map(r => r.end_date)

  const series = [{
    name: tab.label,
    type: 'line',
    data: sorted.map(r => r[tab.valueKey] != null ? Number(r[tab.valueKey]) : null),
    smooth: true,
    connectNulls: false,
    symbol: 'circle',
    symbolSize: 5,
    lineStyle: { color: '#1a73e8', width: 2 },
    itemStyle: { color: '#1a73e8' },
    areaStyle: { color: 'rgba(26,115,232,0.08)' },
  }]

  const yAxisLabel = tab.unit === '天' ? { fontSize: 11, formatter: v => v + '天' } : { fontSize: 11 }

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, top: 16, bottom: 45 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLabel: yAxisLabel },
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
.ocp-root { display: flex; flex-direction: column; gap: 12px; }
.ocp-chart-wrap { width: 100%; }
.ocp-chart { width: 100%; height: 240px; }
.ocp-table-wrap { overflow-x: auto; }
.ocp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ocp-table th, .ocp-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.ocp-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.ocp-table td:first-child, .ocp-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.ocp-comment { font-size: 12px; color: #555; background: #f0f4ff; border-radius: 6px; padding: 8px 12px; line-height: 1.6; }
.ocp-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px 0; text-align: center; }
.ocp-empty-icon { font-size: 28px; }
.ocp-empty-text { font-size: 13px; color: #888; margin: 0; max-width: 320px; }
</style>
