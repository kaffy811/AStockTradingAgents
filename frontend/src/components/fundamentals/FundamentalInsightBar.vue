<template>
  <div v-if="text" class="fib-root">
    <span class="fib-icon">💡</span>
    <span class="fib-text">{{ text }}</span>
  </div>
</template>
<script setup>
defineProps({ text: { type: String, default: '' } })
</script>
<style scoped>
.fib-root { display: flex; align-items: flex-start; gap: 8px; background: var(--status-info-bg, #e8f0fe); border-radius: 8px; padding: 10px 14px; font-size: 12px; color: var(--text); line-height: 1.6; }
.fib-icon { flex-shrink: 0; }
</style>
