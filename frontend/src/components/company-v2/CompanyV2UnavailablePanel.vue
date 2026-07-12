<template>
  <div class="cv2-unavailable">
    <strong>暂无可展示字段</strong>
    <span>{{ reason || 'ALL_NULL_ROWS' }}</span>
  </div>
</template>

<script setup>
defineProps({
  reason: { type: String, default: '' },
})
</script>
