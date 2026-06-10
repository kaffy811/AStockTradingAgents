<template>
  <div class="ws-grid">

    <div class="ws-card">
      <div class="ws-label">{{ t('wl_stat_total') }}</div>
      <div class="ws-value">
        <span v-if="loading" class="ws-dash">—</span>
        <span v-else>{{ items.length }}</span>
      </div>
    </div>

    <div class="ws-card ws-card--up">
      <div class="ws-label">{{ t('wl_stat_up') }}</div>
      <div class="ws-value ws-value--up">
        <span v-if="loading" class="ws-dash">—</span>
        <span v-else>{{ upCount }}</span>
      </div>
    </div>

    <div class="ws-card ws-card--dn">
      <div class="ws-label">{{ t('wl_stat_down') }}</div>
      <div class="ws-value ws-value--dn">
        <span v-if="loading" class="ws-dash">—</span>
        <span v-else>{{ downCount }}</span>
      </div>
    </div>

    <div class="ws-card">
      <div class="ws-label">{{ t('wl_stat_report') }}</div>
      <div class="ws-value">
        <span v-if="loading" class="ws-dash">—</span>
        <span v-else>{{ reportCount }}</span>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  items:   { type: Array,   default: () => [] },
  loading: { type: Boolean, default: false },
})

// change_pct > 0 AND quote available
const upCount = computed(() =>
  props.items.filter(i =>
    i.quote_status !== 'failed' && i.change_pct != null && i.change_pct > 0
  ).length
)

// change_pct < 0 AND quote available
const downCount = computed(() =>
  props.items.filter(i =>
    i.quote_status !== 'failed' && i.change_pct != null && i.change_pct < 0
  ).length
)

const reportCount = computed(() =>
  props.items.filter(i => i.latest_report != null).length
)
</script>

<style scoped>
.ws-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 0;
}

.ws-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.ws-card--up { border-color: var(--status-up-ring); }
.ws-card--dn { border-color: var(--status-down-ring); }

.ws-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ws-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.1;
  font-family: monospace;
}

.ws-value--up { color: var(--danger);  }
.ws-value--dn { color: var(--success); }

.ws-dash { font-size: 18px; color: var(--muted); }

/* ── Mobile ── */
@media (max-width: 540px) {
  .ws-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
  .ws-value { font-size: 22px; }
}

@media (max-width: 320px) {
  .ws-grid { grid-template-columns: 1fr; }
}
</style>
