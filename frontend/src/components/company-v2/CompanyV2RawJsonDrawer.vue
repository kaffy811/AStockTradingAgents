<template>
  <div class="cv2-json">
    <button class="cv2-json-toggle" @click="open = !open">{{ open ? '收起 JSON' : '查看 JSON' }}</button>
    <button class="cv2-json-toggle" @click="copyJson">{{ label }}</button>
    <pre v-if="open">{{ pretty }}</pre>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  data: { type: [Object, Array], default: () => ({}) },
  label: { type: String, default: '复制 JSON' },
})

const open = ref(false)
const pretty = computed(() => JSON.stringify(props.data, null, 2))

async function copyJson() {
  await navigator.clipboard?.writeText(pretty.value)
}
</script>
