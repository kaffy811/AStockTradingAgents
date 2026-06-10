<template>
  <div class="app-shell">
    <AppHeader />

    <!-- ── Page title ── -->
    <div class="ihv-title-bar">
      <div>
        <h1 class="ihv-title">{{ t('ind_title') }}</h1>
        <p class="ihv-subtitle">{{ t('ind_subtitle') }}</p>
      </div>
    </div>

    <!-- ── Hero grid: heat overview + hot blocks ── -->
    <div class="ihv-hero-grid">
      <IndustryHeatOverviewCard
        :industries="industries"
        :selected-code="selectedCode"
        :loading="industriesLoading"
        :error="industriesError"
        @select="onIndustryChange"
        @retry="retryIndustries"
      />
      <IndustryHotBlocksCard
        :industries="industries"
        :selected-code="selectedCode"
        :loading="industriesLoading"
        :error="industriesError"
        :limit="5"
        :expanded="hotBlocksExpanded"
        @select="onIndustryChange"
        @view-all="hotBlocksExpanded = !hotBlocksExpanded"
        @retry="retryIndustries"
      />
    </div>

    <!-- ── Stats ── -->
    <section v-if="!hotError" class="card ihv-stats-section">
      <IndustryHotStats :items="filteredItems" :loading="hotLoading" />
    </section>

    <!-- ── Quick jump stock detail (moved below stats) ── -->
    <section class="card ihv-search-card">
      <div class="ihv-search-label">{{ t('ind_quick_label') }}</div>
      <div class="ihv-search-row">
        <div class="ihv-search-box">
          <StockSearchBox
            v-model:symbol="quickSymbol"
            market="CN"
            :placeholder="t('ind_quick_placeholder')"
            @select="goDetailSelected"
          />
        </div>
        <button
          class="btn btn-sm btn-secondary"
          :disabled="!quickSymbol.trim()"
          @click="goDetailQuick"
        >
          {{ t('ind_quick_go') }}
        </button>
      </div>
    </section>

    <!-- ── Industry toolbar ── -->
    <IndustryToolbar
      :industries="industries"
      :selected-code="selectedCode"
      :filters="filters"
      :sort-key="sortKey"
      :data-sources="availableDataSources"
      :loading="industriesLoading"
      :hot-loading="hotLoading"
      @update:selected-code="onIndustryChange"
      @update:filters="filters = $event"
      @update:sort-key="sortKey = $event"
      @refresh="loadHotStocks"
    />

    <!-- ── Industry overview ── -->
    <IndustryOverviewPanel
      :industry="selectedIndustry"
      :hot-data="hotData"
      :loading="hotLoading"
      :error="hotError"
      market="CN"
    />

    <!-- ── Loading ── -->
    <div v-if="hotLoading" class="ihv-empty">
      <span class="spinner"></span> {{ t('ind_loading') }}
    </div>

    <!-- ── Error ── -->
    <ErrorBox :message="hotError" />

    <!-- ── Empty state ── -->
    <div
      v-if="!hotLoading && !hotError && hotData && hotData.items.length === 0"
      class="ihv-empty"
    >
      {{ t('ind_empty') }}
    </div>

    <!-- ── Empty after filter ── -->
    <div
      v-if="!hotLoading && !hotError && hotData && hotData.items.length > 0 && filteredItems.length === 0"
      class="ihv-empty"
    >
      {{ t('ind_no_results') }}
    </div>

    <!-- ── Stock cards ── -->
    <div v-if="!hotLoading && filteredItems.length > 0" class="ihv-card-list">
      <IndustryStockCard
        v-for="item in filteredItems"
        :key="item.symbol"
        :item="item"
        market="CN"
        :adding-status="watchlistStatus[item.symbol] || ''"
        @detail="goDetail(item.symbol)"
        @analyze="goAnalyze(item.symbol)"
        @history="goHistory(item.symbol)"
        @add-watchlist="addToWatchlist(item.symbol, item.stock_name)"
      />
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '../utils/i18n.js'
import { listIndustries, getIndustryHotStocks } from '../api/industries.js'
import { addWatchlist } from '../api/watchlist.js'
import AppHeader                from '../components/AppHeader.vue'
import ErrorBox                 from '../components/ErrorBox.vue'
import StockSearchBox           from '../components/StockSearchBox.vue'
import IndustryOverviewPanel    from '../components/IndustryOverviewPanel.vue'
import IndustryHotStats         from '../components/IndustryHotStats.vue'
import IndustryToolbar          from '../components/IndustryToolbar.vue'
import IndustryStockCard        from '../components/IndustryStockCard.vue'
import IndustryHeatOverviewCard from '../components/IndustryHeatOverviewCard.vue'
import IndustryHotBlocksCard    from '../components/IndustryHotBlocksCard.vue'

