<template>
  <div class="insight-card">

    <!-- ── Header ────────────────────────────────────────────────────────────── -->
    <div class="insight-header">
      <span class="card-title">技术面解读</span>
      <span v-if="loading" class="insight-loading">
        <span class="spinner spinner--sm"></span>
        <span class="insight-loading-text">计算中…</span>
      </span>
    </div>

    <!-- ── Empty / not yet available ─────────────────────────────────────────── -->
    <div v-if="!loading && !insight" class="insight-empty">
      <p class="insight-empty-title">暂无技术解读</p>
      <p class="insight-empty-msg">K线数据不足，暂无法生成规则型技术面解读。</p>
    </div>

    <template v-else-if="insight">

      <!-- ── Summary line ─────────────────────────────────────────────────────── -->
      <p class="insight-summary">{{ insight.summary }}</p>

      <!-- ── 4-dimension grid ────────────────────────────────────────────────── -->
      <div :class="['insight-grid', compact ? 'insight-grid--compact' : '']">
        <div
          v-for="dim in DIMENSIONS"
          :key="dim.key"
          :class="['insight-dim', `insight-dim--${insight[dim.key].level}`]"
        >
          <div class="dim-header">
            <span :class="['dim-dot', `dim-dot--${insight[dim.key].level}`]"></span>
            <span class="dim-title">{{ insight[dim.key].title }}</span>
            <span :class="['dim-badge', `dim-badge--${insight[dim.key].level}`]">
              {{ levelLabel(insight[dim.key].level) }}
            </span>
          </div>
          <p class="dim-message">{{ insight[dim.key].message }}</p>
        </div>
      </div>

      <!-- ── Disclaimer ──────────────────────────────────────────────────────── -->
      <p class="insight-disclaimer">
        以上解读基于规则型算法，仅描述价格与指标的当前状态，不构成任何投资建议。
      </p>

    </template>
  </div>
</template>

<script setup>
const DIMENSIONS = [
  { key: 'trend'  },
  { key: 'volume' },
  { key: 'macd'   },
  { key: 'rsi'    },
]

defineProps({
  insight: { type: Object,  default: null  },
  loading: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

function levelLabel(level) {
  const MAP = {
    positive: '偏强',
    neutral:  '震荡',
    warning:  '偏弱',
    limited:  '数据不足',
  }
  return MAP[level] || level
}
</script>

<style scoped>
/* ── Header ── */
.insight-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.insight-loading {
  display: flex;
  align-items: center;
  gap: 5px;
}

.insight-loading-text {
  font-size: 12px;
  color: var(--muted);
}

.spinner--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
}

/* ── Empty state ── */
.insight-empty {
  padding: 14px 0 6px;
  text-align: center;
}

.insight-empty-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin: 0 0 6px;
}

.insight-empty-msg {
  font-size: 12px;
  color: var(--muted);
  margin: 0;
}

/* ── Summary line ── */
.insight-summary {
  font-size: 13px;
  color: var(--text);
  line-height: 1.6;
  margin: 0 0 14px;
  padding: 10px 12px;
  background: var(--surface2);
  border-radius: 6px;
  border-left: 3px solid var(--accent);
}

/* ── 4-dimension grid ── */
.insight-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.insight-grid--compact {
  grid-template-columns: 1fr;
}

.insight-dim {
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface2);
}

.insight-dim--positive {
  border-color: var(--status-down-ring);
  background:   var(--status-down-bg);
}

.insight-dim--warning {
  border-color: var(--status-warn-ring);
  background:   var(--status-warn-bg);
}

.insight-dim--neutral {
  border-color: var(--status-info-ring);
  background:   var(--surface-hover);
}

.insight-dim--limited {
  border-color: var(--border);
  background:   var(--surface2);
  opacity: 0.65;
}

/* ── Dimension header ── */
.dim-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.dim-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dim-dot--positive { background: var(--success); }
.dim-dot--warning  { background: var(--warn);    }
.dim-dot--neutral  { background: var(--accent); opacity: 0.6; }
.dim-dot--limited  { background: var(--muted);  }

.dim-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}

.dim-badge {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
}

.dim-badge--positive { background: var(--status-down-bg); color: var(--success); }
.dim-badge--warning  { background: var(--status-warn-bg); color: var(--warn);    }
.dim-badge--neutral  { background: var(--status-info-bg); color: var(--accent);  }
.dim-badge--limited  { background: var(--surface2); color: var(--muted); }

/* ── Dimension message ── */
.dim-message {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.55;
  margin: 0;
}

/* ── Disclaimer ── */
.insight-disclaimer {
  font-size: 11px;
  color: var(--muted);
  opacity: 0.65;
  margin: 0;
  line-height: 1.5;
  font-style: italic;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .insight-grid {
    grid-template-columns: 1fr;
  }
}
</style>
