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
        {{ isMock ? 'Mock 数据' : 'API 数据' }}
      </div>
    </div>
    <div class="cft-right">
      <!-- Refresh all -->
      <button class="cft-btn" :class="refreshing && 'spinning'" @click="$emit('refresh-all')" title="刷新全部已加载模块">
        ↻
      </button>
      <!-- Export CSV -->
      <button class="cft-btn" @click="$emit('export-csv')" title="导出当前分组 CSV">
        ↓ CSV
      </button>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  modelPeriod: { type: String,  default: 'annual' },
  modelLimit:  { type: Number,  default: 8 },
  isMock:      { type: Boolean, default: false },
  refreshing:  { type: Boolean, default: false },
})
defineEmits(['update:period', 'update:limit', 'refresh-all', 'export-csv'])

const periodOpts = [
  { label: '年报', value: 'annual' },
  { label: '季报', value: 'quarterly' },
]
const limitOpts = [5, 8, 10, 20]
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
.cft-left  { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.cft-right { display: flex; align-items: center; gap: 8px; }
.cft-group { display: flex; align-items: center; gap: 6px; }
.cft-label { color: var(--muted); font-size: 11px; white-space: nowrap; }

/* Segmented buttons */
.cft-seg { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.cft-seg-btn {
  background: none; border: none; padding: 4px 10px; font-size: 11px;
  color: var(--muted); cursor: pointer; border-right: 1px solid var(--border);
  transition: background 0.12s;
}
.cft-seg-btn:last-child { border-right: none; }
.cft-seg-btn.active { background: var(--accent, #4a86e8); color: white; font-weight: 600; }
.cft-seg-btn:hover:not(.active) { background: var(--surface2); }

/* Select */
.cft-select {
  border: 1px solid var(--border); border-radius: 6px;
  padding: 3px 8px; font-size: 11px; color: var(--text);
  background: white; cursor: pointer;
}

/* Mode badge */
.cft-mode-badge {
  font-size: 10px; font-weight: 600; padding: 2px 8px;
  border-radius: 20px; border: 1px solid;
}
.cft-mode-badge.mock { color: #856404; background: #fff8e1; border-color: #ffc107; }
.cft-mode-badge.api  { color: #155724; background: #d4edda; border-color: #28a745; }

/* Action buttons */
.cft-btn {
  background: none; border: 1px solid var(--border); border-radius: 6px;
  padding: 4px 10px; font-size: 11px; color: var(--muted);
  cursor: pointer; transition: background 0.12s;
}
.cft-btn:hover { background: var(--surface2); color: var(--text); }
.cft-btn.spinning { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
