<template>
  <section v-if="prices.length > 1 || growth.length" class="reader-visuals" aria-label="报告数据图解">
    <article v-if="prices.length > 1" class="visual-card">
      <h3>最近股价怎么走</h3>
      <p class="visual-caption">每日收盘价 · {{ prices[0].date }} 至 {{ prices.at(-1).date }}</p>
      <div class="price-head"><strong>{{ fmt(prices.at(-1).close) }} <small>{{ currency }}</small></strong><span>图中最后一天的收盘价</span></div>
      <svg viewBox="0 0 340 110" role="img" :aria-label="`收盘价走势，${prices[0].date}至${prices.at(-1).date}`">
        <line x1="8" y1="100" x2="332" y2="100" class="chart-baseline" />
        <polyline :points="pricePoints" fill="none" class="price-line" />
      </svg>
      <p class="visual-explain">线往上表示价格上升，往下表示价格下降。这张图记录已发生的变化，不预测之后的涨跌。</p>
    </article>
    <article v-if="growth.length" class="visual-card">
      <h3>公司生意有什么变化</h3>
      <p class="visual-caption">与去年同一时期相比 · 截至 {{ growth[0].as_of }}</p>
      <div v-for="item in growth" :key="item.label" class="growth-row">
        <div class="growth-label"><span>{{ item.label }}<small>{{ item.label === '营业收入' ? '公司开展业务取得的收入' : '扣除成本费用后赚到的钱' }}</small></span><strong>{{ item.value > 0 ? '+' : '' }}{{ fmt(item.value) }}%</strong></div>
        <div class="growth-track" aria-hidden="true"><span class="zero-line"></span><span :class="['growth-bar', item.value < 0 && 'negative']" :style="barStyle(item.value)"></span></div>
      </div>
      <p class="visual-explain">右侧表示比去年增加，左侧表示减少；{{ growth.some(x => x.value === 0) ? '0% 表示持平。' : '' }}这不是股票涨跌幅。</p>
    </article>
    <p class="visual-provenance">图表来自生成这份报告时使用的数据，重开历史报告不会替换成今天的数据。</p>
  </section>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ visuals: { type: Object, default: () => ({}) }, market: { type: String, default: 'CN' } })
const prices = computed(() => (Array.isArray(props.visuals.prices) ? props.visuals.prices : []).filter(p => p.date && typeof p.close === 'number' && Number.isFinite(p.close) && p.close > 0))
const growth = computed(() => (Array.isArray(props.visuals.growth) ? props.visuals.growth : []).filter(p => p.as_of && typeof p.value === 'number' && Number.isFinite(p.value)))
const currency = computed(() => props.market === 'HK' ? '港元' : '元')
const fmt = value => new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
const pricePoints = computed(() => {
  const values = prices.value.map(p => p.close), low = Math.min(...values), high = Math.max(...values)
  return values.map((v, i) => `${8 + i * 324 / Math.max(1, values.length - 1)},${high === low ? 55 : 100 - (v - low) * 90 / (high - low)}`).join(' ')
})
function barStyle(value) {
  const scale = Math.max(...growth.value.map(p => Math.abs(p.value)), 1)
  const width = Math.abs(value) / scale * 48
  return { left: `${value < 0 ? 50 - width : 50}%`, width: `${width}%` }
}
</script>
<style scoped>
.reader-visuals { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; margin:20px 0; }
.visual-card:only-of-type { grid-column:1/-1; }
.visual-card { border:1px solid var(--border); border-radius:12px; padding:18px; background:var(--surface2); min-width:0; }
h3 { margin:0 0 8px; font-size:15px; color:var(--text); }
.visual-caption,.visual-explain,.visual-provenance { color:var(--muted); font-size:12px; line-height:1.7; }
.visual-caption { margin:0 0 16px; }.visual-explain { margin:10px 0 0; }
.price-head { display:flex; flex-wrap:wrap; align-items:baseline; gap:10px; }.price-head strong { font-size:24px; }.price-head small { font-size:12px; font-weight:400; }.price-head span { font-size:11px; color:var(--muted); }
svg { width:100%; height:110px; display:block; margin-top:12px; }.chart-baseline { stroke:var(--border); }.price-line { stroke:var(--accent); stroke-width:2.5; stroke-linejoin:round; stroke-linecap:round; }
.growth-row { margin:16px 0; }.growth-label { display:flex; justify-content:space-between; align-items:center; gap:12px; font-size:13px; }.growth-label small { display:block; color:var(--muted); font-size:11px; margin-top:4px; }.growth-label strong { white-space:nowrap; font-variant-numeric:tabular-nums; }
.growth-track { position:relative; height:12px; margin-top:10px; background:var(--bg); border-radius:4px; }.zero-line { position:absolute; left:50%; top:-3px; bottom:-3px; width:1px; background:var(--muted); }.growth-bar { position:absolute; height:100%; border-radius:3px; background:var(--accent); }.growth-bar.negative { background:#a97762; }.visual-provenance { grid-column:1/-1; margin:0; }
@media(max-width:720px) { .reader-visuals { grid-template-columns:1fr; } }
</style>
