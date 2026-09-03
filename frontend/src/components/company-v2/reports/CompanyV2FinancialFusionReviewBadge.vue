<template>
  <span :class="['cv2-fusion-pill', toneClass]">
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  count: { type: Number, default: 0 },
})

const toneClass = computed(() => (props.count > 0 ? 'warn' : 'idle'))
const label = computed(() => (props.count > 0 ? `review ${props.count}` : 'review 0'))
</script>
