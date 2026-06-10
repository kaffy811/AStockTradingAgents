<template>
  <div class="ssb-wrap" ref="wrapRef">
    <!-- Input row -->
    <div class="ssb-input-row">
      <input
        ref="inputRef"
        class="ssb-input"
        type="text"
        :value="symbol"
        :disabled="disabled"
        :placeholder="effectivePlaceholder"
        autocomplete="off"
        autocorrect="off"
        spellcheck="false"
        @input="onInput"
        @keydown="onKeydown"
        @focus="onFocus"
      />
      <span v-if="loading" class="ssb-spinner spinner"></span>
    </div>

    <!-- Dropdown -->
    <div v-if="dropdownOpen" class="ssb-dropdown" role="listbox">
      <!-- Error state -->
      <div v-if="errorMsg" class="ssb-error-row">{{ errorMsg }}</div>

      <!-- Results -->
      <template v-else-if="items.length">
        <div
          v-for="(item, idx) in items"
          :key="item.symbol"
          class="ssb-item"
          :class="{ 'ssb-item--active': idx === highlightIdx }"
          role="option"
          @mousedown.prevent="selectItem(item)"
          @mousemove="highlightIdx = idx"
        >
          <span class="ssb-item-symbol">{{ item.symbol }}</span>
          <span class="ssb-item-name">{{ item.name || '—' }}</span>
          <span v-if="item.industry_name" class="ssb-item-industry">{{ item.industry_name }}</span>
        </div>
      </template>

      <!-- No results -->
      <div v-else-if="searched && !loading" class="ssb-empty">
        未找到 "{{ lastQuery }}"，可直接输入代码
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { searchStocks } from '../api/stocks.js'

// ── Props / emits ──────────────────────────────────────────────────────────────
const props = defineProps({
  market:      { type: String,  default: 'CN' },
  disabled:    { type: Boolean, default: false },
  placeholder: { type: String,  default: undefined },
})

const emit = defineEmits(['update:symbol', 'select'])

// v-model:symbol
const symbol = defineModel('symbol', { type: String, default: '' })

// ── Template refs ──────────────────────────────────────────────────────────────
const wrapRef  = ref(null)
const inputRef = ref(null)

// ── State ──────────────────────────────────────────────────────────────────────
const loading      = ref(false)
const errorMsg     = ref('')
const items        = ref([])
const dropdownOpen = ref(false)
const highlightIdx = ref(-1)
const searched     = ref(false)       // true once at least one search completed
const lastQuery    = ref('')          // query used for the last completed search

// ── Computed ───────────────────────────────────────────────────────────────────
const effectivePlaceholder = computed(() => {
  if (props.market === 'HK') return props.placeholder ?? '输入港股代码或名称'
  return props.placeholder ?? '输入股票代码或名称'
})

// ── Debounce timer ─────────────────────────────────────────────────────────────
let debounceTimer = null

function scheduleSearch(q) {
  clearTimeout(debounceTimer)
  if (q.trim().length < 1) {
    closeDropdown()
    return
  }
  debounceTimer = setTimeout(() => doSearch(q), 300)
}

async function doSearch(q) {
  loading.value  = true
  errorMsg.value = ''
  items.value    = []
  searched.value = false
  lastQuery.value = q
  try {
    const data = await searchStocks(props.market, q)
    items.value    = data.items || []
    searched.value = true
    dropdownOpen.value = true
    highlightIdx.value = -1
  } catch (e) {
    errorMsg.value = e.message || '搜索失败'
    dropdownOpen.value = true
  } finally {
    loading.value = false
  }
}

// ── Event handlers ─────────────────────────────────────────────────────────────
function onInput(e) {
  const val = e.target.value
  symbol.value = val
  scheduleSearch(val)
}

function onFocus() {
  // Re-open if there are cached results and input is non-empty
  if (symbol.value.trim() && items.value.length) {
    dropdownOpen.value = true
  }
}

function onKeydown(e) {
  if (!dropdownOpen.value) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlightIdx.value = Math.min(highlightIdx.value + 1, items.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlightIdx.value = Math.max(highlightIdx.value - 1, -1)
  } else if (e.key === 'Enter') {
    // stopPropagation: prevent parent's @keydown.enter (submit / handleAdd)
    // from firing when we're consuming Enter to select a dropdown item.
    e.preventDefault()
    e.stopPropagation()
    if (highlightIdx.value >= 0 && items.value[highlightIdx.value]) {
      selectItem(items.value[highlightIdx.value])
    }
    // If no item is highlighted, keep current typed value and let dropdown close
    // on next input event; do NOT submit — user may still be searching.
    else {
      closeDropdown()
    }
  } else if (e.key === 'Escape') {
    e.stopPropagation()
    closeDropdown()
  }
}

function selectItem(item) {
  symbol.value = item.symbol
  emit('select', item)
  closeDropdown()
}

function closeDropdown() {
  dropdownOpen.value = false
  highlightIdx.value = -1
}

// ── Click-outside ──────────────────────────────────────────────────────────────
function onClickOutside(e) {
  if (wrapRef.value && !wrapRef.value.contains(e.target)) {
    closeDropdown()
  }
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
})

onUnmounted(() => {
  clearTimeout(debounceTimer)
  document.removeEventListener('click', onClickOutside)
})

// ── Watch market change — clear search results ─────────────────────────────────
watch(() => props.market, () => {
  items.value = []
  searched.value = false
  closeDropdown()
})
</script>

<style scoped>
.ssb-wrap {
  position: relative;
  display: inline-block;
  width: 100%;
}

.ssb-input-row {
  position: relative;
  display: flex;
  align-items: center;
}

.ssb-input {
  width: 100%;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 8px 12px;
  font-size: 14px;
  font-family: monospace;
  letter-spacing: 0.03em;
  outline: none;
  transition: border-color 0.15s;
}

.ssb-input:focus { border-color: var(--accent); }

.ssb-spinner {
  position: absolute;
  right: 10px;
  pointer-events: none;
  width: 12px;
  height: 12px;
  border-width: 2px;
  margin-right: 0;
}

/* ── Dropdown ── */
.ssb-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  z-index: 200;
  max-height: 280px;
  overflow-y: auto;
  min-width: 240px;
}

.ssb-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  cursor: pointer;
  transition: background 0.1s;
}

.ssb-item:not(:last-child) {
  border-bottom: 1px solid var(--border);
}

.ssb-item--active,
.ssb-item:hover {
  background: var(--surface2);
}

.ssb-item-symbol {
  font-family: monospace;
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
  flex-shrink: 0;
  min-width: 60px;
}

.ssb-item-name {
  font-size: 13px;
  color: var(--text);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ssb-item-industry {
  font-size: 11px;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 6px;
  flex-shrink: 0;
  white-space: nowrap;
}

.ssb-empty,
.ssb-error-row {
  padding: 12px 14px;
  font-size: 13px;
  color: var(--muted);
  text-align: center;
}

.ssb-error-row { color: var(--danger); }

/* ── Mobile ── */
@media (max-width: 480px) {
  .ssb-dropdown {
    /* stretch to full viewport width edge, aligned to wrap left */
    min-width: 0;
    right: 0;
    left: 0;
  }

  .ssb-item-industry { display: none; }
}
</style>
