<template>
  <div class="app-shell">
    <AppHeader />

    <!-- ── Page title ── -->
    <div class="scv-title-bar">
      <div>
        <h1 class="scv-title">{{ t('cmp_title') }}</h1>
        <p class="scv-subtitle">{{ t('cmp_subtitle') }}</p>
      </div>
      <button
        v-if="selectedStocks.length > 0"
        class="btn btn-sm btn-secondary scv-clear-btn"
        @click="clearAll"
      >
        {{ t('cmp_clear_all') }}
      </button>
    </div>

    <!-- ── Selector ── -->
    <StockCompareSelector
      :selected-stocks="selectedStocks"
      :loading="anyLoading"
      @add="handleAdd"
      @remove="handleRemove"
      @clear="clearAll"
    />

    <!-- ── Summary stats (shown when ≥1 stock) ── -->
    <section v-if="profiles.length > 0" class="card scv-summary-section">
      <StockCompareSummary :profiles="profiles" :loading="anyLoading" />
    </section>

    <!-- ── Compare table / cards ── -->
    <StockCompareTable
      v-if="profiles.length > 0"
      :profiles="profiles"
      :loading="anyLoading"
      @detail="goDetail"
      @analyze="goAnalyze"
      @history="goHistory"
      @remove="handleRemoveProfile"
    />

    <!-- ── Minimum stock hint ── -->
    <div v-if="selectedStocks.length > 0 && selectedStocks.length < 2 && profiles.length < 2" class="scv-min-hint">
      <span>{{ t('cmp_min_hint') }}</span>
    </div>

    <!-- ── Empty state ── -->
    <div v-if="selectedStocks.length === 0" class="scv-empty">
      <div class="scv-empty-icon">📊</div>
      <p>{{ t('cmp_empty') }}</p>
      <p class="scv-empty-sub">{{ t('cmp_empty_sub') }}</p>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from '../utils/i18n.js'
import { getStockProfile } from '../api/stocks.js'
import {
  getCompareList,
  addCompareStock,
  removeCompareStock,
  clearCompareList,
  buildCompareQuery,
} from '../utils/compareStorage.js'
import AppHeader            from '../components/AppHeader.vue'
import StockCompareSelector from '../components/StockCompareSelector.vue'
import StockCompareSummary  from '../components/StockCompareSummary.vue'
import StockCompareTable    from '../components/StockCompareTable.vue'

const router = useRouter()
const route  = useRoute()
const { t }  = useI18n()

// ── State ──────────────────────────────────────────────────────────────────
// selectedStocks: [{ market, symbol, name }]
const selectedStocks = ref([])
// profiles: same order as selectedStocks, may have _loading / _failed flags
const profiles = ref([])

const anyLoading = computed(() => profiles.value.some(p => p._loading))

// ── URL sync ───────────────────────────────────────────────────────────────
// _syncingUrl prevents the watch from re-triggering a load after we push
let _syncingUrl = false

function _buildStocksQuery() {
  return selectedStocks.value.map(s => `${s.market}:${s.symbol}`).join(',')
}

function _pushUrl() {
  _syncingUrl = true
  const q = selectedStocks.value.length > 0 ? { stocks: _buildStocksQuery() } : {}
  router.replace({ path: '/compare', query: q }).finally(() => {
    _syncingUrl = false
  })
}

// ── Add / Remove ───────────────────────────────────────────────────────────
async function handleAdd({ market, symbol, name }) {
  // Guard: already in list or full
  const key = `${market}:${symbol}`
  if (selectedStocks.value.some(s => `${s.market}:${s.symbol}` === key)) return
  if (selectedStocks.value.length >= 4) return

  selectedStocks.value.push({ market, symbol, name })
  profiles.value.push({ _market: market, _symbol: symbol, _name: name, _loading: true })
  // Sync to storage (may already be there from detail page – idempotent via addCompareStock guard)
  addCompareStock({ market, symbol, stock_name: name })
  _pushUrl()
  await _loadProfile(market, symbol)
}

function handleRemove(stock) {
  const idx = selectedStocks.value.findIndex(
    s => s.market === stock.market && s.symbol === stock.symbol
  )
  if (idx === -1) return
  selectedStocks.value.splice(idx, 1)
  profiles.value.splice(idx, 1)
  removeCompareStock(stock.market, stock.symbol)
  _pushUrl()
}

function handleRemoveProfile(p) {
  handleRemove({ market: p._market, symbol: p._symbol })
}

function clearAll() {
  selectedStocks.value = []
  profiles.value = []
  clearCompareList()
  _pushUrl()
}

