<template>
  <div class="card industry-card">
    <!-- ── Header ──────────────────────────────────────────────────────────── -->
    <div class="industry-header">
      <div class="industry-title-area">
        <span class="card-title">行业热门股</span>
        <span v-if="industryInfo" class="industry-subtitle">
          {{ props.market }}/{{ props.symbol }}<template v-if="props.stockName"> {{ props.stockName }}</template>
          &nbsp;·&nbsp; 申万一级：{{ industryInfo.industry_name }}
        </span>
        <span v-else-if="!loading" class="industry-subtitle muted">
          {{ props.market }}/{{ props.symbol }}<template v-if="props.stockName"> {{ props.stockName }}</template>
        </span>
      </div>

      <!-- Source badge -->
      <span v-if="sourceLabel" :class="['source-badge', sourceBadgeClass]">
        {{ sourceLabel }}
      </span>
    </div>

    <!-- ── Loading ─────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="industry-state">
      <span class="spinner"></span>
      <span class="state-text">加载行业热门股…</span>
    </div>

    <!-- ── Error ───────────────────────────────────────────────────────────── -->
    <div v-else-if="errorMsg" class="industry-state industry-state--error">
      <span class="state-text error-text">{{ errorMsg }}</span>
    </div>

    <!-- ── HK / unsupported ────────────────────────────────────────────────── -->
    <div v-else-if="peerSource === 'unsupported'">
      <EmptyState
        icon="🌏"
        title="当前市场暂不支持行业热门股"
        message="港股暂不使用申万行业体系，同行与行业热门股数据可能不完整。技术面、基本面和新闻面分析仍可继续参考。"
        :compact="true"
      />
    </div>

    <!-- ── dynamic_hot ─────────────────────────────────────────────────────── -->
    <template v-else-if="peerSource === 'dynamic_hot' && peers.length > 0">
      <div class="table-wrap">
        <table class="hot-table">
          <thead>
            <tr>
              <th class="col-rank">排名</th>
              <th class="col-name">股票</th>
              <th class="col-score">Hot Score</th>
              <th class="col-amount">成交额</th>
              <th class="col-change">涨跌幅</th>
              <th class="col-action"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in peers" :key="item.symbol">
              <td class="col-rank rank-num">{{ item.rank }}</td>
              <td class="col-name">
                <span class="stock-name">{{ item.name || item.symbol }}</span>
                <span class="stock-symbol">{{ item.symbol }}</span>
              </td>
              <td class="col-score score-val">
                {{ item.hot_score != null ? item.hot_score.toFixed(3) : '—' }}
              </td>
              <td class="col-amount">
                {{ formatAmount(item.score_factors?.amount) }}
              </td>
              <td class="col-change" :class="changePctClass(item.score_factors?.change_pct)">
                {{ formatChangePct(item.score_factors?.change_pct) }}
              </td>
              <td class="col-action">
                <button class="btn btn-secondary btn-xs" @click="goDetail(item)">
                  详情
                </button>
                <button class="btn btn-secondary btn-xs" @click="goAnalyze(item)">
                  分析
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- ── manual_map ──────────────────────────────────────────────────────── -->
    <template v-else-if="peerSource === 'manual_map'">
      <p class="manual-note">
        该股票使用人工精选同行配置，优先级高于动态热门股。人工同行更强调业务可比性，动态热门股更强调市场关注度。
      </p>
      <div v-if="peers.length > 0" class="manual-peers">
        <span
          v-for="item in peers"
          :key="item.symbol"
          class="peer-chip"
        >
          <button class="peer-chip-btn" @click="goAnalyze(item)">
            {{ item.name || item.symbol }}&nbsp;<span class="peer-sym">{{ item.symbol }}</span>
          </button>
        </span>
      </div>
    </template>

    <!-- ── none / empty ────────────────────────────────────────────────────── -->
    <template v-else-if="peerSource === 'none' || (peerSource && peers.length === 0)">
      <EmptyState
        icon="📊"
        title="暂无同行热门股数据"
        :message="noneMessage"
        :compact="true"
      />
    </template>

    <!-- ── Disclaimer ──────────────────────────────────────────────────────── -->
    <p v-if="!loading && peerSource && peerSource !== 'unsupported'" class="disclaimer">
      Hot Score 基于行业内成交额与涨跌幅波动计算，用于衡量市场关注度，不代表投资价值，也不等同于严格业务可比性。
    </p>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getDynamicPeers } from '../api/industries.js'
import EmptyState from './EmptyState.vue'

// ── Props ─────────────────────────────────────────────────────────────────────
const props = defineProps({
  market:    { type: String,  required: true },
  symbol:    { type: String,  required: true },
  visible:   { type: Boolean, default: true  },
  stockName: { type: String,  default: ''    },  // P6-b: 股票中文名
})

const router = useRouter()

// ── State ─────────────────────────────────────────────────────────────────────
const loading       = ref(false)
const errorMsg      = ref('')
const peers         = ref([])
const industryInfo  = ref(null)   // { industry_code, industry_name, ... }
const peerSource    = ref('')     // 'dynamic_hot' | 'manual_map' | 'none' | 'unsupported'
const fallbackReason = ref('')

// ── P6-0 fix: sourceLabel / sourceBadgeClass as computed (was plain object → JSON bug) ──
const SOURCE_LABEL_MAP = {
  dynamic_hot: '动态热门',
  manual_map:  '手动同行',
  none:        '无数据',
  unsupported: '不支持',
  '':          '',
}
const SOURCE_BADGE_MAP = {
  dynamic_hot: 'badge-hot',
  manual_map:  'badge-manual',
  none:        'badge-none',
  unsupported: 'badge-none',
  '':          '',
}
const sourceLabel      = computed(() => SOURCE_LABEL_MAP[peerSource.value] ?? '')
const sourceBadgeClass = computed(() => SOURCE_BADGE_MAP[peerSource.value] ?? '')

