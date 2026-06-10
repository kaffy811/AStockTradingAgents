<template>
  <div class="card ihbc-card">
    <!-- Header -->
    <div class="ihbc-header">
      <div>
        <div class="ihbc-title">{{ t('ind_blocks_title') }}</div>
        <div class="ihbc-subtitle">{{ t('ind_blocks_subtitle') }}</div>
      </div>
      <button
        v-if="hasScores && sortedIndustries.length > limit"
        class="ihbc-view-all-btn"
        @click="emit('view-all')"
      >
        {{ expanded ? t('ind_blocks_collapse') : t('ind_blocks_expand') }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="ihbc-loading">
      <span class="spinner"></span> {{ t('ind_loading') }}
    </div>

    <!-- Error -->
    <EmptyState
      v-else-if="error"
      icon="⚠️"
      :title="t('ind_blocks_err')"
      :message="error"
      :action-text="t('disc_retry')"
      :compact="true"
      @action="emit('retry')"
    />

    <!-- No hot_score data -->
    <EmptyState
      v-else-if="!hasScores"
      icon="📊"
      :title="t('ind_blocks_no_score')"
      :compact="true"
    />

    <!-- Empty industries -->
    <EmptyState
      v-else-if="sortedIndustries.length === 0"
      icon="📊"
      :title="t('ind_heat_empty')"
      :compact="true"
    />

    <!-- List -->
    <div v-else class="ihbc-list">
      <button
        v-for="(ind, idx) in visibleIndustries"
        :key="ind.industry_code"
        :class="['ihbc-row', ind.industry_code === selectedCode ? 'ihbc-row--selected' : '']"
        @click="emit('select', ind.industry_code)"
      >
        <span :class="['ihbc-rank', rankClass(idx + 1)]">{{ idx + 1 }}</span>
        <span class="ihbc-name">{{ ind.industry_name }}</span>
        <span class="ihbc-right">
          <span
            v-if="ind.avg_change_pct != null"
            :class="['ihbc-pct', ind.avg_change_pct > 0 ? 'ihbc-pct--up' : ind.avg_change_pct < 0 ? 'ihbc-pct--dn' : '']"
          >{{ ind.avg_change_pct >= 0 ? '+' : '' }}{{ Number(ind.avg_change_pct).toFixed(2) }}%</span>
          <span v-if="ind.hot_score != null" class="ihbc-score">{{ Number(ind.hot_score).toFixed(2) }}</span>
          <span v-if="ind.stock_count" class="ihbc-count">{{ ind.stock_count }}{{ t('ind_heat_stocks') }}</span>
        </span>
      </button>
    </div>

    <!-- Data note -->
    <p v-if="hasScores && !loading && !error" class="ihbc-note">
      {{ t('ind_blocks_note') }}
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
  limit:        { type: Number,  default: 5 },
  expanded:     { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'view-all', 'retry'])

// Whether any industry in the list has a hot_score field
const hasScores = computed(() =>
  props.industries.some(i => i.hot_score != null)
)

const sortedIndustries = computed(() =>
  [...props.industries]
    .filter(i => i.hot_score != null)
    .sort((a, b) => (b.hot_score ?? 0) - (a.hot_score ?? 0))
)

const visibleIndustries = computed(() =>
  sortedIndustries.value.slice(0, props.expanded ? 20 : props.limit)
)

function rankClass(rank) {
  if (rank === 1) return 'ihbc-rank--gold'
  if (rank === 2) return 'ihbc-rank--silver'
  if (rank === 3) return 'ihbc-rank--bronze'
  return ''
}
</script>

<style scoped>
.ihbc-card {
  padding: 16px 20px 14px;
  display: flex;
  flex-direction: column;
}

.ihbc-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 8px;
}

.ihbc-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 3px;
}

.ihbc-subtitle {
  font-size: 11px;
  color: var(--muted);
  opacity: 0.8;
}

.ihbc-view-all-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 11px;
  color: var(--accent);
  padding: 3px 8px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.15s;
}

.ihbc-view-all-btn:hover {
  background: var(--accent-glow);
}

/* ── Loading ── */
.ihbc-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
  padding: 12px 0;
}

/* ── List ── */
.ihbc-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.ihbc-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 6px;
  border-radius: 6px;
  background: none;
  border: none;
  cursor: pointer;
  width: 100%;
  text-align: left;
  transition: background 0.1s;
}

.ihbc-row:hover {
  background: var(--surface2);
}

.ihbc-row--selected {
  background: var(--accent-glow);
}

.ihbc-rank {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  width: 18px;
  text-align: center;
  flex-shrink: 0;
}

.ihbc-rank--gold   { color: #f0c040; }
.ihbc-rank--silver { color: #b0b8c8; }
.ihbc-rank--bronze { color: #c88850; }

.ihbc-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ihbc-row--selected .ihbc-name {
  color: var(--accent);
  font-weight: 600;
}

.ihbc-code {
  font-size: 10px;
  font-family: monospace;
  color: var(--muted);
  opacity: 0.7;
  flex-shrink: 0;
}

.ihbc-score {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  min-width: 44px;
  text-align: right;
  flex-shrink: 0;
}

.ihbc-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.ihbc-pct {
  font-size: 11px;
  font-weight: 600;
  min-width: 48px;
  text-align: right;
  flex-shrink: 0;
  color: var(--muted);
}

.ihbc-pct--up { color: #26a69a; }
.ihbc-pct--dn { color: #ef5350; }

.ihbc-count {
  font-size: 10px;
  color: var(--muted);
  flex-shrink: 0;
}

/* ── Data note ── */
.ihbc-note {
  margin: 10px 0 0;
  font-size: 10px;
  color: var(--muted);
  opacity: 0.6;
  line-height: 1.5;
}
</style>
