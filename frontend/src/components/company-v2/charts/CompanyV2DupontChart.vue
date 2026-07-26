<template>
  <!-- 杜邦分析：ROE/净利率（百分比轴）+ 资产周转率/权益乘数（倍数轴） -->
  <div>
    <div class="cv2-dupont-formula">
      ROE ≈ 净利率 × 总资产周转率 × 权益乘数
    </div>
    <div class="cv2-chart-wrap">
      <div ref="el" class="cv2-chart" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { sortedRows, extractXLabels, classifyRowsPeriod } from '../../../utils/companyV2PeriodClassifier.js'

const props = defineProps({ rows: { type: Array, default: () => [] } })
const el = ref(null)
let ec = null; let ro = null; let _ec = null

const _pct = v => v == null ? null : +(Number(v) * 100).toFixed(2)
const _n = v => v == null ? null : +Number(v).toFixed(4)

async function init() {
  if (!el.value) return
  if (!_ec) _ec = await import('echarts')
  if (ec) ec.dispose()
  ec = _ec.init(el.value)
  render()
}

function render() {
  if (!ec || !props.rows.length) return
  const pt = classifyRowsPeriod(props.rows)
  const sorted = sortedRows(props.rows)
  const xData = extractXLabels(sorted, pt)
  ec.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['ROE%', '净利率%', '资产周转率(倍)', '权益乘数(倍)'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: 55, top: 35, bottom: 50 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: [
      { type: 'value', name: '%', axisLabel: { fontSize: 10, formatter: v => v + '%' } },
      { type: 'value', name: '倍', axisLabel: { fontSize: 10 } },
    ],
    series: [
      { name: 'ROE%', type: 'line', data: sorted.map(r => _pct(r.roe)), smooth: true, symbol: 'circle', symbolSize: 4, itemStyle: { color: '#6366f1' } },
      { name: '净利率%', type: 'line', data: sorted.map(r => _pct(r.net_margin ?? r.net_margin_pct)), smooth: true, symbol: 'circle', symbolSize: 4, itemStyle: { color: '#10b981' } },
      { name: '资产周转率(倍)', type: 'line', yAxisIndex: 1, data: sorted.map(r => _n(r.asset_turnover ?? r.total_asset_turnover)), smooth: true, symbol: 'circle', symbolSize: 4, itemStyle: { color: '#f59e0b' } },
      { name: '权益乘数(倍)', type: 'line', yAxisIndex: 1, data: sorted.map(r => _n(r.equity_multiplier)), smooth: true, symbol: 'circle', symbolSize: 4, itemStyle: { color: '#ef4444' } },
    ],
  }, true)
}

watch(() => props.rows, render)
onMounted(async () => {
  await init()
  if (el.value) { ro = new ResizeObserver(() => ec?.resize()); ro.observe(el.value) }
})
onUnmounted(() => { ro?.disconnect(); ec?.dispose() })
</script>
<style scoped>
.cv2-chart-wrap { width: 100%; }
.cv2-chart { width: 100%; height: 260px; }
.cv2-dupont-formula { font-size: 12px; color: #6b7280; background: #f9fafb; border-radius: 6px; padding: 6px 10px; margin-bottom: 8px; font-family: monospace; }
</style>
