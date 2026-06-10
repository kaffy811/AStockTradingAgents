<template>
  <div class="app-shell">
    <AppHeader />

    <div class="stock-detail-page">
      <!-- Back button -->
      <button class="back-btn" @click="goBack">← 返回</button>

      <!-- ── 1. 综合仪表盘 ─────────────────────────────────────────────────── -->
      <StockDashboardPanel
        :market="market"
        :symbol="symbol"
        :stock-name="stockName"
        :profile="profile"
        :quote-price="dashboardQuotePrice"
        :quote-change-text="quoteChangeText"
        :quote-change-class="quoteChangeClass"
        :quote-error="quoteError"
        :technical-insight="technicalInsight"
        :news-items="newsItems"
        :latest-report="latestReport"
        :loading="identityLoading"
        :in-watchlist="!!watchlistItemId"
        :watchlist-loading="watchlistLoading"
        :compare-status="compareStatus"
        @analyze="goAnalyze"
        @view-report="onDashboardViewReport"
        @toggle-watchlist="toggleWatchlist"
        @add-to-compare="handleAddToCompare"
        @go-compare="handleGoCompare"
        @scroll-to="scrollToSection"
      />

      <!-- ── 2. K 线图区 ─────────────────────────────────────────────────────── -->
      <div id="section-chart" class="kline-info-bar">
        <span class="kline-title">K 线走势</span>
        <span class="kline-hint">可切换区间、均线与成交量指标</span>
      </div>
      <section class="card chart-section">
        <TechnicalChartPanel
          v-if="market && symbol"
          :market="market"
          :symbol="symbol"
          :height="300"
          @insight-data="onInsightData"
        />
      </section>

      <!-- ── 3. 技术面解读 ─────────────────────────────────────────────────── -->
      <section id="section-insight" class="card">
        <TechnicalInsightCard
          :insight="technicalInsight"
          :loading="technicalInsightLoading"
        />
      </section>

      <!-- ── 4. 相关新闻区 ──────────────────────────────────────────────────── -->
      <section id="section-news" class="card">
        <NewsTimelinePanel
          :news-items="newsItems"
          :loading="newsLoading"
          :error="newsError"
          :hours="72"
          @retry="loadNews"
        />
      </section>

      <!-- ── 5. 本 APP 研究结论区 ──────────────────────────────────────────── -->
      <section id="section-research" class="card">
        <StockDetailResearchPanel
          :market="market"
          :symbol="symbol"
          :stock-name="stockName"
          :latest-report="latestReport"
          :latest-full-report="latestFullReport"
          :full-report-loading="fullReportLoading"
          :summary-excerpt="reportExcerpt"
          :loading="reportsLoading"
        />
      </section>

      <!-- ── 6. 历史报告栏 ──────────────────────────────────────────────────── -->
      <section id="section-history" class="card">
        <div class="card-title">历史报告</div>

        <div v-if="reportsLoading" class="state-row">
          <span class="spinner"></span>
          <span class="state-text">加载历史报告…</span>
        </div>
        <EmptyState
          v-else-if="reports.length === 0"
          icon="📋"
          title="暂无该股票的分析报告"
          message="暂无该股票的分析报告，可前往综合分析页生成。"
          action-text="前往综合分析页"
          :compact="true"
          @action="goAnalyze"
        />
        <div v-else class="report-list">
          <div
            v-for="rep in reports"
            :key="rep.id"
            class="report-row"
            @click="goReport(rep.id)"
          >
            <div class="report-row-left">
              <span :class="['report-type-badge', rep.analysis_scope !== 'comprehensive' && rep.analysis_scope ? 'badge-partial' : '']">
                {{ scopeLabel(rep.analysis_scope) }}
              </span>
              <span v-if="rep.auto_saved" class="auto-saved-mini">自动保存</span>
              <span class="report-name">{{ rep.stock_name || rep.symbol }}</span>
              <span class="report-date">{{ formatTime(rep.created_at) }}</span>
            </div>
            <span class="report-arrow">›</span>
          </div>
        </div>
        <div v-if="!reportsLoading && reports.length >= 5" class="report-more">
          <button class="btn btn-secondary btn-sm" @click="goHistory">
            查看全部历史报告
          </button>
        </div>
      </section>

      <!-- ── 7. 同行业热门股票栏 ────────────────────────────────────────────── -->
      <section id="section-peers" class="card">
        <div class="card-title">同行业热门股票</div>

        <div v-if="hotLoading" class="state-row">
          <span class="spinner"></span>
          <span class="state-text">加载热门股…</span>
        </div>
        <EmptyState
          v-else-if="market !== 'CN'"
          icon="🌏"
          title="当前市场暂不支持行业热门股"
          message="港股暂不使用申万行业体系，行业热门股数据不适用。"
          :compact="true"
        />
        <EmptyState
          v-else-if="!industryCode"
          icon="📊"
          title="暂无行业分类信息"
          message="该股票暂无申万行业分类数据，无法展示同行业热门股。"
          :compact="true"
        />
        <EmptyState
          v-else-if="hotStocks.length === 0"
          icon="📊"
          title="暂无热门股快照"
          message="该行业暂无热门股数据，请稍后重试或运行行业数据刷新脚本。"
          :compact="true"
        />
        <div v-else class="hot-stocks">
          <div v-if="industryName" class="hot-industry-label">
            申万一级行业：{{ industryName }}
          </div>
          <div
            v-for="s in hotStocks"
            :key="s.symbol"
            :class="['hot-stock-row', s.symbol === symbol ? 'hs-current-row' : '']"
            @click="s.symbol !== symbol && goDetail(s)"
          >
            <div class="hs-left">
              <span class="hs-rank">{{ s.rank }}</span>
              <div class="hs-info">
                <span class="hs-name">
                  {{ s.stock_name || s.symbol }}
                  <span v-if="s.symbol === symbol" class="hs-current-badge">当前</span>
                </span>
                <span class="hs-symbol">{{ s.symbol }}</span>
              </div>
            </div>
            <div class="hs-right">
              <span :class="['hs-change', changePctClass(s.change_pct)]">
                {{ formatChangePct(s.change_pct) }}
              </span>
              <span class="hs-amount">{{ formatAmount(s.amount) }}</span>
              <span class="hs-score">热度 {{ s.hot_score != null ? s.hot_score.toFixed(1) : '—' }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { searchStocks, getStockQuote, getStockNews, getStockProfile } from '../api/stocks.js'
import { listReports, getReport } from '../api/reports.js'
import { listWatchlist, addWatchlist, deleteWatchlist } from '../api/watchlist.js'
import { getStockIndustry, getIndustryHotStocks } from '../api/industries.js'
import { addRecentSearch } from '../utils/recentSearches.js'
import {
  getCompareList,
  addCompareStock,
  buildCompareQuery,
} from '../utils/compareStorage.js'
import { formatAmount, formatVolume } from '../utils/marketFormat.js'
import AppHeader                from '../components/AppHeader.vue'
import StockDashboardPanel      from '../components/StockDashboardPanel.vue'
import TechnicalChartPanel      from '../components/TechnicalChartPanel.vue'
import TechnicalInsightCard     from '../components/TechnicalInsightCard.vue'
import NewsTimelinePanel        from '../components/NewsTimelinePanel.vue'
import DataQualitySummary       from '../components/DataQualitySummary.vue'
import EmptyState               from '../components/EmptyState.vue'
import StockDetailResearchPanel from '../components/StockDetailResearchPanel.vue'
import { buildTechnicalInsightSummary } from '../utils/technicalInsights.js'

const route  = useRoute()
const router = useRouter()

// ── Route params ──────────────────────────────────────────────────────────────
const market = computed(() => (route.params.market || '').toUpperCase())
const symbol = computed(() => route.params.symbol || '')

// ── Profile (首屏聚合) ────────────────────────────────────────────────────────
const profile         = ref(null)    // StockProfileResponse | null
const profileLoading  = ref(true)    // drives identity-card skeleton

// ── Identity / quote ──────────────────────────────────────────────────────────
const stockName       = ref('')
const quote           = ref(null)
const quoteError      = ref(false)
const identityLoading = computed(() => profileLoading.value)

// ── Industry ──────────────────────────────────────────────────────────────────
const industryCode = ref('')
const industryName = ref('')

// ── News ──────────────────────────────────────────────────────────────────────
const newsItems   = ref([])
const newsLoading = ref(true)
const newsError   = ref('')

// ── Reports ───────────────────────────────────────────────────────────────────
const reports         = ref([])
const reportsLoading  = ref(true)
const latestReport    = ref(null)
const latestFullReport = ref(null)
const fullReportLoading = ref(false)

// ── Hot stocks ────────────────────────────────────────────────────────────────
const hotStocks  = ref([])
const hotLoading = ref(false)

// ── Technical insight (M12) ───────────────────────────────────────────────────
const technicalInsight        = ref(null)
const technicalInsightLoading = ref(false)

// ── Watchlist ─────────────────────────────────────────────────────────────────
const watchlistItemId = ref(null)   // null = not in list, string = item id
const watchlistLoading = ref(false)

// ── Compare ───────────────────────────────────────────────────────────────────
// '' | 'in_list' | 'added' | 'full'
const compareStatus = ref('')
let _compareTimer = null

function _refreshCompareStatus() {
  const list = getCompareList()
  const key = `${market.value}:${symbol.value}`
  if (list.some(i => `${i.market}:${i.symbol}` === key)) {
    compareStatus.value = 'in_list'
  } else if (list.length >= 4) {
    compareStatus.value = 'full'
  } else {
    compareStatus.value = ''
  }
}

function handleAddToCompare() {
  const result = addCompareStock({
    market: market.value,
    symbol: symbol.value,
    stock_name: stockName.value || symbol.value,
  })
  if (result.ok) {
    compareStatus.value = 'added'
  } else if (result.reason === 'duplicate') {
    compareStatus.value = 'in_list'
  } else {
    compareStatus.value = 'full'
  }
  // Reset to neutral after 2.5s (unless it's genuinely in_list)
  clearTimeout(_compareTimer)
  _compareTimer = setTimeout(() => {
    _refreshCompareStatus()
  }, 2500)
}

function handleGoCompare() {
  const list = getCompareList()
  if (list.length === 0) {
    // Auto-add current stock first
    addCompareStock({
      market: market.value,
      symbol: symbol.value,
      stock_name: stockName.value || symbol.value,
    })
  }
  const latestList = getCompareList()
  router.push({ path: '/compare', query: { stocks: buildCompareQuery(latestList) } })
}

// ── Quote computed helpers ────────────────────────────────────────────────────
// Unified quote data: prefer profile.quote, fall back to old quote.data dict
const _quoteData = computed(() => {
  if (profile.value?.quote?.status === 'success') {
    return profile.value.quote
  }
  // Fallback shape from direct getStockQuote call
  const d = quote.value?.data
  if (!d) return null
  return {
    latest_price: d.price ?? d.current_price ?? d.close,
    change_pct:   d.change_pct ?? d.change_percent,
  }
})

const quoteChangeClass = computed(() => {
  const pct = _quoteData.value?.change_pct
  if (pct == null) return ''
  return pct > 0 ? 'up' : pct < 0 ? 'dn' : ''
})

const quoteChangeText = computed(() => {
  const pct = _quoteData.value?.change_pct
  if (pct == null) return ''
  return (pct > 0 ? '+' : '') + Number(pct).toFixed(2) + '%'
})

// ── Watchlist computed helpers ────────────────────────────────────────────────
const watchlistBtnText = computed(() => {
  if (watchlistLoading.value) return '处理中…'
  return watchlistItemId.value ? '★ 已在自选' : '☆ 加入自选'
})

const watchlistBtnClass = computed(() => {
  return watchlistItemId.value ? 'btn-watchlist-on' : 'btn-secondary'
})

// ── Report excerpt ────────────────────────────────────────────────────────────
const reportExcerpt = computed(() => {
  // Prefer backend-computed summary_excerpt from profile (reduces one extra getReport call)
  if (profile.value?.latest_report?.summary_excerpt) {
    return profile.value.latest_report.summary_excerpt
  }
  // Fallback: extract from full report if loaded for DataQualitySummary
  if (!latestFullReport.value?.report) return ''
  const text = latestFullReport.value.report.replace(/#{1,6}\s/g, '').replace(/[*_`]/g, '')
  return text.slice(0, 280).trimEnd() + (text.length > 280 ? '…' : '')
})

// ── Data loading ──────────────────────────────────────────────────────────────

/**
 * Primary loader: GET /stocks/{market}/{symbol}/profile
 * Populates: stockName, quote, industryCode, industryName, watchlistItemId
 * Falls back to _loadIdentityFallback + loadWatchlist on error.
 */
async function loadProfile() {
  profileLoading.value = true
  profile.value        = null
  stockName.value      = ''
  quote.value          = null
  quoteError.value     = false
  industryCode.value   = ''
  industryName.value   = ''
  watchlistItemId.value = null

  const m = market.value
  const s = symbol.value
  if (!m || !s) { profileLoading.value = false; return }

  try {
    const p = await getStockProfile(m, s)
    profile.value = p

    stockName.value = p.stock_name || ''

    // Quote
    if (p.quote?.status === 'success') {
      quoteError.value = false
      // Keep quote.value null — template reads from _quoteData computed
    } else {
      quoteError.value = true
    }

    // Industry
    if (p.industry) {
      industryCode.value = p.industry.industry_code || ''
      industryName.value = p.industry.industry_name || ''
    }

    // Watchlist
    watchlistItemId.value = p.watchlist?.in_watchlist
      ? (p.watchlist.watchlist_id || 'added')
      : null

    addRecentSearch({ market: m, symbol: s, stock_name: stockName.value })
  } catch (_) {
    // Profile unavailable — fall back to individual requests
    await _loadIdentityFallback()
    await loadWatchlist()
  } finally {
    profileLoading.value = false
  }
}

/** Fallback identity loader (original logic). Used when profile fails. */
async function _loadIdentityFallback() {
  const m = market.value
  const s = symbol.value
  if (!m || !s) return

  const [searchRes, quoteRes] = await Promise.allSettled([
    searchStocks(m, s, 3),
    getStockQuote(m, s),
  ])

  if (searchRes.status === 'fulfilled') {
    const hit = searchRes.value?.items?.find(
      i => i.symbol === s || i.symbol === s.replace(/^0+/, '') || i.symbol.endsWith(s)
    ) || searchRes.value?.items?.[0]
    stockName.value = hit?.name || ''
  }

  if (quoteRes.status === 'fulfilled') {
    quote.value = quoteRes.value
  } else {
    quoteError.value = true
  }

  addRecentSearch({ market: m, symbol: s, stock_name: stockName.value })
}

async function loadNews() {
  newsLoading.value = true
  newsError.value   = ''
  newsItems.value   = []
  const m = market.value
  const s = symbol.value
  if (!m || !s) { newsLoading.value = false; return }
  try {
    const res = await getStockNews(m, s, { hours_back: 72, limit: 20 })
    // Sort by publish_time desc (newest first)
    const sorted = (res.items || []).slice().sort((a, b) => {
      const ta = a.publish_time ? new Date(a.publish_time).getTime() : 0
      const tb = b.publish_time ? new Date(b.publish_time).getTime() : 0
      return tb - ta
    })
    newsItems.value = sorted
  } catch (e) {
    newsError.value = e.message || '新闻加载失败'
  } finally {
    newsLoading.value = false
  }
}

async function loadReports() {
  reportsLoading.value  = true
  reports.value         = []
  latestReport.value    = null
  latestFullReport.value = null
  const m = market.value
  const s = symbol.value
  if (!m || !s) { reportsLoading.value = false; return }
  try {
    const res = await listReports({ market: m, symbol: s, limit: 5 })
    reports.value = res.items || []
    latestReport.value = reports.value[0] || null
  } catch (e) {
    // silent — section shows EmptyState
  } finally {
    reportsLoading.value = false
  }

  // Load full report for DataQualitySummary (sequential, non-blocking for rest of page)
  if (latestReport.value) {
    fullReportLoading.value = true
    try {
      latestFullReport.value = await getReport(latestReport.value.id)
    } catch (e) {
      // DataQualitySummary won't show, rest of section still renders
    } finally {
      fullReportLoading.value = false
    }
  }
}

/**
 * Load hot stocks for the peer panel.
 * industryCode must already be populated (by loadProfile or _loadIndustryFallback).
 */
async function loadHotStocks() {
  hotStocks.value  = []
  const m = market.value
  if (!m || m !== 'CN') return   // HK: no Shenwan hot stocks
  if (!industryCode.value) return

  hotLoading.value = true
  try {
    const hotRes = await getIndustryHotStocks(m, industryCode.value, { limit: 5 })
    hotStocks.value = hotRes.items || []
  } catch (_) {
    // EmptyState shown
  } finally {
    hotLoading.value = false
  }
}

/** Fallback industry loader when profile did not provide industry info. */
async function _loadIndustryFallback() {
  const m = market.value
  const s = symbol.value
  if (!m || !s || m !== 'CN') return

  try {
    const res = await getStockIndustry(m, s)
    industryCode.value = res.industry_code || ''
    industryName.value = res.industry_name || ''
  } catch (_) {
    // Not found — industryCode stays ''
  }
}

async function loadWatchlist() {
  watchlistItemId.value = null
  const m = market.value
  const s = symbol.value
  if (!m || !s) return
  try {
    const res = await listWatchlist()
    const found = (res.items || []).find(i => i.market === m && i.symbol === s)
    watchlistItemId.value = found?.id || null
  } catch (e) {
    // silent — watchlist btn stays "加入自选"
  }
}

async function loadAll() {
  const m = market.value
  const s = symbol.value
  if (!m || !s) return

  _refreshCompareStatus()
  hotStocks.value  = []
  hotLoading.value = false

  // Reset technical insight — TechnicalChartPanel will emit once kline loads
  technicalInsight.value        = null
  technicalInsightLoading.value = true

  // Phase 1: profile (provides identity + quote + industry + watchlist)
  // News and reports run in parallel — they don't depend on profile data.
  await Promise.allSettled([
    loadProfile().then(async () => {
      // If profile didn't provide industry (fallback path or HK), try explicitly
      if (!industryCode.value && m === 'CN') {
        await _loadIndustryFallback()
      }
      // Hot stocks need industryCode — run after profile resolves
      await loadHotStocks()
    }),
    loadNews(),
    loadReports(),
  ])
}

// ── Dashboard helpers (M14) ───────────────────────────────────────────────────

// Formatted price string for StockDashboardPanel prop
const dashboardQuotePrice = computed(() => {
  const v = _quoteData.value?.latest_price
          ?? _quoteData.value?.price
          ?? _quoteData.value?.current_price
          ?? _quoteData.value?.close
  if (v == null || !Number.isFinite(Number(v))) return ''
  return Number(v).toFixed(2)
})

// View report from dashboard: go to report if exists, else scroll to research
function onDashboardViewReport() {
  if (latestReport.value) {
    goReport(latestReport.value.id)
  } else {
    scrollToSection('research')
  }
}

// Smooth-scroll to a named section (id="section-{name}")
function scrollToSection(name) {
  const el = document.getElementById(`section-${name}`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ── Technical insight handler (M12) ──────────────────────────────────────────
function onInsightData(payload) {
  technicalInsightLoading.value = false
  if (payload.error || payload.empty) {
    technicalInsight.value = null
    return
  }
  technicalInsight.value = buildTechnicalInsightSummary({
    klineData: payload.klineData,
    maData:    payload.maData,
    macdData:  payload.macdData,
    rsiData:   payload.rsiData,
  })
}

// Re-run when route params change (navigating between stock detail pages)
watch(
  () => [route.params.market, route.params.symbol],
  () => loadAll(),
  { immediate: true },
)

// ── Watchlist toggle ──────────────────────────────────────────────────────────
async function toggleWatchlist() {
  if (watchlistLoading.value) return
  watchlistLoading.value = true
  try {
    if (watchlistItemId.value) {
      // Remove — use profile's watchlist_id if available (avoids 'added' sentinel)
      const idToDelete = (profile.value?.watchlist?.watchlist_id) || watchlistItemId.value
      if (idToDelete && idToDelete !== 'added') {
        await deleteWatchlist(idToDelete)
      }
      watchlistItemId.value = null
      // Keep profile.watchlist in sync
      if (profile.value?.watchlist) {
        profile.value.watchlist.in_watchlist = false
        profile.value.watchlist.watchlist_id = null
      }
    } else {
      // Add
      const body = { market: market.value, symbol: symbol.value }
      if (stockName.value) body.name = stockName.value
      const res = await addWatchlist(body)
      const newId = res?.id || null
      watchlistItemId.value = newId || 'added'
      // Keep profile.watchlist in sync
      if (profile.value) {
        if (!profile.value.watchlist) profile.value.watchlist = {}
        profile.value.watchlist.in_watchlist = true
        profile.value.watchlist.watchlist_id = newId ? String(newId) : null
      }
    }
  } catch (e) {
    if (e.status === 409) {
      // Already in watchlist — re-fetch watchlist to get real id
      await loadWatchlist()
      // Sync back to profile
      if (profile.value?.watchlist && watchlistItemId.value) {
        profile.value.watchlist.in_watchlist = true
        profile.value.watchlist.watchlist_id = String(watchlistItemId.value)
      }
    }
    // Other errors: silent, state unchanged
  } finally {
    watchlistLoading.value = false
  }
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}

function goAnalyze() {
  router.push({ path: '/', query: { market: market.value, symbol: symbol.value } })
}

function goReport(id) {
  router.push(`/history/${id}`)
}

function goHistory() {
  router.push({ path: '/history', query: { market: market.value, symbol: symbol.value } })
}

function goDetail(stock) {
  router.push(`/stocks/${stock.market || market.value}/${stock.symbol}`)
}

// ── Formatters ────────────────────────────────────────────────────────────────
function formatPrice(val) {
  if (val == null || !Number.isFinite(Number(val))) return '—'
  return Number(val).toFixed(2)
}

function formatChangePct(pct) {
  if (pct == null || !Number.isFinite(pct)) return '—'
  return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'
}

function changePctClass(pct) {
  if (pct == null || !Number.isFinite(pct)) return ''
  return pct > 0 ? 'up' : pct < 0 ? 'dn' : ''
}

function formatNewsTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return ts }
}

function formatTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return ts }
}

