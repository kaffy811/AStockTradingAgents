<template>
  <div v-if="warnings.length" class="warnings">
    <div class="warnings-title">数据质量提示</div>
    <ul>
      <li v-for="w in warnings" :key="w">{{ translateWarning(w) }}</li>
    </ul>
  </div>
</template>

<script setup>
import { translateWarning } from '../utils/warningMap.js'

defineProps({
  warnings: { type: Array, default: () => [] },
})
</script>

<style scoped>
.warnings {
  background: var(--status-warn-bg);
  border: 1px solid var(--status-warn-ring);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}

.warnings-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--warn);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.warnings ul {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.warnings li {
  font-size: 13px;
  color: var(--warn);
  padding-left: 14px;
  position: relative;
}

.warnings li::before {
  content: "⚠";
  position: absolute;
  left: 0;
  font-size: 11px;
}
</style>
