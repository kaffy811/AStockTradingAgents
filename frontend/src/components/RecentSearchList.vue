<template>
  <div class="recent-searches card">
    <!-- Header: always shown -->
    <div class="recent-header">
      <span class="recent-title">{{ t('recent_title') }}</span>
      <button v-if="items.length > 0" class="recent-clear" @click="onClear">{{ t('recent_clear') }}</button>
    </div>

    <!-- Empty state -->
    <p v-if="items.length === 0" class="recent-empty">
      {{ t('recent_empty') }}
    </p>

    <!-- Chips -->
    <div v-else class="recent-chips">
      <button
        v-for="item in visibleItems"
        :key="item.market + ':' + item.symbol"
        class="recent-chip"
        @click="onPick(item)"
      >
        <span class="chip-market">{{ item.market }}</span>
        <span class="chip-symbol">{{ item.symbol }}</span>
        <span v-if="item.stock_name" class="chip-name">{{ item.stock_name }}</span>
        <span v-if="item.count >= 2" :class="['chip-count', item.count >= 5 ? 'chip-count--hi' : '']">
          {{ item.count }}{{ t('recent_count_suffix') }}
        </span>
      </button>
    </div>

    <!-- Expand / collapse toggle -->
    <div v-if="canExpand" class="recent-toggle">
      <button class="recent-toggle-btn" @click="expanded = !expanded">
        {{ expanded ? t('recent_collapse') : t('recent_expand', { count: items.length }) }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getRecentSearches, clearRecentSearches } from '../utils/recentSearches.js'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  defaultLimit:  { type: Number, default: 5 },
  expandedLimit: { type: Number, default: 10 },
})

const emit = defineEmits(['pick', 'clear'])

const items    = ref([])
const expanded = ref(false)

const visibleItems = computed(() =>
  items.value.slice(0, expanded.value ? props.expandedLimit : props.defaultLimit)
)

const canExpand = computed(() => items.value.length > props.defaultLimit)

function refresh() {
  items.value = getRecentSearches()
  // Reset expand state when list is refreshed (e.g. after clear)
  if (items.value.length <= props.defaultLimit) expanded.value = false
}

function onPick(item) {
  emit('pick', { market: item.market, symbol: item.symbol, stock_name: item.stock_name })
}

function onClear() {
  clearRecentSearches()
  expanded.value = false
  emit('clear')
}

function handleStorageEvent() {
  refresh()
}

onMounted(() => {
  refresh()
  window.addEventListener('recent-searches-updated', handleStorageEvent)
})

onUnmounted(() => {
  window.removeEventListener('recent-searches-updated', handleStorageEvent)
})
</script>

<style scoped>
.recent-searches {
  padding: 14px 16px;
}

.recent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.recent-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.recent-clear {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  transition: color 0.15s;
}

.recent-clear:hover {
  color: var(--danger);
}

.recent-empty {
  font-size: 12px;
  color: var(--muted);
  opacity: 0.7;
  margin: 0;
  padding: 4px 0;
}

.recent-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.recent-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  line-height: 1.4;
}

.recent-chip:hover {
  background: var(--status-info-bg);
  border-color: var(--accent);
  color: var(--accent);
}

.chip-market {
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  background: var(--status-info-bg);
  border-radius: 3px;
  padding: 1px 4px;
}

.recent-chip:hover .chip-market {
  background: var(--status-info-ring);
}

.chip-symbol {
  font-weight: 600;
  font-family: monospace;
  font-size: 12px;
}

.chip-name {
  color: var(--muted);
  font-size: 11px;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-count {
  font-size: 10px;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0 4px;
  line-height: 1.6;
  flex-shrink: 0;
}

.chip-count--hi {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

/* ── Expand toggle ── */
.recent-toggle {
  margin-top: 8px;
}

.recent-toggle-btn {
  background: none;
  border: none;
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
  padding: 2px 0;
  opacity: 0.8;
  transition: opacity 0.15s;
}

.recent-toggle-btn:hover {
  opacity: 1;
}
</style>