function reportTypeLabel(type) {
  const MAP = { comprehensive: '综合', technical: '技术面', fundamental: '基本面', peer_comparison: '同行', news: '新闻' }
  return MAP[type] || type
}

const _SCOPE_LABELS = {
  comprehensive:         '综合分析',
  technical_only:        '技术面',
  fundamental_only:      '基本面',
  peer_only:             '同行对比',
  news_only:             '新闻面',
  technical_fundamental: '技术+基本面',
}

function scopeLabel(scope) {
  return _SCOPE_LABELS[scope] || (scope || '综合分析')
}
</script>

<style scoped>
.stock-detail-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 0 16px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Back button ── */
.back-btn {
  align-self: flex-start;
  background: none;
  border: none;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 0;
  transition: color 0.15s;
}
.back-btn:hover { color: var(--accent); }

/* ── K-line info bar ── */
.kline-info-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 6px 4px;
}

.kline-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.kline-hint {
  font-size: 11px;
  color: var(--muted);
}

/* ── Chart section — remove double padding since TechnicalChartPanel adds .card ── */
.chart-section {
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
}

/* ── State row ── */
.state-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  color: var(--muted);
  font-size: 13px;
}

.state-row--sm { padding: 6px 0; }

.state-text { color: var(--muted); font-size: 13px; }

