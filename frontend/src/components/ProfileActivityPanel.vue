<template>
  <div class="pap-wrap">

    <!-- ── Recent reports ─────────────────────────────────────────────────────── -->
    <div class="pap-panel card">
      <div class="pap-header">
        <span class="pap-panel-title">最近报告</span>
        <RouterLink to="/history" class="pap-link">查看全部 ›</RouterLink>
      </div>

      <div v-if="loading" class="pap-state">
        <span class="spinner"></span>
        <span class="pap-state-text">加载中…</span>
      </div>

      <div v-else-if="recentReports.length === 0" class="pap-empty">
        暂无历史报告，<RouterLink to="/" class="pap-accent-link">去生成一份</RouterLink>
      </div>

      <div v-else class="pap-report-list">
        <div
          v-for="rep in recentReports"
          :key="rep.id"
          class="pap-report-row"
          @click="emit('go-report', rep)"
        >
          <div class="pap-report-main">
            <span class="pap-market-badge">{{ rep.market }}</span>
            <span class="pap-symbol">{{ rep.symbol }}</span>
            <span v-if="rep.stock_name" class="pap-name">{{ rep.stock_name }}</span>
            <span :class="['pap-scope-badge', scopeClass(rep.analysis_scope)]">
              {{ scopeLabel(rep.analysis_scope) }}
            </span>
            <span v-if="rep.auto_saved" class="pap-tag">自动保存</span>
          </div>
          <span class="pap-time">{{ fmt(rep.created_at) }}</span>
        </div>
      </div>
    </div>

    <!-- ── Recent searches ────────────────────────────────────────────────────── -->
    <div class="pap-panel card">
      <div class="pap-header">
        <span class="pap-panel-title">最近搜索</span>
        <button
          v-if="recentSearches.length > 0"
          class="pap-link pap-danger-link"
          @click="emit('clear-searches')"
        >
          清空
        </button>
      </div>

      <div v-if="recentSearches.length === 0" class="pap-empty">
        暂无搜索记录
      </div>

      <div v-else class="pap-search-list">
        <div
          v-for="item in recentSearches.slice(0, 10)"
          :key="`${item.market}/${item.symbol}`"
          class="pap-search-row"
          @click="emit('pick-search', item)"
        >
          <span class="pap-market-badge">{{ item.market }}</span>
          <span class="pap-symbol">{{ item.symbol }}</span>
          <span v-if="item.stock_name" class="pap-name">{{ item.stock_name }}</span>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { RouterLink } from 'vue-router'

const props = defineProps({
  recentReports:  { type: Array,   default: () => [] },
  recentSearches: { type: Array,   default: () => [] },
  loading:        { type: Boolean, default: false },
})

const emit = defineEmits(['go-report', 'go-stock', 'pick-search', 'clear-searches'])

// ── Scope label ───────────────────────────────────────────────────────────────
const _SCOPE = {
  comprehensive:         '综合分析',
  technical_only:        '技术面',
  fundamental_only:      '基本面',
  peer_only:             '同行对比',
  news_only:             '新闻面',
  technical_fundamental: '技术+基本面',
}

function scopeLabel(s) { return _SCOPE[s] || s || '综合分析' }

function scopeClass(s) {
  return (!s || s === 'comprehensive') ? 'pap-scope-badge--comp' : 'pap-scope-badge--part'
}

// ── Time ──────────────────────────────────────────────────────────────────────
function fmt(ts) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('zh-CN', {
      month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ts
  }
}
</script>

<style scoped>
/* ── Wrapper: 2 columns on desktop, 1 on mobile ── */
.pap-wrap {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  /* card margin handles gap between panels */
}

.pap-panel {
  /* inherits .card styles; no extra margin needed between siblings */
}

/* ── Panel header ── */
.pap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.pap-panel-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}

.pap-link {
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}

.pap-danger-link { color: var(--danger); }
.pap-accent-link { color: var(--accent); text-decoration: underline; }

/* ── States ── */
.pap-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 0;
  color: var(--muted);
}

.pap-state-text { font-size: 13px; }

.pap-empty {
  font-size: 13px;
  color: var(--muted);
  padding: 12px 0;
}

/* ── Report rows ── */
.pap-report-list { display: flex; flex-direction: column; gap: 7px; }

.pap-report-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
  flex-wrap: wrap;
}

.pap-report-row:hover { background: var(--surface-hover); }

.pap-report-main {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

/* ── Search rows ── */
.pap-search-list { display: flex; flex-direction: column; gap: 6px; }

.pap-search-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
}

.pap-search-row:hover { background: var(--surface-hover); }

/* ── Shared badges ── */
.pap-market-badge {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.pap-symbol {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.pap-name {
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100px;
}

.pap-time {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.pap-scope-badge {
  font-size: 10px;
  font-weight: 600;
  border-radius: 4px;
  padding: 1px 5px;
  border: 1px solid transparent;
  white-space: nowrap;
}

.pap-scope-badge--comp {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

.pap-scope-badge--part {
  color: var(--muted);
  background: var(--surface2);
  border-color: var(--border);
}

.pap-tag {
  font-size: 10px;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 5px;
}

/* ── Mobile: single column ── */
@media (max-width: 600px) {
  .pap-wrap {
    grid-template-columns: 1fr;
  }
}
</style>
