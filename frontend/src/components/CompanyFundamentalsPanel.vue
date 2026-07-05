<template>
  <div class="cfp-root">
    <!-- Overview Cards (always visible) -->
    <div class="cfp-overview">
      <FundamentalStateBanner v-if="overviewBanner" :type="overviewBanner.type" :message="overviewBanner.msg" />
      <CompanyOverviewCards
        :snapshot="overviewSnap"
        :financial="overviewFin"
        :loading="overviewLoading"
      />
    </div>

    <!-- Toolbar -->
    <CompanyFundamentalsToolbar
      :model-period="period"
      :model-limit="limit"
      :is-mock="isMockMode"
      :refreshing="sectionLoading"
      @update:period="period = $event"
      @update:limit="limit = $event"
      @refresh-all="refreshAll"
      @export-csv="exportSectionCsv"
    />

    <!-- Section Tab Nav (sticky) -->
    <div class="cfp-tabs-sticky">
      <CompanyFundamentalSectionTabs
        :sections="sections"
        :active="activeSection"
        @change="onSectionChange"
      />
    </div>

    <!-- Module cards for active section -->
    <div class="cfp-modules">
      <div v-if="sectionLoading" class="cfp-loading">
        <span class="spinner"></span>
        <span>加载中…</span>
      </div>
      <template v-else>
        <FundamentalModuleCard
          v-for="(module, idx) in activeSectionModules"
          :key="module.key"
          :module-meta="enrichedMeta(module)"
          :envelope="moduleData[module.key]"
          :loading="moduleLoading[module.key] || false"
          :stock-code="stockCode"
          :default-expanded="idx < 2"
          @refresh="refreshModule(module.key)"
          @expand-chart="onExpandChart"
          @export-csv="onModuleExportCsv"
        />
        <div v-if="activeSectionModules.length === 0" class="cfp-empty">
          <span>暂无可用模块</span>
        </div>
      </template>
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
import { ref, computed, watch, onMounted } from 'vue'
import { getFundamentalModules, getFundamentalOverview, getFundamentalModule } from '../api/fundamentals.js'
import { adaptModuleData } from '../utils/fundamentalAdapters.js'
import { exportModuleCsv } from '../utils/exportFundamentals.js'
import CompanyOverviewCards from './CompanyOverviewCards.vue'
import CompanyFundamentalSectionTabs from './CompanyFundamentalSectionTabs.vue'
import CompanyFundamentalsToolbar from './CompanyFundamentalsToolbar.vue'
import FundamentalModuleCard from './FundamentalModuleCard.vue'
import FundamentalStateBanner from './FundamentalStateBanner.vue'
import FundamentalChartModal from './fundamentals/FundamentalChartModal.vue'

const props = defineProps({
  market:    { type: String, required: true },
  symbol:    { type: String, required: true },
  stockName: { type: String, default: '' },
})

// Computed stock code
const stockCode = computed(() => props.symbol)

// ── Toolbar state ─────────────────────────────────────────────────────────────
const period = ref('annual')
const limit  = ref(8)
const isMockMode = import.meta.env.VITE_USE_MOCK === 'true'

// ── Module catalog state ─────────────────────────────────────────────────────
const allModules = ref([])
const modulesLoaded = ref(false)

// ── Overview state ───────────────────────────────────────────────────────────
const overviewLoading = ref(true)
const overviewSnap    = ref(null)
const overviewFin     = ref(null)
const overviewBanner  = ref(null)

// ── Section tabs ─────────────────────────────────────────────────────────────
const SECTION_DEFS = [
  { key: 'overview',     label: '公司概览',  modules: ['snapshot', 'valuation', 'financial_summary'] },
  { key: 'financials',   label: '财务分析',  modules: ['growth', 'profitability', 'expense_analysis', 'cashflow_quality', 'dupont'] },
  { key: 'balance',      label: '资产负债',  modules: ['asset_structure', 'solvency', 'operation_capability', 'capital_occupation'] },
  { key: 'shareholders', label: '股东分红',  modules: ['main_business', 'dividend_history', 'major_holders', 'equity_structure'] },
  { key: 'events',       label: '事件观点',  modules: ['announcements', 'analyst_ratings'] },
]

const activeSection = ref('overview')
const sectionLoading = ref(false)

// Cache: moduleKey → envelope
const moduleData    = ref({})
const moduleLoading = ref({})

// ── Chart modal state ─────────────────────────────────────────────────────────
const modalVisible = ref(false)
const modalData    = ref(null)

// ── Sections computed ─────────────────────────────────────────────────────────
const sections = computed(() => {
  const catalogMap = Object.fromEntries(allModules.value.map(m => [m.key, m]))
  return SECTION_DEFS.map(s => ({
    ...s,
    moduleMetas: s.modules
      .map(k => catalogMap[k])
      .filter(Boolean)
      .filter(m => m.display !== false && m.status !== 'hidden'),
  }))
})

const activeSectionModules = computed(() => {
  const sec = sections.value.find(s => s.key === activeSection.value)
  return sec ? sec.moduleMetas : []
})

// Enrich module meta with envelope's meta (if available)
function enrichedMeta(module) {
  const envelope = moduleData.value[module.key]
  if (!envelope?.meta) return module
  return {
    ...module,
    meta:         { ...module.meta, ...envelope.meta },
    field_labels: module.field_labels || envelope.meta?.field_labels || {},
    unit_hints:   module.unit_hints   || envelope.meta?.unit_hints   || {},
  }
}

// ── Load sequence ────────────────────────────────────────────────────────────

async function loadModuleCatalog() {
  try {
    const mods = await getFundamentalModules()
    allModules.value = Array.isArray(mods) ? mods.filter(m => m.display !== false && m.status !== 'hidden') : []
  } catch {
    allModules.value = []
  }
  modulesLoaded.value = true
}

