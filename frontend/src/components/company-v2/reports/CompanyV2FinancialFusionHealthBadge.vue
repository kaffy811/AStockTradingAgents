<template>
  <span :class="['cv2-fusion-pill', toneClass]">
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  health: { type: Object, default: null },
})

const toneClass = computed(() => {
  const status = props.health?.status || 'unknown'
  if (status === 'healthy') return 'ok'
  if (status === 'warning') return 'warn'
  if (status === 'critical') return 'fail'
  return 'idle'
})

const label = computed(() => {
  if (!props.health) return 'health: unknown'
  return `${props.health.status || 'unknown'} · p95 ${props.health.p95_latency_ms ?? '-'}ms`
})
</script>
