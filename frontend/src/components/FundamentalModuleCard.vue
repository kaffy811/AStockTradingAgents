<template>
  <div class="fmc-root">
    <!-- Card header -->
    <div class="fmc-header">
      <div class="fmc-title-row">
        <span class="fmc-title">{{ moduleMeta?.name_zh || moduleKey }}</span>
        <span v-if="isPlanned" class="fmc-planned-badge">即将上线</span>
        <span v-if="isLegacy" class="fmc-legacy-badge">旧版</span>
        <!-- Source badge -->
        <span v-if="sourceActual" class="fmc-source-badge">{{ sourceActual }}</span>
        <div class="fmc-header-actions">
          <!-- Export CSV button (only when data has rows) -->
          <button
            v-if="!isPlanned && hasRows"
            class="fmc-icon-btn"
            title="导出 CSV"
            @click="onExportCsv"
          >↓</button>
          <!-- Export Excel button -->
          <button
            v-if="!isPlanned && hasExportable"
            class="fmc-icon-btn"
            title="导出 Excel"
            @click="onExportXlsx"
          >XLS</button>
          <!-- Expand chart button (only when chart data available) -->
          <button
            v-if="!isPlanned && hasChart"
            class="fmc-icon-btn"
            title="放大图表"
            @click="onExpandChart"
          >⤢</button>
          <!-- Refresh button -->
          <button
            v-if="!isPlanned"
            class="fmc-icon-btn"
            :class="{ spinning: refreshing }"
            :disabled="loading || refreshing"
            title="刷新数据"
            @click="onRefresh"
          >↻</button>
          <!-- Expand/collapse -->
          <button
            class="fmc-icon-btn"
            :title="expanded ? '收起' : '展开'"
            @click="expanded = !expanded"
          >{{ expanded ? '▲' : '▼' }}</button>
        </div>
      </div>
      <p v-if="moduleMeta?.description" class="fmc-desc">{{ moduleMeta.description }}</p>
    </div>

    <!-- Collapsible content area -->
    <template v-if="expanded">
      <!-- State banners -->
      <FundamentalStateBanner v-if="isPlanned" type="info" message="该模块正在建设中，敬请期待。" />
      <template v-else-if="!loading && envelope">
        <FundamentalStateBanner v-if="envelope.errors && envelope.errors.length" type="error" :message="envelope.errors[0]" />
        <FundamentalStateBanner v-else-if="envelope.partial" type="warn" message="部分数据获取不完整，仅供参考。" />
        <FundamentalStateBanner v-else-if="envelope.stale" type="stale" message="数据来自缓存，可能非最新。" />
      </template>

      <!-- Loading -->
      <div v-if="loading || refreshing" class="fmc-loading">
        <span class="spinner"></span>
        <span class="fmc-loading-text">加载中…</span>
      </div>

      <!-- Error / empty with collapsible details -->
      <div v-else-if="!isPlanned && (!envelope || (envelope.errors && envelope.errors.length && !envelope.data))" class="fmc-error">
        <span>暂无数据{{ envelope?.errors?.[0] ? '：' + envelope.errors[0] : '' }}</span>
        <details v-if="envelope?.errors?.length > 1" class="fmc-error-details">
          <summary>查看更多错误</summary>
          <ul>
            <li v-for="(err, i) in envelope.errors" :key="i">{{ err }}</li>
          </ul>
        </details>
      </div>

      <!-- Module renderer -->
      <FundamentalModuleRenderer
        v-else-if="!isPlanned && envelope && envelope.data"
        :module-meta="moduleMeta"
        :data="envelope.data"
      />

      <!-- analyst_ratings disclaimer -->
      <div v-if="moduleKey === 'analyst_ratings'" class="fmc-disclaimer">
        ⚠️ 当前模块基于业绩预告/快报与可选第三方数据生成，不等同于完整机构一致预期或投资建议。
      </div>

      <!-- Stale timestamp -->
      <div v-if="envelope && envelope.generated_at && !loading && !refreshing" class="fmc-footer">
        更新时间：{{ fmtTime(envelope.generated_at) }}
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import FundamentalStateBanner from './FundamentalStateBanner.vue'
import FundamentalModuleRenderer from './FundamentalModuleRenderer.vue'

const props = defineProps({
  moduleMeta: { type: Object,  default: null },
  envelope:   { type: Object,  default: null },
  loading:    { type: Boolean, default: false },
  stockCode:  { type: String,  default: '' },
  defaultExpanded: { type: Boolean, default: true },
})

const emit = defineEmits(['refresh', 'expand-chart', 'export-csv', 'export-xlsx'])

const moduleKey = computed(() => props.moduleMeta?.key || '')
const isPlanned = computed(() => props.moduleMeta?.status === 'planned')
const isLegacy  = computed(() => props.moduleMeta?.status === 'legacy')

// Source badge from envelope
const sourceActual = computed(() => props.envelope?.source?.actual || null)

