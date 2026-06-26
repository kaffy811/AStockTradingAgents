<template>
  <div class="app-shell">
    <AppHeader />

    <!-- Hero panel: product orientation; hidden once analysis starts or result exists -->
    <HomeHeroPanel v-if="!result && !loading" />

    <!-- Dashboard: shown when idle and no result -->
    <HomeDashboardPanel
      v-if="!result && !loading"
      :recent-reports="dashRecentReports"
      :watchlist-items="dashWatchlistItems"
      :recent-searches="dashRecentSearches"
      :hot-items="dashHotItems"
      :industry-name="dashIndustryName"
      :industry-list="dashIndustryList"
      :industry-list-error="dashIndustryListError"
      :compare-list="dashCompareList"
      :loading="dashboardLoading"
      @pick-stock="onDashPickStock"
      @go-report="onDashGoReport"
      @go-stock="onDashGoStock"
      @go-history="onDashGoHistory"
      @go-watchlist="onDashGoWatchlist"
      @go-watchlist-compare="onDashGoWatchlistCompare"
      @go-industries="onDashGoIndustries"
      @go-industry-block="onDashGoIndustryBlock"
      @go-compare="onDashGoCompare"
    />

    <!-- Recent searches: shown only when idle and no result -->
    <RecentSearchList
      v-if="!result && !loading"
      @pick="onRecentSearchPick"
    />

    <StockInputPanel
      ref="stockInputRef"
      :loading="loading"
      :initial-market="initMarket"
      :initial-symbol="initSymbol"
      :show-guide="showFirstGuide"
      @analyze="handleAnalyze"
      @change="handleFormChange"
      @focus-input="dismissGuide"
    />

    <!-- Analysis mode selector: below StockInputPanel, before identity card -->
    <AnalysisModeSelector v-model="analysisScope" />

    <!-- Engine selector: dev mode only (import.meta.env.DEV or localStorage dev_mode) -->
    <EngineSelector v-if="showEngineSelector" v-model="analysisEngine" />

    <!-- Stock identity confirmation card -->
    <StockIdentityCard
      v-if="currentSymbol.trim() && !loading"
      :market="currentMarket"
      :symbol="currentSymbol.trim()"
      @identity="handleIdentity"
    />

    <!-- Discovery panel: always open when no result; collapsible when result exists -->
    <div v-if="result && !discoveryOpen" class="discovery-toggle">
      <button class="btn btn-secondary btn-sm" @click="discoveryOpen = true">
        {{ t('analysis_expand_discovery') }}
      </button>
    </div>
    <DiscoveryPanel
      v-if="!result || discoveryOpen"
      @pick="handlePick"
    />

    <!-- About panel: product info; hidden once analysis starts or result exists -->
    <AboutProductPanel v-if="!result && !loading" />

    <AnalysisProgressPanel
      v-if="loading"
      :market="currentMarket"
      :symbol="currentSymbol.trim()"
      :stock-name="currentStockName"
      :started-at="analysisStartedAt"
      :loading="loading"
      :analysis-scope="analysisScope"
      :mode="_progressMode"
      :progress="realtimeProgress"
      :agent-statuses="agentStatuses"
      :latest-event="latestEvent"
      @cancel="cancelAnalysis"
    />
    <!-- Dev mode: SSE event log -->
    <AnalysisEventTimeline
      v-if="loading && showEngineSelector && realtimeEvents.length > 0"
      :events="realtimeEvents"
      @clear="realtimeEvents = []"
    />
    <ErrorBox :message="errorMsg" />
    <p v-if="errorMsg" class="error-retry-hint">
      {{ t('analysis_error_incomplete') }}
    </p>

    <template v-if="result">
      <AnalysisResultLayout
        :result="result"
        :saved="saveStatus === 'saved'"
        :saving="saveStatus === 'saving'"
        @save="handleSave"
        @reanalyze="handleReanalyze"
        @new-analysis="handleNewAnalysis"
      >
        <template #actions>
          <!-- Save status text -->
          <span v-if="saveStatus === 'saved'" class="save-status save-status--ok">
            ✓ {{ t('analysis_saved') }} &nbsp;
            <RouterLink :to="`/history/${savedReportId}`" class="view-link">{{ t('analysis_view') }}</RouterLink>
          </span>
          <span v-else-if="saveStatus === 'error'" class="save-status save-status--err">
            {{ t('analysis_save_failed') }}{{ saveError }}
          </span>

          <DownloadMenu :result="result" />

          <button
            class="btn btn-secondary btn-sm"
            :disabled="saveStatus === 'saving' || saveStatus === 'saved'"
            @click="handleSave"
          >
            <span v-if="saveStatus === 'saving'" class="spinner"></span>
            {{ saveStatus === 'saving' ? t('analysis_saving')
             : saveStatus === 'saved'  ? t('analysis_saved')
             : t('analysis_save_report') }}
          </button>
        </template>
      </AnalysisResultLayout>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  runComprehensiveAnalysisV2,
  createAnalysisRun,
  getAnalysisRun,
  subscribeAnalysisEvents,
  cancelAnalysisRun,
} from '../api/analysis.js'
import { createReport, listReports }  from '../api/reports.js'
import { getWatchlistEnriched }       from '../api/watchlist.js'
import { listIndustries, getIndustryHotStocks } from '../api/industries.js'
import { addRecentSearch, getRecentSearches } from '../utils/recentSearches.js'
import { getSettings, SETTINGS_EVENT } from '../utils/settings.js'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()
import { getCompareList, buildCompareQuery } from '../utils/compareStorage.js'
import AppHeader              from '../components/AppHeader.vue'
import HomeHeroPanel          from '../components/HomeHeroPanel.vue'
import HomeDashboardPanel     from '../components/HomeDashboardPanel.vue'
import AboutProductPanel      from '../components/AboutProductPanel.vue'
import StockInputPanel        from '../components/StockInputPanel.vue'
import StockIdentityCard      from '../components/StockIdentityCard.vue'
import DiscoveryPanel         from '../components/DiscoveryPanel.vue'
import AnalysisProgressPanel  from '../components/AnalysisProgressPanel.vue'
import ErrorBox               from '../components/ErrorBox.vue'
import DownloadMenu           from '../components/DownloadMenu.vue'
import AnalysisResultLayout   from '../components/AnalysisResultLayout.vue'
import RecentSearchList       from '../components/RecentSearchList.vue'
import AnalysisModeSelector   from '../components/AnalysisModeSelector.vue'
import EngineSelector             from '../components/EngineSelector.vue'
import AnalysisEventTimeline     from '../components/AnalysisEventTimeline.vue'

