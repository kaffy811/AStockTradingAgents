<template>
  <div class="card chart-card">

    <!-- ── Control bar ─────────────────────────────────────────────────────── -->
    <div class="chart-controls">

      <!-- Range / period tabs -->
      <div class="ctrl-tabs" role="group" aria-label="K线区间与周期">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          :class="['ctrl-tab', activeTab === tab.key ? 'ctrl-tab--active' : '']"
          @click="selectTab(tab.key)"
        >{{ tab.label }}</button>
      </div>

      <!-- Indicator toggles + meta + refresh -->
      <div class="ctrl-legend">
        <!-- MA / volume toggles (default on) -->
        <button
          v-for="m in MA_TOGGLES"
          :key="m.key"
          :class="['ctrl-toggle', `toggle-${m.key}`, show[m.key] ? 'toggle--on' : 'toggle--off']"
          :title="show[m.key] ? `隐藏 ${m.label}` : `显示 ${m.label}`"
          @click="toggleIndicator(m.key)"
        >{{ m.label }}</button>

        <span class="ctrl-divider">|</span>

        <!-- MACD / RSI toggles (default off, open sub-charts) -->
        <button
          v-for="m in INDICATOR_TOGGLES"
          :key="m.key"
          :class="['ctrl-toggle', `toggle-${m.key}`, show[m.key] ? 'toggle--on' : 'toggle--off']"
          :title="show[m.key] ? `关闭 ${m.label}` : `开启 ${m.label}`"
          @click="toggleIndicator(m.key)"
        >{{ m.label }}</button>

        <span v-if="stale" class="tag tag--warn" title="当前展示的是最近一次可用行情，可能不是最新数据">
          缓存数据
        </span>
        <span v-if="bars.length > 0" class="ctrl-volunit">{{ volUnitLabel }}</span>

        <button class="btn btn-secondary refresh-btn" :disabled="loading" @click="fetchKline">
          <span v-if="loading" class="spinner"></span>
          <span v-else>刷新</span>
        </button>
      </div>
    </div>

    <!-- ── Range statistics bar ────────────────────────────────────────────── -->
    <div v-if="rangeStats" class="chart-stats">
      <span>最高&nbsp;<strong class="stat-val up">{{ rangeStats.high }}</strong></span>
      <span class="stat-sep">·</span>
      <span>最低&nbsp;<strong class="stat-val dn">{{ rangeStats.low }}</strong></span>
      <span class="stat-sep">·</span>
      <span>区间涨跌&nbsp;<strong :class="['stat-val', rangeStats.pctClass]">{{ rangeStats.pct }}</strong></span>
      <span class="stat-sep">·</span>
      <span class="stat-count">{{ rangeStats.count }} 根K线</span>
    </div>
    <div v-else-if="!loading && !error && bars.length > 0" class="chart-stats chart-stats--empty">
      数据不足，无法计算区间统计
    </div>

    <!-- ── Main K-line chart ───────────────────────────────────────────────── -->
    <div class="chart-wrap" :style="{ height: props.height + 'px' }">
      <div ref="containerRef" class="chart-container" />

      <div v-if="loading" class="chart-overlay">
        <span class="spinner"></span>
        <span class="overlay-text">加载K线数据…</span>
      </div>
      <div v-else-if="error" class="chart-overlay chart-overlay--error">
        <p class="chart-err-msg">{{ error }}</p>
        <button class="btn btn-secondary btn-sm" @click="fetchKline">重新加载</button>
      </div>
      <div
        v-else-if="!loading && !error && bars.length === 0"
        class="chart-overlay chart-overlay--empty"
      >
        <p class="chart-empty-title">暂无 K 线数据</p>
        <p class="chart-empty-msg">当前数据源暂未返回该股票的 K 线数据。你可以稍后重试，或检查股票代码是否正确。</p>
        <button class="btn btn-secondary btn-sm" @click="fetchKline">重新加载</button>
      </div>
    </div>

    <!-- ── MACD sub-chart ──────────────────────────────────────────────────── -->
    <div v-if="show.macd" class="sub-chart-wrap">
      <div class="sub-chart-label">
        MACD <span class="sub-chart-params">(12, 26, 9)</span>
        <span class="sub-legend">
          <span class="sub-legend-dif">DIF</span>
          <span class="sub-legend-dea">DEA</span>
        </span>
      </div>
      <div class="sub-chart-inner">
        <div ref="macdContainerRef" class="sub-chart-container sub-chart-container--macd" />
        <div v-if="!loading && macdData.length === 0" class="sub-chart-empty">
          K线数量不足，暂无法计算 MACD（至少需要 34 根K线）
        </div>
      </div>
    </div>

    <!-- ── RSI sub-chart ───────────────────────────────────────────────────── -->
    <div v-if="show.rsi" class="sub-chart-wrap">
      <div class="sub-chart-label">
        RSI <span class="sub-chart-params">(14)</span>
        <span class="sub-chart-hint-sm">· 70 超买 · 30 超卖</span>
      </div>
      <div class="sub-chart-inner">
        <div ref="rsiContainerRef" class="sub-chart-container sub-chart-container--rsi" />
        <div v-if="!loading && rsiData.length === 0" class="sub-chart-empty">
          K线数量不足，暂无法计算 RSI（至少需要 15 根K线）
        </div>
      </div>
    </div>

    <!-- ── Technical indicator summary ───────────────────────────────────── -->
    <div v-if="showIndicatorSummary" class="indicator-summary">
      <span class="ind-label">技术指标</span>
      <span v-if="show.macd && macdSummary" class="ind-item">
        MACD：DIF {{ fmt3(macdSummary.dif) }}&nbsp;/&nbsp;DEA {{ fmt3(macdSummary.dea) }}&nbsp;/&nbsp;柱 {{ fmt3(macdSummary.histogram) }}
        <span :class="['ind-note', macdSummary.histogram > 0 ? 'up' : 'dn']">
          （{{ macdHistLabel(macdSummary.histogram) }}）
        </span>
      </span>
      <span v-if="show.rsi && rsiSummary" class="ind-item">
        RSI(14)：{{ rsiSummary.value.toFixed(1) }}，{{ rsiLabel(rsiSummary.value) }}
      </span>
    </div>

    <!-- ── Interaction hint ────────────────────────────────────────────────── -->
    <div class="chart-hint">
      <span class="hint-desktop">鼠标悬停查看K线详细数据 · 滚轮缩放 · 拖动平移</span>
      <span class="hint-mobile">左右滑动查看历史走势 · 双指缩放</span>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted, onActivated } from 'vue'
