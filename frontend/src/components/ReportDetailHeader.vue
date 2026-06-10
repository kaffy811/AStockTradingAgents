<template>
  <div class="rdh-card card">

    <!-- ── Loading skeleton ───────────────────────────────────────────────── -->
    <div v-if="loading" class="rdh-loading">
      <span class="spinner"></span>
      <span class="rdh-loading-text">加载报告中…</span>
    </div>

    <template v-else>
      <div class="rdh-grid">

        <!-- ── Left: 报告对象身份 ─────────────────────────────────────────── -->
        <div class="rdh-identity">
          <h2 class="rdh-name">
            <template v-if="report?.stock_name">
              {{ report.stock_name }}
            </template>
            <template v-else-if="report?.market && report?.symbol">
              {{ report.market }}/{{ report.symbol }}
            </template>
            <template v-else>报告详情</template>
          </h2>

          <div class="rdh-meta">
            <template v-if="report?.stock_name && report?.market">
              <span class="rdh-market-badge">{{ report.market }}</span>
              <span class="rdh-symbol">{{ report.symbol }}</span>
            </template>
            <span :class="['rdh-scope-badge', scopeBadgeClass]">
              {{ scopeLabel }}
            </span>
            <span v-if="langBadge" class="rdh-lang-badge">{{ langBadge }}</span>
            <span v-if="report?.auto_saved" class="rdh-tag">自动保存</span>
            <span v-else-if="report" class="rdh-tag">手动保存</span>
            <span v-if="engineLabel" class="rdh-tag rdh-tag--engine">{{ engineLabel }}</span>
          </div>

          <div v-if="report?.created_at" class="rdh-time">
            {{ formatTime(report.created_at) }}
          </div>
          <div v-else-if="report" class="rdh-time rdh-time--unknown">时间未知</div>
        </div>

        <!-- ── Right: 快捷操作 ───────────────────────────────────────────── -->
        <div class="rdh-actions">
          <button class="btn btn-sm btn-secondary rdh-btn" @click="emit('back')">
            ← 返回
          </button>
          <button
            class="btn btn-sm btn-secondary rdh-btn"
            :disabled="!report?.market || !report?.symbol"
            @click="emit('go-stock')"
          >
            股票详情
          </button>
          <button
            class="btn btn-sm btn-secondary rdh-btn"
            :disabled="!report?.market || !report?.symbol"
            @click="emit('reanalyze')"
          >
            重新分析
          </button>
          <DownloadMenu v-if="report" :result="report" />
          <button
            class="btn btn-sm btn-danger rdh-btn"
            :disabled="!report"
            @click="emit('delete')"
          >
            删除报告
          </button>
        </div>

      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DownloadMenu from './DownloadMenu.vue'

// ── Props / emits ─────────────────────────────────────────────────────────────
const props = defineProps({
  report:  { type: Object,  default: null  },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['back', 'go-stock', 'reanalyze', 'delete'])

// ── Scope ──────────────────────────────────────────────────────────────────────
const _SCOPE_LABELS = {
  comprehensive:         '综合分析',
  technical_only:        '仅技术面',
  fundamental_only:      '仅基本面',
  peer_only:             '仅同行对比',
  news_only:             '仅新闻面',
  technical_fundamental: '技术+基本面',
}

const scopeLabel = computed(() => {
  const s = props.report?.analysis_scope || props.report?.metadata?.analysis_scope
  return _SCOPE_LABELS[s] || '综合分析'
})

const scopeBadgeClass = computed(() => {
  const s = props.report?.analysis_scope || props.report?.metadata?.analysis_scope
  return (!s || s === 'comprehensive') ? 'scope--comprehensive' : 'scope--partial'
})

const _LANG_LABELS_SHORT = {
  'zh-CN': null,
  'en-US': 'EN',
  'zh-TW': '繁中',
  'ja-JP': 'JA',
  'ko-KR': 'KO',
  'es-ES': 'ES',
}
const langBadge = computed(() => {
  const lang = props.report?.output_language || props.report?.metadata?.output_language
  if (!lang || lang === 'zh-CN') return null
  return _LANG_LABELS_SHORT[lang] || lang
})

// ── Engine badge ───────────────────────────────────────────────────────────────
const _ENGINE_LABELS = {
  custom_coordinator: '自定义多Agent',
  langgraph:          'LangGraph灰度',
}

const engineLabel = computed(() => {
  const e = props.report?.metadata?.workflow_engine
  return e ? (_ENGINE_LABELS[e] || e) : ''
})

// ── Time formatter ─────────────────────────────────────────────────────────────
function formatTime(ts) {
  if (!ts) return '时间未知'
  try {
    return new Date(ts).toLocaleString('zh-CN', {
      year:   'numeric',
      month:  'numeric',
      day:    'numeric',
      hour:   '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ts
  }
}
</script>

<style scoped>
.rdh-card {
  padding: 18px 24px;
  margin-bottom: 0;
}

/* ── Loading ── */
.rdh-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  color: var(--muted);
  font-size: 13px;
}

.rdh-loading-text { font-size: 13px; color: var(--muted); }

/* ── Grid ── */
.rdh-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 20px;
  align-items: start;
}

/* ── Identity ── */
.rdh-identity {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.rdh-name {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rdh-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.rdh-market-badge {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 2px 7px;
  font-size: 11px;
  font-weight: 700;
}

.rdh-symbol {
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.rdh-scope-badge {
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  padding: 2px 8px;
  white-space: nowrap;
  border: 1px solid transparent;
}

.scope--comprehensive {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

.scope--partial {
  color: var(--muted);
  background: var(--surface2);
  border-color: var(--border);
}

.rdh-tag {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 7px;
  white-space: nowrap;
}

.rdh-lang-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  color: var(--status-warn-text, #b45309);
  background: var(--status-warn-bg, #fef3c7);
  border: 1px solid var(--status-warn-ring, #fcd34d);
}

.rdh-tag--engine {
  color: var(--accent-secondary);
  background: var(--accent-glow);
  border-color: var(--border-glow);
}

.rdh-time {
  font-size: 12px;
  color: var(--muted);
}

.rdh-time--unknown {
  font-style: italic;
}

/* ── Actions ── */
.rdh-actions {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 7px;
  justify-content: flex-end;
}

.rdh-btn {
  white-space: nowrap;
}

.btn-danger {
  background: var(--status-up-bg);
  color: var(--danger);
  border: 1px solid var(--status-up-ring);
}

.btn-danger:hover:not(:disabled) {
  background: var(--status-up-ring);
}

/* ── Mobile ── */
@media (max-width: 600px) {
  .rdh-card { padding: 14px 16px; }

  .rdh-grid {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .rdh-name { font-size: 17px; }

  .rdh-actions {
    justify-content: flex-start;
  }
}
</style>