// ── Load profile ───────────────────────────────────────────────────────────
async function _loadProfile(market, symbol) {
  const idx = profiles.value.findIndex(
    p => p._market === market && p._symbol === symbol
  )
  if (idx === -1) return
  try {
    const data = await getStockProfile(market, symbol)
    profiles.value[idx] = {
      ...data,
      _market: market,
      _symbol: symbol,
      _name: profiles.value[idx]._name,
      _loading: false,
      _failed: false,
    }
  } catch {
    profiles.value[idx] = {
      _market: market,
      _symbol: symbol,
      _name: profiles.value[idx]._name,
      _loading: false,
      _failed: true,
      quote: { status: 'failed' },
      industry: null,
      latest_report: null,
      data_quality: { profile_status: 'failed' },
    }
  }
}

// ── Navigation ─────────────────────────────────────────────────────────────
function goDetail(p) {
  router.push(`/stocks/${p._market}/${p._symbol}`)
}

function goAnalyze(p) {
  router.push({ path: '/', query: { market: p._market, symbol: p._symbol } })
}

function goHistory(p) {
  router.push({ path: '/history', query: { market: p._market, symbol: p._symbol } })
}

// ── Parse URL / storage tokens ─────────────────────────────────────────────
function _parseTokens(stocksParam) {
  return String(stocksParam)
    .split(',')
    .map(t => t.trim())
    .filter(Boolean)
    .slice(0, 4)
    .map(t => {
      const colonIdx = t.indexOf(':')
      if (colonIdx < 1) return null
      const market = t.slice(0, colonIdx).toUpperCase()
      const symbol = t.slice(colonIdx + 1).trim()
      if (!symbol) return null
      if (!['CN', 'HK'].includes(market)) return null
      return { market, symbol, name: '' }
    })
    .filter(Boolean)
}

async function _loadParsed(parsed) {
  if (parsed.length === 0) return
  selectedStocks.value = parsed
  profiles.value = parsed.map(s => ({
    _market: s.market, _symbol: s.symbol, _name: s.name || '', _loading: true,
  }))
  await Promise.allSettled(parsed.map(s => _loadProfile(s.market, s.symbol)))
}

// ── Init ───────────────────────────────────────────────────────────────────
async function _init() {
  const stocksParam = route.query.stocks

  if (stocksParam) {
    // Prefer URL query
    const parsed = _parseTokens(stocksParam)
    await _loadParsed(parsed)
    // Sync parsed items into storage (overwrite with URL truth)
    clearCompareList()
    parsed.forEach(s => addCompareStock({ market: s.market, symbol: s.symbol }))
  } else {
    // Fall back to localStorage
    const stored = getCompareList()
    if (stored.length > 0) {
      const parsed = stored.map(s => ({
        market: s.market, symbol: s.symbol, name: s.stock_name || '',
      }))
      await _loadParsed(parsed)
      // Sync URL to match storage
      _pushUrl()
    }
  }
}

// Listen for external adds (e.g. from StockDetailView)
function _onCompareUpdated() {
  // Only refresh if current view is empty (user hasn't added anything here yet)
  if (selectedStocks.value.length > 0) return
  const stored = getCompareList()
  if (stored.length > 0) {
    const parsed = stored.map(s => ({
      market: s.market, symbol: s.symbol, name: s.stock_name || '',
    }))
    _loadParsed(parsed).then(() => _pushUrl())
  }
}

onMounted(() => {
  _init()
  window.addEventListener('compare-list-updated', _onCompareUpdated)
})

onUnmounted(() => {
  window.removeEventListener('compare-list-updated', _onCompareUpdated)
})
</script>

<style scoped>
/* ── Title bar ── */
.scv-title-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}

.scv-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}

.scv-subtitle {
  font-size: 13px;
  color: var(--muted);
  margin: 0;
}

.scv-clear-btn {
  flex-shrink: 0;
  margin-top: 4px;
}

/* ── Summary section ── */
.scv-summary-section { padding: 14px 20px; }

/* ── Min hint ── */
.scv-min-hint {
  text-align: center;
  color: var(--muted);
  font-size: 13px;
  padding: 16px 0 8px;
}

/* ── Empty state ── */
.scv-empty {
  text-align: center;
  color: var(--muted);
  padding: 48px 20px;
}

.scv-empty-icon {
  font-size: 40px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.scv-empty p {
  margin: 0 0 6px;
  font-size: 14px;
}

.scv-empty-sub {
  font-size: 12px;
  color: var(--muted);
  max-width: 320px;
  margin: 0 auto;
  line-height: 1.5;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .scv-title    { font-size: 18px; }
  .scv-subtitle { font-size: 12px; }

  .scv-title-bar {
    flex-wrap: wrap;
  }
}
</style>
