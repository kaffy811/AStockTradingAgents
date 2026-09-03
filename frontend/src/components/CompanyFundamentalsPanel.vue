<template>
  <div class="cfp-root">
    <!-- AI Summary Strip (always visible) -->
    <AiSummaryStrip
      :envelope="aiSummaryEnvelope"
      :loading="aiSummaryLoading"
      @view-full="scrollToSection('ai-analysis')"
      @refresh="refreshAiSummary"
    />

    <!-- Data source warning banner -->
    <DataSourceBanner
      v-if="authRequired || allModuleErrors.length > 0 || dataSourceUnavailable || (!diagnosticsLoading && unavailableSections.length > 0 && bsFinancialOk)"
      :errors="allModuleErrors"
      :visible="allModuleErrors.length > 0 || dataSourceUnavailable || (!diagnosticsLoading && unavailableSections.length > 0 && bsFinancialOk)"
      :symbol="stockCode"
      :financial-data-ok="bsFinancialOk"
      :auth-required="authRequired"
    />

    <!-- Overview banner (partial/stale warnings) -->
    <FundamentalStateBanner
      v-if="overviewBanner"
      :type="overviewBanner.type"
      :message="overviewBanner.msg"
    />

    <!-- Two-column layout -->
    <div class="cfp-layout">
      <!-- Left: sticky anchor nav -->
      <div class="cfp-nav">
        <CompanyFundamentalAnchorNav
          :sections="anchorSections"
          :active-section-id="activeSectionId"
          @navigate="scrollToSection"
        />
      </div>

      <!-- Right: scrollable content -->
      <div class="cfp-content" ref="contentRef">

        <!-- Section: Overview -->
        <CompanyFundamentalSection
          id="overview"
          title="公司概览"
          :loading="overviewLoading"
          :isEmpty="!overviewSnap && !overviewFin && !overviewLoading"
          emptyReason="公司概览数据暂不可用"
        >
          <CompanyOverviewCards
            :snapshot="overviewSnap"
            :financial="overviewFin"
            :loading="overviewLoading"
          />
        </CompanyFundamentalSection>

        <!-- Section: Highlight & Risk -->
        <CompanyFundamentalSection
          id="highlight-risk"
          title="投资亮点与风险"
          :loading="moduleLoading['ai_analysis'] || false"
          :partial="moduleData['ai_analysis']?.partial || false"
          :errors="moduleData['ai_analysis']?.errors || []"
          :isEmpty="!moduleData['ai_analysis'] && !(moduleLoading['ai_analysis'])"
          emptyReason="AI 分析数据加载中或暂不可用"
        >
          <HighlightRiskPanel
            :envelope="moduleData['ai_analysis'] || null"
            :loading="moduleLoading['ai_analysis'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: AI Analysis full -->
        <CompanyFundamentalSection
          id="ai-analysis"
          title="AI 解析"
          :loading="moduleLoading['ai_analysis'] || false"
          :partial="moduleData['ai_analysis']?.partial || false"
          :errors="moduleData['ai_analysis']?.errors || []"
          :isEmpty="!moduleData['ai_analysis'] && !(moduleLoading['ai_analysis'])"
          emptyReason="AI 分析数据暂不可用"
        >
          <AiAnalysisSectionPanel
            :envelope="moduleData['ai_analysis'] || null"
            :loading="moduleLoading['ai_analysis'] || false"
            :on-refresh="() => refreshModule('ai_analysis')"
          />
        </CompanyFundamentalSection>

        <!-- Data-driven sections loading skeleton (while diagnostics loads) -->
        <div v-if="diagnosticsLoading" class="cfp-sections-skeleton">
          <div class="cfp-skel-section" v-for="i in 3" :key="i">
            <div class="cfp-skel-section-title"></div>
            <div class="cfp-skel-section-body"></div>
          </div>
        </div>

        <!-- Data-driven sections: only rendered after diagnostics complete -->
        <template v-else>

        <!-- Section: Valuation -->
        <CompanyFundamentalSection
          v-if="sectionVisible('valuation')"
          id="valuation"
          title="估值分位"
          :loading="moduleLoading['valuation'] || false"
          :partial="moduleData['valuation']?.partial || false"
          :errors="moduleData['valuation']?.errors || []"
          :isEmpty="!moduleHasRows('valuation') && !(moduleLoading['valuation'])"
          :emptyReason="firstReason(moduleData['valuation'])"
        >
          <ValuationPercentilePanel
            :envelope="moduleData['valuation'] || null"
            :loading="moduleLoading['valuation'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Dividend -->
        <CompanyFundamentalSection
          v-if="sectionVisible('dividend')"
          id="dividend"
          title="分红能力"
          :loading="moduleLoading['dividend_history'] || false"
          :partial="moduleData['dividend_history']?.partial || false"
          :errors="moduleData['dividend_history']?.errors || []"
          :isEmpty="!moduleHasRows('dividend_history') && !(moduleLoading['dividend_history'])"
          :emptyReason="firstReason(moduleData['dividend_history'])"
        >
          <DividendAbilityPanel
            :envelope="moduleData['dividend_history'] || null"
            :loading="moduleLoading['dividend_history'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Main Business -->
        <CompanyFundamentalSection
          v-if="sectionVisible('main-business')"
          id="main-business"
          title="主营构成"
          :loading="moduleLoading['main_business'] || false"
          :partial="moduleData['main_business']?.partial || false"
          :errors="moduleData['main_business']?.errors || []"
          :isEmpty="isMainBusinessEmpty && !(moduleLoading['main_business'])"
          :emptyReason="firstReason(moduleData['main_business'])"
        >
          <MainBusinessPanel
            :envelope="moduleData['main_business'] || null"
            :loading="moduleLoading['main_business'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Industry Position -->
        <CompanyFundamentalSection
          v-if="sectionVisible('industry')"
          id="industry"
          title="行业地位"
          :loading="moduleLoading['industry_rank'] || false"
          :partial="moduleData['industry_rank']?.partial || false"
          :errors="moduleData['industry_rank']?.errors || []"
          :isEmpty="!moduleHasRows('industry_rank') && !(moduleLoading['industry_rank'])"
          :emptyReason="firstReason(moduleData['industry_rank'])"
        >
          <IndustryPositionPanel
            :envelope="moduleData['industry_rank'] || null"
            :loading="moduleLoading['industry_rank'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Performance & Growth -->
        <CompanyFundamentalSection
          v-if="sectionVisible('growth')"
          id="growth"
          title="业绩及成长性"
          :loading="moduleLoading['growth'] || false"
          :partial="moduleData['growth']?.partial || false"
          :errors="moduleData['growth']?.errors || []"
          :isEmpty="!moduleHasRows('growth') && !(moduleLoading['growth'])"
          :emptyReason="firstReason(moduleData['growth'])"
        >
          <PerformanceGrowthPanel
            :envelope="moduleData['growth'] || null"
            :loading="moduleLoading['growth'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Profitability -->
        <CompanyFundamentalSection
          v-if="sectionVisible('profitability')"
          id="profitability"
          title="经营盈利能力"
          :loading="moduleLoading['profitability'] || false"
          :partial="moduleData['profitability']?.partial || false"
          :errors="moduleData['profitability']?.errors || []"
          :isEmpty="!moduleHasRows('profitability') && !(moduleLoading['profitability'])"
          :emptyReason="firstReason(moduleData['profitability'])"
        >
          <ProfitabilityPanel
            :envelope="moduleData['profitability'] || null"
            :loading="moduleLoading['profitability'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Earnings Quality -->
        <CompanyFundamentalSection
          v-if="sectionVisible('earnings-quality')"
          id="earnings-quality"
          title="收益质量"
          :loading="moduleLoading['cashflow_quality'] || false"
          :partial="moduleData['cashflow_quality']?.partial || false"
          :errors="moduleData['cashflow_quality']?.errors || []"
          :isEmpty="!moduleHasRows('cashflow_quality') && !(moduleLoading['cashflow_quality'])"
          :emptyReason="firstReason(moduleData['cashflow_quality'])"
        >
          <EarningsQualityPanel
            :envelope="moduleData['cashflow_quality'] || null"
            :loading="moduleLoading['cashflow_quality'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Asset Structure -->
        <CompanyFundamentalSection
          v-if="sectionVisible('asset-structure')"
          id="asset-structure"
          title="资产结构分析"
          :loading="moduleLoading['asset_structure'] || false"
          :partial="moduleData['asset_structure']?.partial || false"
          :errors="moduleData['asset_structure']?.errors || []"
          :isEmpty="!moduleHasRows('asset_structure') && !(moduleLoading['asset_structure'])"
          :emptyReason="firstReason(moduleData['asset_structure'])"
        >
          <AssetStructurePanel
            :envelope="moduleData['asset_structure'] || null"
            :loading="moduleLoading['asset_structure'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Solvency -->
        <CompanyFundamentalSection
          v-if="sectionVisible('solvency')"
          id="solvency"
          title="偿债能力分析"
          :loading="moduleLoading['solvency'] || false"
          :partial="moduleData['solvency']?.partial || false"
          :errors="moduleData['solvency']?.errors || []"
          :isEmpty="!moduleHasRows('solvency') && !(moduleLoading['solvency'])"
          :emptyReason="firstReason(moduleData['solvency'])"
        >
          <SolvencyPanel
            :envelope="moduleData['solvency'] || null"
            :loading="moduleLoading['solvency'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Capital Occupation -->
        <CompanyFundamentalSection
          v-if="sectionVisible('capital')"
          id="capital"
          title="资金占用分析"
          :loading="moduleLoading['capital_occupation'] || false"
          :partial="moduleData['capital_occupation']?.partial || false"
          :errors="moduleData['capital_occupation']?.errors || []"
          :isEmpty="!moduleHasRows('capital_occupation') && !(moduleLoading['capital_occupation'])"
          :emptyReason="firstReason(moduleData['capital_occupation'])"
        >
          <CapitalOccupationPanel
            :envelope="moduleData['capital_occupation'] || null"
            :loading="moduleLoading['capital_occupation'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Operation Capability -->
        <CompanyFundamentalSection
          v-if="sectionVisible('operations')"
          id="operations"
          title="营运能力分析"
          :loading="moduleLoading['operation_capability'] || false"
          :partial="moduleData['operation_capability']?.partial || false"
          :errors="moduleData['operation_capability']?.errors || []"
          :isEmpty="!moduleHasRows('operation_capability') && !(moduleLoading['operation_capability'])"
          :emptyReason="firstReason(moduleData['operation_capability'])"
        >
          <OperationCapabilityPanel
            :envelope="moduleData['operation_capability'] || null"
            :loading="moduleLoading['operation_capability'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Dupont Analysis -->
        <CompanyFundamentalSection
          v-if="sectionVisible('dupont')"
          id="dupont"
          title="杜邦分析"
          :loading="moduleLoading['dupont'] || false"
          :partial="moduleData['dupont']?.partial || false"
          :errors="moduleData['dupont']?.errors || []"
          :isEmpty="!moduleHasRows('dupont') && !(moduleLoading['dupont'])"
          :emptyReason="firstReason(moduleData['dupont'])"
        >
          <DupontAnalysisPanel
            :envelope="moduleData['dupont'] || null"
            :loading="moduleLoading['dupont'] || false"
          />
        </CompanyFundamentalSection>

        <!-- Section: Holders & Equity -->
        <CompanyFundamentalSection
          v-if="sectionVisible('shareholders')"
          id="shareholders"
          title="股东与股本结构"
          :loading="(moduleLoading['equity_structure'] || moduleLoading['major_holders']) || false"
          :partial="(moduleData['equity_structure']?.partial || moduleData['major_holders']?.partial) || false"
          :errors="[...(moduleData['equity_structure']?.errors || []), ...(moduleData['major_holders']?.errors || [])]"
          :isEmpty="!moduleHasRows('equity_structure') && !moduleHasRows('major_holders') && !moduleLoading['equity_structure'] && !moduleLoading['major_holders']"
          emptyReason="股东与股本数据暂不可用"
        >
          <HolderEquityPanel
            :equity-envelope="moduleData['equity_structure'] || null"
            :holders-envelope="moduleData['major_holders'] || null"
            :loading="(moduleLoading['equity_structure'] || moduleLoading['major_holders']) || false"
          />
        </CompanyFundamentalSection>

        </template><!-- end data-driven sections -->

        <!-- Section: Report Documents (Phase 6A) -->
        <CompanyFundamentalSection
          id="report-documents"
          title="年报文件"
          :loading="moduleLoading['report_documents'] || false"
          :partial="moduleData['report_documents']?.partial || false"
          :errors="moduleData['report_documents']?.errors || []"
          :isEmpty="false"
          emptyReason=""
        >
          <ReportDocumentsPanel
            :envelope="moduleData['report_documents'] || null"
            :loading="moduleLoading['report_documents'] || false"
            :market="market"
            :stock-code="symbol"
          />
        </CompanyFundamentalSection>

        <!-- Section: Report Chat Copilot (Phase 6J) -->
        <CompanyFundamentalSection
          id="report-chat"
          title="问财报"
          :loading="false"
          :partial="false"
          :errors="[]"
          :isEmpty="false"
          emptyReason=""
        >
          <ReportChatPanel
            :market="market"
            :stock-code="symbol"
            :rag-index-status="ragStatus"
            @action="handleChatAction"
          />
        </CompanyFundamentalSection>

        <!-- Unavailable modules panel (shown after diagnostics complete) -->
        <UnavailableModulesPanel
          v-if="!diagnosticsLoading && unavailableSections.length > 0"
          :section-ids="unavailableSections"
          :section-labels="SECTION_LABELS"
        />
      </div>
    </div>

    <!-- Chart zoom modal -->
    <FundamentalChartModal
      :visible="modalVisible"
      :title="modalData?.title || ''"
      :chart-type="modalData?.chartType || 'line'"
      :x-axis="modalData?.xAxis || []"
      :series="modalData?.series || []"
      :radar-indicators="modalData?.radarIndicators || []"
      @close="modalVisible = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { getFundamentalModules, getFundamentalOverview, getFundamentalModule, getFundamentalDiagnostics } from '../api/fundamentals.js'