async function loadOverview() {
  overviewLoading.value = true
  overviewBanner.value  = null
  try {
    const ov = await getFundamentalOverview(stockCode.value)
    overviewSnap.value = ov?.snapshot || null
    overviewFin.value  = ov?.financial_summary || null

    // Pre-populate moduleData cache for overview modules
    if (overviewSnap.value) moduleData.value = { ...moduleData.value, snapshot: overviewSnap.value }
    if (overviewFin.value)  moduleData.value = { ...moduleData.value, financial_summary: overviewFin.value }

    if (overviewSnap.value?.partial || overviewFin.value?.partial) {
      overviewBanner.value = { type: 'warn', msg: '部分数据获取不完整，结果仅供参考。' }
    }
    if (overviewSnap.value?.stale || overviewFin.value?.stale) {
      overviewBanner.value = { type: 'stale', msg: '数据来自缓存，可能非最新。' }
    }
  } catch (e) {
    overviewBanner.value = { type: 'error', msg: `概览数据加载失败：${e.message || '未知错误'}` }
  } finally {
    overviewLoading.value = false
  }
}

async function loadSectionModules(sectionKey) {
  const sec = sections.value.find(s => s.key === sectionKey)
  if (!sec) return

  const toLoad = sec.moduleMetas.filter(m => {
    if (m.status === 'planned') return false
    if (moduleData.value[m.key] !== undefined) return false
    return true
  })

  if (toLoad.length === 0) return

  sectionLoading.value = true
  await Promise.allSettled(toLoad.map(async (m) => {
    moduleLoading.value = { ...moduleLoading.value, [m.key]: true }
    try {
      const env = await getFundamentalModule(stockCode.value, m.key, { period: period.value, limit: limit.value })
      moduleData.value = { ...moduleData.value, [m.key]: env }
    } catch {
      moduleData.value = { ...moduleData.value, [m.key]: null }
    } finally {
      moduleLoading.value = { ...moduleLoading.value, [m.key]: false }
    }
  }))
  sectionLoading.value = false
}

// Refresh a single module (delete cache + re-fetch with current params)
async function refreshModule(key) {
  const newData = { ...moduleData.value }
  delete newData[key]
  moduleData.value = newData

  moduleLoading.value = { ...moduleLoading.value, [key]: true }
  try {
    const env = await getFundamentalModule(stockCode.value, key, { period: period.value, limit: limit.value })
    moduleData.value = { ...moduleData.value, [key]: env }
  } catch {
    moduleData.value = { ...moduleData.value, [key]: null }
  } finally {
    moduleLoading.value = { ...moduleLoading.value, [key]: false }
  }
}

// Refresh all loaded modules in the active section
async function refreshAll() {
  const sec = sections.value.find(s => s.key === activeSection.value)
  if (!sec) return
  const newData = { ...moduleData.value }
  sec.moduleMetas.forEach(m => { delete newData[m.key] })
  moduleData.value = newData
  await loadSectionModules(activeSection.value)
}

// Export all loaded modules in current section as CSV files
function exportSectionCsv() {
  const sec = sections.value.find(s => s.key === activeSection.value)
  if (!sec) return
  sec.moduleMetas.forEach(m => {
    const env = moduleData.value[m.key]
    if (!env?.data) return
    const vm = adaptModuleData(m.key, env.data, m)
    if (vm.rows && vm.rows.length > 0) {
      exportModuleCsv(stockCode.value, m.key, vm, m.field_labels || {})
    }
  })
}

// Export a specific module's data (triggered from card's export-csv event)
function onModuleExportCsv({ moduleKey, moduleMeta, envelope }) {
  if (!envelope?.data || !moduleMeta) return
  const vm = adaptModuleData(moduleKey, envelope.data, moduleMeta)
  exportModuleCsv(stockCode.value, moduleKey, vm, moduleMeta.field_labels || {})
}

// Open chart modal with data from a module card
function onExpandChart({ moduleKey, moduleMeta, envelope }) {
  if (!envelope?.data || !moduleMeta) return
  const vm = adaptModuleData(moduleKey, envelope.data, moduleMeta)
  modalData.value = {
    title:           moduleMeta?.name_zh || moduleKey,
    chartType:       moduleMeta?.chart_type || moduleMeta?.meta?.chart_type || 'line',
    xAxis:           vm.xAxis        || [],
    series:          vm.series       || [],
    radarIndicators: vm.radarIndicators || [],
  }
  modalVisible.value = true
}

async function onSectionChange(key) {
  activeSection.value = key
  await loadSectionModules(key)
}

// When period/limit change: wipe all module cache and reload current section
watch([period, limit], async () => {
  moduleData.value    = {}
  moduleLoading.value = {}
  await loadSectionModules(activeSection.value)
})

onMounted(async () => {
  await loadModuleCatalog()
  await loadOverview()
  await loadSectionModules('overview')
})

// Reset when stock changes
watch(() => [props.market, props.symbol], async () => {
  moduleData.value    = {}
  moduleLoading.value = {}
  overviewSnap.value  = null
  overviewFin.value   = null
  activeSection.value = 'overview'
  period.value        = 'annual'
  limit.value         = 8
  await loadModuleCatalog()
  await loadOverview()
  await loadSectionModules('overview')
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

.cfp-overview {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cfp-tabs-sticky {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #eef3fb;
  padding: 4px 0;
  margin: -4px 0;
}

.cfp-modules {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cfp-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 24px 0;
  color: var(--muted);
  font-size: 13px;
  justify-content: center;
}

.cfp-empty {
  text-align: center;
  padding: 24px 0;
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 540px) {
  .cfp-root { padding: 10px; border-radius: 8px; }
}
</style>