// Required for <keep-alive :include="['ComprehensiveAnalysisView']"> in App.vue
defineOptions({ name: 'ComprehensiveAnalysisView' })

// ── Router ────────────────────────────────────────────────────────────────────
const router = useRouter()

// ── User settings ─────────────────────────────────────────────────────────────
// Read once at startup; re-read when ProfileView saves changes.
const _settings = getSettings()

// ── Route query → StockInputPanel auto-fill ──────────────────────────────────
// Must use watch (not onMounted) because keep-alive caches this component;
// setup() won't re-run on re-activation, but route.query changes will fire the watcher.
const route       = useRoute()
const initMarket  = ref(route.query.market || _settings.default_market || 'CN')
const initSymbol  = ref(route.query.symbol || '')

watch(
  () => route.query,
  (q) => {
    initMarket.value   = q.market || 'CN'
    initSymbol.value   = q.symbol || ''
    // Keep identity card in sync when navigating via URL
    currentMarket.value = q.market || 'CN'
    currentSymbol.value = q.symbol || ''
    // Fill scope from query when provided (e.g. reanalyze from HistoryDetailView)
    if (_VALID_SCOPES.has(q.scope)) {
      analysisScope.value = q.scope
    }
  },
)

// ── Current form state (for StockIdentityCard + AnalysisProgressPanel) ─────────
const currentMarket    = ref(route.query.market || _settings.default_market || 'CN')
const currentSymbol    = ref(route.query.symbol || '')
const currentStockName = ref('')   // filled by StockIdentityCard via @identity event

function handleFormChange({ market, symbol }) {
  currentMarket.value = market
  currentSymbol.value = symbol
  currentStockName.value = ''  // reset name on form change; card will re-resolve
}

function handleIdentity(name) {
  currentStockName.value = name || ''
}

// ── StockInputPanel ref (for fill() calls from DiscoveryPanel) ──────────────
const stockInputRef = ref(null)

// ── First-time guide ─────────────────────────────────────────────────────────
const _GUIDE_KEY   = 'tradingagents:first_analysis_hint_seen'
const showFirstGuide = ref(false)
let _guideTimer = null

