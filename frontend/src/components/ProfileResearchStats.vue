<template>
  <div class="prs-section">
    <div class="prs-title-row">
      <span class="prs-title">研究资产</span>
      <span class="prs-hint">报告统计基于最近加载数据</span>
    </div>

    <div class="prs-grid">

      <div class="prs-card">
        <div class="prs-label">自选股</div>
        <div class="prs-value">
          <span v-if="loading" class="prs-dash">—</span>
          <span v-else>{{ fmt(watchlistCount) }}</span>
        </div>
      </div>

      <div class="prs-card">
        <div class="prs-label">历史报告</div>
        <div class="prs-value">
          <span v-if="loading" class="prs-dash">—</span>
          <span v-else>{{ fmt(reportTotal) }}</span>
        </div>
      </div>

      <div class="prs-card">
        <div class="prs-label">自动保存</div>
        <div class="prs-value">
          <span v-if="loading" class="prs-dash">—</span>
          <span v-else>{{ fmt(autoSavedCount) }}</span>
        </div>
      </div>

      <div class="prs-card">
        <div class="prs-label">手动保存</div>
        <div class="prs-value">
          <span v-if="loading" class="prs-dash">—</span>
          <span v-else>{{ fmt(manualCount) }}</span>
        </div>
      </div>

      <div class="prs-card">
        <div class="prs-label">涉及股票</div>
        <div class="prs-value">
          <span v-if="loading" class="prs-dash">—</span>
          <span v-else>{{ fmt(uniqueStocksCount) }}</span>
        </div>
      </div>

      <div class="prs-card">
        <div class="prs-label">最近搜索</div>
        <div class="prs-value">
          <span v-if="loading" class="prs-dash">—</span>
          <span v-else>{{ recentSearchCount }}</span>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  watchlistCount:   { type: Number, default: null },
  reportTotal:      { type: Number, default: null },
  autoSavedCount:   { type: Number, default: null },
  uniqueStocksCount: { type: Number, default: null },
  recentSearchCount: { type: Number, default: 0 },
  loading:          { type: Boolean, default: false },
})

const manualCount = computed(() => {
  if (props.reportTotal == null || props.autoSavedCount == null) return null
  return Math.max(0, props.reportTotal - props.autoSavedCount)
})

function fmt(v) {
  if (v == null) return '—'
  return String(v)
}
</script>

<style scoped>
.prs-section { margin-bottom: 0; }

.prs-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.prs-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}

.prs-hint {
  font-size: 10px;
  color: var(--muted);
  font-style: italic;
}

.prs-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
}

.prs-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 8px;
  text-align: center;
}

.prs-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 4px;
}

.prs-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  line-height: 1.2;
  font-family: monospace;
}

.prs-dash { font-size: 16px; color: var(--muted); }

/* ── Mobile ── */
@media (max-width: 600px) {
  .prs-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 380px) {
  .prs-grid { grid-template-columns: repeat(2, 1fr); gap: 6px; }
  .prs-value { font-size: 18px; }
}
</style>
