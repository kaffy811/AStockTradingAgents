<template>
  <div class="dashboard-card card">

    <!-- ── Loading skeleton ───────────────────────────────────────────────── -->
    <div v-if="loading" class="db-loading">
      <span class="spinner"></span>
      <span class="db-loading-text">加载股票信息…</span>
    </div>

    <template v-else>

      <!-- ── Main 2-column grid ─────────────────────────────────────────────── -->
      <div class="db-grid">

        <!-- ── Left: 股票核心状态 ─────────────────────────────────────────── -->
        <div class="db-identity">
          <h2 class="db-name">{{ stockName || symbol }}</h2>
          <div class="db-meta">
            <span class="db-market-badge">{{ market }}</span>
            <span class="db-symbol">{{ symbol }}</span>
            <span v-if="industryName" class="db-industry-tag">{{ industryName }}</span>
          </div>

          <!-- Price / change -->
          <div v-if="quotePrice" class="db-price-row">
            <span class="db-price">{{ quotePrice }}</span>
            <span :class="['db-change', quoteChangeClass]">{{ quoteChangeText }}</span>
          </div>
          <div v-else-if="quoteError" class="db-price-row">
            <span class="db-unavail">行情暂不可用</span>
          </div>
          <div v-else class="db-price-row">
            <span class="db-unavail">行情加载中…</span>
          </div>

          <!-- Watchlist badge -->
          <div class="db-watchlist-row">
            <span :class="['db-wl-badge', inWatchlist ? 'db-wl-badge--on' : 'db-wl-badge--off']">
              {{ inWatchlist ? '★ 已在自选' : '☆ 未加自选' }}
            </span>
          </div>
        </div>

        <!-- ── Right: 研究状态 + 快捷操作 ─────────────────────────────────── -->
        <div class="db-right">

          <!-- Research status cards -->
          <div class="db-status-grid">
            <div :class="['db-status-card', `db-status-card--${summary.technical.level}`]">
              <div class="dsc-header">
                <span class="dsc-label">技术面</span>
                <span :class="['dsc-badge', `dsc-badge--${summary.technical.level}`]">
                  {{ levelLabel(summary.technical.level) }}
                </span>
              </div>
              <p class="dsc-text">{{ summary.technical.text }}</p>
            </div>

            <div :class="['db-status-card', `db-status-card--${summary.news.level}`]">
              <div class="dsc-header">
                <span class="dsc-label">新闻面</span>
                <span :class="['dsc-badge', `dsc-badge--${summary.news.level}`]">
                  {{ levelLabel(summary.news.level) }}
                </span>
              </div>
              <p class="dsc-text">{{ summary.news.text }}</p>
            </div>

            <div :class="['db-status-card', `db-status-card--${summary.report.level}`]">
              <div class="dsc-header">
                <span class="dsc-label">研究报告</span>
                <span :class="['dsc-badge', `dsc-badge--${summary.report.level}`]">
                  {{ levelLabel(summary.report.level) }}
                </span>
              </div>
              <p class="dsc-text">{{ summary.report.text }}</p>
            </div>
          </div>

          <!-- Quick action buttons -->
          <div class="db-actions">
            <button class="btn btn-sm btn-primary db-btn" @click="emit('analyze')">
              生成分析
            </button>
            <button
              class="btn btn-sm btn-secondary db-btn"
              :disabled="!summary.report.hasReport"
              @click="emit('view-report')"
            >
              {{ summary.report.hasReport ? '查看报告' : '暂无报告' }}
            </button>
            <button
              :class="['btn', 'btn-sm', 'db-btn', inWatchlist ? 'btn-watchlist-on' : 'btn-secondary']"
              :disabled="watchlistLoading"
              @click="emit('toggle-watchlist')"
            >
              <span v-if="watchlistLoading" class="spinner spinner--sm"></span>
              <span v-else>{{ inWatchlist ? '★ 移出自选' : '☆ 加入自选' }}</span>
            </button>
            <!-- Compare buttons -->
            <button
              :class="['btn', 'btn-sm', 'db-btn', compareBtnClass]"
              :disabled="compareStatus === 'full'"
              @click="emit('add-to-compare')"
            >
              {{ compareBtnLabel }}
            </button>
            <button class="btn btn-sm btn-ghost db-btn" @click="emit('go-compare')">
              → 对比页
            </button>
            <button class="btn btn-sm btn-ghost db-btn" @click="emit('scroll-to', 'chart')">
              ↓ K线走势
            </button>
            <button class="btn btn-sm btn-ghost db-btn" @click="emit('scroll-to', 'news')">
              ↓ 相关新闻
            </button>
          </div>
        </div>
      </div>

      <!-- ── Quote metrics strip ────────────────────────────────────────────── -->
      <div v-if="hasQuoteMetrics" class="db-metrics">
        <div class="db-metric">
          <span class="dbm-label">开盘</span>
          <span class="dbm-val">{{ fmtPrice(profile.quote.open) }}</span>
        </div>
        <div class="db-metric">
          <span class="dbm-label">最高</span>
          <span class="dbm-val up">{{ fmtPrice(profile.quote.high) }}</span>
        </div>
        <div class="db-metric">
          <span class="dbm-label">最低</span>
          <span class="dbm-val dn">{{ fmtPrice(profile.quote.low) }}</span>
        </div>
        <div class="db-metric">
          <span class="dbm-label">昨收</span>
          <span class="dbm-val">{{ fmtPrice(profile.quote.prev_close) }}</span>
        </div>
        <div class="db-metric">
          <span class="dbm-label">成交量</span>
          <span class="dbm-val">{{ fmtVol(profile.quote.volume) }}</span>
        </div>
        <div class="db-metric">
          <span class="dbm-label">成交额</span>
          <span class="dbm-val">{{ fmtAmt(profile.quote.amount) }}</span>
        </div>
      </div>

    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatAmount, formatVolume } from '../utils/marketFormat.js'
