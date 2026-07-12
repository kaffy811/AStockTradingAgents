<template>
  <div class="asp-root">
    <div v-if="isUnavailable" class="asp-empty">
      <span class="asp-empty-icon">📭</span>
      <p class="asp-empty-text">{{ emptyReason }}</p>
    </div>
    <template v-else>
      <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />
      <div class="asp-chart-wrap">
        <div ref="chartEl" class="asp-chart"></div>
      </div>
      <div v-if="tableRows.length" class="asp-table-wrap">
        <table class="asp-table">
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
      <div v-if="comment" class="asp-comment">{{ comment }}</div>
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
  { key: 'total_assets',           label: '总资产',       unit: '元' },
  { key: 'current_vs_noncurrent',  label: '流动/非流动',  unit: '元' },
  { key: 'cash_to_assets_pct',     label: '货币资金占比', unit: '%' },
  { key: 'liability_ratio_pct',    label: '资产负债率',   unit: '%' },
  { key: 'current_asset_ratio_pct',label: '流动资产占比', unit: '%' },
  { key: 'goodwill_to_equity_pct', label: '商誉/净资产',  unit: '%' },
]

const activeMetric = ref('total_assets')
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

function fmtWan(v) {
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

function fmtCell(row, key) {
  if (key === 'current_vs_noncurrent') return '—'
  const tab = metricTabs.find(t => t.key === key)
  if (!tab) return '—'
  if (tab.unit === '%') return fmtPct(row[key])
  return fmtWan(row[key])
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

  if (metric === 'current_vs_noncurrent') {
    series = [
      {
        name: '流动资产',
        type: 'bar',
        stack: 'assets',
        data: sorted.map(r => r.current_assets != null ? Number(r.current_assets) : null),
        itemStyle: { color: '#1a73e8' },
      },
      {
        name: '非流动资产',
        type: 'bar',
        stack: 'assets',
        data: sorted.map(r => r.noncurrent_assets != null ? Number(r.noncurrent_assets) : null),
        itemStyle: { color: '#34a853' },
      },
    ]
  } else if (metric === 'total_assets') {
    series = [{
      name: '总资产',
      type: 'bar',
      data: sorted.map(r => r.total_assets != null ? Number(r.total_assets) : null),
      itemStyle: { color: '#1a73e8' },
    }]
  } else {
    const tab = metricTabs.find(t => t.key === metric)
    series = [{
      name: tab?.label || metric,
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
    if (tab?.unit === '%') {
      yAxis = [{ type: 'value', scale: true, axisLabel: { fontSize: 11, formatter: v => v + '%' } }]
    }
  }

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: series.length > 1 ? { data: series.map(s => s.name), top: 0, right: 10, textStyle: { fontSize: 11 } } : undefined,
    grid: { left: 60, right: 20, top: series.length > 1 ? 30 : 16, bottom: 45 },
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
.asp-root { display: flex; flex-direction: column; gap: 12px; }
.asp-chart-wrap { width: 100%; }
.asp-chart { width: 100%; height: 240px; }
.asp-table-wrap { overflow-x: auto; }
.asp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.asp-table th, .asp-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.asp-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.asp-table td:first-child, .asp-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.asp-comment { font-size: 12px; color: #555; background: #f0f4ff; border-radius: 6px; padding: 8px 12px; line-height: 1.6; }
.asp-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px 0; text-align: center; }
.asp-empty-icon { font-size: 28px; }
.asp-empty-text { font-size: 13px; color: #888; margin: 0; max-width: 320px; }
</style>
