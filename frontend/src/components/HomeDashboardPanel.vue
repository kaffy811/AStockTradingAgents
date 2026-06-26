<template>
  <div class="hdp-wrap">

    <!-- ── Stats bar ─────────────────────────────────────────────────────────── -->
    <div class="hdp-stats">
      <div class="hdp-stat" @click="emit('go-history')">
        <div class="hdp-stat-val">{{ loading ? '—' : recentReports.length }}</div>
        <div class="hdp-stat-label">{{ t('dash_recent_reports') }}</div>
      </div>
      <div class="hdp-stat" @click="emit('go-watchlist')">
        <div class="hdp-stat-val">{{ loading ? '—' : watchlistItems.length }}</div>
        <div class="hdp-stat-label">{{ t('dash_watchlist') }}</div>
      </div>
      <div class="hdp-stat">
        <div class="hdp-stat-val">{{ recentSearches.length }}</div>
        <div class="hdp-stat-label">{{ t('dash_recent_searches') }}</div>
      </div>
      <div class="hdp-stat" @click="emit('go-industries')">
        <div class="hdp-stat-val">{{ loading ? '—' : hotItems.length }}</div>
        <div class="hdp-stat-label">{{ t('dash_hot_industries') }}</div>
      </div>
    </div>

    <!-- ── Two-column grid ───────────────────────────────────────────────────── -->
    <div class="hdp-grid">

      <!-- ── Left column ── -->
      <div class="hdp-col">

        <!-- Recent reports -->
        <div class="hdp-section">
          <div class="hdp-section-header">
            <span class="hdp-section-title">{{ t('dash_section_recent') }}</span>
            <button class="hdp-link" @click="emit('go-history')">{{ t('dash_view_all') }}</button>
          </div>

          <div v-if="loading" class="hdp-state"><span class="spinner"></span></div>
          <div v-else-if="recentReports.length === 0" class="hdp-empty">{{ t('dash_empty_reports') }}</div>
          <div v-else class="hdp-report-list">
            <div
              v-for="rep in recentReports.slice(0, 3)"
              :key="rep.id"
              class="hdp-report-row"
              @click="emit('go-report', rep)"
            >
              <div class="hdp-report-main">
                <span class="hdp-mkt-badge">{{ rep.market }}</span>
                <span class="hdp-symbol">{{ rep.symbol }}</span>
                <span v-if="rep.stock_name" class="hdp-name">{{ rep.stock_name }}</span>
                <span :class="['hdp-scope-badge', rep.analysis_scope === 'comprehensive' ? 'hdp-scope--comp' : 'hdp-scope--part']">
                  {{ scopeLabel(rep.analysis_scope) }}
                </span>
                <span v-if="rep.auto_saved" class="hdp-tag">{{ t('dash_auto_tag') }}</span>
              </div>
              <span class="hdp-time">{{ fmtTime(rep.created_at) }}</span>
            </div>
          </div>
        </div>

        <!-- Watchlist quick-jump -->
        <div class="hdp-section">
          <div class="hdp-section-header">
            <span class="hdp-section-title">{{ t('dash_section_watchlist') }}</span>
            <button class="hdp-link" @click="emit('go-watchlist')">{{ t('dash_view_all') }}</button>
          </div>

          <div v-if="loading" class="hdp-state"><span class="spinner"></span></div>
          <div v-else-if="watchlistItems.length === 0" class="hdp-empty">{{ t('dash_empty_watchlist') }}</div>
          <div v-else class="hdp-wl-list">
            <div
              v-for="item in watchlistItems.slice(0, 4)"
              :key="`${item.market}/${item.symbol}`"
              class="hdp-wl-row"
            >
              <div class="hdp-wl-identity" @click="emit('go-stock', item)">
                <span class="hdp-mkt-badge">{{ item.market }}</span>
                <span class="hdp-symbol">{{ item.symbol }}</span>
                <span v-if="item.name || item.stock_name" class="hdp-name">{{ item.name || item.stock_name }}</span>
              </div>
              <div class="hdp-wl-right">
                <span
                  v-if="item.change_pct != null && item.quote_status !== 'failed'"
                  :class="['hdp-change', item.change_pct > 0 ? 'up' : item.change_pct < 0 ? 'down' : '']"
                >
                  {{ formatChangePct(item.change_pct) }}
                </span>
                <button class="btn btn-sm btn-ghost hdp-pick-btn" @click="emit('pick-stock', item)">
                  {{ t('dash_fill') }}
                </button>
                <button class="btn btn-sm btn-ghost hdp-pick-btn" @click="emit('go-stock', item)">
                  {{ t('dash_detail') }}
                </button>
              </div>
            </div>
          </div>
          <!-- Batch compare entry: only show when ≥2 stocks -->
          <div v-if="!loading && watchlistItems.length >= 2" class="hdp-wl-footer">
            <button class="hdp-link hdp-compare-entry" @click="emit('go-watchlist-compare')">
              ⊞ {{ t('dash_compare_bulk') }}
            </button>
          </div>
        </div>

      </div>

      <!-- ── Right column ── -->
      <div class="hdp-col">

        <!-- Industry blocks (hot sectors) -->
        <div class="hdp-section">
          <div class="hdp-section-header">
            <span class="hdp-section-title">{{ t('ind_blocks_title') }}</span>
            <button class="hdp-link" @click="emit('go-industries')">{{ t('ind_blocks_expand') }} ›</button>
          </div>
          <div class="hdp-section-sub">{{ t('ind_blocks_subtitle') }}</div>

          <div v-if="loading && industryList.length === 0" class="hdp-state"><span class="spinner"></span>{{ t('ind_loading_heat') }}</div>
          <div v-else-if="industryListError" class="hdp-empty hdp-error">{{ t('ind_blocks_err') }}</div>
          <div v-else-if="industryList.length === 0" class="hdp-empty">{{ t('dash_empty_industry') }}</div>
          <div v-else class="hdp-iblk-list">
            <div
              v-for="(ind, idx) in industryList.slice(0, 6)"
              :key="ind.industry_code || ind.code || idx"
              class="hdp-iblk-row"
              @click="emit('go-industry-block', ind)"
            >
              <span :class="['hdp-iblk-rank', idx < 3 ? 'hdp-iblk-rank--top' : '']">{{ idx + 1 }}</span>
              <span class="hdp-iblk-name">{{ ind.industry_name || ind.name || t('ind_unknown') }}</span>
              <span :class="['hdp-change', ind.avg_change_pct > 0 ? 'up' : ind.avg_change_pct < 0 ? 'down' : '']">
                {{ ind.avg_change_pct != null
                  ? (ind.avg_change_pct > 0 ? '+' : '') + Number(ind.avg_change_pct).toFixed(2) + '%'
                  : '—' }}
              </span>
              <span class="hdp-iblk-score">{{ ind.hot_score != null ? fmtScore(ind.hot_score) : '—' }}</span>
            </div>
          </div>
        </div>

        <!-- Industry hot stocks -->
        <div class="hdp-section">
          <div class="hdp-section-header">
            <span class="hdp-section-title">
              {{ t('dash_hot_industries') }}
              <span v-if="industryName" class="hdp-industry-sub">{{ industryName }}</span>
            </span>
            <button class="hdp-link" @click="emit('go-industries')">{{ t('dash_view_industries') }}</button>
          </div>

          <div v-if="loading && hotItems.length === 0" class="hdp-state"><span class="spinner"></span></div>
          <div v-else-if="hotItems.length === 0" class="hdp-empty">{{ t('dash_empty_industry') }}</div>
          <div v-else class="hdp-hot-list">
            <div
              v-for="row in hotItems.slice(0, 5)"
              :key="row.symbol"
              class="hdp-hot-row"
              @click="emit('go-stock', { market: 'CN', symbol: row.symbol, name: row.stock_name })"
            >
              <span :class="['hdp-rank', rankClass(row.rank)]">{{ row.rank }}</span>
              <span class="hdp-hot-sym">{{ row.symbol }}</span>
              <span class="hdp-hot-name">{{ row.stock_name }}</span>
              <span class="hdp-hot-score">{{ fmtScore(row.hot_score) }}</span>
              <span
                v-if="row.change_pct != null"
                :class="['hdp-change', row.change_pct > 0 ? 'up' : row.change_pct < 0 ? 'down' : '']"
              >
                {{ formatChangePct(row.change_pct) }}
              </span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- ── Compare entry ──────────────────────────────────────────────────────── -->
    <div class="hdp-compare-bar">
      <template v-if="compareList.length > 0">
        <span class="hdp-compare-label">
          {{ t('dash_compare_label') }}
          <span class="hdp-compare-count">{{ compareList.length }}/4</span>
        </span>
        <div class="hdp-compare-chips">
          <span
            v-for="item in compareList"
            :key="`${item.market}:${item.symbol}`"
            class="hdp-compare-chip"
          >
            <span class="hdp-mkt-badge">{{ item.market }}</span>
            {{ item.symbol }}
          </span>
        </div>
        <button class="btn btn-sm btn-secondary" @click="emit('go-compare')">{{ t('dash_compare_btn') }}</button>
      </template>
      <template v-else>
        <span class="hdp-compare-hint">{{ t('dash_compare_hint') }}</span>
        <button class="btn btn-sm btn-ghost" @click="emit('go-compare')">{{ t('dash_compare_page') }}</button>
      </template>
    </div>

  </div>
