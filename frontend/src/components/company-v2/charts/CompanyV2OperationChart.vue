<template>
  <CompanyV2OperationBarChart :rows="rows" />
</template>

<script setup>
import CompanyV2OperationBarChart from './CompanyV2OperationBarChart.vue'

defineProps({
  rows: { type: Array, default: () => [] },
})
</script>