import { createChart, CrosshairMode, ColorType, LineStyle } from 'lightweight-charts'
import { getKline } from '../api/stocks.js'
import { formatPrice, formatChangePct, changePctClass } from '../utils/marketFormat.js'
import { calculateMACD, calculateRSI } from '../utils/technicalIndicators.js'

// ── Props / emits ─────────────────────────────────────────────────────────────
const props = defineProps({
  market:  { type: String,  required: true },
  symbol:  { type: String,  required: true },
  visible: { type: Boolean, default: true  },
  height:  { type: Number,  default: 340   },
})

const emit = defineEmits(['insight-data'])

// ── Tab / range config ────────────────────────────────────────────────────────
const TABS = [
  { key: '1m', label: '1月', period: 'daily',   limit: 30  },
  { key: '3m', label: '3月', period: 'daily',   limit: 90  },
  { key: '6m', label: '6月', period: 'daily',   limit: 180 },
  { key: '1y', label: '1年', period: 'daily',   limit: 250 },
  { key: 'wk', label: '周K', period: 'weekly',  limit: 52  },
  { key: 'mo', label: '月K', period: 'monthly', limit: 60  },
]

// ── Indicator toggle configs ──────────────────────────────────────────────────
const MA_TOGGLES = [
  { key: 'ma5',  label: 'MA5'  },
  { key: 'ma10', label: 'MA10' },
  { key: 'ma20', label: 'MA20' },
  { key: 'ma60', label: 'MA60' },
  { key: 'vol',  label: '成交量' },
]

const INDICATOR_TOGGLES = [
  { key: 'macd', label: 'MACD' },
  { key: 'rsi',  label: 'RSI'  },
]

// ── Reactive state ────────────────────────────────────────────────────────────
const activeTab  = ref('3m')
const bars       = ref([])
const loading    = ref(false)
const error      = ref('')
const stale      = ref(false)
const volumeUnit = ref('lot')

