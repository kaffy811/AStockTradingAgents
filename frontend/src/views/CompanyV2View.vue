<template>
  <main :class="['company-v2-page', embedded && 'company-v2-page-embedded']">
    <!-- 1. Company Profile Header -->
    <header class="cv2-hero">
      <button v-if="!embedded" class="cv2-back" @click="router.back()">← 返回</button>
      <div class="cv2-hero-center">
        <h1>
          <span v-if="stockBasic.company_name" class="cv2-company-name">
            {{ stockBasic.company_name }}
          </span>
          <span v-else>{{ market }}/{{ symbol }}</span>
        </h1>
        <div class="cv2-hero-meta">
          <span class="cv2-hero-code">{{ symbol }}</span>
          <span v-if="stockBasic.exchange" class="cv2-hero-exchange">{{ stockBasic.exchange }}</span>
          <span v-if="stockBasic.industry" class="cv2-hero-industry">{{ stockBasic.industry }}</span>
          <span v-if="stockBasic.list_date" class="cv2-hero-listdate">
            上市: {{ stockBasic.list_date }}
          </span>
        </div>
        <p v-if="priceLabel" class="cv2-price-label">
          <span class="cv2-price-value">{{ latestPrice }}</span>
          <span v-if="!priceIsRealtime" class="cv2-non-realtime">（非实时）</span>
          <span class="cv2-price-source">{{ priceLabel }}</span>
        </p>
        <!-- Phase 6T-E: 真实历史范围语义（不夸大为"上市以来"） -->
        <p v-if="historyRangeLabel" class="cv2-history-range" data-testid="history-range-label">
          历史财务：{{ historyRangeLabel }}
          <span v-if="historyData.history_truncated && historyData.truncation_reason" class="cv2-range-truncated">
            （数据源覆盖有限）
          </span>
        </p>
      </div>
      <div class="cv2-hero-right">
        <!-- Phase 6T-E1: 默认年度（上市以来）；季度懒加载（默认最近5年），已缓存不重复请求 -->
        <div class="cv2-period-tabs" data-testid="period-tabs">
          <button
            :class="['cv2-period-tab', periodTab === 'annual' && 'active']"
            @click="periodTab = 'annual'"
          >年度</button>
          <button
            :class="['cv2-period-tab', periodTab === 'quarterly' && 'active']"
            :disabled="quarterlyLoading"
            @click="switchToQuarterly"
          >{{ quarterlyLoading ? '季度…' : '季度' }}</button>
        </div>
        <label class="cv2-raw-switch">
          <input v-model="includeRaw" type="checkbox" @change="load(true)" />
          include raw
        </label>
      </div>
    </header>

    <div v-if="loading" class="cv2-loading">加载中...</div>
    <div v-else-if="error" class="cv2-error">{{ error }}</div>
    <template v-else>
      <CompanyV2CompanyProfileCard
        :stock-basic="stockBasic"
        :symbol="symbol"
        :market="market"
        data-testid="company-profile-card"
      />

      <!-- 2. Overview Cards (来自 quote_overview) -->
      <CompanyV2StockBasicCard
        v-if="quoteRow && Object.keys(quoteRow).length"
        :quote-row="quoteRow"
        :stock-basic="stockBasic"
        data-testid="stock-basic-card"
      />

      <!-- Debug Panel（默认折叠） -->
      <details class="cv2-debug-details" data-testid="debug-panel">
        <summary class="cv2-debug-summary">Debug / 诊断面板</summary>
        <CompanyV2DebugPanel :data="debugData" @refresh="refresh" />
      </details>

      <!-- 3-10. 财务主模块（按顺序展示） -->
      <CompanyV2Section
        v-for="item in visibleModules"
        :key="item.key"
        :title="item.title"
        :module-key="item.key"
        :envelope="item.envelope"
        :history-data="displayHistoryModules[item.key]"
        :market="market"
        :symbol="symbol"
      />

      <!-- 不可展示模块列表 -->
      <section v-if="unavailableModules.length" class="cv2-section">
        <h2>暂无可展示数据</h2>
        <CompanyV2FallbackTable
          :rows="unavailableModules"
          :columns="['key', 'reason']"
        />
      </section>

      <!-- 数据准确性提示 -->
      <footer class="cv2-disclaimer">
        数据来源：公开数据源聚合、CNINFO 公告文件及系统计算。行情可能存在延迟，财务数据最终以交易所及巨潮资讯披露文件为准。本页面不构成投资建议。
      </footer>

      <div data-testid="company-v2-bottom-sentinel" class="cv2-bottom-sentinel" />
    </template>
  </main>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getCompanyV2FullDebug, refreshCompanyV2Debug, getCompanyV2History, getCompanyV2StockBasic } from '../api/companyV2.js'
import CompanyV2DebugPanel from '../components/company-v2/CompanyV2DebugPanel.vue'
import CompanyV2Section from '../components/company-v2/CompanyV2Section.vue'
import CompanyV2FallbackTable from '../components/company-v2/CompanyV2FallbackTable.vue'
import CompanyV2CompanyProfileCard from '../components/company-v2/CompanyV2CompanyProfileCard.vue'
import CompanyV2StockBasicCard from '../components/company-v2/CompanyV2StockBasicCard.vue'