import { buildDashboardSummary } from '../utils/dashboardSummary.js'

// ── Props ─────────────────────────────────────────────────────────────────────
const props = defineProps({
  market:          { type: String,  required: true },
  symbol:          { type: String,  required: true },
  stockName:       { type: String,  default: '' },
  profile:         { type: Object,  default: null },
  quotePrice:      { type: String,  default: '' },
  quoteChangeText: { type: String,  default: '' },
  quoteChangeClass: { type: String, default: '' },
  quoteError:      { type: Boolean, default: false },
  technicalInsight: { type: Object, default: null },
  newsItems:       { type: Array,   default: () => [] },
  latestReport:    { type: Object,  default: null },
  loading:         { type: Boolean, default: false },
  inWatchlist:     { type: Boolean, default: false },
  watchlistLoading: { type: Boolean, default: false },
  compareStatus:   { type: String,  default: '' },  // '' | 'in_list' | 'added' | 'full'
})

// ── Emits ─────────────────────────────────────────────────────────────────────
const emit = defineEmits(['analyze', 'view-report', 'toggle-watchlist', 'scroll-to', 'add-to-compare', 'go-compare'])

// ── Computed ──────────────────────────────────────────────────────────────────
const industryName = computed(() => props.profile?.industry?.industry_name || '')

const hasQuoteMetrics = computed(() => props.profile?.quote?.status === 'success')

const summary = computed(() =>
  buildDashboardSummary({
    technicalInsight: props.technicalInsight,
    newsItems:        props.newsItems,
    latestReport:     props.latestReport,
  })
)

// ── Compare button helpers ─────────────────────────────────────────────────────
const compareBtnLabel = computed(() => {
  if (props.compareStatus === 'in_list' || props.compareStatus === 'added') return '已在对比'
  if (props.compareStatus === 'full') return '最多对比 4 只'
  return '+ 加入对比'
})

const compareBtnClass = computed(() => {
  if (props.compareStatus === 'in_list' || props.compareStatus === 'added') return 'btn-compare-on'
  if (props.compareStatus === 'full') return 'btn-secondary'
  return 'btn-secondary'
})

// ── Level label ───────────────────────────────────────────────────────────────
function levelLabel(level) {
  const MAP = { positive: '偏强', neutral: '中性', warning: '需关注', limited: '数据有限' }
  return MAP[level] || level
}

// ── Formatters (local, no external dep) ──────────────────────────────────────
function fmtPrice(val) {
  if (val == null || !Number.isFinite(Number(val))) return '—'
  return Number(val).toFixed(2)
}