// MA / vol toggles default on; MACD / RSI default off
const show = reactive({ ma5: true, ma10: true, ma20: true, ma60: true, vol: true, macd: false, rsi: false })

// Indicator data refs (reactive — used by computed summary)
const macdData = ref([])   // { time, dif, dea, histogram }[]
const rsiData  = ref([])   // { time, value }[]

// DOM refs
const containerRef    = ref(null)
const macdContainerRef = ref(null)
const rsiContainerRef  = ref(null)

// ── Race-condition guard ──────────────────────────────────────────────────────
let fetchGen = 0

// ── Non-reactive chart instances ──────────────────────────────────────────────
let chart        = null
let candleSeries = null
let volSeries    = null
let ma5S = null, ma10S = null, ma20S = null, ma60S = null
let ro   = null

let macdChart = null, macdDifS = null, macdDeaS = null, macdHistS = null
let roMacd    = null

let rsiChart = null, rsiS = null
let roRsi    = null

// ── Color palette — read from CSS variables at chart-init time ────────────────
// C is null until initChart() is called (after theme has been applied to html[data-theme]).
let C = null

function buildColors() {
  const css = getComputedStyle(document.documentElement)
  const v = (name, fb) => css.getPropertyValue(name).trim() || fb
  return {
    bg:       v('--chart-bg',             '#0b1120'),
    border:   v('--chart-grid',           '#2e3347'),
    text:     v('--text-primary',         '#e2e8f0'),
    muted:    v('--text-muted',           '#7a859c'),
    upCandle: v('--up-color',             '#ef5350'),
    dnCandle: v('--down-color',           '#26a69a'),
    ma5:      v('--chart-ma5',            '#4f8ef7'),
    ma10:     v('--chart-ma10',           '#f5a623'),
    ma20:     v('--chart-ma20',           '#f5554a'),
    ma60:     v('--chart-ma60',           '#a78bfa'),
    volUp:    v('--chart-volume-up',      'rgba(239,83,80,0.45)'),
    volDn:    v('--chart-volume-down',    'rgba(38,166,154,0.45)'),
    // MACD
    macdDif:  v('--chart-ma5',            '#4f8ef7'),
    macdDea:  v('--chart-ma10',           '#f5a623'),
    macdUp:   v('--chart-volume-up',      'rgba(239,83,80,0.60)'),
    macdDn:   v('--chart-volume-down',    'rgba(38,166,154,0.60)'),
    // RSI
    rsi:      v('--accent-secondary',     '#c084fc'),
    rsi70:    v('--chart-rsi-overbought', 'rgba(239,83,80,0.45)'),
    rsi30:    v('--chart-rsi-oversold',   'rgba(38,166,154,0.45)'),
  }
}

// ── Computed ──────────────────────────────────────────────────────────────────
const volUnitLabel = computed(() =>
  volumeUnit.value === 'lot' ? '成交量单位：手' : '成交量单位：股'
)

const rangeStats = computed(() => {
  const valid = bars.value.filter(b =>
    Number.isFinite(b.open) && Number.isFinite(b.high) &&
    Number.isFinite(b.low)  && Number.isFinite(b.close)
  )
  if (valid.length < 2) return null

  let high = -Infinity, low = Infinity
  for (const b of valid) {
    if (b.high > high) high = b.high
    if (b.low  < low)  low  = b.low
  }

  const firstOpen = valid[0].open
  const lastClose = valid[valid.length - 1].close
  const pctVal = firstOpen !== 0 ? (lastClose - firstOpen) / firstOpen * 100 : null

  return {
    high:     formatPrice(high),
    low:      formatPrice(low),
    pct:      pctVal != null ? formatChangePct(pctVal) : '—',
    pctClass: pctVal != null ? changePctClass(pctVal)  : '',
    count:    valid.length,
  }
})

const macdSummary = computed(() => {
  if (!macdData.value.length) return null
  return macdData.value[macdData.value.length - 1]
})

const rsiSummary = computed(() => {
  if (!rsiData.value.length) return null
  return rsiData.value[rsiData.value.length - 1]
})

const showIndicatorSummary = computed(() =>
  (show.macd && macdSummary.value != null) ||
  (show.rsi  && rsiSummary.value  != null)
)

