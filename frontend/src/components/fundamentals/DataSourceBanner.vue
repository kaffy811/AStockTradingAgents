<template>
  <div v-if="shouldShow && !dismissed" class="dsb-root">
    <!-- Type rows -->
    <div class="dsb-rows">
      <div
        v-for="type in bannerTypes" :key="type"
        :class="['dsb-row', { 'dsb-type-info': type === 'market_unavailable_financial_ok' }]"
      >
        <span class="dsb-icon">{{ typeIcon(type) }}</span>
        <span class="dsb-msg">{{ typeMsg(type) }}</span>
      </div>
      <!-- Generic fallback when visible but no classified types -->
      <div v-if="bannerTypes.length === 0" class="dsb-row">
        <span class="dsb-icon">⚠️</span>
        <span class="dsb-msg">部分模块数据不完整，请以已披露财报为准。</span>
      </div>
    </div>

    <!-- Details toggle（auth 错误不进入 provider 错误列表，Phase 6N-8A）-->
    <button
      v-if="sanitizedErrors.length && !hasAuthError"
      class="dsb-toggle"
      @click="showDetails = !showDetails"
    >{{ showDetails ? '收起详情' : '查看详情' }}</button>

    <!-- Error details -->
    <ul v-if="showDetails && sanitizedErrors.length && !hasAuthError" class="dsb-details">
      <li v-for="(err, i) in sanitizedErrors" :key="i" class="dsb-detail-item">{{ err }}</li>
    </ul>

    <!-- Dismiss -->
    <button class="dsb-close" @click="dismiss" aria-label="关闭">×</button>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  errors:          { type: Array,   default: () => [] },
  visible:         { type: Boolean, default: false },
  symbol:          { type: String,  default: '' },
  source:          { type: Object,  default: () => ({}) },
  data:            { type: Object,  default: () => ({}) },
  /** True when BaoStock financial modules (growth/profitability/…) are known OK.
   *  Enables a gentler "market data limited, financial data OK" banner type. */
  financialDataOk: { type: Boolean, default: false },
  /** Phase 6N-8A: true when any request failed with HTTP 401.
   *  Auth errors must show a login prompt and suppress ALL provider copy. */
  authRequired: { type: Boolean, default: false },
})

const showDetails = ref(false)
const dismissed   = ref(false)

// ── Dismiss per session ──────────────────────────────────────────────────────
function getStorageKey() {
  return `cfp_banner_dismissed_${props.symbol || 'default'}`
}

function dismiss() {
  dismissed.value = true
  try { sessionStorage.setItem(getStorageKey(), '1') } catch {}
}

function checkDismissed() {
  try { dismissed.value = !!sessionStorage.getItem(getStorageKey()) } catch { dismissed.value = false }
}

watch(() => props.symbol, () => {
  showDetails.value = false
  checkDismissed()
}, { immediate: true })

watch(() => props.visible, () => {
  showDetails.value = false
  checkDismissed()
})

// ── Sanitize errors (strip Python tracebacks) ────────────────────────────────
const sanitizedErrors = computed(() =>
  props.errors
    .map(e => (typeof e === 'string' ? e : String(e || ''))
      .replace(/Traceback[\s\S]*/g, '')
      .replace(/File "[^"]*"[^\n]*/g, '')
      .trim()
    )
    .filter(Boolean)
)

// ── Classification ───────────────────────────────────────────────────────────
// Phase 6N-8A: auth errors detected from prop or error text.
// When auth fails, ONLY the login prompt is shown — provider copy is suppressed
// (HTTP 401 is not a data-source failure).
const hasAuthError = computed(() => {
  if (props.authRequired) return true
  return /登录已过期|请重新登录|AUTH_REQUIRED|认证失败/.test(sanitizedErrors.value.join(' '))
})

const bannerTypes = computed(() => {
  if (hasAuthError.value) return ['auth_required']
  if (!props.visible && !props.errors.length) return []
  const types = new Set()
  const errText = sanitizedErrors.value.join(' ')
  if (/TUSHARE_TOKEN 未配置|Token 未配置|AI API Key 未配置/i.test(errText)) types.add('no_token')
  if (/ETL 不足|industry_rank snapshot not available|行业排名快照不存在/i.test(errText)) types.add('etl_missing')
  if (/均无数据|income 和 fina_indicator 均无数据/.test(errText)) types.add('upstream_empty')
  // Phase 6N-8B: cache timeout vs provider failure must be distinguished
  if (/TimeoutError|cache.*unavailable|CACHE_UNAVAILABLE/i.test(errText)) types.add('cache_timeout')
  // Phase 6N-8B: network failure (RemoteDisconnected, provider unavailable)
  if (/RemoteDisconnected|QUOTE_PROVIDER_UNAVAILABLE|provider.*network|network.*error/i.test(errText)) types.add('provider_network')
  // Phase 6N-8B: provider returned empty (not a network error)
  if (/PROVIDER_EMPTY|DATA_SOURCE_EMPTY|免费源.*未返回|未返回数据/i.test(errText)) types.add('provider_empty')
  // Phase 6N-8B: rows hidden because all fields were null
  if (/all.?null|全空|核心字段.*为空/i.test(errText)) types.add('all_null_rows_hidden')
  // Phase 6N-8B: PDF not found
  if (/REPORT_PDF_NOT_FOUND|暂未找到.*PDF|PDF.*未找到/i.test(errText)) types.add('pdf_not_found')
  // Phase 6A: free data source banner
  const actualSource = props.source?.actual || ''
  if (actualSource === 'baostock' || actualSource === 'akshare') {
    if (props.financialDataOk) {
      // BaoStock financial modules are OK — only market/valuation data is limited
      types.add('market_unavailable_financial_ok')
    } else {
      types.add('free_source_limited')
    }
  }
  // Phase 6N-4: when financial data is OK but there are unavailable (market) sections
  if (props.financialDataOk && props.visible && types.size === 0 && !errText.length) {
    types.add('market_unavailable_financial_ok')
  }
  // Phase 6A: module removed in free mode
  if (props.data?.removed === true) types.add('module_removed')
  return [...types]
})

