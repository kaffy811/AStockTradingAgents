<template>
  <div class="fmt-root">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      :class="[
        'fmt-tab',
        { 'fmt-tab--active': tab.key === modelValue },
        { 'fmt-tab--disabled': tab.disabled },
      ]"
      :title="tab.disabled ? (tab.tooltip || '暂不可用') : tab.label"
      :disabled="tab.disabled"
      @click="!tab.disabled && emit('update:modelValue', tab.key)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  tabs:       { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])
</script>

<style scoped>
.fmt-root {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.fmt-tab {
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid #e0e0e0;
  background: #f5f5f5;
  color: var(--color-text-secondary, #555);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  white-space: nowrap;
}

.fmt-tab:hover:not(.fmt-tab--disabled) {
  background: #e8f0fe;
  border-color: #1a73e8;
  color: #1a73e8;
}

.fmt-tab--active {
  background: #1a73e8;
  border-color: #1a73e8;
  color: #fff;
  font-weight: 600;
}

.fmt-tab--active:hover {
  background: #1557c0;
  border-color: #1557c0;
  color: #fff;
}

.fmt-tab--disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
