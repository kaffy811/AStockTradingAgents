<template>
  <div class="fpf-root">
    <!-- 报告期 -->
    <div class="fpf-group">
      <span class="fpf-label">报告期</span>
      <div class="fpf-btns">
        <button
          v-for="opt in periodOpts"
          :key="opt.value"
          :class="['fpf-btn', { 'fpf-btn--active': period === opt.value }]"
          @click="emit('update:period', opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
    </div>
    <!-- 年份 -->
    <div class="fpf-group">
      <span class="fpf-label">年份</span>
      <div class="fpf-btns">
        <button
          v-for="opt in limitOpts"
          :key="opt.value"
          :class="['fpf-btn', { 'fpf-btn--active': limit === opt.value }]"
          @click="emit('update:limit', opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  period: { type: String, default: 'annual' },
  limit:  { type: Number, default: 8 },
})

const emit = defineEmits(['update:period', 'update:limit'])

const periodOpts = [
  { value: 'annual',    label: '年报' },
  { value: 'quarterly', label: '中报' },
  { value: 'all',       label: '全部' },
]

const limitOpts = [
  { value: 3,  label: '近3年' },
  { value: 5,  label: '近5年' },
  { value: 10, label: '近10年' },
]
</script>

<style scoped>
.fpf-root {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.fpf-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.fpf-label {
  font-size: 12px;
  color: var(--color-text-secondary, #888);
  flex-shrink: 0;
}

.fpf-btns {
  display: flex;
  gap: 4px;
}

.fpf-btn {
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
  background: #f5f5f5;
  color: var(--color-text-secondary, #555);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.fpf-btn:hover {
  background: #e8f0fe;
  border-color: #1a73e8;
  color: #1a73e8;
}

.fpf-btn--active {
  background: #1a73e8;
  border-color: #1a73e8;
  color: #fff;
  font-weight: 600;
}
</style>
