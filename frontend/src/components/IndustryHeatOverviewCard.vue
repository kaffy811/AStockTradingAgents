<template>
  <div class="card ihoc-card">
    <!-- Header -->
    <div class="ihoc-header">
      <div>
        <div class="ihoc-title">{{ t('ind_heat_title') }}</div>
        <div class="ihoc-subtitle">{{ t('ind_heat_subtitle') }}</div>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="ihoc-grid">
      <div v-for="n in 12" :key="n" class="ihoc-tile ihoc-tile--skeleton"></div>
    </div>

    <!-- Error -->
    <EmptyState
      v-else-if="error"
      icon="⚠️"
      :title="t('ind_heat_err')"
      :message="error"
      :action-text="t('disc_retry')"
      :compact="true"
      @action="emit('retry')"
    />

    <!-- Empty -->
    <EmptyState
      v-else-if="industries.length === 0"
      icon="📊"
      :title="t('ind_heat_empty')"
      :compact="true"
    />

    <!-- Grid -->
    <div v-else class="ihoc-grid">
      <button
        v-for="ind in industries"
        :key="ind.industry_code"
        :class="['ihoc-tile', ind.industry_code === selectedCode ? 'ihoc-tile--selected' : '']"
        :style="tileStyle(ind)"
        :title="tileTooltip(ind)"
        @click="emit('select', ind.industry_code)"
      >
        <span class="ihoc-tile-name">{{ ind.industry_name }}</span>
        <span v-if="ind.hot_score != null" class="ihoc-tile-score">
          {{ Number(ind.hot_score).toFixed(2) }}
        </span>
      </button>
    </div>

    <!-- Data note -->
    <p v-if="!loading && !error && industries.length > 0" class="ihoc-note">
      {{ t('ind_heat_note') }}
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EmptyState from './EmptyState.vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  industries:   { type: Array,   default: () => [] },
  selectedCode: { type: String,  default: '' },
  loading:      { type: Boolean, default: false },
  error:        { type: String,  default: '' },
})

const emit = defineEmits(['select', 'retry'])

// Compute the max hot_score in the list to normalize color intensity
const maxScore = computed(() => {
  const scores = props.industries.map(i => Number(i.hot_score)).filter(v => !isNaN(v) && v > 0)
  return scores.length ? Math.max(...scores) : 0
})

function tileStyle(ind) {
  if (ind.hot_score == null || maxScore.value === 0) return {}
  const t = Math.min(Number(ind.hot_score) / maxScore.value, 1)
  // Heat tint scaled from accent-primary; max mix ~35% to stay readable across themes
  const pct = Math.max(2, Math.round(t * 35))
  return { background: `color-mix(in srgb, var(--accent-primary) ${pct}%, transparent)` }
}

function tileTooltip(ind) {
  const parts = [ind.industry_name]
  if (ind.hot_score != null)      parts.push(`${t('ind_heat_score')}${Number(ind.hot_score).toFixed(2)}`)
  if (ind.stock_count)            parts.push(`${t('ind_heat_sample')}${ind.stock_count}${t('ind_heat_stocks')}`)
  if (ind.avg_change_pct != null) {
    const pct = Number(ind.avg_change_pct).toFixed(2)
    parts.push(`${t('ind_heat_avg_change')}${pct >= 0 ? '+' : ''}${pct}%`)
  }
  return parts.join('\n')
}
</script>

<style scoped>
.ihoc-card {
  padding: 16px 20px 14px;
}

.ihoc-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
}

.ihoc-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 3px;
}

.ihoc-subtitle {
  font-size: 11px;
  color: var(--muted);
  opacity: 0.8;
}

/* ── Grid ── */
.ihoc-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 5px;
}

.ihoc-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 4px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  text-align: center;
  min-height: 46px;
}

.ihoc-tile:hover {
  border-color: var(--accent);
  background: var(--accent-glow);
}

.ihoc-tile--selected {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 16%, transparent) !important;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 40%, transparent);
}

.ihoc-tile--skeleton {
  background: var(--surface2);
  border-color: transparent;
  animation: ihoc-pulse 1.4s ease-in-out infinite;
  cursor: default;
}

@keyframes ihoc-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}

.ihoc-tile-name {
  font-size: 10px;
  font-weight: 500;
  color: var(--text);
  line-height: 1.3;
  word-break: keep-all;
  overflow-wrap: break-word;
  hyphens: none;
  max-width: 100%;
}

.ihoc-tile--selected .ihoc-tile-name {
  color: var(--accent);
  font-weight: 600;
}

.ihoc-tile-score {
  font-size: 9px;
  color: var(--muted);
  opacity: 0.8;
}

/* ── Data note ── */
.ihoc-note {
  margin: 10px 0 0;
  font-size: 10px;
  color: var(--muted);
  opacity: 0.6;
  line-height: 1.5;
}

/* ── Responsive ── */
@media (max-width: 540px) {
  .ihoc-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 380px) {
  .ihoc-grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .ihoc-tile-name {
    font-size: 9px;
  }
}
</style>