import { isAuthError, AUTH_REQUIRED_MESSAGE } from '../utils/apiErrorClassifier.js'
import { hasDisplayableData } from '../utils/fundamentalAdapters.js'
import CompanyOverviewCards from './CompanyOverviewCards.vue'
import FundamentalStateBanner from './FundamentalStateBanner.vue'
import FundamentalChartModal from './fundamentals/FundamentalChartModal.vue'
import AiSummaryStrip from './fundamentals/AiSummaryStrip.vue'
import DataSourceBanner from './fundamentals/DataSourceBanner.vue'
import CompanyFundamentalAnchorNav from './fundamentals/CompanyFundamentalAnchorNav.vue'
import CompanyFundamentalSection from './fundamentals/CompanyFundamentalSection.vue'
import HighlightRiskPanel from './fundamentals/HighlightRiskPanel.vue'
import AiAnalysisSectionPanel from './fundamentals/AiAnalysisSectionPanel.vue'
import ValuationPercentilePanel from './fundamentals/ValuationPercentilePanel.vue'
import DividendAbilityPanel from './fundamentals/DividendAbilityPanel.vue'
import MainBusinessPanel from './fundamentals/MainBusinessPanel.vue'
import IndustryPositionPanel from './fundamentals/IndustryPositionPanel.vue'
import PerformanceGrowthPanel from './fundamentals/PerformanceGrowthPanel.vue'
import ProfitabilityPanel from './fundamentals/ProfitabilityPanel.vue'
import EarningsQualityPanel from './fundamentals/EarningsQualityPanel.vue'
import AssetStructurePanel from './fundamentals/AssetStructurePanel.vue'
import SolvencyPanel from './fundamentals/SolvencyPanel.vue'
import CapitalOccupationPanel from './fundamentals/CapitalOccupationPanel.vue'
import OperationCapabilityPanel from './fundamentals/OperationCapabilityPanel.vue'
import DupontAnalysisPanel from './fundamentals/DupontAnalysisPanel.vue'
import HolderEquityPanel from './fundamentals/HolderEquityPanel.vue'
import ReportDocumentsPanel from './fundamentals/ReportDocumentsPanel.vue'
import ReportChatPanel from './fundamentals/ReportChatPanel.vue'
import UnavailableModulesPanel from './fundamentals/UnavailableModulesPanel.vue'