const noneMessage = computed(() => {
  const base = '当前未找到足够的同行样本。技术面、基本面和新闻面分析仍可继续参考。'
  if (fallbackReason.value) return `${base} （${fallbackReason.value}）`
  return base
})

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function fetchDynamicPeers() {
  if (!props.visible || !props.market || !props.symbol) return

  // HK (and any non-CN market without PEER_MAP) won't have SW industry data.
  // Short-circuit with a friendly message instead of making a request that
  // returns an empty peers array with a cryptic message field.
  if (props.market !== 'CN') {
    loading.value        = false
    errorMsg.value       = ''
    industryInfo.value   = null
    peers.value          = []
    fallbackReason.value = ''
    peerSource.value     = 'unsupported'
    return
  }

  loading.value      = true
  errorMsg.value     = ''
  peerSource.value   = ''

  try {
    const res = await getDynamicPeers(props.market, props.symbol, { limit: 5 })
    industryInfo.value   = res.industry   || null
    peers.value          = res.peers      || []
    peerSource.value     = res.data_quality?.peer_source || 'none'
    fallbackReason.value = res.data_quality?.fallback_reason || ''
  } catch (e) {
    errorMsg.value = e.message || '行业热门股加载失败'
  } finally {
    loading.value = false
  }
}

// Re-fetch when the parent supplies a different ticker (watch, not onMounted,
// because HistoryDetailView is not keep-alive cached — every mount re-runs setup).
watch(
  () => [props.market, props.symbol, props.visible],
  fetchDynamicPeers,
  { immediate: true },
)

// ── Navigation ────────────────────────────────────────────────────────────────
function goDetail(item) {
  router.push(`/stocks/${item.market || props.market}/${item.symbol}`)
}

function goAnalyze(item) {
  router.push({ path: '/', query: { market: item.market || props.market, symbol: item.symbol } })
}

// ── Formatting helpers ────────────────────────────────────────────────────────
function formatAmount(yuan) {
  if (yuan == null || !Number.isFinite(yuan)) return '—'
  const yi = yuan / 1e8
  return yi >= 1
    ? yi.toFixed(1) + '亿'
    : (yuan / 1e4).toFixed(0) + '万'
}

function formatChangePct(pct) {
  if (pct == null || !Number.isFinite(pct)) return '—'
  return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'
}

function changePctClass(pct) {
  if (pct == null || !Number.isFinite(pct)) return ''
  return pct > 0 ? 'pct-up' : pct < 0 ? 'pct-dn' : ''
}
</script>

<style scoped>
/* Inherits .card from base.css */

.industry-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.industry-title-area {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

/* Override card-title margin for inline use */
.industry-title-area .card-title {
  margin-bottom: 0;
}

.industry-subtitle {
  font-size: 12px;
  color: var(--muted);
}

/* ── Source badge ── */
.source-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
  border: 1px solid transparent;
}

.badge-hot {
  background: var(--status-down-bg);
  border-color: var(--status-down-ring);
  color: var(--success);
}

.badge-manual {
  background: var(--status-info-bg);
  border-color: var(--border-glow);
  color: var(--accent);
}

.badge-none {
  background: var(--surface2);
  border-color: var(--border);
  color: var(--muted);
}

/* ── State rows ── */
.industry-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
}

.industry-state--error .state-text {
  color: var(--danger);
}

.state-text {
  font-size: 13px;
  color: var(--muted);
}

.muted { color: var(--muted); }
.error-text { color: var(--danger); }

/* ── Table ── */
.table-wrap {
  overflow-x: auto;          /* horizontal scroll on small screens */
  -webkit-overflow-scrolling: touch;
}

.hot-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.hot-table th {
  text-align: left;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.hot-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.hot-table tbody tr:last-child td {
  border-bottom: none;
}

.hot-table tbody tr:hover {
  background: var(--surface2);
}

/* Column widths */
.col-rank   { width: 46px;  text-align: center; }
.col-name   { min-width: 110px; }
.col-score  { width: 80px;  text-align: right; }
.col-amount { width: 80px;  text-align: right; }
.col-change { width: 76px;  text-align: right; }
.col-action { width: 100px; text-align: center; display: flex; gap: 4px; align-items: center; }

.rank-num {
  font-weight: 700;
  color: var(--muted);
  text-align: center;
}

.stock-name {
  display: block;
  font-weight: 600;
  color: var(--text);
}

.stock-symbol {
  display: block;
  font-size: 11px;
  color: var(--muted);
}

.score-val { color: var(--accent); font-weight: 600; }

.pct-up { color: var(--success); font-weight: 600; }
.pct-dn { color: var(--danger);  font-weight: 600; }

.btn-xs {
  padding: 2px 8px;
  font-size: 11px;
  height: 22px;
  line-height: 1;
}

/* ── Manual map ── */
.manual-note {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.6;
  margin: 0 0 12px;
}

.manual-peers {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}

.peer-chip-btn {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.peer-chip-btn:hover {
  background: var(--status-info-bg);
  border-color: var(--accent);
  color: var(--accent);
}

.peer-sym {
  color: var(--muted);
  font-size: 11px;
}

/* ── Empty / none ── */
.empty-note {
  font-size: 13px;
  padding: 10px 0;
  margin: 0;
}

/* ── Disclaimer ── */
.disclaimer {
  font-size: 11px;
  color: var(--muted);
  margin: 12px 0 0;
  line-height: 1.5;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .industry-header {
    flex-direction: column;
    gap: 6px;
  }
  .col-score,
  .col-amount {
    display: none;   /* hide on very small screens; scroll still available */
  }
}
</style>