function fmtVol(val)  { return formatVolume(val) }
function fmtAmt(val)  { return formatAmount(val) }
</script>

<style scoped>
/* ── Card ── */
.dashboard-card {
  padding: 20px 24px;
}

/* ── Loading ── */
.db-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 0;
  color: var(--muted);
  font-size: 13px;
}

.db-loading-text { font-size: 13px; color: var(--muted); }

/* ── Main 2-column grid ── */
.db-grid {
  display: grid;
  grid-template-columns: 1fr 1.6fr;
  gap: 24px;
  align-items: start;
  margin-bottom: 16px;
}

/* ── Left: identity ── */
.db-identity {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.db-name {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.db-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.db-market-badge {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 2px 7px;
  font-size: 11px;
  font-weight: 700;
}

.db-symbol {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.db-industry-tag {
  font-size: 11px;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 7px;
}

.db-price-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.db-price {
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
  font-family: monospace;
  line-height: 1.1;
}

.db-change {
  font-size: 15px;
  font-weight: 600;
}

.up { color: var(--danger);  }
.dn { color: var(--success); }

.db-unavail {
  font-size: 13px;
  color: var(--muted);
  font-style: italic;
}

.db-watchlist-row { margin-top: 2px; }

.db-wl-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 20px;
  border: 1px solid transparent;
}

.db-wl-badge--on {
  background: var(--status-down-bg);
  color: var(--success);
  border-color: var(--status-down-ring);
}

.db-wl-badge--off {
  background: var(--surface2);
  color: var(--muted);
  border-color: var(--border);
}

/* ── Right: status + actions ── */
.db-right {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

/* ── Status cards ── */
.db-status-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.db-status-card {
  padding: 10px 11px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface2);
  min-width: 0;
}

.db-status-card--positive {
  border-color: var(--status-down-ring);
  background:   var(--status-down-bg);
}

.db-status-card--warning {
  border-color: var(--status-warn-ring);
  background:   var(--status-warn-bg);
}

.db-status-card--neutral {
  border-color: var(--status-info-ring);
  background:   var(--surface-hover);
}

.db-status-card--limited {
  border-color: var(--border);
  background:   var(--surface2);
  opacity: 0.7;
}

.dsc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  margin-bottom: 5px;
}

.dsc-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
}

.dsc-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  white-space: nowrap;
  flex-shrink: 0;
}

.dsc-badge--positive { background: var(--status-down-bg); color: var(--success); }
.dsc-badge--warning  { background: var(--status-warn-bg); color: var(--warn);    }
.dsc-badge--neutral  { background: var(--status-info-bg); color: var(--accent);  }
.dsc-badge--limited  { background: var(--surface2); color: var(--muted); }

.dsc-text {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.4;
  margin: 0;
  word-break: break-word;
}

/* ── Action buttons ── */
.db-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.db-btn {
  min-width: 80px;
}

.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-primary);
}

.btn-ghost {
  background: transparent;
  color: var(--muted);
  border-color: var(--border);
  font-size: 11px;
}

.btn-ghost:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--border-glow);
  background: var(--surface-hover);
}

.btn-watchlist-on {
  background: var(--status-down-bg);
  color: var(--success);
  border: 1px solid var(--status-down-ring);
}

.btn-watchlist-on:hover:not(:disabled) {
  background: var(--status-down-ring);
}

.btn-compare-on {
  background: var(--status-info-bg);
  color: var(--accent);
  border: 1px solid var(--status-info-ring);
}

.spinner--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
}

/* ── Quote metrics strip ── */
.db-metrics {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 4px;
  padding: 12px 0 4px;
  border-top: 1px solid var(--border);
  margin-top: 4px;
}

.db-metric {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.dbm-label {
  font-size: 10px;
  color: var(--muted);
}

.dbm-val {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  font-family: monospace;
}

/* ── Mobile ── */
@media (max-width: 640px) {
  .dashboard-card { padding: 16px; }

  .db-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .db-name { font-size: 18px; }

  .db-price { font-size: 22px; }

  .db-status-grid {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .db-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .db-btn { min-width: unset; width: 100%; text-align: center; justify-content: center; }

  .db-metrics {
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
}

@media (max-width: 400px) {
  .db-metrics { grid-template-columns: repeat(2, 1fr); }
}
</style>