const props = defineProps({
  market:    { type: String, required: true },
  symbol:    { type: String, required: true },
  stockName: { type: String, default: '' },
})

const stockCode = computed(() => props.symbol)

// ── Anchor sections definition ──────────────────────────────────────────────
const ANCHOR_SECTIONS = [
  { id: 'overview',         label: '公司概览',      modules: ['snapshot', 'valuation', 'financial_summary'] },
  { id: 'highlight-risk',   label: '投资亮点与风险', modules: ['ai_analysis'] },
  { id: 'ai-analysis',      label: 'AI 解析',       modules: ['ai_analysis'] },
  { id: 'valuation',        label: '估值分位',       modules: ['valuation'] },
  { id: 'dividend',         label: '分红能力',       modules: ['dividend_history'] },
  { id: 'main-business',    label: '主营构成',       modules: ['main_business'] },
  { id: 'industry',         label: '行业地位',       modules: ['industry_rank'] },
  { id: 'growth',           label: '业绩及成长性',   modules: ['growth', 'financial_summary'] },
  { id: 'profitability',    label: '经营盈利能力',   modules: ['profitability', 'expense_analysis'] },
  { id: 'earnings-quality', label: '收益质量',       modules: ['cashflow_quality'] },
  { id: 'asset-structure',  label: '资产结构',       modules: ['asset_structure'] },
  { id: 'solvency',         label: '偿债能力',       modules: ['solvency'] },
  { id: 'capital',          label: '资金占用',       modules: ['capital_occupation'] },
  { id: 'operations',       label: '营运能力',       modules: ['operation_capability'] },
  { id: 'dupont',           label: '杜邦分析',       modules: ['dupont'] },
  { id: 'shareholders',     label: '股东与股本',     modules: ['major_holders', 'equity_structure'] },
  { id: 'report-documents', label: '年报文件',       modules: ['report_documents'] },
  { id: 'report-chat',      label: '问财报',         modules: [] },
]

