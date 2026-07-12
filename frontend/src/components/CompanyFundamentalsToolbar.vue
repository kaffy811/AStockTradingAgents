<template>
  <div class="cft-root">
    <div class="cft-left">
      <!-- Period selector -->
      <div class="cft-group">
        <span class="cft-label">周期</span>
        <div class="cft-seg">
          <button
            v-for="opt in periodOpts"
            :key="opt.value"
            :class="['cft-seg-btn', modelPeriod === opt.value && 'active']"
            @click="$emit('update:period', opt.value)"
          >{{ opt.label }}</button>
        </div>
      </div>
      <!-- Limit selector -->
      <div class="cft-group">
        <span class="cft-label">期数</span>
        <select class="cft-select" :value="modelLimit" @change="$emit('update:limit', Number($event.target.value))">
          <option v-for="n in limitOpts" :key="n" :value="n">{{ n }} 期</option>
        </select>
      </div>
      <!-- Mode badge -->
      <div :class="['cft-mode-badge', isMock ? 'mock' : 'api']">
        {{ isMock ? 'Mock' : 'API' }}
      </div>
    </div>
    <div class="cft-right">
      <!-- Refresh all -->
      <button
        class="cft-btn"
        :class="refreshing && 'spinning'"
        :disabled="refreshing"
        @click="$emit('refresh-all')"
        title="刷新当前分组"
      >↻</button>
      <!-- Export CSV -->
      <button class="cft-btn" @click="$emit('export-csv')" title="导出当前分组 CSV">
        ↓ CSV
      </button>
      <!-- Export Excel dropdown -->
      <div class="cft-dropdown" ref="dropdownRef">
        <button
          class="cft-btn cft-btn-excel"
          :class="exporting && 'spinning'"
          :disabled="exporting"
          @click="toggleDropdown"
          title="导出 Excel"
        >{{ exporting ? '…' : '↓ Excel' }}</button>
        <div v-if="dropdownOpen" class="cft-dropdown-menu">
          <button class="cft-dropdown-item" @click="onExportSection">
            导出当前分组
          </button>
          <button class="cft-dropdown-item" @click="onExportAllLoaded">
            导出全部已加载
          </button>
          <div class="cft-dropdown-divider"></div>
          <button class="cft-dropdown-item cft-dropdown-item--warn" @click="onLoadAllThenExport">
            加载全部后导出
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  modelPeriod: { type: String,  default: 'annual' },
  modelLimit:  { type: Number,  default: 8 },
  isMock:      { type: Boolean, default: false },
  refreshing:  { type: Boolean, default: false },
  exporting:   { type: Boolean, default: false },
})

const emit = defineEmits(['update:period', 'update:limit', 'refresh-all', 'export-csv', 'export-section-xlsx', 'export-all-xlsx', 'load-all-export-xlsx'])

const periodOpts = [
  { label: '年报', value: 'annual' },
  { label: '季报', value: 'quarterly' },
]
const limitOpts = [5, 8, 10, 20]

const dropdownOpen = ref(false)
const dropdownRef = ref(null)

function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value
}

function onExportSection() {
  dropdownOpen.value = false
  emit('export-section-xlsx')
}

function onExportAllLoaded() {
  dropdownOpen.value = false
  emit('export-all-xlsx')
}

function onLoadAllThenExport() {
  dropdownOpen.value = false
  emit('load-all-export-xlsx')
}

// Close dropdown on outside click
function onClickOutside(e) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target)) {
    dropdownOpen.value = false
  }
}
onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))
</script>

<style scoped>
.cft-root {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
  background: white; border-radius: 10px;
  padding: 8px 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  font-size: 12px;
}
.cft-left  { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cft-right { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cft-group { display: flex; align-items: center; gap: 5px; }
.cft-label { color: var(--muted); font-size: 11px; white-space: nowrap; }

/* Segmented buttons */
.cft-seg { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.cft-seg-btn {
  background: none; border: none; padding: 4px 9px; font-size: 11px;
  color: var(--muted); cursor: pointer; border-right: 1px solid var(--border);
  transition: background 0.12s;
}
.cft-seg-btn:last-child { border-right: none; }
.cft-seg-btn.active { background: var(--accent, #4a86e8); color: white; font-weight: 600; }
.cft-seg-btn:hover:not(.active) { background: var(--surface2); }

/* Select */
.cft-select {
  border: 1px solid var(--border); border-radius: 6px;
  padding: 3px 7px; font-size: 11px; color: var(--text);
  background: white; cursor: pointer;
}

/* Mode badge */
.cft-mode-badge {
  font-size: 10px; font-weight: 600; padding: 2px 7px;
  border-radius: 20px; border: 1px solid;
}
.cft-mode-badge.mock { color: #856404; background: #fff8e1; border-color: #ffc107; }
.cft-mode-badge.api  { color: #155724; background: #d4edda; border-color: #28a745; }

/* Action buttons */
.cft-btn {
  background: none; border: 1px solid var(--border); border-radius: 6px;
  padding: 4px 9px; font-size: 11px; color: var(--muted);
  cursor: pointer; transition: background 0.12s;
  white-space: nowrap;
}
.cft-btn:hover:not(:disabled) { background: var(--surface2); color: var(--text); }
.cft-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.cft-btn.spinning { animation: spin 0.8s linear infinite; }
.cft-btn-excel { color: #155724; border-color: #28a745; }
.cft-btn-excel:hover:not(:disabled) { background: #d4edda; }

@keyframes spin { to { transform: rotate(360deg); } }

/* Dropdown */
.cft-dropdown { position: relative; }
.cft-dropdown-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 100;
  background: white; border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,.12);
  min-width: 160px; overflow: hidden;
}
.cft-dropdown-item {
  display: block; width: 100%; text-align: left;
  padding: 9px 14px; font-size: 12px; color: var(--text);
  background: none; border: none; cursor: pointer;
  transition: background 0.12s;
}
.cft-dropdown-item:hover { background: var(--surface2); }
.cft-dropdown-item--warn { color: #856404; }
.cft-dropdown-divider { height: 1px; background: var(--border); margin: 2px 0; }

@media (max-width: 540px) {
  .cft-root { padding: 8px 10px; }
  .cft-label { display: none; }
}
</style>
