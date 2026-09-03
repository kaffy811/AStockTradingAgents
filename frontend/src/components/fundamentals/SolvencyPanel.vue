<template>
  <div class="sp-root">
    <div v-if="isUnavailable" class="sp-empty">
      <span class="sp-empty-icon">📭</span>
      <p class="sp-empty-text">{{ emptyReason }}</p>
    </div>
    <template v-else>
      <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />
      <div class="sp-chart-wrap">
        <div ref="chartEl" class="sp-chart"></div>
      </div>
      <div v-if="tableRows.length" class="sp-table-wrap">
        <table class="sp-table">
          <thead>
            <tr>
              <th>报告期</th>
              <th v-for="col in tableColumns" :key="col.key">{{ col.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableRows" :key="row.end_date">
              <td>{{ row.end_date }}</td>
              <td v-for="col in tableColumns" :key="col.key">{{ fmtCell(row[col.key], col) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="comment" class="sp-comment">{{ comment }}</div>
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
  { key: 'short_term', label: '短期偿债' },
  { key: 'long_term',  label: '长期偿债' },
  { key: 'debt_to_assets_pct', label: '资产负债率' },
]

const activeMetric = ref('short_term')
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

const tableColumns = computed(() => {
  if (activeMetric.value === 'short_term') {
    return [
      { key: 'current_ratio', label: '流动比率', unit: 'x' },
      { key: 'quick_ratio', label: '速动比率', unit: 'x' },
      { key: 'cash_ratio', label: '现金比率', unit: 'x' },
    ]
  }
  if (activeMetric.value === 'long_term') {
    return [
      { key: 'debt_to_assets_pct', label: '资产负债率', unit: '%' },
      { key: 'equity_multiplier', label: '权益乘数', unit: 'x' },
    ]
  }
  return [{ key: 'debt_to_assets_pct', label: '资产负债率', unit: '%' }]
})

function fmtCell(v, col) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (col.unit === '%') return n.toFixed(2) + '%'
  return n.toFixed(2) + (col.unit === 'x' ? 'x' : '')
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
  let series = []
  let yAxis = [{ type: 'value', scale: true, axisLabel: { fontSize: 11 } }]

  if (metric === 'short_term') {
    series = [
      { name: '流动比率', type: 'line', data: sorted.map(r => r.current_ratio != null ? Number(r.current_ratio) : null), smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { color: '#1a73e8', width: 2 }, itemStyle: { color: '#1a73e8' } },
      { name: '速动比率', type: 'line', data: sorted.map(r => r.quick_ratio != null ? Number(r.quick_ratio) : null), smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { color: '#34a853', width: 2 }, itemStyle: { color: '#34a853' } },
      { name: '现金比率', type: 'line', data: sorted.map(r => r.cash_ratio != null ? Number(r.cash_ratio) : null), smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { color: '#fbbc04', width: 2 }, itemStyle: { color: '#fbbc04' } },
    ]
  } else if (metric === 'long_term') {
    series = [
      { name: '资产负债率(%)', type: 'bar', data: sorted.map(r => r.debt_to_assets_pct != null ? Number(r.debt_to_assets_pct) : null), itemStyle: { color: '#1a73e8' }, yAxisIndex: 0 },
      { name: '权益乘数', type: 'line', data: sorted.map(r => r.equity_multiplier != null ? Number(r.equity_multiplier) : null), smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { color: '#e8503a', width: 2 }, itemStyle: { color: '#e8503a' }, yAxisIndex: 1 },
    ]
    yAxis = [
      { type: 'value', scale: true, axisLabel: { fontSize: 11, formatter: v => v + '%' } },
      { type: 'value', scale: true, axisLabel: { fontSize: 11 }, splitLine: { show: false } },
    ]
  } else {
    series = [{
      name: '资产负债率',
      type: 'line',
      data: sorted.map(r => r.debt_to_assets_pct != null ? Number(r.debt_to_assets_pct) : null),
      smooth: true,
      connectNulls: false,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color: '#1a73e8', width: 2 },
      itemStyle: { color: '#1a73e8' },
      areaStyle: { color: 'rgba(26,115,232,0.08)' },
    }]
    yAxis = [{ type: 'value', scale: true, axisLabel: { fontSize: 11, formatter: v => v + '%' } }]
  }

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: series.length > 1 ? { data: series.map(s => s.name), top: 0, right: 10, textStyle: { fontSize: 11 } } : undefined,
    grid: { left: 60, right: yAxis.length > 1 ? 55 : 20, top: series.length > 1 ? 30 : 16, bottom: 45 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis,
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
.sp-root { display: flex; flex-direction: column; gap: 12px; }
.sp-chart-wrap { width: 100%; }
.sp-chart { width: 100%; height: 240px; }
.sp-table-wrap { overflow-x: auto; }
.sp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.sp-table th, .sp-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.sp-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.sp-table td:first-child, .sp-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.sp-comment { font-size: 12px; color: #555; background: #f0f4ff; border-radius: 6px; padding: 8px 12px; line-height: 1.6; }
.sp-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px 0; text-align: center; }
.sp-empty-icon { font-size: 28px; }
.sp-empty-text { font-size: 13px; color: #888; margin: 0; max-width: 320px; }
</style>