// ── Date normalisation ────────────────────────────────────────────────────────
function normalizeDate(d) {
  const s = String(d)
  if (s.length === 8 && !s.includes('-')) {
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
  }
  return s
}

// ── MA calculation ────────────────────────────────────────────────────────────
function calcMA(times, closes, period) {
  const result = []
  for (let i = period - 1; i < closes.length; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += closes[j]
    result.push({ time: times[i], value: parseFloat((sum / period).toFixed(3)) })
  }
  return result
}

// ── Bar transformation ────────────────────────────────────────────────────────
function transformBars(rawBars) {
  const candles = [], volumes = [], times = [], closes = []
  for (const bar of rawBars) {
    const { open, high, low, close, volume, date } = bar
    if (
      !Number.isFinite(open) || !Number.isFinite(high) ||
      !Number.isFinite(low)  || !Number.isFinite(close)
    ) continue
    const t = normalizeDate(date)
    candles.push({ time: t, open, high, low, close })
    volumes.push({
      time:  t,
      value: Number.isFinite(volume) ? volume : 0,
      color: close >= open ? C.volUp : C.volDn,
    })
    times.push(t)
    closes.push(close)
  }
  return {
    candles, volumes,
    ma5:   calcMA(times, closes,  5),
    ma10:  calcMA(times, closes, 10),
    ma20:  calcMA(times, closes, 20),
    ma60:  calcMA(times, closes, 60),
    times, closes,
  }
}

// ── Main chart init ───────────────────────────────────────────────────────────
function initChart() {
  if (!containerRef.value || chart) return
  C = buildColors()   // read CSS vars after theme is applied
  const w = containerRef.value.clientWidth || 800

  chart = createChart(containerRef.value, {
    width:  w,
    height: props.height,
    layout: { background: { type: ColorType.Solid, color: C.bg }, textColor: C.text, fontSize: 11 },
    grid:   { vertLines: { color: C.border }, horzLines: { color: C.border } },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: C.border, scaleMargins: { top: 0.05, bottom: 0.25 } },
    timeScale: { borderColor: C.border, barSpacing: 6, rightOffset: 5, timeVisible: false },
    handleScroll: true, handleScale: true,
  })

  candleSeries = chart.addCandlestickSeries({
    upColor: C.upCandle, downColor: C.dnCandle,
    borderVisible: false, wickUpColor: C.upCandle, wickDownColor: C.dnCandle,
  })

  volSeries = chart.addHistogramSeries({
    priceScaleId: '', priceFormat: { type: 'volume' }, color: C.volUp,
  })
  volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } })

  const lineBase = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false }
  ma5S  = chart.addLineSeries({ ...lineBase, color: C.ma5  })
  ma10S = chart.addLineSeries({ ...lineBase, color: C.ma10 })
  ma20S = chart.addLineSeries({ ...lineBase, color: C.ma20 })
  ma60S = chart.addLineSeries({ ...lineBase, color: C.ma60 })
}

// ── Main chart update ─────────────────────────────────────────────────────────
function updateChart(rawBars) {
  if (!chart || !candleSeries) return null
  const { candles, volumes, ma5, ma10, ma20, ma60, times, closes } = transformBars(rawBars)
  candleSeries.setData(candles)
  volSeries.setData(volumes)
  ma5S.setData(ma5)
  ma10S.setData(ma10)
  ma20S.setData(ma20)
  ma60S.setData(ma60)
  chart.timeScale().fitContent()
  applySeriesVisibility()

  // Update sub-charts (only when their chart instance is active)
  _updateMacdData(times, closes)
  _updateRsiData(times, closes)

  return { candles, volumes, ma5, ma10, ma20, ma60, times, closes }
}

// ── Series visibility ─────────────────────────────────────────────────────────
function applySeriesVisibility() {
  ma5S?.applyOptions({ visible: show.ma5   })
  ma10S?.applyOptions({ visible: show.ma10  })
  ma20S?.applyOptions({ visible: show.ma20  })
  ma60S?.applyOptions({ visible: show.ma60  })
  volSeries?.applyOptions({ visible: show.vol })
}

