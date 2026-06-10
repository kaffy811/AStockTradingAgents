<template>
  <div class="rlc-card card">

    <!-- ── Top row: identity + badges ────────────────────────────────────────── -->
    <div class="rlc-top">
      <div class="rlc-identity">
        <h3 class="rlc-name">
          {{ report.stock_name || `${report.market}/${report.symbol}` }}
        </h3>
        <div class="rlc-meta">
          <span class="rlc-market-badge">{{ report.market }}</span>
          <span class="rlc-symbol">{{ report.symbol }}</span>
          <span :class="['rlc-scope-badge', scopeBadgeClass]">{{ scopeText }}</span>
          <span v-if="langLabel" class="rlc-lang-badge">{{ langLabel }}</span>
          <span v-if="report.auto_saved" class="rlc-tag">{{ t('rpt_card_auto') }}</span>
          <span v-else class="rlc-tag">{{ t('rpt_card_manual') }}</span>
        </div>
      </div>

      <div class="rlc-time">{{ formatTime(report.created_at) }}</div>
    </div>

    <!-- ── Warnings hint ──────────────────────────────────────────────────────── -->
    <div v-if="warningCount > 0" class="rlc-warn">
      ⚠ {{ t('rpt_card_warn', { n: warningCount }) }}
    </div>

    <!-- ── Actions ───────────────────────────────────────────────────────────── -->
    <div class="rlc-actions">
      <button class="btn btn-sm btn-secondary rlc-btn" @click="emit('view')">
        {{ t('rpt_card_view') }}
      </button>
      <button
        class="btn btn-sm btn-secondary rlc-btn"
        :disabled="!report.market || !report.symbol"
        @click="emit('go-stock')"
      >
        {{ t('rpt_card_stock') }}
      </button>
      <button
        class="btn btn-sm btn-secondary rlc-btn"
        :disabled="!report.market || !report.symbol"
        @click="emit('reanalyze')"
      >
        {{ t('rpt_card_reanalyze') }}
      </button>
      <button
        class="btn btn-sm btn-danger rlc-btn"
        :disabled="isDeleting"
        @click="emit('delete')"
      >
        <span v-if="isDeleting" class="spinner spinner--sm"></span>
        <span v-else>{{ t('rpt_card_delete') }}</span>
      </button>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  report:     { type: Object,  required: true },
  isDeleting: { type: Boolean, default: false },
})

const emit = defineEmits(['view', 'delete', 'go-stock', 'reanalyze'])

// ── Scope ─────────────────────────────────────────────────────────────────────
function scopeLabelFn(scope) {
  const map = {
    comprehensive:         () => t('mode_comprehensive'),
    technical_only:        () => t('mode_technical'),
    fundamental_only:      () => t('mode_fundamental'),
    peer_only:             () => t('mode_peer'),
    news_only:             () => t('mode_news'),
    technical_fundamental: () => t('mode_tech_fund'),
  }
  return (map[scope] || map['comprehensive'])()
}

const scopeText = computed(() => scopeLabelFn(props.report?.analysis_scope))

const scopeBadgeClass = computed(() => {
  const s = props.report?.analysis_scope
  return (!s || s === 'comprehensive') ? 'rlc-scope-badge--comprehensive' : 'rlc-scope-badge--partial'
})

const warningCount = computed(() =>
  Array.isArray(props.report?.warnings) ? props.report.warnings.length : 0
)

const _LANG_LABELS = {
  'zh-CN': '简中',
  'en-US': 'EN',
  'zh-TW': '繁中',
  'ja-JP': 'JA',
  'ko-KR': 'KO',
  'es-ES': 'ES',
}
const langLabel = computed(() => {
  const lang = props.report?.output_language
  if (!lang || lang === 'zh-CN') return null
  return _LANG_LABELS[lang] || lang
})

// ── Time ──────────────────────────────────────────────────────────────────────
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
.rlc-card {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── Top row ── */
.rlc-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.rlc-identity {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.rlc-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rlc-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.rlc-market-badge {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
}

.rlc-symbol {
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.rlc-scope-badge {
  font-size: 10px;
  font-weight: 600;
  border-radius: 4px;
  padding: 1px 7px;
  white-space: nowrap;
  border: 1px solid transparent;
}

.rlc-scope-badge--comprehensive {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

.rlc-scope-badge--partial {
  color: var(--muted);
  background: var(--surface2);
  border-color: var(--border);
}

.rlc-lang-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  color: var(--status-warn-text, #b45309);
  background: var(--status-warn-bg, #fef3c7);
  border: 1px solid var(--status-warn-ring, #fcd34d);
}

.rlc-tag {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 6px;
}

.rlc-time {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── Warning hint ── */
.rlc-warn {
  font-size: 11px;
  color: var(--warn);
}

/* ── Actions ── */
.rlc-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rlc-btn {
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

.spinner--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .rlc-card { padding: 12px 14px; }

  .rlc-time { width: 100%; }

  .rlc-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .rlc-btn { width: 100%; text-align: center; }
}
</style>