function _initGuide() {
  if (!localStorage.getItem(_GUIDE_KEY)) {
    showFirstGuide.value = true
    _guideTimer = setTimeout(dismissGuide, 8000)
  }
}

function dismissGuide() {
  if (!showFirstGuide.value) return
  showFirstGuide.value = false
  if (_guideTimer) { clearTimeout(_guideTimer); _guideTimer = null }
  try { localStorage.setItem(_GUIDE_KEY, '1') } catch { /* ignore */ }
}

// ── Discovery panel ──────────────────────────────────────────────────────────
const discoveryOpen = ref(true)

function handlePick({ market, symbol }) {
  stockInputRef.value?.fill(market, symbol)
}

function onRecentSearchPick({ market, symbol }) {
  stockInputRef.value?.fill(market, symbol)
}

// ── Dashboard data ────────────────────────────────────────────────────────────
const dashboardLoading    = ref(false)
const dashRecentReports   = ref([])
const dashWatchlistItems  = ref([])
const dashRecentSearches  = ref(getRecentSearches())
const dashHotItems        = ref([])
const dashIndustryName    = ref('')
const dashIndustryList      = ref([])
const dashIndustryListError = ref('')
const dashCompareList       = ref(getCompareList())

async function loadDashboardData() {
  dashboardLoading.value = true
  // Recent searches and compare list are synchronous localStorage reads
  dashRecentSearches.value = getRecentSearches()
  dashCompareList.value    = getCompareList()

  const [reportsRes, watchlistRes, industriesRes] = await Promise.allSettled([
    listReports({ limit: 5 }),
    getWatchlistEnriched(),
    listIndustries('CN'),
  ])

  if (reportsRes.status === 'fulfilled') {
    dashRecentReports.value = (reportsRes.value?.items || reportsRes.value || []).slice(0, 5)
  }
  if (watchlistRes.status === 'fulfilled') {
    dashWatchlistItems.value = (watchlistRes.value?.items || watchlistRes.value || []).slice(0, 4)
  }

  // Load industry list sorted by hot_score desc; pick the first for hot stocks
  if (industriesRes.status === 'fulfilled') {
    dashIndustryListError.value = ''
    const industries = industriesRes.value || []
    // Sort by hot_score descending for the industry blocks panel
    const sorted = [...industries].sort((a, b) => (b.hot_score ?? 0) - (a.hot_score ?? 0))
    dashIndustryList.value = sorted.slice(0, 6)

    const first = sorted[0] || industries[0]
    if (first) {
      dashIndustryName.value = first.industry_name || first.name || ''
      try {
        const hotData = await getIndustryHotStocks('CN', first.industry_code || first.code, { limit: 20 })
        dashHotItems.value = (hotData?.items || []).slice(0, 20)
      } catch { /* non-fatal */ }
    }
  } else {
    dashIndustryListError.value = industriesRes.reason?.message || '行业数据加载失败'
  }

  dashboardLoading.value = false
}

// ── Dashboard event handlers ──────────────────────────────────────────────────
function onDashPickStock({ market, symbol }) {
  stockInputRef.value?.fill(market, symbol)
}

function onDashGoReport(rep) {
  router.push(`/history/${rep.id}`)
}

function onDashGoStock({ market, symbol }) {
  router.push(`/stocks/${market}/${symbol}`)
}

function onDashGoHistory() {
  router.push('/history')
}

function onDashGoWatchlist() {
  router.push('/watchlist')
}

function onDashGoWatchlistCompare() {
  router.push('/watchlist?mode=compare')
}

function onDashGoIndustries() {
  router.push('/industries')
}

function onDashGoIndustryBlock(ind) {
  const code = ind.industry_code || ind.code
  router.push(code ? { path: '/industries', query: { focus: code } } : '/industries')
}

function onDashGoCompare() {
  const list = getCompareList()
  if (list.length > 0) {
    router.push({ path: '/compare', query: { stocks: buildCompareQuery(list) } })
  } else {
    router.push('/compare')
  }
}

// ── Analysis scope (from route.query.scope, else settings default) ────────────
const _VALID_SCOPES = new Set([
  'comprehensive', 'technical_only', 'fundamental_only',
  'peer_only', 'news_only', 'technical_fundamental',
])

const _initScope = _VALID_SCOPES.has(route.query.scope)
  ? route.query.scope
  : (_settings.default_analysis_scope || 'comprehensive')
const analysisScope = ref(_initScope)

// report output language — separate from UI language
const reportLanguage = ref(_settings.report_language || 'zh-CN')