const route = useRoute()
const router = useRouter()
const emit = defineEmits(['load-error'])
defineProps({
  embedded: { type: Boolean, default: false },
})
const loading = ref(false)
const error = ref('')
const debugData = ref({})
const historyData = ref({})   // 全历史数据
const stockBasic = ref({})    // 公司/股票基本信息
const includeRaw = ref(false)
// Phase 6T-E1: 默认年度（上市以来）；季度数据懒加载（后端默认最近5年）
const periodTab = ref('annual')
const quarterlyHistoryData = ref(null)   // 懒加载缓存：切换股票时清空
const quarterlyLoading = ref(false)

const market = computed(() => String(route.params.market || '').toUpperCase())
const symbol = computed(() => String(route.params.symbol || ''))

// 历史模块数据（传给 CompanyV2Section）
const historyModules = computed(() => historyData.value.modules || {})
const historyRangeLabel = computed(() => {
  const src = periodTab.value === 'quarterly' && quarterlyHistoryData.value
    ? quarterlyHistoryData.value : historyData.value
  return src.history_range_label || ''
})

// Phase 6T-E1: 年度为默认数据；季度 tab 使用懒加载的 quarterly 数据（已缓存不重复请求）
const displayHistoryModules = computed(() => {
  if (periodTab.value === 'quarterly' && quarterlyHistoryData.value?.modules) {
    return quarterlyHistoryData.value.modules
  }
  return historyModules.value
})

async function switchToQuarterly() {
  periodTab.value = 'quarterly'
  if (quarterlyHistoryData.value?.modules || quarterlyLoading.value) return
  quarterlyLoading.value = true
  const seq = _loadSeq
  try {
    // 后端默认季度范围为最近 5 年；用户显式扩展时再传 start_year
    const data = await getCompanyV2History(market.value, symbol.value, { period: 'quarterly' })
    if (seq === _loadSeq) quarterlyHistoryData.value = data || null
  } catch (e) {
    if (e?.name !== 'AbortError' && seq === _loadSeq) quarterlyHistoryData.value = null
  } finally {
    if (seq === _loadSeq) quarterlyLoading.value = false
  }
}

const titles = {
  quote_overview: '行情概览',
  valuation: '估值',
  profitability: '盈利能力',
  growth: '成长能力',
  cashflow_quality: '现金流质量',
  solvency: '偿债能力',
  operation_capability: '营运能力',
  dupont: '杜邦分析',
  report_documents: '报告文件',
  ai_analysis_status: 'AI 状态',
  // report_rag 已合并入 report_documents，不再作为独立模块展示
}

// 模块展示顺序
const MODULE_ORDER = [
  'quote_overview', 'valuation', 'profitability', 'growth',
  'cashflow_quality', 'solvency', 'operation_capability', 'dupont',
  'report_documents', 'ai_analysis_status',
]

const moduleEntries = computed(() => {
  const modules = debugData.value.modules || {}
  return MODULE_ORDER
    .filter(key => key in modules && key !== 'report_rag')
    .map(key => ({
      key,
      title: titles[key] || key,
      envelope: modules[key],
    }))
})

const statusPanelModules = new Set(['report_documents', 'ai_analysis_status'])
const visibleModules = computed(() => moduleEntries.value.filter(item => (
  item.envelope?.render?.has_displayable_data || item.envelope?.ok || statusPanelModules.has(item.key)
)))
const unavailableModules = computed(() => moduleEntries.value
  .filter(item => !item.envelope?.render?.has_displayable_data && !item.envelope?.ok && !statusPanelModules.has(item.key))
  .map(item => ({ key: item.key, reason: item.envelope?.render?.reason || item.envelope?.errors?.[0]?.error_code || 'UNKNOWN' })))

// 价格信息
const quoteRow = computed(() => {
  const rows = debugData.value.modules?.quote_overview?.normalized?.rows || []
  return rows[0] || {}
})
const latestPrice = computed(() => {
  const v = quoteRow.value.latest_price ?? quoteRow.value.recent_close
  return v != null ? Number(v).toFixed(2) : '—'
})
const priceLabel = computed(() => quoteRow.value.price_label || '')
const priceIsRealtime = computed(() => !!quoteRow.value.price_is_realtime)

// Phase 6T-E: 请求取消 + 序号守卫，防止股票快速切换时旧请求覆盖新页面
let _abortController = null
let _loadSeq = 0

