<template>
  <div class="scs-card card">

    <!-- Search row -->
    <div class="scs-search-row">
      <div class="scs-market-group">
        <label class="scs-label">{{ t('input_market_label') }}</label>
        <select v-model="searchMarket" class="scs-select">
          <option value="CN">CN — {{ t('input_market_cn') }}</option>
          <option value="HK">HK — {{ t('input_market_hk') }}</option>
        </select>
      </div>

      <div class="scs-ssb-group">
        <label class="scs-label">{{ t('cmp_sel_search') }}</label>
        <StockSearchBox
          v-model:symbol="searchSymbol"
          :market="searchMarket"
          @select="onSelect"
          @keydown.enter="onAddManual"
        />
      </div>

      <button
        class="btn btn-sm btn-primary scs-add-btn"
        :disabled="!searchSymbol.trim() || isFull"
        @click="onAddManual"
      >
        {{ t('cmp_sel_add') }}
      </button>
    </div>

    <!-- Inline tip -->
    <div v-if="dupTip" class="scs-tip scs-tip--warn">{{ dupTip }}</div>
    <div v-else-if="isFull" class="scs-tip scs-tip--info">{{ t('cmp_sel_full') }}</div>

    <!-- Chips -->
    <div v-if="selectedStocks.length > 0" class="scs-chips">
      <div
        v-for="stock in selectedStocks"
        :key="`${stock.market}/${stock.symbol}`"
        class="scs-chip"
      >
        <span class="scs-chip-market">{{ stock.market }}</span>
        <span class="scs-chip-symbol">{{ stock.symbol }}</span>
        <span v-if="stock.name" class="scs-chip-name">{{ stock.name }}</span>
        <button class="scs-chip-remove" @click="emit('remove', stock)">×</button>
      </div>
    </div>

    <!-- Min count hint -->
    <div v-if="selectedStocks.length === 0" class="scs-hint">
      {{ t('cmp_sel_hint0') }}
    </div>
    <div v-else-if="selectedStocks.length === 1" class="scs-hint">
      {{ t('cmp_sel_hint1') }}
    </div>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import StockSearchBox from './StockSearchBox.vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  selectedStocks: { type: Array,   default: () => [] },
  loading:        { type: Boolean, default: false },
})

const emit = defineEmits(['add', 'remove', 'clear'])

const searchMarket = ref('CN')
const searchSymbol = ref('')
const dupTip       = ref('')

const isFull = computed(() => props.selectedStocks.length >= 4)

let dupTimer = null
function showDup(msg) {
  dupTip.value = msg
  clearTimeout(dupTimer)
  dupTimer = setTimeout(() => { dupTip.value = '' }, 2500)
}

function tryAdd(market, symbol, name = '') {
  const sym = symbol.trim()
  if (!sym) return
  if (isFull.value) { showDup(t('cmp_sel_full')); return }
  const key = `${market}/${sym}`
  if (props.selectedStocks.some(s => `${s.market}/${s.symbol}` === key)) {
    showDup(t('cmp_sel_dup', { key }))
    return
  }
  emit('add', { market, symbol: sym, name })
  searchSymbol.value = ''
}

function onSelect(item) {
  tryAdd(searchMarket.value, item.symbol, item.name || item.stock_name || '')
}

function onAddManual() {
  tryAdd(searchMarket.value, searchSymbol.value)
}
</script>

<style scoped>
.scs-card {
  padding: 14px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── Search row ── */
.scs-search-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.scs-market-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
}

.scs-ssb-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 160px;
}

.scs-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.scs-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 12px;
  outline: none;
  cursor: pointer;
  min-width: 100px;
}

.scs-select:focus { border-color: var(--accent); }

.scs-add-btn {
  flex-shrink: 0;
  align-self: flex-end;
}

/* ── Tips ── */
.scs-tip {
  font-size: 12px;
  padding: 4px 0;
}

.scs-tip--warn { color: var(--warn); }
.scs-tip--info { color: var(--muted); }

/* ── Chips ── */
.scs-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.scs-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 3px 8px 3px 6px;
  font-size: 12px;
  max-width: 200px;
}

.scs-chip-market {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 3px;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.scs-chip-symbol {
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.scs-chip-name {
  font-size: 11px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 80px;
}

.scs-chip-remove {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 14px;
  line-height: 1;
  padding: 0 0 0 2px;
  flex-shrink: 0;
  transition: color 0.12s;
}

.scs-chip-remove:hover { color: var(--danger); }

/* ── Hint ── */
.scs-hint {
  font-size: 12px;
  color: var(--muted);
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .scs-search-row {
    flex-direction: column;
    align-items: stretch;
  }

  .scs-market-group,
  .scs-ssb-group { width: 100%; }

  .scs-add-btn { width: 100%; }
}
</style>
