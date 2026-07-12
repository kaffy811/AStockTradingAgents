<template>
  <div class="ump-root">
    <button class="ump-toggle" @click="expanded = !expanded">
      <span class="ump-icon">ℹ</span>
      <span class="ump-title">以下 {{ sectionIds.length }} 个模块暂无可展示数据</span>
      <span class="ump-chevron" :class="{ 'ump-chevron--open': expanded }">▾</span>
    </button>

    <div v-if="expanded" class="ump-body">
      <div class="ump-tags">
        <span
          v-for="id in sectionIds"
          :key="id"
          class="ump-tag"
          :title="getReasonHint(id)"
        >{{ sectionLabels[id] || id }}</span>
      </div>
      <p class="ump-hint">
        {{ defaultHintText }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  sectionIds:    { type: Array,  default: () => [] },
  sectionLabels: { type: Object, default: () => ({}) },
  /** Optional per-section reason map (id → reason_code string) */
  sectionReasons:{ type: Object, default: () => ({}) },
})

const expanded = ref(false)

// Phase 6N-8B: reason-aware hint per section
const REASON_HINTS = {
  FREE_MODE_UNAVAILABLE:    '该模块在 Free Mode 下不可用（需 Tushare Pro）',
  PROVIDER_EMPTY:           '免费数据源暂未返回数据',
  ALL_NULL_ROWS:            '返回记录但核心字段均为空，且低成本来源暂无法补齐',
  SHARE_CAPITAL_MISSING:    '免费源未返回股本，无法计算总市值',
  QUOTE_PROVIDER_UNAVAILABLE: '行情数据源网络不可用',
}

function getReasonHint(id) {
  const code = props.sectionReasons[id]
  return code ? (REASON_HINTS[code] || code) : ''
}

const defaultHintText = computed(() => {
  // If any module has ALL_NULL_ROWS reason, show a clear message
  const hasAllNull = Object.values(props.sectionReasons).some(r => r === 'ALL_NULL_ROWS')
  if (hasAllNull) {
    return '部分模块返回了记录，但核心字段均为空值，已自动隐藏以避免展示无意义的"—"表格。' +
      '免费模式下，BaoStock 覆盖盈利/成长/偿债/杜邦等季频数据；估值分位、主营构成、分红历史依赖 Tushare Pro 接口。'
  }
  return '免费模式（Free Mode）下，BaoStock 覆盖盈利/成长/偿债/杜邦等季频数据；' +
    '估值分位、主营构成、分红历史依赖 Tushare Pro 接口，免费模式下暂不可用。' +
    '接入 Tushare Pro Token（TUSHARE_TOKEN）可解锁全部模块。'
})
</script>

<style scoped>
.ump-root {
  border: 1px dashed var(--border, #dde3ef);
  border-radius: 8px;
  overflow: hidden;
}

.ump-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  background: var(--surface2, #f8f9fa);
  border: none;
  cursor: pointer;
  text-align: left;
  color: var(--color-text-secondary, #888);
  font-size: 12px;
}

.ump-toggle:hover {
  background: var(--surface3, #f0f3fa);
}

.ump-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.ump-title {
  flex: 1;
  font-weight: 600;
}

.ump-chevron {
  font-size: 14px;
  transition: transform 0.2s;
  flex-shrink: 0;
}

.ump-chevron--open {
  transform: rotate(180deg);
}

.ump-body {
  padding: 10px 14px 12px;
  background: var(--surface2, #f8f9fa);
  border-top: 1px dashed var(--border, #dde3ef);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ump-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ump-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--border, #e8edf5);
  color: var(--muted, #999);
}

.ump-hint {
  font-size: 11px;
  color: var(--muted, #aaa);
  line-height: 1.5;
  margin: 0;
}

.ump-hint code {
  font-family: monospace;
  background: var(--border, #e8edf5);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 10px;
}
</style>
