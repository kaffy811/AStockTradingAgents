<template>
  <div class="research-panel">
    <div class="card-title">本 APP 研究结论</div>

    <div v-if="loading" class="state-row">
      <span class="spinner"></span>
      <span class="state-text">加载分析报告…</span>
    </div>

    <template v-else-if="latestReport">
      <!-- Meta row: scope badge + auto-saved + time -->
      <div class="rp-meta">
        <span :class="['rp-scope-badge', isPartial ? 'badge-partial' : '']">
          {{ formatScopeLabel(latestReport.analysis_scope) }}
        </span>
        <span v-if="latestReport.auto_saved" class="rp-auto-saved">自动保存</span>
        <span class="rp-time">{{ formatTime(latestReport.created_at) }}</span>
      </div>

      <!-- DataQualitySummary — only after full report loads -->
      <DataQualitySummary
        v-if="latestFullReport"
        :result="latestFullReport"
      />
      <div v-else-if="fullReportLoading" class="state-row state-row--sm">
        <span class="spinner spinner--sm"></span>
        <span class="state-text">加载完整报告数据…</span>
      </div>

      <!-- Summary excerpt -->
      <div v-if="summaryExcerpt" class="rp-excerpt">{{ summaryExcerpt }}</div>

      <!-- Action buttons -->
      <div class="rp-actions">
        <button class="btn btn-sm btn-primary" @click="onViewReport">
          查看完整报告
        </button>
        <button class="btn btn-sm btn-secondary" @click="onReanalyze">
          重新分析
        </button>
        <button class="btn btn-sm btn-ghost" :disabled="!summaryExcerpt" @click="onCopy">
          {{ copyLabel }}
        </button>
      </div>
    </template>

    <!-- No report yet -->
    <EmptyState
      v-else
      icon="🔍"
      title="暂无研究结论"
      message="尚未对该股票进行综合分析，点击下方按钮生成第一份研究报告。"
      action-text="生成分析"
      :compact="true"
      @action="onReanalyze"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { copyText } from '../utils/reportText.js'
import { formatScopeLabel } from '../utils/marketFormat.js'
import { goReportDetail, goAnalyze } from '../utils/navigation.js'
import DataQualitySummary from './DataQualitySummary.vue'
import EmptyState from './EmptyState.vue'

const props = defineProps({
  market:            { type: String, required: true },
  symbol:            { type: String, required: true },
  stockName:         { type: String, default: '' },
  latestReport:      { type: Object, default: null },
  latestFullReport:  { type: Object, default: null },
  fullReportLoading: { type: Boolean, default: false },
  summaryExcerpt:    { type: String, default: '' },
  loading:           { type: Boolean, default: false },
})

const router    = useRouter()
const copyLabel = ref('复制摘要')

const isPartial = computed(() => {
  const s = props.latestReport?.analysis_scope
  return s && s !== 'comprehensive'
})

function formatTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString('zh-CN', {
      month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch { return ts }
}

function onViewReport() {
  if (props.latestReport?.id) goReportDetail(router, props.latestReport.id)
}

function onReanalyze() {
  goAnalyze(router, props.market, props.symbol)
}

async function onCopy() {
  if (!props.summaryExcerpt) return
  const ok = await copyText(props.summaryExcerpt)
  if (ok) {
    copyLabel.value = '已复制 ✓'
    setTimeout(() => { copyLabel.value = '复制摘要' }, 2000)
  }
}
</script>

<style scoped>
/* ── Meta row ── */
.rp-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.rp-scope-badge {
  font-size: 11px;
  font-weight: 600;
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 1px 7px;
  white-space: nowrap;
  border: 1px solid var(--status-info-ring);
}

.rp-scope-badge.badge-partial {
  background: var(--surface2);
  color: var(--muted);
  border-color: var(--border);
}

.rp-auto-saved {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 5px;
}

.rp-time {
  font-size: 12px;
  color: var(--muted);
}

/* ── Excerpt ── */
.rp-excerpt {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.7;
  margin: 12px 0;
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Actions ── */
.rp-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.btn-ghost {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  cursor: pointer;
  border-radius: 6px;
  font-size: 12px;
  padding: 5px 12px;
  transition: background 0.12s, color 0.12s;
}

.btn-ghost:hover:not(:disabled) {
  background: var(--surface2);
  color: var(--text);
}

.btn-ghost:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ── State row (local copy for scoped styles) ── */
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

/* ── Mobile ── */
@media (max-width: 540px) {
  .rp-actions .btn { flex: 1; text-align: center; min-width: 0; }
}
</style>