// Check if data has exportable rows (without running full adapter) — for CSV
const hasRows = computed(() => {
  const d = props.envelope?.data
  if (!d) return false
  return !!(
    d.series?.length ||
    d.records?.length ||
    d.rankings?.length ||
    d.periods?.length ||
    d.top10_float_holders?.length ||
    d.forecasts?.length ||
    d.forecast_items?.length ||
    d.items?.length
  )
})

// Broader check — covers rows AND scalar metrics — for Excel export
const hasExportable = computed(() => {
  const d = props.envelope?.data
  if (!d) return false
  const hasRowArrays = !!(
    d.series?.length ||
    d.records?.length ||
    d.rankings?.length ||
    d.periods?.length ||
    d.top10_float_holders?.length ||
    d.forecasts?.length ||
    d.forecast_items?.length ||
    d.items?.length
  )
  // Also exportable if there are scalar fields (metrics)
  const hasScalars = Object.values(d).some(v =>
    v !== null && v !== undefined && typeof v !== 'object'
  )
  return hasRowArrays || hasScalars
})

// Check if data has chart content
const hasChart = computed(() => {
  if (!props.envelope?.data) return false
  const chartType = props.moduleMeta?.chart_type || props.moduleMeta?.meta?.chart_type
  if (!chartType || chartType === 'none') return false
  const d = props.envelope.data
  return !!(d.series?.length || d.periods?.length || d.top10_float_holders?.length)
})

// Expand/collapse state — use defaultExpanded prop
const expanded = ref(props.defaultExpanded !== false)

// Refresh state
const refreshing = ref(false)

function onRefresh() {
  if (props.loading || refreshing.value) return
  refreshing.value = true
  emit('refresh', moduleKey.value)
  // Reset after a short guard (parent will update loading/envelope)
  setTimeout(() => { refreshing.value = false }, 800)
}

function onExportCsv() {
  emit('export-csv', { moduleKey: moduleKey.value, moduleMeta: props.moduleMeta, envelope: props.envelope })
}

function onExportXlsx() {
  emit('export-xlsx', { moduleKey: moduleKey.value, moduleMeta: props.moduleMeta, envelope: props.envelope })
}

function onExpandChart() {
  emit('expand-chart', { moduleKey: moduleKey.value, moduleMeta: props.moduleMeta, envelope: props.envelope })
}

function fmtTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString('zh-CN', {
      month: 'numeric', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return ts }
}
</script>

<style scoped>
.fmc-root {
  background: white;
  border-radius: 14px;
  padding: 16px 18px;
  box-shadow: 0 1px 5px rgba(0,0,0,.07);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.fmc-header { display: flex; flex-direction: column; gap: 4px; }
.fmc-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.fmc-title { font-size: 14px; font-weight: 600; color: var(--text); flex: 1; min-width: 0; }
.fmc-header-actions { display: flex; align-items: center; gap: 4px; margin-left: auto; flex-shrink: 0; }

.fmc-planned-badge {
  font-size: 10px; font-weight: 600; color: var(--accent);
  background: var(--status-info-bg); border-radius: 4px; padding: 1px 6px;
  border: 1px solid var(--status-info-ring);
}
.fmc-legacy-badge {
  font-size: 10px; color: var(--muted); background: var(--surface2);
  border-radius: 4px; padding: 1px 5px; border: 1px solid var(--border);
}
.fmc-source-badge {
  font-size: 10px; color: #155724; background: #d4edda;
  border-radius: 4px; padding: 1px 6px; border: 1px solid #28a745;
  font-weight: 500; white-space: nowrap;
}

.fmc-desc { font-size: 12px; color: var(--muted); margin: 0; line-height: 1.5; }
.fmc-icon-btn {
  background: none; border: 1px solid var(--border); border-radius: 6px;
  padding: 2px 7px; font-size: 13px; color: var(--muted); cursor: pointer;
  line-height: 1.5; transition: color 0.15s, border-color 0.15s;
}
.fmc-icon-btn:hover:not(:disabled) { color: var(--text); border-color: var(--accent); }
.fmc-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.fmc-icon-btn.spinning { animation: spin 0.8s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.fmc-loading { display: flex; align-items: center; gap: 8px; padding: 16px 0; color: var(--muted); font-size: 13px; }
.fmc-loading-text { color: var(--muted); font-size: 13px; }
.fmc-error { font-size: 13px; color: var(--muted); padding: 12px 0; text-align: center; }
.fmc-error-details { margin-top: 8px; font-size: 12px; text-align: left; }
.fmc-error-details summary { cursor: pointer; color: var(--accent); }
.fmc-error-details ul { margin: 6px 0 0 16px; padding: 0; list-style: disc; color: var(--muted); }
.fmc-disclaimer {
  font-size: 11px; color: #856404;
  background: #fff8e1; border-radius: 6px; padding: 8px 12px; line-height: 1.5;
}
.fmc-footer { font-size: 11px; color: var(--muted); text-align: right; border-top: 1px solid var(--border); padding-top: 8px; }
</style>