// ── Diagnostics-driven visibility ────────────────────────────────────────────
const diagnosticsLoading  = ref(true)
const sectionVisibility   = ref({})   // section_id → bool
const unavailableSections = ref([])   // section IDs with no data
const ragStatus           = ref('unknown')  // ready | not_indexed | empty | unknown

// Sections that are always visible regardless of data availability
const ALWAYS_SHOW = new Set(['overview', 'highlight-risk', 'ai-analysis', 'report-documents', 'report-chat'])

function sectionVisible(id) {
  if (ALWAYS_SHOW.has(id)) return true
  // While diagnostics loads, hide data-driven sections (prevents empty-card flash)
  if (diagnosticsLoading.value) return false
  return sectionVisibility.value[id] !== false
}

// ── Data normalization ────────────────────────────────────────────────────────
/**
 * All panels expect `data.rows` but backend modules may use `series`, `periods`,
 * or `records`. Add `rows` as alias so panels can read data uniformly.
 * Original fields are preserved for backward-compatible adapters.
 */
function normalizeEnvelope(env) {
  if (!env?.data) return env
  const d = env.data
  if (d.rows != null) return env   // already has rows, no change
  const rows = d.series || d.periods || d.records || []
  return { ...env, data: { ...d, rows } }
}

/**
 * Check if a module has any renderable data rows with at least one non-empty field.
 * Phase 6N-8B: uses hasDisplayableData so all-null rows do not count as "has data".
 */
