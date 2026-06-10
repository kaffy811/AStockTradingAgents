<template>
  <div class="wt-card card">

    <!-- ── Filter row ─────────────────────────────────────────────────────────── -->
    <div class="wt-filters">

      <!-- Market -->
      <div class="form-group wt-fg">
        <label class="wt-label">{{ t('wl_tb_market') }}</label>
        <select
          :value="filters.market"
          class="wt-select"
          @change="patchFilter('market', $event.target.value)"
        >
          <option value="">{{ t('rpt_flt_all') }}</option>
          <option value="CN">CN</option>
          <option value="HK">HK</option>
        </select>
      </div>

      <!-- Direction -->
      <div class="form-group wt-fg">
        <label class="wt-label">{{ t('wl_tb_change') }}</label>
        <select
          :value="filters.direction"
          class="wt-select"
          @change="patchFilter('direction', $event.target.value)"
        >
          <option value="">{{ t('rpt_flt_all') }}</option>
          <option value="up">{{ t('wl_tb_up_only') }}</option>
          <option value="down">{{ t('wl_tb_down_only') }}</option>
          <option value="unavail">{{ t('wl_tb_unavail') }}</option>
        </select>
      </div>

      <!-- Industry -->
      <div v-if="industries.length > 0" class="form-group wt-fg">
        <label class="wt-label">{{ t('wl_tb_industry') }}</label>
        <select
          :value="filters.industry"
          class="wt-select"
          @change="patchFilter('industry', $event.target.value)"
        >
          <option value="">{{ t('rpt_flt_all') }}</option>
          <option v-for="n in industries" :key="n" :value="n">{{ n }}</option>
        </select>
      </div>

      <!-- Report filter -->
      <div class="form-group wt-fg">
        <label class="wt-label">{{ t('wl_tb_report') }}</label>
        <select
          :value="filters.reportFilter"
          class="wt-select"
          @change="patchFilter('reportFilter', $event.target.value)"
        >
          <option value="">{{ t('rpt_flt_all') }}</option>
          <option value="has">{{ t('wl_tb_has_report') }}</option>
          <option value="none">{{ t('wl_tb_no_report') }}</option>
        </select>
      </div>

      <!-- Sort -->
      <div class="form-group wt-fg">
        <label class="wt-label">{{ t('wl_tb_sort') }}</label>
        <select
          :value="sortKey"
          class="wt-select"
          @change="emit('update:sortKey', $event.target.value)"
        >
          <option value="default">{{ t('wl_tb_sort_time') }}</option>
          <option value="change_desc">{{ t('wl_tb_sort_chg_desc') }}</option>
          <option value="change_asc">{{ t('wl_tb_sort_chg_asc') }}</option>
          <option value="symbol">{{ t('wl_tb_sort_symbol') }}</option>
          <option value="name">{{ t('wl_tb_sort_name') }}</option>
        </select>
      </div>

    </div>

    <!-- ── Action row ─────────────────────────────────────────────────────────── -->
    <div class="wt-actions">

      <!-- Bulk mode: off -->
      <template v-if="!bulkMode">
        <button class="btn btn-secondary btn-sm wt-btn" @click="emit('toggle-bulk')">
          {{ t('wl_tb_bulk') }}
        </button>
      </template>

      <!-- Bulk mode: on -->
      <template v-else>
        <span class="wt-selected-count">{{ t('wl_tb_selected', { count: selectedCount }) }}</span>
        <button class="btn btn-secondary btn-sm wt-btn" @click="emit('clear-selection')">
          {{ t('wl_tb_clear_sel') }}
        </button>
        <button
          class="btn btn-sm btn-compare wt-btn"
          :disabled="selectedCount < 2 || selectedCount > 4"
          :title="selectedCount < 2 ? t('wl_tb_cmp_min') : selectedCount > 4 ? t('wl_tb_cmp_max') : ''"
          @click="emit('compare')"
        >
          {{ t('wl_tb_compare') }}
        </button>
        <button
          class="btn btn-sm btn-danger wt-btn"
          :disabled="selectedCount === 0"
          @click="emit('batch-delete')"
        >
          {{ t('wl_tb_batch_del') }}
        </button>
        <button class="btn btn-secondary btn-sm wt-btn" @click="emit('toggle-bulk')">
          {{ t('wl_tb_exit_bulk') }}
        </button>
      </template>

      <!-- Refresh -->
      <button
        class="btn btn-secondary btn-sm wt-btn wt-refresh"
        :disabled="loading"
        @click="emit('refresh')"
      >
        <span v-if="loading" class="spinner spinner--sm"></span>
        <span v-else>{{ t('wl_tb_refresh') }}</span>
      </button>

    </div>

  </div>
</template>

<script setup>
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  filters: {
    type: Object,
    default: () => ({ market: '', direction: '', industry: '', reportFilter: '' }),
  },
  sortKey:        { type: String,  default: 'default' },
  bulkMode:       { type: Boolean, default: false },
  selectedCount:  { type: Number,  default: 0 },
  industries:     { type: Array,   default: () => [] },
  loading:        { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:filters',
  'update:sortKey',
  'toggle-bulk',
  'clear-selection',
  'batch-delete',
  'compare',
  'refresh',
])

function patchFilter(key, value) {
  emit('update:filters', { ...props.filters, [key]: value })
}
</script>

<style scoped>
.wt-card {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wt-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
}

.wt-fg {
  display: flex;
  flex-direction: column;
  min-width: 100px;
}

.wt-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  margin-bottom: 5px;
}

.wt-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
}

.wt-select:focus { border-color: var(--accent); }

/* ── Actions row ── */
.wt-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.wt-btn {
  white-space: nowrap;
}

.wt-refresh {
  margin-left: auto;
}

.wt-selected-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.btn-danger {
  background: var(--status-up-bg);
  color: var(--danger);
  border: 1px solid var(--status-up-ring);
}

.btn-danger:hover:not(:disabled) {
  background: var(--status-up-ring);
}

.btn-compare {
  background: var(--status-info-bg);
  color: var(--accent);
  border: 1px solid var(--status-info-ring);
}

.btn-compare:hover:not(:disabled) {
  background: var(--status-info-ring);
}

.btn-compare:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.spinner--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .wt-card { padding: 12px 14px; }

  .wt-filters {
    flex-direction: column;
    gap: 8px;
  }

  .wt-fg {
    width: 100%;
    min-width: unset;
  }

  .wt-refresh {
    margin-left: 0;
  }
}
</style>