const shouldShow = computed(() =>
  props.visible || props.errors.length > 0 || props.authRequired
)

function typeIcon(type) {
  if (type === 'auth_required')               return '🔒'
  if (type === 'no_token')                    return '⚠️'
  if (type === 'etl_missing')                 return 'ℹ️'
  if (type === 'upstream_empty')              return '📭'
  if (type === 'free_source_limited')         return 'ℹ️'
  if (type === 'market_unavailable_financial_ok') return 'ℹ️'
  if (type === 'module_removed')              return '🚫'
  if (type === 'cache_timeout')               return '⏱'
  if (type === 'provider_network')            return '📡'
  if (type === 'provider_empty')              return '📭'
  if (type === 'all_null_rows_hidden')        return 'ℹ️'
  if (type === 'pdf_not_found')               return '📄'
  return '⚠️'
}

function typeMsg(type) {
  if (type === 'auth_required')
    return '登录已过期，请重新登录后查看行情、新闻和财报数据。'
  if (type === 'no_token')
    return '真实财务数据源未配置，当前仅展示可用缓存、Mock 数据或占位内容。'
  if (type === 'etl_missing')
    return '部分全市场/行业数据尚未完成 ETL，相关排名和对比模块可能为空。'
  if (type === 'upstream_empty')
    return '上游暂未返回该股票的部分财务数据，相关模块已显示为空状态。'
  if (type === 'free_source_limited')
    return '当前为公开免费数据源（BaoStock/AkShare），部分财务字段可能缺失或口径不一致，数据仅供参考。'
  if (type === 'market_unavailable_financial_ok')
    return '行情/估值数据暂不可用（AkShare 受当前环境限制）；BaoStock 财务基本面数据已正常加载，成长、盈利、现金流等分析模块可正常使用。'
  if (type === 'module_removed')
    return '该模块在当前数据源配置下不可用。'
  // Phase 6N-8B
  if (type === 'cache_timeout')
    return '缓存服务暂时不可用，已尝试直接读取公开数据源。'
  if (type === 'provider_network')
    return '部分公开数据源网络暂不可用，已展示可用缓存或其他来源数据。'
  if (type === 'provider_empty')
    return '部分字段当前免费数据源未返回，已展示可用字段。'
  if (type === 'all_null_rows_hidden')
    return '部分模块返回记录但核心字段为空，已自动隐藏。'
  if (type === 'pdf_not_found')
    return '暂未找到可确认年报 PDF，已记录搜索来源和年份。'
  return ''
}
</script>

<style scoped>
.dsb-root {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #fffbeb;
  border: 1px solid #f59e0b;
  border-radius: 8px;
  padding: 10px 40px 10px 14px;
  font-size: 13px;
  color: #92400e;
  position: relative;
}

/* Info variant — used when financial data is OK and only market data is limited */
.dsb-root:has(.dsb-type-info) {
  background: #eff6ff;
  border-color: #3b82f6;
  color: #1e40af;
}
.dsb-root:has(.dsb-type-info) .dsb-close { color: #1e40af; }
.dsb-root:has(.dsb-type-info) .dsb-toggle { border-color: #3b82f6; color: #1e40af; }
.dsb-root:has(.dsb-type-info) .dsb-toggle:hover { background: #dbeafe; }

.dsb-rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dsb-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.dsb-icon {
  flex-shrink: 0;
  font-size: 14px;
  line-height: 1.5;
}

.dsb-msg {
  flex: 1;
  line-height: 1.5;
}

.dsb-toggle {
  align-self: flex-start;
  background: none;
  border: 1px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  cursor: pointer;
  padding: 2px 8px;
  transition: background 0.15s;
}
.dsb-toggle:hover { background: #fef3c7; }

.dsb-details {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dsb-detail-item {
  font-size: 12px;
  line-height: 1.4;
  color: #78350f;
  word-break: break-all;
}

.dsb-close {
  position: absolute;
  top: 8px;
  right: 10px;
  background: none;
  border: none;
  font-size: 18px;
  color: #92400e;
  cursor: pointer;
  line-height: 1;
  padding: 0 2px;
  opacity: 0.7;
  transition: opacity 0.15s;
}
.dsb-close:hover { opacity: 1; }
</style>
