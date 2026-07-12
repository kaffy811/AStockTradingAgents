<template>
  <div class="empty-reason">
    <div class="empty-reason__icon">{{ icon }}</div>
    <div class="empty-reason__text">{{ displayText }}</div>
    <button v-if="props.onRetry" class="empty-reason__retry" @click="props.onRetry">重试</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  reasons:  { type: Array, default: () => [] },
  errors:   { type: Array, default: () => [] },
  type:     { type: String, default: 'no_data' }, // no_token|no_data|etl_missing|planned|api_error|partial
  onRetry:  { type: Function, default: null },
})

const icon = computed(() => ({
  no_token:    '🔑',
  no_data:     '📭',
  etl_missing: 'ℹ️',
  planned:     '🚧',
  api_error:   '⚠️',
  partial:     '⚠️',
}[props.type] || '📭'))

const displayText = computed(() => {
  const raw = props.reasons[0] || props.errors[0] || '暂无数据'
  return String(raw)
    .replace(/Traceback[\s\S]*/g, '')
    .replace(/File "[^"]*"[^\n]*/g, '')
    .trim()
    .slice(0, 200)
})
</script>

<style scoped>
.empty-reason {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  color: #888;
}

.empty-reason__icon {
  font-size: 28px;
}

.empty-reason__text {
  font-size: 13px;
  text-align: center;
  max-width: 300px;
  line-height: 1.5;
}

.empty-reason__retry {
  background: #3b82f6;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}

.empty-reason__retry:hover {
  background: #2563eb;
}
</style>
