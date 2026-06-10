<template>
  <div class="itb-card card">

    <div class="itb-row">

      <!-- 行业选择 -->
      <div class="itb-group">
        <label class="itb-label">{{ t('ind_tb_industry') }}</label>
        <select
          class="itb-select"
          :value="selectedCode"
          :disabled="loading"
          @change="emit('update:selectedCode', $event.target.value)"
        >
          <option v-for="ind in industries" :key="ind.industry_code" :value="ind.industry_code">
            {{ ind.industry_name }}
          </option>
        </select>
      </div>

      <!-- 涨跌筛选 -->
      <div class="itb-group">
        <label class="itb-label">{{ t('wl_tb_change') }}</label>
        <select
          class="itb-select"
          :value="filters.changeFilter"
          @change="patchFilter('changeFilter', $event.target.value)"
        >
          <option value="all">{{ t('rpt_flt_all') }}</option>
          <option value="up">{{ t('wl_tb_up_only') }}</option>
          <option value="down">{{ t('wl_tb_down_only') }}</option>
          <option value="missing">{{ t('ind_tb_missing') }}</option>
        </select>
      </div>

      <!-- 数据源筛选 -->
      <div class="itb-group">
        <label class="itb-label">{{ t('ind_tb_source') }}</label>
        <select
          class="itb-select"
          :value="filters.dataSourceFilter"
          @change="patchFilter('dataSourceFilter', $event.target.value)"
        >
          <option value="all">{{ t('rpt_flt_all') }}</option>
          <option v-for="src in dataSources" :key="src" :value="src">{{ src }}</option>
        </select>
      </div>

      <!-- 排序 -->
      <div class="itb-group">
        <label class="itb-label">{{ t('wl_tb_sort') }}</label>
        <select
          class="itb-select"
          :value="sortKey"
          @change="emit('update:sortKey', $event.target.value)"
        >
          <option value="rank">{{ t('ind_tb_rank') }}</option>
          <option value="hot_score_desc">{{ t('ind_tb_score_desc') }}</option>
          <option value="change_desc">{{ t('ind_tb_chg_desc') }}</option>
          <option value="change_asc">{{ t('ind_tb_chg_asc') }}</option>
          <option value="amount_desc">{{ t('ind_tb_amount_desc') }}</option>
          <option value="symbol">{{ t('wl_tb_sort_symbol') }}</option>
        </select>
      </div>

      <!-- 刷新 -->
      <button
        class="btn btn-sm btn-secondary itb-refresh"
        :disabled="hotLoading"
        @click="emit('refresh')"
      >
        <span v-if="hotLoading" class="spinner"></span>
        <span v-else>{{ t('wl_tb_refresh') }}</span>
      </button>

    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  industries:  { type: Array,   default: () => [] },
  selectedCode:{ type: String,  default: '' },
  filters:     { type: Object,  default: () => ({ changeFilter: 'all', dataSourceFilter: 'all' }) },
  sortKey:     { type: String,  default: 'rank' },
  dataSources: { type: Array,   default: () => [] },
  loading:     { type: Boolean, default: false },
  hotLoading:  { type: Boolean, default: false },
})

const emit = defineEmits(['update:selectedCode', 'update:filters', 'update:sortKey', 'refresh'])

function patchFilter(key, value) {
  emit('update:filters', { ...props.filters, [key]: value })
}
</script>

<style scoped>
.itb-card {
  padding: 14px 20px;
}

.itb-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.itb-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 120px;
}

.itb-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.itb-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 12px;
  outline: none;
  width: 100%;
  cursor: pointer;
}

.itb-select:focus { border-color: var(--accent); }
.itb-select:disabled { opacity: 0.5; cursor: not-allowed; }

.itb-refresh {
  flex-shrink: 0;
  align-self: flex-end;
  min-width: 60px;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .itb-row {
    flex-direction: column;
    align-items: stretch;
  }

  .itb-group { min-width: unset; }

  .itb-refresh { width: 100%; }
}
</style>
