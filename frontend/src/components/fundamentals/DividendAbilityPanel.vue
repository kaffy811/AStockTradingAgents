<template>
  <div class="dap-root">
    <!-- Summary cards -->
    <div v-if="summary" class="dap-summary-grid">
      <div class="dap-summary-card">
        <div class="dap-summary-label">平均派息比例</div>
        <div class="dap-summary-value">{{ fmtPct(summary.average_payout_ratio_pct) }}</div>
      </div>
      <div class="dap-summary-card">
        <div class="dap-summary-label">最新股息率</div>
        <div class="dap-summary-value">{{ fmtPct(summary.latest_dividend_yield_pct) }}</div>
      </div>
      <div class="dap-summary-card">
        <div class="dap-summary-label">连续分红年数</div>
        <div class="dap-summary-value">{{ fmtCount(summary.consecutive_years) }}</div>
      </div>
    </div>

    <!-- Chart -->
    <div class="dap-chart-wrap">
      <div ref="chartEl" class="dap-chart"></div>
    </div>

    <!-- Table -->
    <div v-if="rows.length" class="dap-table-wrap">
      <table class="dap-table">
        <thead>
          <tr>
            <th>报告期</th>
            <th>每股股息</th>
            <th>派息比例(%)</th>
            <th>股息率(%)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.end_date">
            <td>{{ row.end_date }}</td>
            <td>{{ fmtNum(row.div_per_share) }}</td>
            <td>{{ fmtPct(row.payout_ratio_pct) }}</td>
            <td>{{ fmtPct(row.dividend_yield_pct) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="reasons.length" class="dap-reasons">
      <span v-for="r in reasons" :key="r" class="dap-reason">{{ r }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  envelope: { type: Object, default: null },
  loading:  { type: Boolean, default: false },
})

const rows    = computed(() => props.envelope?.data?.rows    || [])
const summary = computed(() => props.envelope?.data?.summary || null)
const reasons = computed(() => props.envelope?.data?.reasons || [])
const displayRows = computed(() => rows.value.slice().reverse().slice(0, 10))

function fmtNum(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(3)
}

function fmtPct(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2) + '%'
}

function fmtCount(v) {
  if (v == null) return '—'
  return String(v) + ' 年'
}

const chartEl = ref(null)
let chartInstance = null
let ro = null
let _ecCache = null

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

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['每股股息', '派息比例(%)'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 50, right: 55, top: 30, bottom: 45 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: [
      { type: 'value', name: '每股股息', scale: true, axisLabel: { fontSize: 11 } },
      { type: 'value', name: '派息比例(%)', scale: true, axisLabel: { fontSize: 11, formatter: v => v + '%' }, splitLine: { show: false } },
    ],
    series: [
      {
        name: '每股股息',
        type: 'bar',
        data: sorted.map(r => r.div_per_share != null ? Number(r.div_per_share) : null),
        itemStyle: { color: '#1a73e8' },
        yAxisIndex: 0,
      },
      {
        name: '派息比例(%)',
        type: 'line',
        data: sorted.map(r => r.payout_ratio_pct != null ? Number(r.payout_ratio_pct) : null),
        smooth: true,
        lineStyle: { color: '#e8503a', width: 2 },
        itemStyle: { color: '#e8503a' },
        yAxisIndex: 1,
        symbol: 'circle',
        symbolSize: 4,
      },
    ],
  }, true)
}

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

.dap-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}

.dap-summary-card {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
  text-align: center;
}

.dap-summary-label {
  font-size: 11px;
  color: var(--color-text-secondary, #888);
  margin-bottom: 4px;
}

.dap-summary-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary, #1a2540);
}

.dap-chart-wrap { width: 100%; }
.dap-chart { width: 100%; height: 220px; }
.dap-table-wrap { overflow-x: auto; }
.dap-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.dap-table th, .dap-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.dap-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.dap-table td:first-child, .dap-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.dap-reasons { display: flex; flex-direction: column; gap: 4px; }
.dap-reason { font-size: 12px; color: #92400e; background: #fffbeb; border-radius: 4px; padding: 4px 8px; }
</style>