// ── MACD chart ────────────────────────────────────────────────────────────────
function _subChartOptions(height) {
  return {
    width:  800,    // overridden by resize observer
    height,
    layout: { background: { type: ColorType.Solid, color: C.bg }, textColor: C.text, fontSize: 10 },
    grid:   { vertLines: { color: C.border }, horzLines: { color: C.border } },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: C.border },
    timeScale: { borderColor: C.border, barSpacing: 6, rightOffset: 5, timeVisible: true },
    handleScroll: true, handleScale: true,
  }
}

function initMacdChart() {
  if (!macdContainerRef.value || macdChart) return

  const w = macdContainerRef.value.clientWidth || 800
  macdChart = createChart(macdContainerRef.value, { ..._subChartOptions(140), width: w })

  const lineBase = { lineWidth: 1, priceLineVisible: false, lastValueVisible: true }
  macdHistS = macdChart.addHistogramSeries({ color: C.macdUp, priceLineVisible: false, lastValueVisible: false })
  macdDifS  = macdChart.addLineSeries({ ...lineBase, color: C.macdDif })
  macdDeaS  = macdChart.addLineSeries({ ...lineBase, color: C.macdDea })

  roMacd = new ResizeObserver(entries => {
    if (!macdChart) return
    const { width } = entries[0].contentRect
    if (width > 0) macdChart.applyOptions({ width })
  })
  roMacd.observe(macdContainerRef.value)
}

function destroyMacdChart() {
  roMacd?.disconnect()
  macdChart?.remove()
  macdChart = macdDifS = macdDeaS = macdHistS = null
  roMacd = null
  macdData.value = []
}

function _updateMacdData(times, closes) {
  if (!macdChart) return

  const data = calculateMACD(times, closes)
  macdData.value = data

  if (!data.length) {
    macdHistS?.setData([])
    macdDifS?.setData([])
    macdDeaS?.setData([])
    return
  }

  macdHistS?.setData(data.map(d => ({
    time:  d.time,
    value: d.histogram,
    color: d.histogram >= 0 ? C.macdUp : C.macdDn,
  })))
  macdDifS?.setData(data.map(d => ({ time: d.time, value: d.dif })))
  macdDeaS?.setData(data.map(d => ({ time: d.time, value: d.dea })))
  macdChart.timeScale().fitContent()
}

// ── RSI chart ─────────────────────────────────────────────────────────────────
function initRsiChart() {
  if (!rsiContainerRef.value || rsiChart) return

  const w = rsiContainerRef.value.clientWidth || 800
  rsiChart = createChart(rsiContainerRef.value, { ..._subChartOptions(120), width: w })

  rsiS = rsiChart.addLineSeries({
    color:            C.rsi,
    lineWidth:        1.5,
    priceLineVisible: false,
    lastValueVisible: true,
  })

  // Reference lines for overbought (70) and oversold (30)
  rsiS.createPriceLine({ price: 70, color: C.rsi70, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true,  title: '超买' })
  rsiS.createPriceLine({ price: 30, color: C.rsi30, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true,  title: '超卖' })
  rsiS.createPriceLine({ price: 50, color: C.border, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false })

  roRsi = new ResizeObserver(entries => {
    if (!rsiChart) return
    const { width } = entries[0].contentRect
    if (width > 0) rsiChart.applyOptions({ width })
  })
  roRsi.observe(rsiContainerRef.value)
}

function destroyRsiChart() {
  roRsi?.disconnect()
  rsiChart?.remove()
  rsiChart = rsiS = null
  roRsi = null
  rsiData.value = []
}

function _updateRsiData(times, closes) {
  if (!rsiChart) return

  const data = calculateRSI(times, closes)
  rsiData.value = data

  rsiS?.setData(data)
  if (data.length) rsiChart.timeScale().fitContent()
}

// ── Indicator toggle ──────────────────────────────────────────────────────────
function toggleIndicator(key) {
  show[key] = !show[key]
  // MA / volume: direct series visibility, no sub-chart lifecycle
  if (key !== 'macd' && key !== 'rsi') {
    applySeriesVisibility()
  }
  // MACD / RSI lifecycle handled by watchers below
}

// ── Tab selection ─────────────────────────────────────────────────────────────
function selectTab(key) {
  if (activeTab.value === key) return
  activeTab.value = key
  fetchKline()
}

