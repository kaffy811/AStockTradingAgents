<template>
  <div class="rfp-card card">

    <div class="rfp-grid">

      <!-- ── 市场 ── -->
      <div class="form-group">
        <label class="rfp-label">{{ t('rpt_flt_market') }}</label>
        <select
          :value="filters.market"
          class="rfp-select"
          @change="patch('market', $event.target.value)"
        >
          <option value="">{{ t('rpt_flt_all') }}</option>
          <option value="CN">CN</option>
          <option value="HK">HK</option>
        </select>
      </div>

      <!-- ── 股票代码 / 名称 ── -->
      <div class="form-group rfp-ssb-group">
        <label class="rfp-label">{{ t('rpt_flt_code') }}</label>
        <StockSearchBox
          :symbol="filters.symbol"
          :market="filters.market || 'CN'"
          @update:symbol="patch('symbol', $event)"
          @select="onStockSelect"
          @keydown.enter="emit('search')"
        />
      </div>

      <!-- ── 报告类型 ── -->
      <div class="form-group">
        <label class="rfp-label">{{ t('rpt_flt_type') }}</label>
        <select
          :value="filters.scope"
          class="rfp-select"
          @change="patch('scope', $event.target.value)"
        >
          <option value="">{{ t('rpt_flt_all') }}</option>
          <option value="comprehensive">{{ t('mode_comprehensive') }}</option>
          <option value="technical_only">{{ t('mode_technical') }}</option>
          <option value="fundamental_only">{{ t('mode_fundamental') }}</option>
          <option value="peer_only">{{ t('mode_peer') }}</option>
          <option value="news_only">{{ t('mode_news') }}</option>
          <option value="technical_fundamental">{{ t('mode_tech_fund') }}</option>
        </select>
      </div>

      <!-- ── 保存方式 ── -->
      <div class="form-group">
        <label class="rfp-label">{{ t('rpt_flt_save') }}</label>
        <select
          :value="filters.autoSaved"
          class="rfp-select"
          @change="patch('autoSaved', $event.target.value)"
        >
          <option value="">{{ t('rpt_flt_all') }}</option>
          <option value="true">{{ t('rpt_flt_auto') }}</option>
          <option value="false">{{ t('rpt_flt_manual') }}</option>
        </select>
      </div>

      <!-- ── 时间范围 ── -->
      <div class="form-group">
        <label class="rfp-label">{{ t('rpt_flt_range') }}</label>
        <select
          :value="filters.dateRange"
          class="rfp-select"
          @change="patch('dateRange', $event.target.value)"
        >
          <option value="">{{ t('rpt_flt_all') }}</option>
          <option value="7d">{{ t('rpt_flt_7d') }}</option>
          <option value="30d">{{ t('rpt_flt_30d') }}</option>
          <option value="90d">{{ t('rpt_flt_90d') }}</option>
        </select>
      </div>

      <!-- ── Buttons ── -->
      <div class="rfp-btn-row">
        <button
          class="btn btn-primary btn-sm rfp-btn"
          :disabled="loading"
          @click="emit('search')"
        >
          <span v-if="loading" class="spinner spinner--sm"></span>
          <span v-else>{{ t('rpt_flt_query') }}</span>
        </button>
        <button
          class="btn btn-secondary btn-sm rfp-btn"
          :disabled="loading"
          @click="emit('reset')"
        >
          {{ t('rpt_flt_reset') }}
        </button>
      </div>

    </div>
  </div>
</template>

<script setup>
import StockSearchBox from './StockSearchBox.vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  filters: {
    type: Object,
    default: () => ({ market: '', symbol: '', scope: '', autoSaved: '', dateRange: '' }),
  },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['update:filters', 'search', 'reset'])

function patch(key, value) {
  emit('update:filters', { ...props.filters, [key]: value })
}

function onStockSelect(item) {
  emit('update:filters', { ...props.filters, symbol: item.symbol })
  emit('search')
}
</script>

<style scoped>
.rfp-card {
  padding: 16px 20px;
}

.rfp-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
}

.rfp-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  display: block;
  margin-bottom: 5px;
}

.rfp-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 7px 10px;
  font-size: 13px;
  outline: none;
  width: 100%;
}

.rfp-select:focus { border-color: var(--accent); }

.form-group { display: flex; flex-direction: column; min-width: 110px; }

.rfp-ssb-group { flex: 1; min-width: 140px; }

.rfp-btn-row {
  display: flex;
  gap: 7px;
  align-items: center;
  padding-bottom: 1px;
}

.rfp-btn { min-width: 64px; }

.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-primary);
}

.spinner--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .rfp-card { padding: 14px 16px; }

  .rfp-grid {
    flex-direction: column;
    gap: 10px;
  }

  .rfp-grid .form-group,
  .rfp-ssb-group {
    width: 100%;
    min-width: unset;
  }

  .rfp-btn-row {
    width: 100%;
  }

  .rfp-btn { flex: 1; }
}
</style>
