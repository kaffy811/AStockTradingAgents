<template>
  <div v-if="message" class="error-box" style="margin-bottom:20px">
    <strong>请求失败</strong>{{ message }}
  </div>
</template>

<script setup>
defineProps({
  message: { type: String, default: '' },
})
</script>