// ── Fetch kline ───────────────────────────────────────────────────────────────
async function fetchKline() {
  if (!props.visible || !props.market || !props.symbol) return

  const gen = ++fetchGen
  const tab = TABS.find(t => t.key === activeTab.value) || TABS[1]

  loading.value = true
  error.value   = ''

  try {
    const res = await getKline(props.market, props.symbol, {
      period: tab.period,
      adjust: 'qfq',
      limit:  tab.limit,
    })

    if (gen !== fetchGen) return   // superseded

    bars.value       = res.data        || []
    stale.value      = res.stale       || false
    volumeUnit.value = res.volume_unit || 'lot'

    if (bars.value.length > 0) {
      const chartData = updateChart(bars.value)
      if (chartData) {
        const { candles, volumes, ma5, ma10, ma20, ma60, times, closes } = chartData
        emit('insight-data', {
          market:   props.market,
          symbol:   props.symbol,
          rangeKey: activeTab.value,
          klineData: { candles, volumes },
          maData:   { ma5, ma10, ma20, ma60 },
          macdData: calculateMACD(times, closes),
          rsiData:  calculateRSI(times, closes),
        })
      }
    } else {
      candleSeries?.setData([])
      volSeries?.setData([])
      ma5S?.setData([])
      ma10S?.setData([])
      ma20S?.setData([])
      ma60S?.setData([])
      // Clear indicator data if no bars
      macdData.value = []
      rsiData.value  = []
      if (macdChart) { macdHistS?.setData([]); macdDifS?.setData([]); macdDeaS?.setData([]) }
      if (rsiChart)  { rsiS?.setData([]) }
      emit('insight-data', { market: props.market, symbol: props.symbol, empty: true })
    }
  } catch (e) {
    if (gen !== fetchGen) return
    error.value = e.message || 'K线数据加载失败'
    emit('insight-data', { market: props.market, symbol: props.symbol, error: true })
  } finally {
    if (gen === fetchGen) loading.value = false
  }
}

// ── Theme refresh — re-apply colors when user switches theme ─────────────────
function refreshChartColors() {
  if (!chart) return
  C = buildColors()

  const layout = { background: { type: ColorType.Solid, color: C.bg }, textColor: C.text, fontSize: 11 }
  const grid   = { vertLines: { color: C.border }, horzLines: { color: C.border } }
  const scaleOpts = { borderColor: C.border }

  chart.applyOptions({ layout, grid, rightPriceScale: scaleOpts, timeScale: scaleOpts })

  candleSeries?.applyOptions({
    upColor: C.upCandle, downColor: C.dnCandle,
    wickUpColor: C.upCandle, wickDownColor: C.dnCandle,
  })
  ma5S?.applyOptions({ color: C.ma5 })
  ma10S?.applyOptions({ color: C.ma10 })
  ma20S?.applyOptions({ color: C.ma20 })
  ma60S?.applyOptions({ color: C.ma60 })

  // Re-set volume data with new bar colors
  if (volSeries && bars.value.length > 0) {
    const { volumes } = transformBars(bars.value)
    volSeries.setData(volumes)
  }

  // MACD sub-chart
  if (macdChart) {
    macdChart.applyOptions({ layout: { ...layout, fontSize: 10 }, grid, rightPriceScale: scaleOpts, timeScale: scaleOpts })
    macdDifS?.applyOptions({ color: C.macdDif })
    macdDeaS?.applyOptions({ color: C.macdDea })
    if (macdData.value.length > 0) {
      macdHistS?.setData(macdData.value.map(d => ({
        time: d.time, value: d.histogram,
        color: d.histogram >= 0 ? C.macdUp : C.macdDn,
      })))
    }
  }

  // RSI sub-chart
  if (rsiChart) {
    rsiChart.applyOptions({ layout: { ...layout, fontSize: 10 }, grid, rightPriceScale: scaleOpts, timeScale: scaleOpts })
    rsiS?.applyOptions({ color: C.rsi })
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  initChart()

  if (containerRef.value) {
    ro = new ResizeObserver(entries => {
      if (!chart) return
      const { width } = entries[0].contentRect
      if (width > 0) chart.applyOptions({ width })
    })
    ro.observe(containerRef.value)
  }

  window.addEventListener('tradingagents-settings-updated', refreshChartColors)

  fetchKline()
})