const router = useRouter()
const { t } = useI18n()

// ── State ──────────────────────────────────────────────────────────────────
const industriesLoading = ref(false)
const industriesError   = ref('')
const industries        = ref([])
const selectedCode      = ref('')

const hotLoading = ref(false)
const hotError   = ref('')
const hotData    = ref(null)

const watchlistStatus = reactive({})
const quickSymbol     = ref('')

const filters = ref({ changeFilter: 'all', dataSourceFilter: 'all' })
const sortKey  = ref('rank')

// Hot blocks expand state
const hotBlocksExpanded = ref(false)

// ── Constants ──────────────────────────────────────────────────────────────
const PREFERRED_NAMES = ['食品饮料', '银行', '电力设备']
const MARKET    = 'CN'
const HOT_LIMIT = 20

// ── Derived ────────────────────────────────────────────────────────────────
const selectedIndustry = computed(() =>
  industries.value.find(i => i.industry_code === selectedCode.value) ?? null
)

const availableDataSources = computed(() => {
  if (!hotData.value?.items) return []
  const s = new Set(hotData.value.items.map(i => i.data_source).filter(Boolean))
  return [...s].sort()
})

// ── filteredItems (pure computed, no API call) ─────────────────────────────
const filteredItems = computed(() => {
  if (!hotData.value?.items) return []
  let list = [...hotData.value.items]

  const cf = filters.value.changeFilter
  if (cf === 'up') {
    list = list.filter(i => i.change_pct != null && Number(i.change_pct) > 0)
  } else if (cf === 'down') {
    list = list.filter(i => i.change_pct != null && Number(i.change_pct) < 0)
  } else if (cf === 'missing') {
    list = list.filter(i => i.change_pct == null)
  }

  const dsf = filters.value.dataSourceFilter
  if (dsf && dsf !== 'all') {
    list = list.filter(i => i.data_source === dsf)
  }

  const sk = sortKey.value
  list = [...list].sort((a, b) => {
    if (sk === 'rank')           return (a.rank ?? Infinity) - (b.rank ?? Infinity)
    if (sk === 'hot_score_desc') return (b.hot_score ?? -Infinity) - (a.hot_score ?? -Infinity)
    if (sk === 'change_desc')    return (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity)
    if (sk === 'change_asc')     return (a.change_pct ?? Infinity)  - (b.change_pct ?? Infinity)
    if (sk === 'amount_desc')    return (b.amount ?? -Infinity)     - (a.amount ?? -Infinity)
    if (sk === 'symbol')         return (a.symbol || '').localeCompare(b.symbol || '')
    return 0
  })

  return list
})

// ── Industry list ──────────────────────────────────────────────────────────
async function loadIndustries() {
  industriesLoading.value = true
  industriesError.value   = ''
  try {
    const list = await listIndustries(MARKET)
    industries.value = list

    let defaultInd = null
    for (const name of PREFERRED_NAMES) {
      defaultInd = list.find(ind => ind.industry_name.includes(name))
      if (defaultInd) break
    }
    if (!defaultInd && list.length) defaultInd = list[0]
    if (defaultInd) selectedCode.value = defaultInd.industry_code
  } catch (e) {
    industriesError.value = e.message || '行业列表加载失败'
  } finally {
    industriesLoading.value = false
  }
}