// ── Engine selector (dev mode only) ─────────────────────────────────────────
// Visible only in local dev build (import.meta.env.DEV) OR when
// localStorage tradingagents:dev_mode = "true" has been set manually.
// Production users never see this UI and requests never include the engine field.
const showEngineSelector = computed(() =>
  import.meta.env.DEV ||
  localStorage.getItem('tradingagents:dev_mode') === 'true'
)

const _VALID_ENGINES = new Set(['custom_coordinator', 'langgraph'])
const _storedEngine  = localStorage.getItem('tradingagents:analysis_engine')
const analysisEngine = ref(
  _VALID_ENGINES.has(_storedEngine) ? _storedEngine : 'custom_coordinator'
)

watch(analysisEngine, (value) => {
  if (_VALID_ENGINES.has(value)) {
    localStorage.setItem('tradingagents:analysis_engine', value)
  }
})

// ── Core state ──────────────────────────────────────────────────────────────
const loading           = ref(false)
const errorMsg          = ref('')
const result            = ref(null)
const analysisStartedAt = ref(null)

// ── M25-a SSE realtime state ──────────────────────────────────────────────────
const currentRunId     = ref(null)   // active SSE run ID
const realtimeProgress = ref(null)   // 0-100 from SSE events
const agentStatuses    = ref({})     // { name: 'pending'|'running'|'success'|'failed'|'skipped' }
const latestEvent      = ref(null)   // last SSE event object
const realtimeEvents   = ref([])     // full event log (dev mode display)
const _progressMode    = ref('time') // 'time' | 'realtime'

// ── M25-b reliability guards ──────────────────────────────────────────────────
const reportReadyHandled = ref(false)  // prevent double result processing
const fallbackStarted    = ref(false)  // prevent double fallback
const cancelRequested    = ref(false)  // distinguish cancel from network error
const _isMounted         = ref(false)  // guard post-unmount state updates

// Collapse discovery panel once a result arrives
watch(result, (val) => {
  if (val !== null) discoveryOpen.value = false
})

// ── Save state ──────────────────────────────────────────────────────────────
const saveStatus    = ref('idle')   // 'idle' | 'saving' | 'saved' | 'error'
const saveError     = ref('')
const savedReportId = ref(null)

// ── Loading UX state ─────────────────────────────────────────────────────────
const elapsedSeconds  = ref(0)
const loadingHint     = ref('')
const abortController = ref(null)
const _timerId        = ref(null)

// ── Loading hint thresholds ──────────────────────────────────────────────────
function _hintForSeconds(s) {
  if (s < 15)  return '正在启动多维分析，请稍候...'
  if (s < 45)  return '正在获取行情、基本面、同行与新闻数据...'
  if (s < 90)  return '数据源或 LLM 响应较慢，系统仍在处理中...'
  return '本次分析耗时较长，可继续等待或取消后重试。'
}

// ── Timer helpers ─────────────────────────────────────────────────────────────
function _startTimer() {
  elapsedSeconds.value = 0
  loadingHint.value    = _hintForSeconds(0)
  _timerId.value = setInterval(() => {
    elapsedSeconds.value++
    loadingHint.value = _hintForSeconds(elapsedSeconds.value)
  }, 1000)
}

function _stopTimer() {
  if (_timerId.value !== null) {
    clearInterval(_timerId.value)
    _timerId.value = null
  }
}

// ── Sync default scope when user changes setting in ProfileView ───────────────
function _onSettingsUpdate(e) {
  const s = e?.detail || getSettings()
  // Only update if user hasn't manually changed scope this session
  if (!result.value && !loading.value) {
    analysisScope.value = s.default_analysis_scope || 'comprehensive'
    initMarket.value    = s.default_market || 'CN'
    currentMarket.value = s.default_market || 'CN'
  }
  reportLanguage.value = s.report_language || 'zh-CN'
}
onMounted(() => {
  _isMounted.value = true
  window.addEventListener(SETTINGS_EVENT, _onSettingsUpdate)
  loadDashboardData()
  _initGuide()
})

// ── Cleanup on unmount (navigation away during loading) ──────────────────────
onUnmounted(() => {
  _isMounted.value = false
  _stopTimer()
  abortController.value?.abort()
  window.removeEventListener(SETTINGS_EVENT, _onSettingsUpdate)
  if (_guideTimer) { clearTimeout(_guideTimer); _guideTimer = null }
})

