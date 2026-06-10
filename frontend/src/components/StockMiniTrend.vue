<template>
  <div class="smt-wrap">

    <!-- Loading -->
    <div v-if="state === 'loading'" class="smt-skeleton"></div>

    <!-- Error -->
    <div v-else-if="state === 'error'" class="smt-fallback">趋势暂不可用</div>

    <!-- Insufficient data -->
    <div v-else-if="state === 'insufficient'" class="smt-fallback">数据不足</div>

    <!-- SVG trend line -->
    <svg
      v-else-if="state === 'ok'"
      :width="svgWidth"
      :height="height"
      class="smt-svg"
      :viewBox="`0 0 ${svgWidth} ${height}`"
      preserveAspectRatio="none"
    >
      <!-- Area fill -->
      <path
        :d="areaPath"
        :class="['smt-area', trendClass]"
      />
      <!-- Line -->
      <polyline
        :points="linePoints"
        :class="['smt-line', trendClass]"
        fill="none"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { getKline } from '../api/stocks.js'

const props = defineProps({
  market: { type: String, required: true },
  symbol: { type: String, required: true },
  height: { type: Number, default: 42 },
  points: { type: Number, default: 30 },
})

// Internal width — responsive via ResizeObserver
const containerRef  = ref(null)
const svgWidth      = ref(120)

// State: 'loading' | 'ok' | 'error' | 'insufficient'
const state     = ref('loading')
const closes    = ref([])
let   _mounted  = true

// ── ResizeObserver ─────────────────────────────────────────────────────────
let ro = null

onMounted(() => {
  // Use the parent wrapper to measure width
  const el = document.querySelector('.smt-wrap')
  if (el && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect?.width
      if (w && w > 0) svgWidth.value = Math.round(w)
    })
    ro.observe(el)
  }
  loadKline()
})

onBeforeUnmount(() => {
  _mounted = false
  ro?.disconnect()
})

// Reload when market/symbol changes
watch(() => [props.market, props.symbol], () => {
  state.value  = 'loading'
  closes.value = []
  loadKline()
})

// ── Load kline data ────────────────────────────────────────────────────────
async function loadKline() {
  try {
    const data = await getKline(props.market, props.symbol, {
      period: 'daily',
      limit: props.points,
    })
    if (!_mounted) return

    const items = data?.items ?? data?.kline ?? []
    const c = items
      .map(d => Number(d.close ?? d.c ?? d[4]))
      .filter(v => Number.isFinite(v))

    if (c.length < 2) {
      state.value = 'insufficient'
      return
    }
    closes.value = c
    state.value  = 'ok'
  } catch {
    if (_mounted) state.value = 'error'
  }
}

// ── SVG calculation ────────────────────────────────────────────────────────
const PAD_X = 2
const PAD_Y = 4

const trendClass = computed(() => {
  if (closes.value.length < 2) return 'smt--neutral'
  const first = closes.value[0]
  const last  = closes.value[closes.value.length - 1]
  if (last > first) return 'smt--up'
  if (last < first) return 'smt--down'
  return 'smt--neutral'
})

const linePoints = computed(() => {
  const arr = closes.value
  if (arr.length < 2) return ''

  const minV = Math.min(...arr)
  const maxV = Math.max(...arr)
  const rangeV = maxV - minV

  const w = svgWidth.value
  const h = props.height

  const drawW = w - PAD_X * 2
  const drawH = h - PAD_Y * 2

  return arr.map((v, i) => {
    const x = PAD_X + (i / (arr.length - 1)) * drawW
    // If all prices equal, draw at vertical center
    const y = rangeV === 0
      ? h / 2
      : PAD_Y + (1 - (v - minV) / rangeV) * drawH
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

// Area path (line + vertical close)
const areaPath = computed(() => {
  const pts = linePoints.value
  if (!pts) return ''
  const arr = pts.trim().split(' ')
  if (arr.length < 2) return ''

  const firstX = arr[0].split(',')[0]
  const lastX  = arr[arr.length - 1].split(',')[0]
  const bottom = props.height

  return `M ${firstX},${bottom} L ${arr[0]} ${arr.slice(1).map(p => `L ${p}`).join(' ')} L ${lastX},${bottom} Z`
})
</script>

<style scoped>
.smt-wrap {
  width: 100%;
  min-width: 60px;
  display: flex;
  align-items: center;
}

/* ── Skeleton ── */
.smt-skeleton {
  width: 100%;
  height: 42px;
  border-radius: 4px;
  background: var(--surface2);
  animation: smt-pulse 1.2s ease-in-out infinite;
}

@keyframes smt-pulse {
  0%, 100% { opacity: 0.4; }
  50%       { opacity: 0.9; }
}

/* ── Fallback text ── */
.smt-fallback {
  font-size: 10px;
  color: var(--muted);
  white-space: nowrap;
}

/* ── SVG ── */
.smt-svg {
  width: 100%;
  overflow: visible;
  display: block;
}

/* Line colors — Chinese convention: red = up, green = down */
.smt-line.smt--up      { stroke: var(--up-color); }
.smt-line.smt--down    { stroke: var(--down-color); }
.smt-line.smt--neutral { stroke: var(--muted); }

/* Area fill (very subtle) */
.smt-area.smt--up      { fill: var(--up-color);      fill-opacity: 0.08; }
.smt-area.smt--down    { fill: var(--down-color);    fill-opacity: 0.08; }
.smt-area.smt--neutral { fill: var(--neutral-color); fill-opacity: 0.06; }
</style>
