<template>
  <div :class="['fsb-root', `fsb-${type}`]">
    <span class="fsb-icon">{{ icons[type] || 'ℹ️' }}</span>
    <span class="fsb-msg">{{ message }}</span>
  </div>
</template>

<script setup>
defineProps({
  type: { type: String, default: 'warn' }, // 'warn' | 'error' | 'stale' | 'info'
  message: { type: String, required: true },
})
const icons = { warn: '⚠️', error: '❌', stale: '🕒', info: 'ℹ️' }
</script>

<style scoped>
.fsb-root {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 12px;
}
.fsb-warn  { background: #fff8e1; color: #856404; }
.fsb-error { background: #fdecea; color: #c0392b; }
.fsb-stale { background: var(--surface2, #f5f5f5); color: var(--muted); }
.fsb-info  { background: var(--status-info-bg, #e8f0fe); color: var(--accent); }
.fsb-icon { font-size: 14px; }
</style>