async function retryIndustries() {
  await loadIndustries()
  if (selectedCode.value) await loadHotStocks()
}

// ── Hot stocks ─────────────────────────────────────────────────────────────
async function loadHotStocks() {
  if (!selectedCode.value) return
  hotLoading.value = true
  hotError.value   = ''
  hotData.value    = null
  try {
    const data = await getIndustryHotStocks(MARKET, selectedCode.value, { limit: HOT_LIMIT })
    hotData.value = data
  } catch (e) {
    hotError.value = e.message || '热门股数据加载失败'
  } finally {
    hotLoading.value = false
  }
}

function onIndustryChange(code) {
  if (code === selectedCode.value) return
  selectedCode.value = code
  filters.value = { changeFilter: 'all', dataSourceFilter: 'all' }
  sortKey.value  = 'rank'
  resetWatchlistStatus()
  loadHotStocks()
}

function resetWatchlistStatus() {
  Object.keys(watchlistStatus).forEach(k => delete watchlistStatus[k])
}

// ── Navigation ─────────────────────────────────────────────────────────────
function goDetail(symbol) {
  router.push(`/stocks/${MARKET}/${symbol}`)
}

function goAnalyze(symbol) {
  router.push({ path: '/', query: { symbol, market: MARKET } })
}

function goHistory(symbol) {
  router.push({ path: '/history', query: { symbol, market: MARKET } })
}

function goDetailSelected(item) {
  router.push(`/stocks/CN/${item.symbol}`)
}

function goDetailQuick() {
  const sym = quickSymbol.value.trim()
  if (!sym) return
  router.push(`/stocks/CN/${sym}`)
}

// ── Watchlist ──────────────────────────────────────────────────────────────
async function addToWatchlist(symbol, name) {
  if (watchlistStatus[symbol] === 'added' || watchlistStatus[symbol] === 'exists') return
  watchlistStatus[symbol] = 'adding'
  try {
    await addWatchlist({ market: MARKET, symbol, name })
    watchlistStatus[symbol] = 'added'
  } catch (e) {
    const msg = e.message || ''
    if (e.status === 409 || msg.toLowerCase().includes('already') || msg.toLowerCase().includes('duplicate')) {
      watchlistStatus[symbol] = 'exists'
    } else {
      watchlistStatus[symbol] = 'error'
    }
  }
}

// ── Init ───────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadIndustries()
  await loadHotStocks()
})
</script>

<style scoped>
/* ── Title bar ── */
.ihv-title-bar { margin-bottom: 16px; }

.ihv-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}

.ihv-subtitle {
  font-size: 13px;
  color: var(--muted);
  margin: 0;
}

/* ── Hero grid: side-by-side cards ── */
.ihv-hero-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;       /* cards have their own margin from app-shell */
  /* Override: remove the gap between the two hero cards since app-shell cards have built-in margin */
}

/* ── Search card ── */
.ihv-search-card { padding: 14px 20px; }

.ihv-search-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 8px;
}

.ihv-search-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.ihv-search-box {
  flex: 1;
  min-width: 180px;
}

/* ── Stats section ── */
.ihv-stats-section { padding: 14px 20px; }

/* ── Empty / loading ── */
.ihv-empty {
  text-align: center;
  color: var(--muted);
  padding: 40px 0;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

/* ── Card list ── */
.ihv-card-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── Mobile ── */
@media (max-width: 640px) {
  /* Stack hero cards vertically on mobile */
  .ihv-hero-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .ihv-title    { font-size: 18px; }
  .ihv-subtitle { font-size: 12px; }

  .ihv-search-row {
    flex-direction: column;
    align-items: stretch;
  }

  .ihv-search-box { width: 100%; }
  .ihv-search-row .btn { width: 100%; }
}

@media (max-width: 375px) {
  .ihv-title-bar { margin-bottom: 12px; }
}
</style>
