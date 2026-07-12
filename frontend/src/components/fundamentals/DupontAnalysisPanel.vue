<template>
  <div class="dap-root">
    <div v-if="isUnavailable" class="dap-empty">
      <span class="dap-empty-icon">📭</span>
      <p class="dap-empty-text">{{ emptyReason }}</p>
    </div>
    <template v-else>
      <!-- Formula display -->
      <div class="dap-formula">
        ROE = 净利率 × 总资产周转率 × 权益乘数
      </div>

      <FundamentalMetricTabs :tabs="metricTabs" v-model="activeMetric" />
      <div class="dap-chart-wrap">
        <div ref="chartEl" class="dap-chart"></div>
      </div>
      <div v-if="tableRows.length" class="dap-table-wrap">
        <table class="dap-table">
          <thead>
            <tr>
              <th>年度</th>
              <th>ROE(%)</th>
              <th>净利率(%)</th>
              <th>总资产周转率</th>
              <th>权益乘数</th>
              <th>三因子乘积(%)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableRows" :key="row.end_date">
              <td>{{ row.end_date }}</td>
              <td>{{ fmtPct(row.roe_pct) }}</td>
              <td>{{ fmtPct(row.net_margin_pct) }}</td>
              <td>{{ fmtNum(row.assets_turn) }}</td>
              <td>{{ fmtNum(row.equity_multiplier) }}</td>
              <td>{{ fmtPct(row.factor_product_pct) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="comment" class="dap-comment">{{ comment }}</div>
      <div v-if="disclaimer" class="dap-disclaimer">注：{{ disclaimer }}</div>
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
  { key: 'roe',              label: 'ROE' },
  { key: 'net_margin',       label: '净利率' },
  { key: 'assets_turnover',  label: '总资产周转率' },
  { key: 'equity_multiplier',label: '权益乘数' },
  { key: 'all',              label: '全部因子' },
]

const activeMetric = ref('roe')
const chartEl = ref(null)
let chartInstance = null
let ro = null
let _ecCache = null

const rows = computed(() => props.envelope?.data?.rows || [])
const reasons = computed(() => props.envelope?.data?.reasons || [])
const comment = computed(() => props.envelope?.data?.comment || '')
const disclaimer = computed(() => props.envelope?.data?.disclaimer || '')

const isUnavailable = computed(() => !props.loading && rows.value.length === 0)
const emptyReason = computed(() => {
  if (reasons.value.length) return reasons.value[0]
  const e = props.envelope?.errors
  if (Array.isArray(e) && e.length) return e[0]
  return '暂无数据'
})

const tableRows = computed(() =>
  rows.value.slice().sort((a, b) => (b.end_date || '').localeCompare(a.end_date || '')).slice(0, 10)
)

function fmtPct(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2) + '%'
}

function fmtNum(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(4)
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
  let yAxis = [{ type: 'value', scale: true, axisLabel: { fontSize: 11, formatter: v => v + '%' } }]

  if (metric === 'all') {
    series = [
      { name: 'ROE(%)', type: 'bar', data: sorted.map(r => r.roe_pct != null ? Number(r.roe_pct) : null), itemStyle: { color: '#1a73e8' }, yAxisIndex: 0 },
      { name: '净利率(%)', type: 'line', data: sorted.map(r => r.net_margin_pct != null ? Number(r.net_margin_pct) : null), smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { color: '#34a853', width: 2 }, itemStyle: { color: '#34a853' }, yAxisIndex: 0 },
      { name: '权益乘数', type: 'line', data: sorted.map(r => r.equity_multiplier != null ? Number(r.equity_multiplier) : null), smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { color: '#fbbc04', width: 2 }, itemStyle: { color: '#fbbc04' }, yAxisIndex: 1 },
    ]
    yAxis = [
      { type: 'value', scale: true, axisLabel: { fontSize: 11, formatter: v => v + '%' } },
      { type: 'value', scale: true, axisLabel: { fontSize: 11 }, splitLine: { show: false } },
    ]
  } else if (metric === 'roe') {
    series = [
      { name: 'ROE(%)', type: 'bar', data: sorted.map(r => r.roe_pct != null ? Number(r.roe_pct) : null), itemStyle: { color: '#1a73e8' } },
      { name: '三因子乘积(%)', type: 'line', data: sorted.map(r => r.factor_product_pct != null ? Number(r.factor_product_pct) : null), smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { color: '#e8503a', width: 2, type: 'dashed' }, itemStyle: { color: '#e8503a' } },
    ]
  } else if (metric === 'net_margin') {
    series = [{
      name: '净利率(%)',
      type: 'line',
      data: sorted.map(r => r.net_margin_pct != null ? Number(r.net_margin_pct) : null),
      smooth: true, connectNulls: false, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#34a853', width: 2 }, itemStyle: { color: '#34a853' },
      areaStyle: { color: 'rgba(52,168,83,0.08)' },
    }]
  } else if (metric === 'assets_turnover') {
    series = [{
      name: '总资产周转率(次)',
      type: 'line',
      data: sorted.map(r => r.assets_turn != null ? Number(r.assets_turn) : null),
      smooth: true, connectNulls: false, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#1a73e8', width: 2 }, itemStyle: { color: '#1a73e8' },
      areaStyle: { color: 'rgba(26,115,232,0.08)' },
    }]
    yAxis = [{ type: 'value', scale: true, axisLabel: { fontSize: 11 } }]
  } else if (metric === 'equity_multiplier') {
    series = [{
      name: '权益乘数',
      type: 'line',
      data: sorted.map(r => r.equity_multiplier != null ? Number(r.equity_multiplier) : null),
      smooth: true, connectNulls: false, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#fbbc04', width: 2 }, itemStyle: { color: '#fbbc04' },
      areaStyle: { color: 'rgba(251,188,4,0.08)' },
    }]
    yAxis = [{ type: 'value', scale: true, axisLabel: { fontSize: 11 } }]
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
.dap-root { display: flex; flex-direction: column; gap: 12px; }
.dap-formula {
  font-size: 13px; font-weight: 600; color: #1a2540;
  background: #f0f4ff; border-radius: 8px; padding: 8px 14px;
  border-left: 3px solid #1a73e8;
}
.dap-chart-wrap { width: 100%; }
.dap-chart { width: 100%; height: 240px; }
.dap-table-wrap { overflow-x: auto; }
.dap-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.dap-table th, .dap-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.dap-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.dap-table td:first-child, .dap-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.dap-comment { font-size: 12px; color: #555; background: #f0f4ff; border-radius: 6px; padding: 8px 12px; line-height: 1.6; }
.dap-disclaimer { font-size: 11px; color: #999; padding: 4px 0; }
.dap-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px 0; text-align: center; }
.dap-empty-icon { font-size: 28px; }
.dap-empty-text { font-size: 13px; color: #888; margin: 0; max-width: 320px; }
</style>
