<template>
  <div class="coc-root">
    <div v-if="loading" class="coc-skeleton">
      <div class="skel-row">
        <div class="skel-block wide"></div>
        <div class="skel-block"></div>
        <div class="skel-block"></div>
        <div class="skel-block"></div>
      </div>
    </div>
    <div v-else class="coc-grid">
      <!-- Price / change -->
      <div class="coc-card primary">
        <div class="coc-label">最新价</div>
        <div :class="['coc-price', priceClass]">{{ price }}</div>
        <div :class="['coc-change', priceClass]">{{ change }}</div>
      </div>
      <!-- PE TTM -->
      <div class="coc-card">
        <div class="coc-label">PE(TTM)</div>
        <div class="coc-value">{{ fmt(snapData.pe_ttm) }}</div>
        <div class="coc-unit">倍</div>
      </div>
      <!-- PB -->
      <div class="coc-card">
        <div class="coc-label">PB</div>
        <div class="coc-value">{{ fmt(snapData.pb) }}</div>
        <div class="coc-unit">倍</div>
      </div>
      <!-- 总市值 -->
      <div class="coc-card">
        <div class="coc-label">总市值</div>
        <div class="coc-value">{{ fmtMv(snapData.total_mv) }}</div>
        <div class="coc-unit">{{ mvUnit }}</div>
      </div>
      <!-- ROE (from financial summary) -->
      <div class="coc-card">
        <div class="coc-label">ROE</div>
        <div class="coc-value">{{ fmtPct(finData.roe) }}</div>
        <div class="coc-unit">%</div>
      </div>
      <!-- 股息率 -->
      <div class="coc-card">
        <div class="coc-label">股息率(TTM)</div>
        <div class="coc-value">{{ fmtPct(snapData.dv_ttm) }}</div>
        <div class="coc-unit">%</div>
      </div>
    </div>
    <div v-if="!loading && sourceNote" class="coc-note">{{ sourceNote }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  snapshot: { type: Object, default: null },
  financial: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const snapData = computed(() => props.snapshot?.data || {})
const finData = computed(() => {
  // financial_summary data might have a series array
  const d = props.financial?.data || {}
  if (Array.isArray(d.series) && d.series.length > 0) return d.series[0]
  return d
})

function fmt(v) { return v != null && Number.isFinite(Number(v)) ? Number(v).toFixed(2) : '—' }
function fmtPct(v) { return v != null && Number.isFinite(Number(v)) ? Number(v).toFixed(2) : '—' }

const price = computed(() => {
  const p = snapData.value.price ?? snapData.value.latest_price ?? snapData.value.close
  return p != null ? Number(p).toFixed(2) : '—'
})
const change = computed(() => {
  const c = snapData.value.change_pct
  if (c == null || !Number.isFinite(Number(c))) return ''
  return (Number(c) > 0 ? '+' : '') + Number(c).toFixed(2) + '%'
})
const priceClass = computed(() => {
  const c = snapData.value.change_pct
  if (!Number.isFinite(Number(c))) return ''
  return Number(c) > 0 ? 'up' : Number(c) < 0 ? 'dn' : ''
})

// Market cap formatting
const mvUnit = computed(() => {
  const v = snapData.value.total_mv
  if (v == null) return ''
  return Number(v) >= 100000000 ? '亿元' : '万元'
})
function fmtMv(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  return n >= 100000000 ? (n / 100000000).toFixed(2) : (n / 10000).toFixed(2)
}

const sourceNote = computed(() => {
  const s = props.snapshot?.stale || props.financial?.stale
  return s ? '数据来自缓存' : ''
})
</script>

<style scoped>
.coc-root { width: 100%; }

.coc-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.coc-card {
  background: white;
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.coc-card.primary {
  grid-column: span 1;
  background: var(--status-info-bg, #e8f0fe);
  border: 1px solid var(--status-info-ring, #c3d4f5);
}

.coc-label { font-size: 11px; color: var(--muted); }
.coc-price { font-size: 20px; font-weight: 700; color: var(--text); }
.coc-change { font-size: 12px; font-weight: 600; }
.coc-value { font-size: 16px; font-weight: 600; color: var(--text); }
.coc-unit { font-size: 11px; color: var(--muted); }

.up { color: var(--status-up, #e04040); }
.dn { color: var(--status-down, #00a870); }

/* Skeleton */
.coc-skeleton { padding: 8px 0; }
.skel-row { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 10px; }
.skel-block { height: 72px; background: var(--surface2, #f0f0f0); border-radius: 10px; animation: pulse 1.5s infinite; }
.skel-block.wide { height: 72px; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

.coc-note { font-size: 11px; color: var(--muted); text-align: right; margin-top: 4px; }

@media (max-width: 540px) {
  .coc-grid { grid-template-columns: repeat(2, 1fr); }
  .skel-row { grid-template-columns: 1fr 1fr; }
}
</style>