</template>

<script setup>
import { formatChangePct } from '../utils/marketFormat.js'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  recentReports:  { type: Array,   default: () => [] },
  watchlistItems: { type: Array,   default: () => [] },
  recentSearches: { type: Array,   default: () => [] },
  hotItems:       { type: Array,   default: () => [] },
  industryName:   { type: String,  default: '' },
  industryList:      { type: Array,   default: () => [] },
  industryListError: { type: String,  default: '' },
  compareList:       { type: Array,   default: () => [] },
  loading:        { type: Boolean, default: false },
})

const emit = defineEmits([
  'pick-stock',
  'go-report',
  'go-stock',
  'go-history',
  'go-watchlist',
  'go-watchlist-compare',
  'go-industries',
  'go-industry-block',
  'go-compare',
])

function scopeLabel(s) {
  const map = {
    comprehensive:         t('scope_comprehensive'),
    technical_only:        t('scope_technical'),
    fundamental_only:      t('scope_fundamental'),
    peer_only:             t('scope_peer'),
    news_only:             t('scope_news'),
    technical_fundamental: t('scope_tech_fund'),
  }
  return map[s] || s || t('scope_comprehensive')
}

function fmtTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return '' }
}

function fmtScore(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return Number(v).toFixed(2)
}

function rankClass(rank) {
  if (rank === 1) return 'hdp-rank--gold'
  if (rank === 2) return 'hdp-rank--silver'
  if (rank === 3) return 'hdp-rank--bronze'
  return 'hdp-rank--normal'
}
</script>

