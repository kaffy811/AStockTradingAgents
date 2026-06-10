<template>
  <div class="sct-wrap">

    <!-- ── Loading skeleton ── -->
    <div v-if="loading && profiles.length === 0" class="sct-loading">
      <span class="spinner"></span> {{ t('ind_loading') }}
    </div>

    <!-- ── Desktop table ── -->
    <div v-if="profiles.length > 0" class="sct-table-wrap card">
      <table class="sct-table">
        <thead>
          <tr>
            <th class="sct-th sct-th--stock">{{ t('cmp_tbl_stock') }}</th>
            <th class="sct-th sct-th--price">{{ t('cmp_tbl_price') }}</th>
            <th class="sct-th sct-th--change">{{ t('cmp_tbl_change') }}</th>
            <th class="sct-th sct-th--industry">{{ t('cmp_tbl_industry') }}</th>
            <th class="sct-th sct-th--report">{{ t('cmp_tbl_report') }}</th>
            <th class="sct-th sct-th--quality">{{ t('cmp_tbl_quality') }}</th>
            <th class="sct-th sct-th--trend">{{ t('cmp_tbl_trend') }}</th>
            <th class="sct-th sct-th--actions">{{ t('cmp_tbl_ops') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(p, i) in profiles"
            :key="`${p._market}/${p._symbol}`"
            :class="{ 'sct-row--loading': p._loading }"
          >
            <!-- Stock identity -->
            <td class="sct-td">
              <div class="sct-identity">
                <span class="sct-market-badge">{{ p._market }}</span>
                <div class="sct-names">
                  <span class="sct-name">{{ stockName(p) }}</span>
                  <span class="sct-symbol">{{ p._symbol }}</span>
                </div>
              </div>
            </td>

            <!-- Price -->
            <td class="sct-td sct-td--price">
              <span v-if="p._loading" class="sct-muted">…</span>
              <span v-else-if="p._failed || p?.quote?.status !== 'success'" class="sct-muted sct-unavail">
                {{ t('wl_card_quote_fail') }}
              </span>
              <span v-else class="sct-price">{{ fmtPrice(p?.quote?.latest_price) }}</span>
            </td>

            <!-- Change pct -->
            <td class="sct-td">
              <span v-if="p._loading || p._failed || p?.quote?.status !== 'success'" class="sct-muted">—</span>
              <span v-else :class="['sct-change', changePctClass(p?.quote?.change_pct)]">
                {{ formatChangePct(p?.quote?.change_pct) }}
              </span>
            </td>

            <!-- Industry -->
            <td class="sct-td">
              <span v-if="p._loading" class="sct-muted">…</span>
              <span v-else-if="p?.industry?.industry_name" class="sct-industry">
                {{ p.industry.industry_name }}
              </span>
              <span v-else class="sct-muted">{{ t('cmp_tbl_industry_na') }}</span>
            </td>

            <!-- Latest report -->
            <td class="sct-td">
              <span v-if="p._loading" class="sct-muted">…</span>
              <template v-else-if="p?.latest_report">
                <div class="sct-report-scope">{{ scopeLabel(p.latest_report.analysis_scope) }}</div>
                <div class="sct-report-time">{{ fmtTime(p.latest_report.created_at) }}</div>
              </template>
              <span v-else class="sct-muted">{{ t('wl_card_no_report') }}</span>
            </td>

            <!-- Data quality -->
            <td class="sct-td">
              <span v-if="p._loading" class="sct-muted">…</span>
              <div v-else class="sct-quality-dots">
                <span :class="['sct-qdot', qualityDotClass(p?.quote?.status)]" title="行情"></span>
                <span :class="['sct-qdot', qualityDotClass(p?.industry?.status)]" title="行业"></span>
                <span :class="['sct-qdot', qualityDotClass(p?.latest_report ? 'success' : 'none')]" title="报告"></span>
              </div>
            </td>

            <!-- Trend -->
            <td class="sct-td sct-td--trend">
              <span v-if="p._failed" class="sct-muted sct-unavail">{{ t('cmp_tbl_data_na') }}</span>
              <StockMiniTrend
                v-else-if="!p._loading"
                :market="p._market"
                :symbol="p._symbol"
                :height="42"
                :points="30"
              />
            </td>

            <!-- Actions -->
            <td class="sct-td sct-td--actions">
              <div class="sct-action-row">
                <button class="btn btn-sm btn-secondary" @click="emit('detail', p)">{{ t('ind_card_detail') }}</button>
                <button class="btn btn-sm btn-secondary" @click="emit('analyze', p)">{{ t('ind_card_analyze') }}</button>
                <button class="btn btn-sm btn-secondary" @click="emit('history', p)">{{ t('ind_card_history') }}</button>
                <button class="btn btn-sm sct-remove-btn" @click="emit('remove', p)">{{ t('cmp_tbl_remove') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ── Mobile cards ── -->
    <div v-if="profiles.length > 0" class="sct-cards">
      <div
        v-for="p in profiles"
        :key="`card-${p._market}/${p._symbol}`"
        class="sct-card card"
      >
        <!-- Card header -->
        <div class="sct-card-header">
          <span class="sct-market-badge">{{ p._market }}</span>
          <span class="sct-card-name">{{ stockName(p) }}</span>
          <span class="sct-card-symbol">{{ p._symbol }}</span>
          <span
            v-if="!p._loading && !p._failed && p?.quote?.status === 'success'"
            :class="['sct-card-change', changePctClass(p?.quote?.change_pct)]"
          >
            {{ formatChangePct(p?.quote?.change_pct) }}
          </span>
        </div>

        <!-- Card fields -->
        <div class="sct-card-fields">
          <div class="sct-card-field">
            <span class="sct-field-label">{{ t('cmp_tbl_price') }}</span>
            <span class="sct-field-value">
              <span v-if="p._loading">…</span>
              <span v-else-if="p._failed || p?.quote?.status !== 'success'" class="sct-unavail">{{ t('cmp_tbl_na') }}</span>
              <span v-else>{{ fmtPrice(p?.quote?.latest_price) }}</span>
            </span>
          </div>
          <div class="sct-card-field">
            <span class="sct-field-label">{{ t('cmp_tbl_industry') }}</span>
            <span class="sct-field-value">
              <span v-if="p._loading">…</span>
              <span v-else>{{ p?.industry?.industry_name || '—' }}</span>
            </span>
          </div>
          <div class="sct-card-field">
            <span class="sct-field-label">{{ t('cmp_tbl_report') }}</span>
            <span class="sct-field-value">
              <span v-if="p._loading">…</span>
              <template v-else-if="p?.latest_report">
                {{ scopeLabel(p.latest_report.analysis_scope) }}
                <span class="sct-time-small">{{ fmtTime(p.latest_report.created_at) }}</span>
              </template>
              <span v-else class="sct-muted">{{ t('wl_card_no_report') }}</span>
            </span>
          </div>
        </div>

        <!-- Card trend -->
        <div class="sct-card-trend">
          <span class="sct-field-label">{{ t('cmp_tbl_trend') }}</span>
          <div class="sct-trend-box">
            <span v-if="p._failed" class="sct-muted sct-unavail">{{ t('cmp_tbl_data_na') }}</span>
            <StockMiniTrend
              v-else-if="!p._loading"
              :market="p._market"
              :symbol="p._symbol"
              :height="36"
              :points="30"
            />
          </div>
        </div>

        <!-- Card actions -->
        <div class="sct-card-actions">
          <button class="btn btn-sm btn-secondary" @click="emit('detail', p)">{{ t('ind_card_detail') }}</button>
          <button class="btn btn-sm btn-secondary" @click="emit('analyze', p)">{{ t('ind_card_analyze') }}</button>
          <button class="btn btn-sm btn-secondary" @click="emit('history', p)">{{ t('ind_card_history') }}</button>
          <button class="btn btn-sm sct-remove-btn" @click="emit('remove', p)">{{ t('cmp_tbl_remove') }}</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { formatChangePct, changePctClass } from '../utils/marketFormat.js'
import StockMiniTrend from './StockMiniTrend.vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  profiles: { type: Array,   default: () => [] },
  loading:  { type: Boolean, default: false },
})

const emit = defineEmits(['detail', 'analyze', 'history', 'remove'])

function scopeLabel(s) {
  const map = {
    comprehensive:         () => t('badge_comprehensive'),
    technical_only:        () => t('badge_technical'),
    fundamental_only:      () => t('badge_fundamental'),
    peer_only:             () => t('badge_peer'),
    news_only:             () => t('badge_news'),
    technical_fundamental: () => t('badge_tech_fund'),
  }
  return (map[s] || (() => t('badge_comprehensive')))()
}

function stockName(p) {
  return p?.quote?.stock_name || p?.industry?.stock_name || p?._name || `${p._market}/${p._symbol}`
}

function fmtPrice(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(2)
}

function fmtTime(ts) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return ts }
}