.spinner--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
}

/* ── History reports ── */
.report-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.report-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.12s;
  border-radius: 4px;
  padding-left: 6px;
  padding-right: 6px;
}

.report-row:last-child { border-bottom: none; }

.report-row:hover { background: var(--surface2); }

.report-row-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.report-type-badge {
  font-size: 11px;
  font-weight: 600;
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 1px 7px;
  white-space: nowrap;
  border: 1px solid var(--status-info-ring);
}

.report-type-badge.badge-partial {
  background: var(--surface2);
  color: var(--muted);
  border-color: var(--border);
}

.auto-saved-mini {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 5px;
}

.report-name {
  font-size: 13px;
  color: var(--text);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}

.report-date {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.report-arrow {
  color: var(--muted);
  font-size: 16px;
  flex-shrink: 0;
}

.report-more {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: center;
}

/* ── Hot stocks ── */
.hot-industry-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
}

.hot-stocks {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.hot-stock-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 6px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s;
}

.hot-stock-row:last-child { border-bottom: none; }
.hot-stock-row:hover { background: var(--surface2); }

.hs-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.hs-rank {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  width: 18px;
  text-align: center;
  flex-shrink: 0;
}

.hs-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.hs-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

.hs-symbol {
  font-size: 11px;
  color: var(--muted);
  font-family: monospace;
}

.hs-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  flex-shrink: 0;
}

.hs-change {
  font-size: 13px;
  font-weight: 600;
}

.hs-amount {
  font-size: 11px;
  color: var(--muted);
}

.hs-score {
  font-size: 11px;
  color: var(--muted);
}

.hs-current-row {
  background: var(--surface-hover);
  cursor: default;
}

.hs-current-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  background: var(--status-info-bg);
  border-radius: 3px;
  padding: 0 4px;
  margin-left: 4px;
  vertical-align: middle;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .stock-detail-page { padding: 0 10px 32px; gap: 12px; }

  .report-name { max-width: 80px; }
  .hs-name     { max-width: 90px; }
}
</style>
