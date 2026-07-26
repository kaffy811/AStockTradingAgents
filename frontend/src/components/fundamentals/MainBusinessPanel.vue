<template>
  <div class="mbp-root">
    <FundamentalMetricTabs :tabs="availableTabs" v-model="activeTab" />

    <div class="mbp-content">
      <!-- Chart -->
      <div class="mbp-chart-wrap">
        <div ref="chartEl" class="mbp-chart"></div>
      </div>

      <!-- Table -->
      <div v-if="activeRows.length" class="mbp-table-wrap">
        <table class="mbp-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>营收</th>
              <th>营收占比(%)</th>
              <th>毛利率(%)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in activeRows" :key="row.item">
              <td>{{ row.item }}</td>
              <td>{{ fmtBig(row.revenue) }}</td>
              <td>{{ fmtNum(row.revenue_ratio_pct) }}</td>
              <td>{{ fmtNum(row.gross_margin_pct) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="mbp-empty">
        <span class="mbp-empty-text">暂无{{ activeTabLabel }}数据</span>
      </div>
    </div>

    <div v-if="reasons.length" class="mbp-reasons">
      <span v-for="r in reasons" :key="r" class="mbp-reason">{{ r }}</span>
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

const byProduct  = computed(() => props.envelope?.data?.by_product  || [])
const byRegion   = computed(() => props.envelope?.data?.by_region   || [])
const byIndustry = computed(() => props.envelope?.data?.by_industry || [])
const reasons    = computed(() => props.envelope?.data?.reasons     || [])

const allTabs = computed(() => [
  { key: 'product',  label: '按产品', disabled: false },
  { key: 'region',   label: '按地区', disabled: false },
  {
    key: 'industry',
    label: '按行业',
    disabled: !byIndustry.value.length,
    tooltip: '暂无按行业分类数据',
  },
])

const availableTabs = computed(() => allTabs.value)

const activeTab = ref('product')

const activeRows = computed(() => {
  if (activeTab.value === 'product') return byProduct.value
  if (activeTab.value === 'region')  return byRegion.value
  if (activeTab.value === 'industry') return byIndustry.value
  return []
})

const activeTabLabel = computed(() => {
  return allTabs.value.find(t => t.key === activeTab.value)?.label || ''
})

const chartEl = ref(null)
let chartInstance = null
let ro = null
let _ecCache = null

function fmtBig(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  return n.toFixed(2)
}

function fmtNum(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2)
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
  const rows = activeRows.value
  if (!rows.length) {
    chartInstance.setOption({ series: [] }, true)
    return
  }

  const pieData = rows
    .filter(r => r.revenue_ratio_pct != null)
    .map(r => ({ name: r.item, value: Number(r.revenue_ratio_pct) }))

  chartInstance.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { fontSize: 11 } },
    series: [{
      name: '营收占比',
      type: 'pie',
      radius: ['35%', '65%'],
      center: ['38%', '50%'],
      data: pieData,
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 12 } },
    }],
  }, true)
}

watch(activeTab, () => renderChart())
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
.mbp-root { display: flex; flex-direction: column; gap: 12px; }
.mbp-content { display: flex; flex-direction: column; gap: 12px; }
.mbp-chart-wrap { width: 100%; }
.mbp-chart { width: 100%; height: 220px; }
.mbp-table-wrap { overflow-x: auto; }
.mbp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.mbp-table th, .mbp-table td {
  border: 1px solid #e5e7eb; padding: 5px 8px; text-align: right; white-space: nowrap;
}
.mbp-table th { background: #f8fafc; font-weight: 600; color: #666; text-align: center; }
.mbp-table td:first-child, .mbp-table th:first-child { text-align: left; }
.mbp-empty { text-align: center; padding: 20px 0; color: var(--color-text-secondary, #888); font-size: 13px; }
.mbp-reasons { display: flex; flex-direction: column; gap: 4px; }
.mbp-reason { font-size: 12px; color: #92400e; background: #fffbeb; border-radius: 4px; padding: 4px 8px; }
</style>