// ── Cancel ───────────────────────────────────────────────────────────────────
async function cancelAnalysis() {
  if (cancelRequested.value) return
  cancelRequested.value = true
  // Abort first — stops the fetch reader immediately
  abortController.value?.abort()
  // Then signal backend to stop the run
  if (_progressMode.value === 'realtime' && currentRunId.value) {
    try { await cancelAnalysisRun(currentRunId.value) } catch { /* non-fatal */ }
  }
}

// ── Reset SSE state ───────────────────────────────────────────────────────────
function _resetSseState() {
  currentRunId.value       = null
  realtimeProgress.value   = null
  agentStatuses.value      = {}
  latestEvent.value        = null
  realtimeEvents.value     = []
  _progressMode.value      = 'time'
  reportReadyHandled.value = false
  fallbackStarted.value    = false
  cancelRequested.value    = false
}

// ── SSE event handler ─────────────────────────────────────────────────────────
function _handleSseEvent(evt) {
  if (!_isMounted.value) return
  latestEvent.value = evt
  realtimeEvents.value = [...realtimeEvents.value, evt]

  if (evt.progress !== undefined) {
    realtimeProgress.value = evt.progress
  }

  // Update agent statuses
  if (evt.event === 'agent_started' && evt.agent) {
    agentStatuses.value = { ...agentStatuses.value, [evt.agent]: 'running' }
  } else if (evt.event === 'agent_completed' && evt.agent) {
    agentStatuses.value = { ...agentStatuses.value, [evt.agent]: 'success' }
  } else if (evt.event === 'agent_failed' && evt.agent) {
    agentStatuses.value = { ...agentStatuses.value, [evt.agent]: 'failed' }
  } else if (evt.event === 'synthesis_started') {
    agentStatuses.value = { ...agentStatuses.value, synthesis: 'running' }
  } else if (evt.event === 'synthesis_completed') {
    agentStatuses.value = { ...agentStatuses.value, synthesis: 'success' }
  } else if (evt.event === 'identity_resolved' && evt.stock_identity) {
    // Update stock name display if not already known
    if (!currentStockName.value && evt.stock_name) {
      currentStockName.value = evt.stock_name
    }
  }
}

// ── Poll run once (never throws) ──────────────────────────────────────────────
async function _pollRunOnce(runId) {
  try {
    return await getAnalysisRun(runId)
  } catch {
    return null
  }
}

// ── Main analyze flow ─────────────────────────────────────────────────────────
async function handleAnalyze({ market, symbol }) {
  if (loading.value) return

  dismissGuide()

  // Create a fresh controller for this request
  const controller = new AbortController()
  abortController.value = controller

  // Reset display state; keep existing result until a new one arrives
  loading.value           = true
  errorMsg.value          = ''
  analysisStartedAt.value = Date.now()
  _resetSseState()

  _startTimer()

  const engineParam = showEngineSelector.value ? analysisEngine.value : undefined

  // ── SSE path (custom_coordinator and langgraph) ──────────────────────────
  // engine=langgraph also uses SSE (M25-c); direct API is the fallback on failure
  try {
    _progressMode.value = 'realtime'

    // 1. Create run — pass engine when set (langgraph SSE or default coordinator)
    const run = await createAnalysisRun(
      {
        market,
        symbol,
        analysis_scope:  analysisScope.value,
        output_language: reportLanguage.value,
        engine:          engineParam,
      },
      { signal: controller.signal },
    )
    currentRunId.value = run.run_id

    // 2. Subscribe to events
    let reportData    = null
    let sseNetError   = null   // network/reconnect failure (→ fallback to legacy)
    let analysisError = null   // backend analysis_failed event

    await subscribeAnalysisEvents(
      run.run_id,
      {
        onEvent(evt) {
          _handleSseEvent(evt)
          if (evt.event === 'report_ready' && evt.result && !reportReadyHandled.value) {
            reportReadyHandled.value = true
            reportData = evt.result
          }
          if (evt.event === 'analysis_failed') {
            analysisError = evt.error || t('analysis_error_default')
          }
        },
        onError(err) {
          sseNetError = err?.message || 'SSE 连接异常'
        },
      },
      controller.signal,
    )

    // 3. Post-stream checks
    if (cancelRequested.value || controller.signal.aborted) {
      if (_isMounted.value) {
        errorMsg.value = t('analysis_stopped')
      }
      return
    }
    if (analysisError) {
      throw new Error(analysisError)
    }
    if (sseNetError) {
      // Network/reconnect failure → try one poll before giving up
      if (!reportData) {
        const runState = await _pollRunOnce(run.run_id)
        if (runState?.result) {
          reportData = runState.result
        } else {
          // Fall back to legacy blocking API
          if (!fallbackStarted.value) {
            fallbackStarted.value = true
            _resetSseState()
            await _runLegacyApi(market, symbol, undefined, controller)
          }
          return
        }
      }
    }
    if (!reportData) {
      // SSE stream ended without report_ready → poll once for result
      const runState = await _pollRunOnce(run.run_id)
      if (runState?.result) {
        reportData = runState.result
      } else {
        throw new Error('分析完成但未收到报告数据，请刷新重试。')
      }
    }

    await _onAnalysisSuccess(reportData, market, symbol)

  } catch (e) {
    if (!_isMounted.value) return
    if (e.name === 'AbortError' || controller.signal.aborted || cancelRequested.value) {
      errorMsg.value = t('analysis_stopped')
    } else if (!fallbackStarted.value) {
      // Unexpected SSE failure → fallback to legacy blocking API (preserves engine)
      fallbackStarted.value = true
      _resetSseState()
      await _runLegacyApi(market, symbol, engineParam, controller)
      return
    } else {
      errorMsg.value = e.message || t('analysis_request_failed')
    }
  } finally {
    _stopTimer()
    loading.value         = false
    abortController.value = null
  }
}

