<template>
  <div
    class="wsc-card card"
    :class="{ 'wsc-card--selected': selected && bulkMode }"
    @click="bulkMode ? emit('toggle-select') : undefined"
  >

    <!-- ── Top row: checkbox (bulk) + identity + quote ────────────────────────── -->
    <div class="wsc-top">

      <!-- Bulk checkbox -->
      <div v-if="bulkMode" class="wsc-checkbox-wrap">
        <span :class="['wsc-checkbox', selected ? 'wsc-checkbox--on' : 'wsc-checkbox--off']">
          {{ selected ? '☑' : '☐' }}
        </span>
      </div>

      <!-- Identity -->
      <div class="wsc-identity">
        <div class="wsc-name-row">
          <h3 class="wsc-name">{{ item.name || item.symbol }}</h3>
          <span class="wsc-market-badge">{{ item.market }}</span>
          <span class="wsc-symbol">{{ item.symbol }}</span>
        </div>
        <div class="wsc-meta">
          <span v-if="industryLabel" class="wsc-industry">{{ industryLabel }}</span>
        </div>
      </div>

      <!-- Quote -->
      <div class="wsc-quote">
        <template v-if="item.quote_status !== 'failed' && item.latest_price != null">
          <span class="wsc-price">{{ fmtPrice(item.latest_price) }}</span>
          <span v-if="item.change_pct != null" :class="['wsc-chg', changePctClass(item.change_pct)]">
            {{ fmtChangePct(item.change_pct) }}
          </span>
        </template>
        <span v-else-if="item.quote_status === 'failed'" class="wsc-unavail">{{ t('wl_card_quote_fail') }}</span>
        <span v-else class="wsc-unavail">—</span>
      </div>

    </div>

    <!-- ── Latest report ──────────────────────────────────────────────────────── -->
    <div class="wsc-report">
      <template v-if="item.latest_report">
        <span class="wsc-report-time">{{ t('wl_card_recent') }}{{ formatTime(item.latest_report.created_at) }}</span>
        <span v-if="item.latest_report.analysis_scope" class="wsc-report-scope">
          {{ scopeLabel(item.latest_report.analysis_scope) }}
        </span>
        <span v-if="item.latest_report.warnings?.length" class="wsc-warn">
          ⚠ {{ t('wl_card_warnings', { n: item.latest_report.warnings.length }) }}
        </span>
      </template>
      <span v-else class="wsc-no-report">{{ t('wl_card_no_report') }}</span>
    </div>

    <!-- ── Note ───────────────────────────────────────────────────────────────── -->
    <div class="wsc-note-wrap">
      <template v-if="!isEditingNote">
        <div
          class="wsc-note"
          :class="{ 'wsc-note--clickable': !bulkMode }"
          @click.stop="!bulkMode && emit('edit-note')"
        >
          <span v-if="item.note">{{ item.note }}</span>
          <span v-else class="wsc-note-placeholder">{{ t('wl_card_note_placeholder') }}</span>
        </div>
      </template>
      <template v-else>
        <div class="wsc-note-edit" @click.stop>
          <textarea
            ref="textareaRef"
            :value="editNoteValue"
            class="wsc-textarea"
            rows="2"
            :disabled="isSavingNote"
            :placeholder="t('wl_card_note_hint')"
            @input="emit('update:editNoteValue', $event.target.value)"
            @keydown="onNoteKeydown"
            @blur="emit('save-note')"
          />
          <span v-if="isSavingNote" class="spinner spinner--sm" />
        </div>
        <div v-if="noteError" class="wsc-note-error">{{ noteError }}</div>
      </template>
    </div>

    <!-- ── Actions (hidden in bulk mode) ─────────────────────────────────────── -->
    <div v-if="!bulkMode" class="wsc-actions" @click.stop>
      <button class="btn btn-primary btn-sm wsc-btn" @click="emit('detail')">
        {{ t('wl_card_detail') }}
      </button>
      <button class="btn btn-secondary btn-sm wsc-btn" @click="emit('analyze')">
        {{ item.latest_report ? t('wl_card_reanalyze') : t('wl_card_analyze') }}
      </button>
      <button
        v-if="item.latest_report"
        class="btn btn-secondary btn-sm wsc-btn"
        @click="emit('history')"
      >
        {{ t('wl_card_recent_rpt') }}
      </button>
      <button class="btn btn-secondary btn-sm wsc-btn" @click="emit('history')">
        {{ t('wl_card_history') }}
      </button>
      <button class="btn btn-sm btn-danger wsc-btn" @click="emit('delete')">
        {{ t('wl_card_delete') }}
      </button>
    </div>

  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { formatPrice, formatChangePct, changePctClass } from '../utils/marketFormat.js'
import { formatTime } from '../utils/warningMap.js'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  item:           { type: Object,  required: true },
  selected:       { type: Boolean, default: false },
  bulkMode:       { type: Boolean, default: false },
  isEditingNote:  { type: Boolean, default: false },
  editNoteValue:  { type: String,  default: '' },
  isSavingNote:   { type: Boolean, default: false },
  noteError:      { type: String,  default: '' },
})