function moduleHasRows(key) {
  const d = moduleData.value[key]?.data
  if (!d) return false
  // Quick non-null array checks for non-tabular data
  if (Array.isArray(d.rankings) && d.rankings.length > 0) return true
  if (Array.isArray(d.top10_float_holders) && d.top10_float_holders.length > 0) return true
  if (Array.isArray(d.holder_num_series) && d.holder_num_series.length > 0) return true
  // For tabular row data — require at least one row with a real value
  const rows = d.rows || d.series || d.periods || d.records || []
  if (!rows.length) return false
  return hasDisplayableData(rows)
}

const SECTION_LABELS = Object.fromEntries(ANCHOR_SECTIONS.map(s => [s.id, s.label]))
function sectionLabel(id) { return SECTION_LABELS[id] || id }

const anchorSections = computed(() =>
  ANCHOR_SECTIONS.filter(s => sectionVisible(s.id))
)
const plannedSections = computed(() => ANCHOR_SECTIONS.filter(s => s.planned === true))

// ── State ───────────────────────────────────────────────────────────────────
const overviewLoading = ref(true)
const overviewSnap    = ref(null)
const overviewFin     = ref(null)
const overviewBanner  = ref(null)

const moduleData    = ref({})
const moduleLoading = ref({})

const aiSummaryEnvelope = ref(null)
const aiSummaryLoading  = ref(false)

