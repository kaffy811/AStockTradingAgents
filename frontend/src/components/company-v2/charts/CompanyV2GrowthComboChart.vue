<template>
  <!-- 成长能力：营收/净利润柱 + 同比折线（双Y轴） -->
  <div class="cv2-chart-wrap">
    <div ref="el" class="cv2-chart" />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { sortedRows, extractXLabels, classifyRowsPeriod } from '../../../utils/companyV2PeriodClassifier.js'

const props = defineProps({ rows: { type: Array, default: () => [] } })
const el = ref(null)
let ec = null
let ro = null
let _ec = null

const _fmt = (v, unit = '亿') => {
  if (v == null || isNaN(Number(v))) return null
  const n = Number(v)
  if (unit === '亿') return +(n / 1e8).toFixed(2)
  return +n.toFixed(2)
}
const _pct = v => v == null ? null : +(Number(v) * 100).toFixed(2)

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
  // Phase 6T-E: 字段与 provider 真实口径对齐——
  // BaoStock growth 表无营收同比；绝对值来自 profit 表主营业务收入（不得标注为"营业收入"）。
  // 兼容旧快照字段（revenue/net_profit_parent）作为 fallback。
  const mainRevenue = sorted.map(r => _fmt(r.main_business_revenue ?? r.revenue))
  const netProfit = sorted.map(r => _fmt(r.net_profit ?? r.net_profit_parent))
  const npYoy = sorted.map(r => _pct(r.net_profit_yoy))
  const parentNpYoy = sorted.map(r => _pct(r.net_profit_parent_yoy ?? r.parent_net_profit_yoy))
  ec.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['主营收入(亿)', '净利润(亿)', '净利同比%', '归母净利同比%'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: 55, top: 35, bottom: 50 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11, rotate: 30 } },
    yAxis: [
      { type: 'value', name: '亿元', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10 } },
      { type: 'value', name: '%', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10, formatter: v => v + '%' } },
    ],
    series: [
      { name: '主营收入(亿)', type: 'bar', data: mainRevenue, itemStyle: { color: '#60a5fa' }, barMaxWidth: 28 },
      { name: '净利润(亿)', type: 'bar', data: netProfit, itemStyle: { color: '#34d399' }, barMaxWidth: 28 },
      { name: '净利同比%', type: 'line', yAxisIndex: 1, data: npYoy, smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { width: 1.5 }, itemStyle: { color: '#f59e0b' } },
      { name: '归母净利同比%', type: 'line', yAxisIndex: 1, data: parentNpYoy, smooth: true, symbol: 'circle', symbolSize: 4, lineStyle: { width: 1.5 }, itemStyle: { color: '#f87171' } },
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
.cv2-chart { width: 100%; height: 280px; }
</style>
