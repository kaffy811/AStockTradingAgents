<template>
  <div class="card discovery-panel">
    <!-- Tab bar -->
    <div class="dp-tabs">
      <button
        :class="['dp-tab', { 'dp-tab--active': activeTab === 'recommend' }]"
        @click="activeTab = 'recommend'"
      >{{ t('disc_tab_quick') }}</button>
      <button
        :class="['dp-tab', { 'dp-tab--active': activeTab === 'industry' }]"
        @click="switchToIndustry"
      >{{ t('disc_tab_industry') }}</button>
    </div>

    <!-- 推荐搜索 -->
    <div v-if="activeTab === 'recommend'" class="dp-content">
      <p class="dp-hint">{{ t('disc_hint_recommend') }}</p>
      <p class="dp-section-label">{{ topSearches.length > 0 ? t('disc_section_top') : t('disc_section_default') }}</p>
      <div class="chips-wrap">
        <button
          v-for="chip in displayChips"
          :key="chip.market + ':' + chip.symbol"
          class="pick-chip"
          @click="emit('pick', { market: chip.market, symbol: chip.symbol })"
        >
          <span class="chip-market">{{ chip.market }}</span>
          <span class="chip-sym">{{ chip.symbol }}</span>
          <span class="chip-name">{{ chip.name || chip.stock_name }}</span>
          <span v-if="chip.count >= 2" :class="['chip-freq', chip.count >= 5 ? 'chip-freq--hi' : '']">
            {{ chip.count }}{{ t('disc_count_suffix') }}
          </span>
        </button>
      </div>
    </div>

    <!-- 行业热门 -->
    <div v-else class="dp-content">
      <!-- Industry select / loading / error -->
      <div class="dp-ctrl">
        <div v-if="indLoading" class="dp-state">
          <span class="spinner"></span> {{ t('disc_loading_industries') }}
        </div>
        <template v-else-if="indError">
          <!-- Industry list failed to load — show error + retry inline -->
        </template>
        <select
          v-else
          v-model="selectedCode"
          class="ind-select"
          @change="loadHot"
        >
          <option
            v-for="ind in industries"
            :key="ind.industry_code"
            :value="ind.industry_code"
          >{{ ind.industry_name }}</option>
        </select>
        <span v-if="!indError" class="dp-hint-inline">{{ t('disc_hint_industry') }}</span>
      </div>

      <!-- Industry list error -->
      <EmptyState
        v-if="indError"
        icon="⚠️"
        :title="t('disc_error_industry')"
        :message="indError"
        :action-text="t('disc_retry')"
        :compact="true"
        @action="retryIndustries"
      />

      <!-- Hot stocks loading -->
      <div v-else-if="hotLoading" class="dp-state">
        <span class="spinner"></span> {{ t('disc_loading_hot') }}
      </div>

      <!-- Hot stocks error -->
      <EmptyState
        v-else-if="hotError"
        icon="⚠️"
        :title="t('disc_error_industry')"
        :message="hotError"
        :action-text="t('disc_retry')"
        :compact="true"
        @action="loadHot"
      />

      <!-- Hot stocks empty -->
      <EmptyState
        v-else-if="!hotData || !hotData.items || hotData.items.length === 0"
        icon="📊"
        :title="t('disc_error_industry')"
        message=""
        :action-text="t('disc_retry')"
        :compact="true"
        @action="loadHot"
      />

      <!-- List -->
      <div v-else class="hot-list">
        <div
          v-for="item in hotData.items"
          :key="item.symbol"
          class="hot-row"
        >
          <span class="hot-rank">{{ item.rank }}</span>
          <span class="hot-name-sym">
            <span class="hot-name">{{ item.stock_name || item.symbol }}</span>
            <span class="hot-sym">{{ item.symbol }}</span>
          </span>
          <span :class="['hot-pct', pctClass(item.change_pct)]">{{ formatPct(item.change_pct) }}</span>
          <button
            class="btn btn-secondary btn-xs"
            @click="emit('pick', { market: 'CN', symbol: item.symbol })"
          >分析</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { listIndustries, getIndustryHotStocks } from '../api/industries.js'
import { getTopSearches } from '../utils/recentSearches.js'
import EmptyState from './EmptyState.vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const DEFAULT_PICKS = [
  { market: 'CN', symbol: '600519', name: '贵州茅台' },
  { market: 'CN', symbol: '000001', name: '平安银行' },
  { market: 'CN', symbol: '300750', name: '宁德时代' },
  { market: 'HK', symbol: '00700', name: '腾讯控股' },
  { market: 'HK', symbol: '09988', name: '阿里巴巴-W' },
]

const emit = defineEmits(['pick'])

