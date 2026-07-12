<template>
  <div class="cv2-table-wrap">
    <table class="cv2-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in safeRows" :key="index">
          <td v-for="column in columns" :key="column" :title="cellTitle(row, column)">
            {{ displayCell(row, column) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
})

const safeRows = computed(() => props.rows.filter(row => row && typeof row === 'object'))

function displayCell(row, column) {
  const displayValue = row?.display_fields?.[column]?.display_value
  if (displayValue !== undefined && displayValue !== null && displayValue !== '') return String(displayValue)
  return display(row?.[column])
}

function cellTitle(row, column) {
  const meta = row?.display_fields?.[column] || {}
  return [
    `raw_value: ${display(meta.raw_value ?? row?.[column])}`,
    `display_type: ${meta.display_type || '—'}`,
  ].join('\n')
}

function display(value) {
  if (value === null || value === undefined || value === '' || value === '—' || Number.isNaN(value)) return '—'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4)
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<style scoped>
.cv2-table-wrap {
  width: 100%;
  overflow-x: auto;
  margin-top: 14px;
}
.cv2-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.cv2-table th,
.cv2-table td {
  border-bottom: 1px solid #e5e7eb;
  padding: 8px;
  text-align: left;
}
</style>
