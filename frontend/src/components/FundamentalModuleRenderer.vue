<template>
  <div class="fmr-root">
    <!-- Metric cards (if any) -->
    <FundamentalMetricGrid v-if="vm.metrics.length > 0" :metrics="vm.metrics" />

    <!-- Main chart (if series data exists and chart_type != none) -->
    <FundamentalChart
      v-if="showChart"
      :chart-type="chartType"
      :x-axis="vm.xAxis"
      :series="vm.series"
      :height="320"
      :empty-state="moduleMeta?.empty_state || '暂无图表数据'"
      :radar-indicators="vm.radarIndicators || []"
    />

    <!-- Data table -->
    <FundamentalTable
      v-if="vm.rows.length > 0"
      :rows="vm.rows"
      :columns="visibleColumns"
      :field-labels="effectiveLabels"
      :unit-hints="unitHints"
    />

    <!-- Insight / comment bar -->
    <FundamentalInsightBar v-if="vm.insight" :text="vm.insight" />

    <!-- Fallback for no data -->
    <div v-if="vm.metrics.length === 0 && vm.rows.length === 0 && !showChart" class="fmr-empty">
      {{ moduleMeta?.empty_state || '暂无数据' }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { adaptModuleData } from '../utils/fundamentalAdapters.js'
import FundamentalChart      from './fundamentals/FundamentalChart.vue'
import FundamentalTable      from './fundamentals/FundamentalTable.vue'
import FundamentalMetricGrid from './fundamentals/FundamentalMetricGrid.vue'
import FundamentalInsightBar from './fundamentals/FundamentalInsightBar.vue'

const props = defineProps({
  moduleMeta: { type: Object, default: null },
  data:       { type: Object, default: null },
})

// Use meta from envelope (set by build_api_response) or module-level fields
const renderType = computed(() => props.moduleMeta?.meta?.render_type || props.moduleMeta?.render_type || 'table')
const chartType  = computed(() => props.moduleMeta?.meta?.chart_type  || props.moduleMeta?.chart_type  || 'none')
const fieldLabels = computed(() => ({ ...(props.moduleMeta?.meta?.field_labels || props.moduleMeta?.field_labels || {}) }))
const unitHints  = computed(() => ({ ...(props.moduleMeta?.meta?.unit_hints  || props.moduleMeta?.unit_hints  || {}) }))

// Merge auto date labels
const effectiveLabels = computed(() => ({
  end_date: '报告期', trade_date: '交易日', ann_date: '披露日',
  ex_date: '除权日', pay_date: '派息日',
  ...fieldLabels.value,
}))

// Run adapter
const vm = computed(() => adaptModuleData(props.moduleMeta?.key || '', props.data, {
  ...props.moduleMeta,
  field_labels: effectiveLabels.value,
  unit_hints: unitHints.value,
}))

const showChart = computed(() => {
  if (chartType.value === 'none') return false
  if (!vm.value.series.length) return false
  return true
})

// Columns: use adapter's columns, limit long-text fields
const EXCLUDE_COLS = new Set(['source','ts_code','symbol','curr_type','data_note','sentiment','change_reason'])
const visibleColumns = computed(() => {
  const cols = vm.value.columns || []
  return cols.filter(c => !EXCLUDE_COLS.has(c))
})
</script>

<style scoped>
.fmr-root { display: flex; flex-direction: column; gap: 14px; }
.fmr-empty { text-align: center; color: var(--muted); font-size: 13px; padding: 20px 0; }
</style>
