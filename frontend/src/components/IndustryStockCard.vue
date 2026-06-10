<template>
  <div class="isc-card card">

    <!-- Top row: rank + identity + change -->
    <div class="isc-header">

      <div class="isc-rank-block">
        <span :class="['isc-rank-badge', rankClass(item.rank)]">{{ item.rank ?? '—' }}</span>
        <span class="isc-score">{{ fmtScore(item.hot_score) }}</span>
      </div>

      <div class="isc-identity">
        <span class="isc-name">{{ item.stock_name || item.symbol }}</span>
        <span class="isc-symbol-row">
          <span class="isc-market-badge">{{ market }}</span>
          <span class="isc-symbol">{{ item.symbol }}</span>
        </span>
      </div>

      <div class="isc-change-block">
        <span :class="['isc-change', changePctClass(item.change_pct)]">
          {{ formatChangePct(item.change_pct) }}
        </span>
        <span class="isc-amount">{{ formatAmount(item.amount) }}</span>
      </div>

    </div>

    <!-- Data source -->
    <div v-if="item.data_source" class="isc-source">
      {{ t('ind_card_source') }}{{ item.data_source }}
    </div>

    <!-- Actions -->
    <div class="isc-actions">
      <button class="btn btn-sm btn-secondary" @click="emit('detail')">{{ t('ind_card_detail') }}</button>
      <button class="btn btn-sm btn-secondary" @click="emit('analyze')">{{ t('ind_card_analyze') }}</button>
      <button class="btn btn-sm btn-secondary" @click="emit('history')">{{ t('ind_card_history') }}</button>
      <button
        class="btn btn-sm"
        :class="addBtnClass"
        :disabled="addingStatus === 'adding'"
        @click="onAddClick"
      >
        <span v-if="addingStatus === 'adding'" class="spinner"></span>
        {{ addBtnLabel }}
      </button>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatAmount, formatChangePct, changePctClass } from '../utils/marketFormat.js'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  item:         { type: Object, required: true },
  market:       { type: String, default: 'CN' },
  addingStatus: { type: String, default: '' },   // idle | adding | added | exists | error
})

const emit = defineEmits(['detail', 'analyze', 'history', 'add-watchlist'])

function rankClass(rank) {
  if (rank === 1) return 'isc-rank--gold'
  if (rank === 2) return 'isc-rank--silver'
  if (rank === 3) return 'isc-rank--bronze'
  return 'isc-rank--normal'
}

function fmtScore(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return Number(v).toFixed(1)
}

const addBtnLabel = computed(() => {
  if (props.addingStatus === 'adding') return t('ind_card_adding')
  if (props.addingStatus === 'added')  return t('ind_card_added')
  if (props.addingStatus === 'exists') return t('ind_card_in_wl')
  if (props.addingStatus === 'error')  return t('ind_card_retry')
  return t('ind_card_add_wl')
})

const addBtnClass = computed(() => {
  if (props.addingStatus === 'added' || props.addingStatus === 'exists') return 'isc-btn--added'
  if (props.addingStatus === 'error') return 'isc-btn--err'
  return 'btn-secondary'
})

function onAddClick() {
  if (props.addingStatus === 'added' || props.addingStatus === 'exists') return
  emit('add-watchlist')
}
</script>

<style scoped>
.isc-card {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── Header ── */
.isc-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

/* Rank block */
.isc-rank-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  min-width: 36px;
}

.isc-rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
}

.isc-rank--gold   { background: rgba(255, 215, 0, 0.25); color: #b8860b; }
.isc-rank--silver { background: rgba(192, 192, 192, 0.25); color: #888; }
.isc-rank--bronze { background: rgba(205, 127, 50, 0.25); color: #a0522d; }
.isc-rank--normal { background: var(--surface2); color: var(--muted); }

.isc-score {
  font-size: 10px;
  color: var(--muted);
  font-family: monospace;
  white-space: nowrap;
}

/* Identity */
.isc-identity {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.isc-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.isc-symbol-row {
  display: flex;
  align-items: center;
  gap: 5px;
}

.isc-market-badge {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 10px;
  font-weight: 700;
}

.isc-symbol {
  font-size: 12px;
  font-family: monospace;
  color: var(--muted);
}

/* Change block */
.isc-change-block {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  flex-shrink: 0;
}

.isc-change {
  font-size: 15px;
  font-weight: 700;
}

.up   { color: var(--danger); }
.down { color: var(--success); }

.isc-amount {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}

/* ── Data source ── */
.isc-source {
  font-size: 11px;
  color: var(--muted);
}

/* ── Actions ── */
.isc-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.isc-btn--added {
  background: var(--status-down-bg);
  color: var(--success);
  border: 1px solid var(--status-down-ring);
}

.isc-btn--err {
  background: var(--status-up-bg);
  color: var(--danger);
  border: 1px solid var(--status-up-ring);
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .isc-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .isc-actions .btn { width: 100%; text-align: center; }
}
</style>