// ── Legacy blocking API (fallback / langgraph) ────────────────────────────────
async function _runLegacyApi(market, symbol, engine, controller) {
  _progressMode.value = 'time'
  try {
    const data = await runComprehensiveAnalysisV2(
      {
        market,
        symbol,
        analysis_scope:  analysisScope.value,
        output_language: reportLanguage.value,
        engine,
      },
      { signal: controller.signal },
    )
    if (!_isMounted.value) return
    await _onAnalysisSuccess(data, market, symbol)
  } catch (e) {
    if (!_isMounted.value) return
    if (e.name === 'AbortError' || cancelRequested.value) {
      errorMsg.value = t('analysis_stopped')
    } else {
      errorMsg.value = e.message || t('analysis_request_failed')
    }
  } finally {
    _stopTimer()
    loading.value         = false
    abortController.value = null
  }
}

// ── Shared success handler ────────────────────────────────────────────────────
async function _onAnalysisSuccess(data, market, symbol) {
  if (!_isMounted.value) return
  result.value        = data
  saveStatus.value    = 'idle'
  saveError.value     = ''
  savedReportId.value = null

  addRecentSearch({ market, symbol, stock_name: data.stock_name || currentStockName.value })

  if (getSettings().auto_save_report !== false) {
    try {
      const saved = await createReport({ ...data, auto_saved: true })
      if (!_isMounted.value) return
      savedReportId.value = saved.id
      saveStatus.value    = 'saved'
    } catch {
      // Auto-save failure is silent
    }
  }
}

// ── Re-analyze (from ResearchActionPanel) ────────────────────────────────────
function handleReanalyze() {
  if (!result.value) return
  handleAnalyze({ market: result.value.market, symbol: result.value.symbol })
}

function handleNewAnalysis() {
  result.value    = null
  errorMsg.value  = ''
  _resetSseState()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ── Save ──────────────────────────────────────────────────────────────────────
async function handleSave() {
  if (!result.value || saveStatus.value === 'saving' || saveStatus.value === 'saved') return
  // Already auto-saved — treat as already done
  if (savedReportId.value) {
    saveStatus.value = 'saved'
    return
  }
  saveStatus.value = 'saving'
  saveError.value  = ''
  try {
    const resp = await createReport(result.value)
    savedReportId.value = resp.id
    saveStatus.value = 'saved'
  } catch (e) {
    saveError.value  = e.message || '未知错误'
    saveStatus.value = 'error'
  }
}
</script>

<style scoped>
/* Save status shown in AnalysisResultLayout #actions slot */
.save-status {
  font-size: 12px;
}

/* Discovery toggle shown when result exists and panel is collapsed */
.discovery-toggle {
  margin-bottom: 16px;
}

.save-status--ok  { color: var(--success); }
.save-status--err { color: var(--danger); }

.error-retry-hint {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 12px;
  line-height: 1.5;
}

.view-link {
  color: var(--accent);
  text-decoration: underline;
  font-size: 12px;
}
</style>
