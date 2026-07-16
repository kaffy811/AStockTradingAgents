<template>
  <div class="cv2-unavailable">
    <strong>{{ title }}</strong>
    <span v-if="displayReason">{{ displayReason }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  reason: { type: String, default: '' },
})

const title = computed(() => ({
  OUTLIER_REQUIRES_REVIEW: '指标口径待确认',
  FIELD_CONFLICT: '指标口径待确认',
  NOT_APPLICABLE_FOR_INDUSTRY: '该行业不适用',
  PROVIDER_TIMEOUT: '数据源暂时不可用',
})[props.reason] || '当前暂无该类数据。')

const displayReason = computed(() => ({
  OUTLIER_REQUIRES_REVIEW: '该指标存在异常波动，暂不展示为正常趋势。',
  FIELD_CONFLICT: '不同来源的字段口径存在差异。',
  NOT_APPLICABLE_FOR_INDUSTRY: '该行业不适用这些通用企业指标。',
  PROVIDER_TIMEOUT: '请稍后重试。',
})[props.reason] || '')
</script>
