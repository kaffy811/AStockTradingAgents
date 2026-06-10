<template>
  <div class="engine-selector card">
    <div class="engine-header">
      <span class="engine-title">开发者选项</span>
      <span class="engine-hint">分析引擎（仅开发模式可见）</span>
    </div>
    <div class="engine-grid">
      <button
        v-for="opt in OPTIONS"
        :key="opt.value"
        :class="['engine-chip', { 'engine-chip--active': modelValue === opt.value }]"
        :title="opt.desc"
        @click="emit('update:modelValue', opt.value)"
      >
        <span class="engine-label">{{ opt.label }}</span>
        <span class="engine-desc">{{ opt.desc }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, default: 'custom_coordinator' },
})

const emit = defineEmits(['update:modelValue'])

const OPTIONS = [
  {
    value: 'custom_coordinator',
    label: '默认 Coordinator',
    desc:  '当前稳定生产路径',
  },
  {
    value: 'langgraph',
    label: 'LangGraph 灰度',
    desc:  '实验性工作流编排路径，仅用于开发验证',
  },
]
</script>

<style scoped>
.engine-selector {
  padding: 10px 16px;
  border: 1.5px dashed var(--border);
  background: rgba(255, 200, 50, 0.04);
}

.engine-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}

.engine-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.engine-hint {
  font-size: 11px;
  color: var(--muted);
  opacity: 0.7;
}

.engine-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.engine-chip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  background: var(--surface2);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  padding: 7px 12px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  text-align: left;
  min-width: 120px;
}

.engine-chip:hover {
  border-color: var(--accent);
  background: var(--surface-hover);
}

.engine-chip--active {
  border-color: var(--accent);
  background: var(--status-info-bg);
}

.engine-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.3;
}

.engine-chip--active .engine-label {
  color: var(--accent);
}

.engine-desc {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.4;
}

/* ── Mobile: chips can wrap ── */
@media (max-width: 375px) {
  .engine-grid {
    flex-direction: column;
  }

  .engine-chip {
    width: 100%;
    min-width: unset;
  }
}
</style>