onActivated(() => {
  if (chart && containerRef.value) {
    const w = containerRef.value.clientWidth
    if (w > 0) chart.applyOptions({ width: w })
  }
  if (macdChart && macdContainerRef.value) {
    const w = macdContainerRef.value.clientWidth
    if (w > 0) macdChart.applyOptions({ width: w })
  }
  if (rsiChart && rsiContainerRef.value) {
    const w = rsiContainerRef.value.clientWidth
    if (w > 0) rsiChart.applyOptions({ width: w })
  }
})

onUnmounted(() => {
  window.removeEventListener('tradingagents-settings-updated', refreshChartColors)
  ro?.disconnect()
  chart?.remove()
  chart = candleSeries = volSeries = ma5S = ma10S = ma20S = ma60S = null
  ro    = null
  destroyMacdChart()
  destroyRsiChart()
})

// ── Watchers ──────────────────────────────────────────────────────────────────

// Stock change: reset tab and refetch
watch(
  () => [props.market, props.symbol],
  ([newM, newS], [oldM, oldS]) => {
    if (newM !== oldM || newS !== oldS) {
      activeTab.value = '3m'
      fetchKline()
    }
  },
  { immediate: false },
)

// MACD toggle: create / destroy sub-chart
watch(() => show.macd, async (val) => {
  if (val) {
    await nextTick()   // wait for v-if to mount the DOM element
    initMacdChart()
    // Recompute from current bars
    const valid  = bars.value.filter(b => Number.isFinite(b.close))
    const times  = valid.map(b => normalizeDate(b.date))
    const closes = valid.map(b => b.close)
    _updateMacdData(times, closes)
  } else {
    destroyMacdChart()
  }
})

// RSI toggle: create / destroy sub-chart
watch(() => show.rsi, async (val) => {
  if (val) {
    await nextTick()
    initRsiChart()
    const valid  = bars.value.filter(b => Number.isFinite(b.close))
    const times  = valid.map(b => normalizeDate(b.date))
    const closes = valid.map(b => b.close)
    _updateRsiData(times, closes)
  } else {
    destroyRsiChart()
  }
})

// ── Text formatters ───────────────────────────────────────────────────────────
function fmt3(val) {
  if (val == null || !Number.isFinite(val)) return '—'
  return (val >= 0 ? '+' : '') + val.toFixed(3)
}

function rsiLabel(val) {
  if (val >= 70) return '偏强，注意短期过热'
  if (val <= 30) return '偏弱，注意短期超跌'
  if (val >= 50) return '中性偏强'
  return '中性偏弱'
}

function macdHistLabel(val) {
  if (Math.abs(val) < 0.0001) return 'MACD 动能接近零轴'
  return val > 0 ? 'DIF 位于 DEA 上方' : 'DIF 位于 DEA 下方'
}
</script>

<style scoped>
/* ── Control bar ── */
.chart-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.ctrl-tabs {
  display: flex;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  gap: 4px;
  flex-shrink: 0;
}
.ctrl-tabs::-webkit-scrollbar { display: none; }

.ctrl-tab {
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.12s, background 0.12s, border-color 0.12s;
}
.ctrl-tab:hover { color: var(--text); background: var(--status-info-bg); }
.ctrl-tab--active {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--border-glow);
}

.ctrl-legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-left: auto;
}

.ctrl-divider {
  color: var(--border);
  padding: 0 2px;
  font-size: 12px;
  user-select: none;
}

.ctrl-toggle {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: opacity 0.15s, background 0.15s;
  white-space: nowrap;
}

.ctrl-toggle.toggle--off {
  background: var(--surface2);
  border-color: var(--border);
  color: var(--muted);
  text-decoration: line-through;
  opacity: 0.55;
}

/* MA / vol on-state colours */
.toggle-ma5.toggle--on  { background: var(--status-info-bg); border-color: var(--border-glow); color: var(--chart-ma5); }
.toggle-ma10.toggle--on { background: var(--status-warn-bg); border-color: var(--status-warn-ring); color: var(--chart-ma10); }
.toggle-ma20.toggle--on { background: var(--status-up-bg); border-color: var(--status-up-ring); color: var(--chart-ma20); }
.toggle-ma60.toggle--on { background: var(--accent-glow); border-color: var(--border-glow); color: var(--chart-ma60); }
.toggle-vol.toggle--on  { background: var(--surface-muted); border-color: var(--border); color: var(--muted); }

