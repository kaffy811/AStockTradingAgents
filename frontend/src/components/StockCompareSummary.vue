<template>
  <div class="scs-wrap">

    <div class="scs-stat">
      <div class="scs-stat-label">{{ t('cmp_stat_selected') }}</div>
      <div class="scs-stat-value">
        <span v-if="loading" class="scs-dash">—</span>
        <span v-else>{{ totalCount }}<span class="scs-stat-max">/4</span></span>
      </div>
    </div>

    <div class="scs-stat">
      <div class="scs-stat-label">{{ t('cmp_stat_quote') }}</div>
      <div class="scs-stat-value">
        <span v-if="loading" class="scs-dash">—</span>
        <span v-else>{{ quoteAvail }}</span>
      </div>
    </div>

    <div class="scs-stat">
      <div class="scs-stat-label">{{ t('cmp_stat_report') }}</div>
      <div class="scs-stat-value">
        <span v-if="loading" class="scs-dash">—</span>
        <span v-else>{{ hasReport }}</span>
      </div>
    </div>

    <div class="scs-stat">
      <div class="scs-stat-label">{{ t('cmp_stat_industry') }}</div>
      <div class="scs-stat-value">
        <span v-if="loading" class="scs-dash">—</span>
        <span v-else>{{ industryCount }}</span>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  profiles: { type: Array,   default: () => [] },
  loading:  { type: Boolean, default: false },
})

const totalCount = computed(() => props.profiles.length)

const quoteAvail = computed(() =>
  props.profiles.filter(p => p?.quote?.status === 'success').length
)

const hasReport = computed(() =>
  props.profiles.filter(p => p?.latest_report != null).length
)

const industryCount = computed(() => {
  const names = props.profiles
    .map(p => p?.industry?.industry_name)
    .filter(n => n && typeof n === 'string')
  return new Set(names).size
})
</script>

<style scoped>
.scs-wrap {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.scs-stat {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 8px;
  text-align: center;
}

.scs-stat-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 4px;
}

.scs-stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  line-height: 1.2;
  font-family: monospace;
}

.scs-stat-max {
  font-size: 13px;
  font-weight: 400;
  color: var(--muted);
}

.scs-dash { font-size: 16px; color: var(--muted); }

/* ── Mobile ── */
@media (max-width: 600px) {
  .scs-wrap { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 375px) {
  .scs-wrap { grid-template-columns: repeat(2, 1fr); gap: 6px; }
  .scs-stat-value { font-size: 18px; }
}
</style>