const dataSourceUnavailable = ref(false)

// Phase 6N-8A: set when any request fails with 401 —
// banner shows a login prompt and suppresses provider-failure copy.
const authRequired = ref(false)

// Scroll spy
const activeSectionId = ref('overview')
const contentRef      = ref(null)

// Chart modal
const modalVisible = ref(false)
const modalData    = ref(null)

// ── Computed helpers ─────────────────────────────────────────────────────────

// Collect all errors from all loaded modules into a flat array
const allModuleErrors = computed(() =>
  Object.values(moduleData.value).flatMap(env => env?.errors || [])
)

// True when BaoStock financial modules (growth/profitability/…) are available.
// Used to distinguish "market data limited" from "all financial data unavailable".
const bsFinancialOk = computed(() =>
  ['growth', 'profitability', 'earnings-quality', 'solvency', 'operations', 'dupont']
    .some(id => sectionVisibility.value[id] === true)
)

const isMainBusinessEmpty = computed(() => {
  const d = moduleData.value['main_business']?.data
  if (!d) return true
  return !(d.by_product?.length || d.by_region?.length || d.by_industry?.length)
})

function firstReason(envelope) {
  const r = envelope?.data?.reasons
  if (Array.isArray(r) && r.length) return r[0]
  const e = envelope?.errors
  if (Array.isArray(e) && e.length) return e[0]
  return ''
}

// ── Data source detection ────────────────────────────────────────────────────
function detectDataSourceUnavailable(envelope) {
  if (!envelope) return
  if (!envelope.partial) return
  const errs = envelope.errors || envelope.data?.reasons || []
  const isUnavailable = errs.some(e =>
    typeof e === 'string' && (e.includes('未配置') || e.includes('unavailable') || e.includes('TUSHARE') || e.includes('503'))
  )
  if (isUnavailable) {
    dataSourceUnavailable.value = true
    if (errs.length) dataSourceMessage.value = errs[0]
  }
}

// ── Loading functions ────────────────────────────────────────────────────────
async function loadOverview() {
  overviewLoading.value = true
  overviewBanner.value  = null
  try {
    const ov = await getFundamentalOverview(stockCode.value)
    overviewSnap.value = ov?.snapshot || null
    overviewFin.value  = ov?.financial_summary || null

    if (overviewSnap.value) moduleData.value = { ...moduleData.value, snapshot: overviewSnap.value }
    if (overviewFin.value)  moduleData.value = { ...moduleData.value, financial_summary: overviewFin.value }

    detectDataSourceUnavailable(overviewSnap.value)
    detectDataSourceUnavailable(overviewFin.value)

    if (overviewSnap.value?.partial || overviewFin.value?.partial) {
      // P1-D dedup: DataSourceBanner already covers provider-unavailable partials.
      // Only show overviewBanner for partial if DataSourceBanner is NOT visible.
      if (!dataSourceUnavailable.value) {
        overviewBanner.value = { type: 'warn', msg: '部分数据获取不完整，结果仅供参考。' }
      }
    }
    if (overviewSnap.value?.stale || overviewFin.value?.stale) {
      overviewBanner.value = { type: 'stale', msg: '数据来自缓存，可能非最新。' }
    }
  } catch (e) {
    // Phase 6N-8A: 401 → login prompt, never a provider-failure message
    if (isAuthError(e)) {
      authRequired.value = true
      // P1-D dedup: DataSourceBanner shows auth error via authRequired flag;
      // do NOT also set overviewBanner to avoid duplicate banners.
    } else {
      overviewBanner.value = { type: 'error', msg: `概览数据加载失败：${e.message || '未知错误'}` }
    }
  } finally {
    overviewLoading.value = false
  }
}