async function load(force = false) {
  if (_abortController) _abortController.abort()
  _abortController = typeof AbortController !== 'undefined' ? new AbortController() : null
  const signal = _abortController?.signal
  const seq = ++_loadSeq

  loading.value = true
  error.value = ''
  try {
    // Phase 6T-E1: 切换股票时重置季度懒加载缓存与 tab
    quarterlyHistoryData.value = null
    quarterlyLoading.value = false
    periodTab.value = 'annual'
    // 并行加载：快照数据 + 历史数据（默认 annual，上市以来）+ 公司基本信息
    // profile=page：轻量生产展示；仅当用户打开 include raw 时请求完整 debug profile
    // 不默认 period=all / 上市以来全部季度
    const [debugResult, historyResult, basicResult] = await Promise.allSettled([
      getCompanyV2FullDebug(market.value, symbol.value, {
        include_raw: includeRaw.value,
        force_refresh: force,
        max_raw_chars: 20000,
        history: true,
        period: 'annual',
        profile: includeRaw.value ? 'debug' : 'page',
        signal,
      }),
      getCompanyV2History(market.value, symbol.value, { period: 'annual', force_refresh: force, signal }).catch(() => ({})),
      getCompanyV2StockBasic(market.value, symbol.value).catch(() => ({})),
    ])
    if (seq !== _loadSeq) return  // 已被更新的请求取代，丢弃旧结果
    if (debugResult.status === 'fulfilled') {
      debugData.value = debugResult.value
      if (debugResult.value?.history) {
        historyData.value = debugResult.value.history
      }
      if (debugResult.value?.stock_basic) {
        stockBasic.value = debugResult.value.stock_basic
      }
    } else {
      throw debugResult.reason
    }
    if (historyResult.status === 'fulfilled') {
      historyData.value = Object.keys(historyData.value || {}).length ? historyData.value : (historyResult.value || {})
    }
    if (basicResult.status === 'fulfilled') {
      stockBasic.value = Object.keys(stockBasic.value || {}).length ? stockBasic.value : (basicResult.value || {})
    }
  } catch (e) {
    if (e?.name === 'AbortError' || seq !== _loadSeq) return
    error.value = e.message || 'CompanyV2 加载失败'
    emit('load-error', e)
  } finally {
    if (seq === _loadSeq) loading.value = false
  }
}

async function refresh() {
  await refreshCompanyV2Debug(market.value, symbol.value)
  await load(true)
}

onMounted(() => load(false))
watch([market, symbol], () => load(false))
onUnmounted(() => { if (_abortController) _abortController.abort() })
</script>

<style scoped>
.company-v2-page {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0 80px;
  color: #111827;
}
.company-v2-page-embedded { width: 100%; padding: 0 0 16px; }
.cv2-hero {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 18px;
}
.cv2-hero-center { flex: 1; }
.cv2-hero h1 { margin: 0 0 6px; font-size: 22px; font-weight: 700; }
.cv2-company-name { color: #111827; }
.cv2-hero-meta {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-bottom: 6px;
}
.cv2-hero-code {
  font-size: 13px; font-weight: 600; color: #374151;
  background: #f3f4f6; padding: 2px 8px; border-radius: 4px;
}
.cv2-hero-exchange, .cv2-hero-industry {
  font-size: 12px; color: #6b7280;
  background: #f9fafb; padding: 2px 8px; border-radius: 4px;
  border: 1px solid #e5e7eb;
}
.cv2-hero-listdate {
  font-size: 12px; color: #9ca3af;
}
.cv2-price-label {
  margin: 4px 0 0; font-size: 14px; color: #374151;
  display: flex; gap: 6px; align-items: baseline;
}
.cv2-price-value { font-size: 22px; font-weight: 700; color: #111827; }
.cv2-non-realtime { font-size: 11px; color: #f59e0b; background: #fef3c7; padding: 1px 5px; border-radius: 3px; }
.cv2-price-source { font-size: 11px; color: #9ca3af; }
.cv2-hero-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.cv2-history-range { margin: 4px 0 0; font-size: 12px; color: #6b7280; }
.cv2-range-truncated { color: #92400e; }
.cv2-period-tabs { display: inline-flex; border: 1px solid #d1d5db; border-radius: 8px; overflow: clip; }
.cv2-period-tab {
  border: none; background: #fff; padding: 6px 12px; font-size: 13px;
  color: #4b5563; cursor: pointer;
}
.cv2-period-tab.active { background: #111827; color: #fff; }
.cv2-raw-switch { display: flex; align-items: center; gap: 8px; color: #4b5563; font-size: 13px; }
.cv2-back { border: 1px solid #d1d5db; background: #fff; border-radius: 8px; padding: 8px 12px; cursor: pointer; flex-shrink: 0; }
.cv2-loading, .cv2-error { padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }
.cv2-debug-details { margin-top: 4px; margin-bottom: 16px; }
.cv2-debug-summary {
  cursor: pointer; font-size: 13px; color: #6b7280; padding: 6px 10px;
  border: 1px solid #e5e7eb; border-radius: 6px; background: #f9fafb;
  list-style: none; user-select: none;
}
.cv2-debug-summary::-webkit-details-marker { display: none; }
.cv2-debug-summary::before { content: '▶ '; font-size: 10px; }
.cv2-debug-details[open] .cv2-debug-summary::before { content: '▼ '; }
.cv2-disclaimer {
  margin-top: 32px; padding: 12px 16px;
  font-size: 11px; color: #9ca3af;
  border-top: 1px solid #f3f4f6; line-height: 1.6;
}
.cv2-bottom-sentinel { height: 1px; }
</style>