const activeTab    = ref('recommend')
const topSearches  = ref([])
const indLoading   = ref(false)
const indError     = ref('')
const industries   = ref([])
const selectedCode = ref('')
const hotLoading   = ref(false)
const hotError     = ref('')
const hotData      = ref(null)
const indLoaded    = ref(false)

// ── High-frequency top searches ───────────────────────────────────────────────
const displayChips = computed(() => {
  if (topSearches.value.length > 0) return topSearches.value
  return DEFAULT_PICKS
})

function refreshTopSearches() {
  topSearches.value = getTopSearches(5)
}

function handleRecentUpdate() {
  refreshTopSearches()
}

onMounted(() => {
  refreshTopSearches()
  window.addEventListener('recent-searches-updated', handleRecentUpdate)
})

onUnmounted(() => {
  window.removeEventListener('recent-searches-updated', handleRecentUpdate)
})

async function loadIndustries() {
  if (indLoaded.value) return
  indLoading.value = true
  indError.value   = ''
  hotError.value   = ''
  try {
    const list = await listIndustries('CN')
    industries.value = list
    const pref = list.find(i => i.industry_name.includes('食品饮料')) || list[0]
    if (pref) selectedCode.value = pref.industry_code
    indLoaded.value = true
    await loadHot()
  } catch (e) {
    indError.value = e.message || t('disc_error_industry')
  } finally {
    indLoading.value = false
  }
}

function retryIndustries() {
  indLoaded.value = false
  loadIndustries()
}

async function loadHot() {
  if (!selectedCode.value) return
  hotLoading.value = true
  hotError.value   = ''
  hotData.value    = null
  try {
    hotData.value = await getIndustryHotStocks('CN', selectedCode.value, { limit: 5 })
  } catch (e) {
    hotError.value = e.message || t('disc_loading_hot')
  } finally {
    hotLoading.value = false
  }
}

function switchToIndustry() {
  activeTab.value = 'industry'
  loadIndustries()
}

function formatPct(v) {
  if (v == null || !Number.isFinite(v)) return '—'
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
}

function pctClass(v) {
  if (v == null) return ''
  return v > 0 ? 'pct-up' : v < 0 ? 'pct-dn' : ''
}
</script>

<style scoped>
.discovery-panel {
  margin-bottom: 20px;
}

/* ── Tabs ── */
.dp-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
}

.dp-tab {
  padding: 5px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 20px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}

.dp-tab:hover {
  color: var(--accent);
  border-color: var(--border-glow);
}

.dp-tab--active {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--border-glow);
}

/* ── Content ── */
.dp-content { /* no extra margin */ }

.dp-hint {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 10px;
}

.dp-hint-inline {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

/* ── Section label ── */
.dp-section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 8px;
}

/* ── Recommend chips ── */
.chips-wrap {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  /* prevent body overflow on mobile */
  max-width: 100%;
}

.pick-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: border-color 0.15s, color 0.15s;
}

.pick-chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.chip-market {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
}

.chip-sym {
  font-family: monospace;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
}

.chip-name {
  color: var(--text);
}

.chip-freq {
  font-size: 10px;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0 4px;
  line-height: 1.6;
  flex-shrink: 0;
}

.chip-freq--hi {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

/* ── Industry ctrl ── */
.dp-ctrl {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.ind-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 13px;
  outline: none;
  min-width: 140px;
  cursor: pointer;
}

.ind-select:focus { border-color: var(--accent); }

/* ── State rows ── */
.dp-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  font-size: 13px;
  color: var(--muted);
}

.dp-muted { color: var(--muted); }
.dp-err   { font-size: 13px; color: var(--danger); padding: 10px 0; }

/* ── Hot list ── */
.hot-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.hot-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 6px;
  border-radius: 6px;
  transition: background 0.1s;
}

.hot-row:hover { background: var(--surface2); }

.hot-rank {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  width: 20px;
  text-align: center;
  flex-shrink: 0;
}

.hot-name-sym {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.hot-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hot-sym {
  font-size: 11px;
  font-family: monospace;
  color: var(--muted);
}

.hot-pct {
  font-size: 12px;
  font-weight: 600;
  min-width: 56px;
  text-align: right;
  flex-shrink: 0;
}

.pct-up { color: var(--danger); }
.pct-dn { color: var(--success); }

.btn-xs {
  padding: 3px 10px;
  font-size: 11px;
  height: 24px;
  line-height: 1;
  flex-shrink: 0;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .dp-ctrl {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .ind-select {
    width: 100%;
    min-width: 0;
  }

  .dp-hint-inline { white-space: normal; }

  /* Chips: wrap naturally, no horizontal overflow */
  .chips-wrap {
    flex-wrap: wrap;
    overflow-x: visible;
  }
}
</style>
