<template>
  <div class="rcs-grid">

    <!-- Total (from backend total) -->
    <div class="rcs-card">
      <div class="rcs-label">{{ t('rpt_stat_total') }}</div>
      <div class="rcs-value">
        <span v-if="loading" class="rcs-dash">—</span>
        <span v-else>{{ total }}</span>
      </div>
    </div>

    <!-- Auto-saved (current page) -->
    <div class="rcs-card">
      <div class="rcs-label">{{ t('rpt_stat_auto') }}</div>
      <div class="rcs-value">
        <span v-if="loading" class="rcs-dash">—</span>
        <span v-else>{{ autoSavedCount }}</span>
      </div>
      <div class="rcs-sub">{{ t('rpt_stat_cur_page') }}</div>
    </div>

    <!-- Manual (current page) -->
    <div class="rcs-card">
      <div class="rcs-label">{{ t('rpt_stat_manual') }}</div>
      <div class="rcs-value">
        <span v-if="loading" class="rcs-dash">—</span>
        <span v-else>{{ manualCount }}</span>
      </div>
      <div class="rcs-sub">{{ t('rpt_stat_cur_page') }}</div>
    </div>

    <!-- Unique stocks (current page) -->
    <div class="rcs-card">
      <div class="rcs-label">{{ t('rpt_stat_stocks') }}</div>
      <div class="rcs-value">
        <span v-if="loading" class="rcs-dash">—</span>
        <span v-else>{{ uniqueStockCount }}</span>
      </div>
      <div class="rcs-sub">{{ t('rpt_stat_cur_page') }}</div>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  reports: { type: Array,   default: () => [] },
  total:   { type: Number,  default: 0 },
  loading: { type: Boolean, default: false },
})

const autoSavedCount = computed(() =>
  props.reports.filter(r => r.auto_saved).length
)

const manualCount = computed(() =>
  props.reports.filter(r => !r.auto_saved).length
)

const uniqueStockCount = computed(() => {
  const seen = new Set(props.reports.map(r => `${r.market}:${r.symbol}`))
  return seen.size
})
</script>

<style scoped>
.rcs-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 0;
}

.rcs-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.rcs-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.rcs-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.1;
  font-family: monospace;
}

.rcs-dash {
  font-size: 18px;
  color: var(--muted);
}

.rcs-sub {
  font-size: 10px;
  color: var(--muted);
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .rcs-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .rcs-value { font-size: 22px; }
}

@media (max-width: 340px) {
  .rcs-grid { grid-template-columns: 1fr; }
}
</style>
