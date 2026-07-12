<template>
  <section :id="id" class="cfs-root">
    <!-- Header -->
    <div class="cfs-header">
      <h2 class="cfs-title">{{ title }}</h2>
      <div v-if="tooltip" class="cfs-tooltip-wrap">
        <span class="cfs-tooltip-icon" @mouseenter="tipVisible = true" @mouseleave="tipVisible = false">?</span>
        <div v-if="tipVisible" class="cfs-tooltip-popup">{{ tooltip }}</div>
      </div>
      <span v-if="partial && !isEmpty" class="cfs-partial-badge">数据不完整</span>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="cfs-skeleton">
      <div class="cfs-skel-line"></div>
      <div class="cfs-skel-line cfs-skel-line--medium"></div>
      <div class="cfs-skel-line cfs-skel-line--short"></div>
    </div>

    <!-- Empty / error state -->
    <div v-else-if="isEmpty" class="cfs-empty">
      <span class="cfs-empty-icon">📭</span>
      <p class="cfs-empty-text">{{ emptyReason || (errors && errors.length ? errors[0] : '暂无数据') }}</p>
    </div>

    <!-- Content slot -->
    <div v-else class="cfs-body">
      <slot />
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  id:          { type: String, default: '' },
  title:       { type: String, default: '' },
  tooltip:     { type: String, default: '' },
  loading:     { type: Boolean, default: false },
  partial:     { type: Boolean, default: false },
  errors:      { type: Array, default: () => [] },
  isEmpty:     { type: Boolean, default: false },
  emptyReason: { type: String, default: '' },
})

const tipVisible = ref(false)
</script>

<style scoped>
.cfs-root {
  background: #fff;
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  scroll-margin-top: 16px;
}

.cfs-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.cfs-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-primary, #1a2540);
  margin: 0;
  flex: 1;
}

.cfs-tooltip-wrap {
  position: relative;
  flex-shrink: 0;
}

.cfs-tooltip-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #e5e7eb;
  color: #6b7280;
  font-size: 11px;
  font-weight: 700;
  cursor: help;
  user-select: none;
}

.cfs-tooltip-popup {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  top: 26px;
  background: #1a2540;
  color: #fff;
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 6px;
  white-space: nowrap;
  z-index: 100;
  max-width: 240px;
  white-space: normal;
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}

.cfs-partial-badge {
  font-size: 11px;
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #f59e0b;
  border-radius: 4px;
  padding: 2px 7px;
  flex-shrink: 0;
}

/* Loading skeleton */
.cfs-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cfs-skel-line {
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(90deg, #e8eef8 25%, #d4ddf5 50%, #e8eef8 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
  width: 100%;
}

.cfs-skel-line--medium { width: 70%; }
.cfs-skel-line--short  { width: 45%; }

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Empty state */
.cfs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 0;
  text-align: center;
}

.cfs-empty-icon {
  font-size: 28px;
}

.cfs-empty-text {
  font-size: 13px;
  color: var(--color-text-secondary, #888);
  margin: 0;
  line-height: 1.5;
  max-width: 320px;
}

/* Body */
.cfs-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 640px) {
  .cfs-root { padding: 14px; }
}
</style>
