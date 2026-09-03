<template>
  <div class="hep-root">
    <!-- Equity Structure Section -->
    <div class="hep-section">
      <h3 class="hep-section-title">股本结构</h3>
      <div v-if="equityUnavailable" class="hep-empty">
        <p class="hep-empty-text">{{ equityEmptyReason }}</p>
      </div>
      <template v-else>
        <div class="hep-equity-summary">
          <div v-for="item in equitySummaryItems" :key="item.label" class="hep-metric">
            <span class="hep-metric-label">{{ item.label }}</span>
            <span class="hep-metric-value">{{ item.value }}</span>
          </div>
        </div>
        <div v-if="equityRow" class="hep-equity-date">数据日期：{{ equityRow.trade_date }}</div>
      </template>
    </div>

    <!-- Holder Number Trend Section -->
    <div class="hep-section">
      <h3 class="hep-section-title">股东户数趋势</h3>
      <div v-if="holderTrendUnavailable" class="hep-empty">
        <p class="hep-empty-text">{{ holdersEmptyReason }}</p>
      </div>
      <template v-else>
        <div class="hep-chart-wrap">
          <div ref="chartEl" class="hep-chart"></div>
        </div>
        <div v-if="holderTrend.length" class="hep-table-wrap">
          <table class="hep-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>股东户数</th>
                <th>环比变化</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in holderTrend" :key="row.end_date">
                <td>{{ row.end_date }}</td>
                <td>{{ fmtInt(row.holder_num) }}</td>
                <td :class="changeClass(row.holder_num_change)">{{ fmtChange(row.holder_num_change) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <!-- Top 10 Float Holders Section -->
    <div class="hep-section">
      <h3 class="hep-section-title">前十大流通股东</h3>
      <div v-if="top10Unavailable" class="hep-empty">
        <p class="hep-empty-text">暂无前十大流通股东数据</p>
      </div>
      <div v-else class="hep-table-wrap">
        <table class="hep-table">
          <thead>
            <tr>
              <th>股东名称</th>
              <th>持股数量</th>
              <th>持股比例</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(h, i) in top10Holders" :key="i">
              <td class="hep-holder-name">{{ h.holder_name || '—' }}</td>
              <td>{{ fmtShares(h.hold_amount) }}</td>
              <td>{{ fmtPct(h.hold_ratio_pct) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="holdersComment" class="hep-comment">{{ holdersComment }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  equityEnvelope:  { type: Object, default: null },
  holdersEnvelope: { type: Object, default: null },
  loading:         { type: Boolean, default: false },
})

const chartEl = ref(null)
let chartInstance = null
let ro = null
let _ecCache = null

// Equity structure
const equityData = computed(() => props.equityEnvelope?.data || null)
const equityReasons = computed(() => equityData.value?.reasons || [])
const equityRow = computed(() => {
  const rows = equityData.value?.rows
  if (Array.isArray(rows) && rows.length) return rows[0]
  // fallback: summary fields directly on data
  if (equityData.value?.trade_date) return equityData.value
  return null
})
const equityUnavailable = computed(() => !props.loading && !equityRow.value)
const equityEmptyReason = computed(() => {
  if (equityReasons.value.length) return equityReasons.value[0]
  const e = props.equityEnvelope?.errors
  if (Array.isArray(e) && e.length) return e[0]
  return '暂无股本结构数据'
})

function fmtWan(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (Math.abs(n) >= 10000) return (n / 10000).toFixed(2) + '亿股'
  return n.toFixed(2) + '万股'
}

function fmtPct(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2) + '%'
}

function fmtInt(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toLocaleString()
}

function fmtShares(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿股'
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万股'
  return n.toFixed(0) + '股'
}

function fmtChange(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  const sign = n > 0 ? '+' : ''
  return sign + n.toFixed(0)
}

function changeClass(v) {
  if (v == null) return ''
  const n = Number(v)
  if (n > 0) return 'hep-up'
  if (n < 0) return 'hep-down'
  return ''
}

const equitySummaryItems = computed(() => {
  const r = equityRow.value
  if (!r) return []
  return [
    { label: '总股本', value: fmtWan(r.total_share_wan) },
    { label: '流通股本', value: fmtWan(r.float_share_wan) },
    { label: '自由流通', value: fmtWan(r.free_share_wan) },
    { label: '流通比例', value: fmtPct(r.float_ratio_pct) },
    { label: '自由流通比例', value: fmtPct(r.free_ratio_pct) },
  ]
})

// Holders data
const holdersData = computed(() => props.holdersEnvelope?.data || null)
const holdersReasons = computed(() => holdersData.value?.reasons || [])
const holderTrend = computed(() => holdersData.value?.holder_number_trend || holdersData.value?.holder_num_series || [])
const top10Holders = computed(() => holdersData.value?.top10_float_holders || holdersData.value?.rows || [])
const holdersComment = computed(() => holdersData.value?.comment || '')
const holderTrendUnavailable = computed(() => !props.loading && holderTrend.value.length === 0)
const top10Unavailable = computed(() => !props.loading && top10Holders.value.length === 0)
const holdersEmptyReason = computed(() => {
  if (holdersReasons.value.length) return holdersReasons.value[0]
  const e = props.holdersEnvelope?.errors
  if (Array.isArray(e) && e.length) return e[0]
  return '暂无股东户数数据'
})

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
  const trend = holderTrend.value
  if (!trend.length) return

  const sorted = trend.slice().sort((a, b) => (a.end_date || '').localeCompare(b.end_date || ''))
  const xData = sorted.map(r => r.end_date)
  const yData = sorted.map(r => r.holder_num != null ? Number(r.holder_num) : null)

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 70, right: 20, top: 16, bottom: 45 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 11, formatter: v => (v / 1000).toFixed(0) + 'K' } },
    series: [{
      name: '股东户数',
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

watch(() => props.holdersEnvelope, () => renderChart())

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
.hep-root { display: flex; flex-direction: column; gap: 20px; }
.hep-section { display: flex; flex-direction: column; gap: 10px; }
.hep-section-title {
  font-size: 13px; font-weight: 700; color: #1a2540;
  margin: 0; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb;
}
.hep-equity-summary {
  display: flex; flex-wrap: wrap; gap: 10px;
}
.hep-metric {
  display: flex; flex-direction: column; gap: 2px;
  background: #f8fafc; border-radius: 8px; padding: 8px 14px;
  min-width: 100px;
}
.hep-metric-label { font-size: 11px; color: #888; }
.hep-metric-value { font-size: 14px; font-weight: 600; color: #1a2540; }
.hep-equity-date { font-size: 11px; color: #aaa; }
.hep-chart-wrap { width: 100%; }
.hep-chart { width: 100%; height: 200px; }
.hep-table-wrap { overflow-x: auto; }
.hep-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.hep-table th, .hep-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.hep-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.hep-table td:first-child, .hep-table th:first-child {
  text-align: left; position: sticky; left: 0; background: #fff;
}
.hep-holder-name { max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
.hep-up { color: #e8503a; }
.hep-down { color: #34a853; }
.hep-comment { font-size: 12px; color: #555; background: #f0f4ff; border-radius: 6px; padding: 8px 12px; line-height: 1.6; }
.hep-empty { padding: 16px 0; }
.hep-empty-text { font-size: 13px; color: #888; margin: 0; }
</style>