<style scoped>
.hdp-wrap {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── Stats bar ── */
.hdp-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}

.hdp-stat {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 8px;
  text-align: center;
  cursor: pointer;
  transition: background 0.12s;
}

.hdp-stat:hover { background: var(--surface-hover); }

.hdp-stat-val {
  font-size: 20px;
  font-weight: 700;
  color: var(--accent);
  font-family: monospace;
  line-height: 1.2;
}

.hdp-stat-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-top: 2px;
}

/* ── Two-column grid ── */
.hdp-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}

.hdp-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── Section ── */
.hdp-section {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hdp-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hdp-section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 6px;
}

.hdp-industry-sub {
  font-size: 11px;
  color: var(--muted);
  font-weight: 400;
}

.hdp-link {
  font-size: 12px;
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  white-space: nowrap;
}

/* ── States ── */
.hdp-state {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
  color: var(--muted);
  font-size: 12px;
}

.hdp-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 6px 0;
}

.hdp-error { color: var(--danger); }

/* ── Shared ── */
.hdp-mkt-badge {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 3px;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.hdp-symbol {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  font-family: monospace;
}

.hdp-name {
  font-size: 11px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 80px;
}

.hdp-time {
  font-size: 10px;
  color: var(--muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.up   { color: var(--danger); }
.down { color: var(--success); }

/* ── Recent reports ── */
.hdp-report-list { display: flex; flex-direction: column; gap: 5px; }

.hdp-report-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 7px 8px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s;
  flex-wrap: wrap;
}

.hdp-report-row:hover { background: var(--surface-hover); }

.hdp-report-main {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.hdp-scope-badge {
  font-size: 10px;
  font-weight: 600;
  border-radius: 3px;
  padding: 1px 5px;
  border: 1px solid transparent;
  white-space: nowrap;
}

.hdp-scope--comp {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

.hdp-scope--part {
  color: var(--muted);
  background: var(--surface2);
  border-color: var(--border);
}

.hdp-tag {
  font-size: 10px;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0 4px;
}

/* ── Watchlist quick-jump ── */
.hdp-wl-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.hdp-compare-entry {
  font-size: 11px;
  letter-spacing: 0.02em;
}

.hdp-wl-list { display: flex; flex-direction: column; gap: 5px; }

.hdp-wl-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 6px 8px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.hdp-wl-identity {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.hdp-wl-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.hdp-change {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.hdp-pick-btn {
  font-size: 11px;
  padding: 2px 7px;
  color: var(--muted);
}

.hdp-pick-btn:hover { color: var(--accent); }

/* ── Industry blocks (hot sectors) ── */
.hdp-section-sub {
  font-size: 10px;
  color: var(--muted);
  margin-top: -4px;
}

.hdp-iblk-list { display: flex; flex-direction: column; gap: 4px; }

.hdp-iblk-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s;
}

.hdp-iblk-row:hover { background: var(--surface-hover); }

.hdp-iblk-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
  background: var(--surface2);
  color: var(--muted);
}

.hdp-iblk-rank--top { background: rgba(255, 215, 0, 0.2); color: #b8860b; }

.hdp-iblk-name {
  font-size: 12px;
  color: var(--text);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hdp-iblk-score {
  font-size: 10px;
  color: var(--muted);
  font-family: monospace;
  flex-shrink: 0;
}

/* ── Industry hot stocks ── */
.hdp-hot-list { display: flex; flex-direction: column; gap: 4px; }

.hdp-hot-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 8px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s;
}

.hdp-hot-row:hover { background: var(--surface-hover); }

.hdp-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.hdp-rank--gold   { background: rgba(255, 215, 0, 0.25); color: #b8860b; }
.hdp-rank--silver { background: rgba(192, 192, 192, 0.25); color: #888; }
.hdp-rank--bronze { background: rgba(205, 127, 50, 0.25); color: #a0522d; }
.hdp-rank--normal { background: var(--surface2); color: var(--muted); }

.hdp-hot-sym {
  font-family: monospace;
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
  flex-shrink: 0;
}

.hdp-hot-name {
  font-size: 11px;
  color: var(--muted);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hdp-hot-score {
  font-size: 10px;
  color: var(--muted);
  font-family: monospace;
  flex-shrink: 0;
}

/* ── Compare bar ── */
.hdp-compare-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  flex-wrap: wrap;
}

.hdp-compare-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}

.hdp-compare-count {
  color: var(--accent);
}

.hdp-compare-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex: 1;
}

.hdp-compare-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: var(--status-info-bg);
  border: 1px solid var(--status-info-ring);
  border-radius: 10px;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
}

.hdp-compare-hint {
  font-size: 12px;
  color: var(--muted);
  flex: 1;
}

/* ── Mobile: single column ── */
@media (max-width: 640px) {
  .hdp-stats { grid-template-columns: repeat(2, 1fr); }
  .hdp-grid  { grid-template-columns: 1fr; }
}

@media (max-width: 375px) {
  .hdp-stats { grid-template-columns: repeat(2, 1fr); gap: 6px; }
  .hdp-stat-val { font-size: 16px; }
}
</style>