const emit = defineEmits([
  'toggle-select',
  'detail',
  'analyze',
  'history',
  'delete',
  'edit-note',
  'update:editNoteValue',
  'save-note',
  'cancel-note',
])

const textareaRef = ref(null)

// Auto-focus textarea when editing starts
watch(() => props.isEditingNote, (val) => {
  if (val) nextTick(() => textareaRef.value?.focus())
})

// ── Scope label ───────────────────────────────────────────────────────────────
function scopeLabel(s) {
  const map = {
    comprehensive:         () => t('badge_comprehensive'),
    technical_only:        () => t('badge_technical'),
    fundamental_only:      () => t('badge_fundamental'),
    peer_only:             () => t('badge_peer'),
    news_only:             () => t('badge_news'),
    technical_fundamental: () => t('badge_tech_fund'),
  }
  return (map[s] || (() => s || ''))()
}

// ── Industry fallback ─────────────────────────────────────────────────────────
const industryLabel = computed(() => props.item.industry_name || '')

// ── Formatters ────────────────────────────────────────────────────────────────
function fmtPrice(v) { return formatPrice(v) }
function fmtChangePct(v) { return formatChangePct(v) }

// ── Note keydown ──────────────────────────────────────────────────────────────
function onNoteKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    emit('save-note')
  } else if (event.key === 'Escape') {
    emit('cancel-note')
  }
}
</script>

<style scoped>
.wsc-card {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: default;
  transition: box-shadow 0.15s;
}

.wsc-card--selected {
  box-shadow: 0 0 0 2px var(--accent);
  cursor: pointer;
}

/* ── Top row ── */
.wsc-top {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

/* ── Checkbox ── */
.wsc-checkbox-wrap {
  flex-shrink: 0;
  padding-top: 2px;
}

.wsc-checkbox {
  font-size: 18px;
  cursor: pointer;
  color: var(--muted);
}

.wsc-checkbox--on { color: var(--accent); }

/* ── Identity ── */
.wsc-identity {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wsc-name-row {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}

.wsc-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}

.wsc-market-badge {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.wsc-symbol {
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.wsc-meta { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }

.wsc-industry {
  font-size: 11px;
  color: var(--accent);
  background: var(--status-info-bg);
  border-radius: 4px;
  padding: 1px 6px;
  white-space: nowrap;
}

/* ── Quote ── */
.wsc-quote {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
}

.wsc-price {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  font-family: monospace;
}

.wsc-chg {
  font-size: 12px;
  font-weight: 600;
}

.wsc-chg.up   { color: var(--danger);  }
.wsc-chg.down { color: var(--success); }

.wsc-unavail {
  font-size: 11px;
  color: var(--muted);
  font-style: italic;
}

/* ── Report row ── */
.wsc-report {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
}

.wsc-report-time { color: var(--muted); }
.wsc-report-scope {
  color: var(--accent);
  background: var(--status-info-bg);
  border-radius: 3px;
  padding: 1px 5px;
}
.wsc-warn { color: var(--warn); }
.wsc-no-report { color: var(--muted); font-style: italic; }

/* ── Note ── */
.wsc-note-wrap { min-width: 0; }

.wsc-note {
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-radius: 4px;
  padding: 2px 4px;
  margin-left: -4px;
}

.wsc-note--clickable {
  cursor: text;
  transition: background 0.15s;
}

.wsc-note--clickable:hover { background: var(--surface2); }

.wsc-note-placeholder {
  font-style: italic;
  opacity: 0.6;
}

.wsc-note-edit {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.wsc-textarea {
  flex: 1;
  min-width: 0;
  background: var(--surface2);
  border: 1px solid var(--accent);
  border-radius: 4px;
  color: var(--text);
  font-size: 12px;
  padding: 4px 8px;
  resize: none;
  outline: none;
  line-height: 1.5;
  font-family: inherit;
}

.wsc-textarea:focus { box-shadow: 0 0 0 2px var(--status-info-ring); }
.wsc-textarea:disabled { opacity: 0.5; cursor: not-allowed; }

.wsc-note-error {
  font-size: 11px;
  color: var(--danger);
  margin-top: 3px;
}

/* ── Actions ── */
.wsc-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}

.wsc-btn { white-space: nowrap; }

.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-primary);
}

.btn-danger {
  background: var(--status-up-bg);
  color: var(--danger);
  border: 1px solid var(--status-up-ring);
}

.btn-danger:hover:not(:disabled) { background: var(--status-up-ring); }

.spinner--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
  margin-top: 4px;
  flex-shrink: 0;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .wsc-card { padding: 12px 14px; }

  .wsc-name { max-width: 120px; }

  .wsc-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .wsc-btn {
    width: 100%;
    text-align: center;
    justify-content: center;
  }
}
</style>