async function loadAiSummary() {
  if (aiSummaryEnvelope.value !== null) return
  aiSummaryLoading.value = true
  try {
    const env = await getFundamentalModule(stockCode.value, 'ai_analysis', { mode: 'summary' })
    aiSummaryEnvelope.value = env
    if (env && !moduleData.value['ai_analysis']) {
      moduleData.value = { ...moduleData.value, ai_analysis: env }
    }
  } catch {
    aiSummaryEnvelope.value = null
  } finally {
    aiSummaryLoading.value = false
  }
}

async function loadModule(key) {
  if (moduleData.value[key] !== undefined || moduleLoading.value[key]) return  // already cached or in-flight
  moduleLoading.value = { ...moduleLoading.value, [key]: true }
  try {
    const env = await getFundamentalModule(stockCode.value, key)
    detectDataSourceUnavailable(env)
    moduleData.value = { ...moduleData.value, [key]: normalizeEnvelope(env) }
  } catch (e) {
    // Phase 6N-8A: don't swallow auth errors into "provider failed" state
    if (isAuthError(e)) authRequired.value = true
    moduleData.value = { ...moduleData.value, [key]: null }
  } finally {
    moduleLoading.value = { ...moduleLoading.value, [key]: false }
  }
}

async function loadModulesForSection(sectionId) {
  const sec = ANCHOR_SECTIONS.find(s => s.id === sectionId)
  if (!sec || sec.planned) return
  const toLoad = sec.modules.filter(k => moduleData.value[k] === undefined)
  await Promise.allSettled(toLoad.map(k => loadModule(k)))
}

async function refreshAiSummary() {
  aiSummaryLoading.value = true
  try {
    const env = await getFundamentalModule(stockCode.value, 'ai_analysis', { mode: 'summary', force_refresh: true })
    aiSummaryEnvelope.value = env
    moduleData.value = { ...moduleData.value, ai_analysis: env }
  } catch {
    // keep old data, don't crash
  } finally {
    aiSummaryLoading.value = false
  }
}

async function refreshModule(key) {
  const newData = { ...moduleData.value }
  delete newData[key]
  moduleData.value = newData
  moduleLoading.value = { ...moduleLoading.value, [key]: true }
  try {
    const env = await getFundamentalModule(stockCode.value, key)
    moduleData.value = { ...moduleData.value, [key]: normalizeEnvelope(env) }
  } catch {
    moduleData.value = { ...moduleData.value, [key]: null }
  } finally {
    moduleLoading.value = { ...moduleLoading.value, [key]: false }
  }
}

// ── Report-chat action handler ───────────────────────────────────────────────
async function handleChatAction(action) {
  if (action === 'discover_reports' || action === 'build_index') {
    // Scroll to report-documents section so user can act
    await scrollToSection('report-documents')
  }
}

// ── Scroll to section ────────────────────────────────────────────────────────
async function scrollToSection(sectionId) {
  // Trigger load for target section
  await loadModulesForSection(sectionId)
  await nextTick()
  const el = document.getElementById(sectionId)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    activeSectionId.value = sectionId
  }
}

// ── Intersection Observer (scroll spy) ──────────────────────────────────────
let intersectionObserver = null

function setupScrollSpy() {
  if (intersectionObserver) {
    intersectionObserver.disconnect()
  }
  const sectionIds = ANCHOR_SECTIONS.filter(s => s.planned !== true).map(s => s.id)
  intersectionObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          activeSectionId.value = entry.target.id
          // Load modules for newly visible sections on demand
          loadModulesForSection(entry.target.id)
          break
        }
      }
    },
    { threshold: 0.15, rootMargin: '-60px 0px -60% 0px' }
  )
  sectionIds.forEach(id => {
    const el = document.getElementById(id)
    if (el) intersectionObserver.observe(el)
  })
}

// ── Diagnostics loader ───────────────────────────────────────────────────────
async function loadDiagnostics() {
  diagnosticsLoading.value = true
  try {
    const result = await getFundamentalDiagnostics(props.symbol)
    if (result) {
      sectionVisibility.value = result.visibility || {}
      unavailableSections.value = result.unavailable_sections || []
      ragStatus.value = result.rag_status || 'unknown'
    }
  } catch (e) {
    // diagnostics failure is non-fatal; show all sections
    console.warn('[diagnostics] failed:', e)
  } finally {
    diagnosticsLoading.value = false
  }
}