/* MACD / RSI on-state colours */
.toggle-macd.toggle--on { background: var(--status-info-bg); border-color: var(--border-glow); color: var(--chart-ma5); }
.toggle-rsi.toggle--on  { background: var(--accent-glow); border-color: var(--border-glow); color: var(--accent-secondary); }

.ctrl-volunit {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}

.tag {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}

.tag--warn {
  background: var(--status-warn-bg);
  border-color: var(--status-warn-ring);
  color: var(--warn);
}

.refresh-btn {
  padding: 3px 12px;
  font-size: 11px;
  min-width: 48px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
.refresh-btn .spinner { width: 10px; height: 10px; margin-right: 0; }

/* ── Stats bar ── */
.chart-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
  padding: 6px 8px;
  background: var(--surface2);
  border-radius: 4px;
  border: 1px solid var(--border);
}
.chart-stats--empty { font-style: italic; }

.stat-sep   { color: var(--border); flex-shrink: 0; }
.stat-val   { font-family: monospace; }
.stat-count { white-space: nowrap; }

.up { color: var(--danger);  }
.dn { color: var(--success); }

/* ── Main chart area ── */
.chart-wrap {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: 6px;
  background: #0f1117;
}
.chart-container { width: 100%; height: 100%; }

/* ── Overlays ── */
.chart-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #0f1117;
  z-index: 10;
  border-radius: 6px;
}
.chart-overlay--error   { background: rgba(10, 12, 18, 0.94); }
.chart-overlay--empty   { background: rgba(10, 12, 18, 0.94); padding: 0 24px; text-align: center; }
.overlay-text           { color: var(--muted); font-size: 13px; margin-left: 6px; }
.chart-empty-title      { font-size: 13px; font-weight: 600; color: var(--text); margin: 0 0 6px; }
.chart-empty-msg        { font-size: 12px; color: var(--muted); max-width: 300px; line-height: 1.6; margin: 0 0 12px; }
.chart-err-msg          { color: var(--danger); font-size: 13px; text-align: center; max-width: 320px; line-height: 1.5; }

/* ── Sub-chart (MACD / RSI) ── */
.sub-chart-wrap {
  margin-top: 8px;
  border-top: 1px solid var(--border);
  padding-top: 6px;
}

.sub-chart-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  margin-bottom: 4px;
  padding-left: 2px;
}
.sub-chart-params   { font-weight: 400; opacity: 0.75; }
.sub-chart-hint-sm  { font-weight: 400; font-size: 10px; opacity: 0.65; }

.sub-legend         { display: flex; gap: 6px; margin-left: auto; }
.sub-legend-dif     { font-size: 10px; font-weight: 700; color: var(--chart-ma5); }
.sub-legend-dea     { font-size: 10px; font-weight: 700; color: var(--chart-ma10); }

.sub-chart-inner {
  position: relative;
  width: 100%;
}
.sub-chart-container {
  width: 100%;
  background: #0f1117;
  border-radius: 4px;
  overflow: hidden;
}
.sub-chart-container--macd { height: 140px; }
.sub-chart-container--rsi  { height: 120px; }

.sub-chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--muted);
  font-style: italic;
  background: rgba(15, 17, 23, 0.92);
  border-radius: 4px;
  text-align: center;
  padding: 0 16px;
  z-index: 5;
}

/* ── Indicator summary ── */
.indicator-summary {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 8px;
  padding: 7px 10px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--muted);
}

.ind-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.ind-item {
  font-family: monospace;
  font-size: 12px;
  color: var(--text);
}

.ind-note {
  font-family: sans-serif;
  font-size: 11px;
  color: var(--muted);
}

/* ── Interaction hint ── */
.chart-hint {
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted);
  opacity: 0.75;
}
.hint-desktop { display: inline; }
.hint-mobile  { display: none;   }

/* ── Mobile ── */
@media (max-width: 540px) {
  .chart-controls { flex-direction: column; align-items: flex-start; gap: 8px; }
  .ctrl-legend    { margin-left: 0; gap: 5px; }

  .hint-desktop { display: none;   }
  .hint-mobile  { display: inline; }

  .indicator-summary { gap: 6px 8px; }
  .ind-item { font-size: 11px; }
}
</style>