function qualityDotClass(status) {
  if (!status || status === 'none' || status === 'failed') return 'sct-qdot--fail'
  if (status === 'success') return 'sct-qdot--ok'
  return 'sct-qdot--warn'
}
</script>

<style scoped>
.sct-wrap {}

/* ── Loading ── */
.sct-loading {
  text-align: center;
  color: var(--muted);
  padding: 32px 0;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

/* ── Table ── */
.sct-table-wrap {
  padding: 0;
  overflow-x: auto;
}

.sct-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.sct-th {
  padding: 10px 14px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.sct-td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.sct-table tbody tr:last-child .sct-td { border-bottom: none; }
.sct-table tbody tr:hover { background: var(--surface2); }
.sct-row--loading { opacity: 0.6; }

/* Column widths */
.sct-th--price,  .sct-td--price  { width: 90px; }
.sct-th--change                  { width: 80px; }
.sct-th--industry                { min-width: 100px; }
.sct-th--report                  { min-width: 120px; }
.sct-th--quality                 { width: 80px; }
.sct-th--trend, .sct-td--trend   { width: 130px; min-width: 100px; }
.sct-th--actions, .sct-td--actions { width: 180px; }

/* ── Identity ── */
.sct-identity {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.sct-market-badge {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 2px;
}

.sct-names {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.sct-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}

.sct-symbol {
  font-size: 11px;
  font-family: monospace;
  color: var(--muted);
}

/* Price & change */
.sct-price {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.sct-change {
  font-weight: 600;
  font-size: 13px;
}

.up   { color: var(--danger); }
.down { color: var(--success); }

.sct-muted { color: var(--muted); font-size: 12px; }
.sct-unavail { font-size: 11px; }

/* Industry */
.sct-industry {
  font-size: 12px;
  color: var(--text);
}

/* Report */
.sct-report-scope {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}
.sct-report-time {
  font-size: 11px;
  color: var(--muted);
}

/* Quality dots */
.sct-quality-dots {
  display: flex;
  gap: 5px;
  align-items: center;
}

.sct-qdot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sct-qdot--ok   { background: var(--success); }
.sct-qdot--warn { background: var(--warn); }
.sct-qdot--fail { background: var(--border); }

/* Actions row */
.sct-action-row {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.sct-remove-btn {
  background: var(--status-up-bg);
  color: var(--danger);
  border: 1px solid var(--status-up-ring);
}
.sct-remove-btn:hover { background: var(--status-up-ring); }

/* ── Mobile cards (hidden on desktop) ── */
.sct-cards { display: none; }

.sct-card {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sct-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.sct-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}

.sct-card-symbol {
  font-size: 12px;
  font-family: monospace;
  color: var(--muted);
}

.sct-card-change {
  font-size: 13px;
  font-weight: 700;
  margin-left: auto;
}

.sct-card-fields {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.sct-card-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sct-field-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.sct-field-value {
  font-size: 12px;
  color: var(--text);
}

.sct-time-small {
  font-size: 10px;
  color: var(--muted);
  display: block;
}

.sct-card-trend {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sct-trend-box {
  width: 100%;
}

.sct-card-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.sct-card-actions .btn { text-align: center; }

/* ── Mobile: hide table, show cards ── */
@media (max-width: 600px) {
  .sct-table-wrap { display: none; }
  .sct-cards      { display: flex; flex-direction: column; gap: 0; }

  .sct-card-fields {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