// ── Mount and cleanup ────────────────────────────────────────────────────────
onMounted(async () => {
  // Phase 1: load overview + AI summary + diagnostics in parallel
  await Promise.allSettled([
    loadOverview(),
    loadAiSummary(),
    loadDiagnostics(),
  ])

  // Phase 2: load first-screen modules only if visible
  const firstScreenMods = []
  if (sectionVisible('valuation')) firstScreenMods.push(loadModule('valuation'))
  await Promise.allSettled(firstScreenMods)

  // Phase 3: background pre-load visible data-driven modules
  const bgMods = []
  if (sectionVisible('growth'))           bgMods.push(loadModule('growth'))
  if (sectionVisible('profitability'))    bgMods.push(loadModule('profitability'))
  if (sectionVisible('earnings-quality')) bgMods.push(loadModule('cashflow_quality'))
  if (sectionVisible('main-business'))    bgMods.push(loadModule('main_business'))
  if (sectionVisible('industry'))         bgMods.push(loadModule('industry_rank'))
  if (sectionVisible('dividend'))         bgMods.push(loadModule('dividend_history'))
  if (bgMods.length > 0 && !dataSourceUnavailable.value) {
    Promise.allSettled(bgMods)
  }

  // Set up scroll spy after DOM is ready
  await nextTick()
  setupScrollSpy()
})

onUnmounted(() => {
  if (intersectionObserver) {
    intersectionObserver.disconnect()
    intersectionObserver = null
  }
})

// Reset when stock changes
watch(() => [props.market, props.symbol], async () => {
  if (intersectionObserver) {
    intersectionObserver.disconnect()
    intersectionObserver = null
  }
  moduleData.value          = {}
  moduleLoading.value       = {}
  overviewSnap.value        = null
  overviewFin.value         = null
  aiSummaryEnvelope.value   = null
  dataSourceUnavailable.value = false
  activeSectionId.value     = 'overview'
  sectionVisibility.value   = {}
  unavailableSections.value = []
  ragStatus.value           = 'unknown'
  diagnosticsLoading.value  = true

  await Promise.allSettled([
    loadOverview(),
    loadAiSummary(),
    loadDiagnostics(),
  ])

  // Load first-screen modules only if visible (after diagnostics)
  if (sectionVisible('valuation')) await loadModule('valuation')

  if (!dataSourceUnavailable.value) {
    const bgMods = []
    if (sectionVisible('growth'))           bgMods.push(loadModule('growth'))
    if (sectionVisible('profitability'))    bgMods.push(loadModule('profitability'))
    if (sectionVisible('earnings-quality')) bgMods.push(loadModule('cashflow_quality'))
    if (sectionVisible('main-business'))    bgMods.push(loadModule('main_business'))
    if (sectionVisible('industry'))         bgMods.push(loadModule('industry_rank'))
    if (sectionVisible('dividend'))         bgMods.push(loadModule('dividend_history'))
    if (bgMods.length) Promise.allSettled(bgMods)
  }

  await nextTick()
  setupScrollSpy()
})
</script>

<style scoped>
.cfp-root {
  background: #eef3fb;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 400px;
}

/* Two-column layout */
.cfp-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.cfp-nav {
  width: 180px;
  flex-shrink: 0;
}

.cfp-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

@media (max-width: 768px) {
  .cfp-layout {
    flex-direction: column;
  }

  .cfp-nav {
    width: 100%;
    position: static; /* no sticky on mobile */
  }

  .cfp-content {
    min-width: 0;
  }
}

@media (max-width: 640px) {
  .cfp-root {
    padding: 10px;
    border-radius: 8px;
  }
}

/* Diagnostics loading skeleton (replaces data-driven sections while loading) */
.cfp-sections-skeleton {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cfp-skel-section {
  background: #fff;
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cfp-skel-section-title {
  height: 14px;
  width: 120px;
  border-radius: 6px;
  background: linear-gradient(90deg, #e8eef8 25%, #d4ddf5 50%, #e8eef8 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}

.cfp-skel-section-body {
  height: 80px;
  border-radius: 8px;
  background: linear-gradient(90deg, #f0f4fb 25%, #e4ecf7 50%, #f0f4fb 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
