<template>
  <div class="ihs-wrap">

    <div class="ihs-card">
      <div class="ihs-label">{{ t('ind_stat_count') }}</div>
      <div class="ihs-value">
        <span v-if="loading" class="ihs-dash">—</span>
        <span v-else>{{ totalCount }}</span>
      </div>
    </div>

    <div class="ihs-card ihs-card--up">
      <div class="ihs-label">{{ t('ind_stat_up') }}</div>
      <div class="ihs-value ihs-val--up">
        <span v-if="loading" class="ihs-dash">—</span>
        <span v-else>{{ upCount }}</span>
      </div>
    </div>

    <div class="ihs-card ihs-card--down">
      <div class="ihs-label">{{ t('ind_stat_down') }}</div>
      <div class="ihs-value ihs-val--down">
        <span v-if="loading" class="ihs-dash">—</span>
        <span v-else>{{ downCount }}</span>
      </div>
    </div>

    <div class="ihs-card">
      <div class="ihs-label">{{ t('ind_stat_avg_score') }}</div>
      <div class="ihs-value">
        <span v-if="loading" class="ihs-dash">—</span>
        <span v-else>{{ avgScore }}</span>
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

const totalCount = computed(() => props.items.length)

const upCount = computed(() =>
  props.items.filter(i => i.change_pct != null && Number(i.change_pct) > 0).length
)

const downCount = computed(() =>
  props.items.filter(i => i.change_pct != null && Number(i.change_pct) < 0).length
)

const avgScore = computed(() => {
  const scores = props.items
    .map(i => i.hot_score)
    .filter(s => s != null && Number.isFinite(Number(s)))
    .map(Number)
  if (scores.length === 0) return '—'
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length
  return avg.toFixed(3)
})
</script>

<style scoped>
.ihs-wrap {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.ihs-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 8px;
  text-align: center;
}

.ihs-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 4px;
}

.ihs-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  line-height: 1.2;
  font-family: monospace;
}

.ihs-val--up   { color: var(--danger); }
.ihs-val--down { color: var(--success); }

.ihs-dash { font-size: 16px; color: var(--muted); }

/* ── Mobile ── */
@media (max-width: 600px) {
  .ihs-wrap { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 375px) {
  .ihs-wrap { grid-template-columns: repeat(2, 1fr); gap: 6px; }
  .ihs-value { font-size: 18px; }
}
</style>
