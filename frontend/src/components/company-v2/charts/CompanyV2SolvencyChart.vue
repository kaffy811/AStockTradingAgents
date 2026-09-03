<template>
  <CompanyV2SolvencyRadarOrBars :rows="rows" />
</template>

<script setup>
import CompanyV2SolvencyRadarOrBars from './CompanyV2SolvencyRadarOrBars.vue'

defineProps({
  rows: { type: Array, default: () => [] },
})
</script>
