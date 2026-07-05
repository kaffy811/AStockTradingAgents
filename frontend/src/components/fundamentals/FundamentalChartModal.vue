<template>
  <Teleport to="body">
    <div v-if="visible" class="fcm-overlay" @click.self="close">
      <div class="fcm-dialog">
        <!-- Header -->
        <div class="fcm-header">
          <span class="fcm-title">{{ title }}</span>
          <button class="fcm-close" @click="close">✕</button>
        </div>
        <!-- Chart -->
        <div ref="chartEl" class="fcm-canvas"></div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue'

const props = defineProps({
  visible:         { type: Boolean, default: false },
  title:           { type: String,  default: '' },
  chartType:       { type: String,  default: 'line' },
  xAxis:           { type: Array,   default: () => [] },
  series:          { type: Array,   default: () => [] },
  radarIndicators: { type: Array,   default: () => [] },
})
const emit = defineEmits(['close'])

const chartEl = ref(null)
let chartInstance = null

function close() { emit('close') }

function buildOption() {
  const type = props.chartType
  if (type === 'pie' || type === 'donut') {
    const s = props.series[0] || {}
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { orient: 'vertical', right: '5%', top: 'center', type: 'scroll' },
      series: [{
        name: s.name, type: 'pie',
        radius: type === 'donut' ? ['40%', '65%'] : '65%',
        center: ['40%', '50%'],
        data: (s.data || []).filter(d => d.value != null && d.value > 0),
        label: { formatter: '{b}\n{d}%', fontSize: 12 },
      }],
    }
  }
  if (type === 'radar') {
    return {
      tooltip: {},
      radar: {
        indicator: props.radarIndicators.length
          ? props.radarIndicators
          : props.xAxis.map(n => ({ name: n, max: 100 })),
        radius: '65%',
      },
      series: props.series.map(s => ({
        type: 'radar',
        data: [{ value: s.data, name: s.name }],
        areaStyle: { opacity: 0.2 },
      })),
    }
  }
  const isBar = type === 'bar' || type === 'stacked_bar'
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { type: 'scroll', top: 4, data: props.series.map(s => s.name) },
    grid: { left: 12, right: 12, top: 50, bottom: 60, containLabel: true },
    xAxis: {
      type: 'category',
      data: props.xAxis,
      axisLabel: { fontSize: 11, rotate: props.xAxis.length > 8 ? 30 : 0 },
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 11 } },
    series: props.series.map(s => ({
      name: s.name, type: isBar ? 'bar' : 'line',
      data: s.data, stack: s.stack,
      connectNulls: false, smooth: !isBar, barMaxWidth: 50,
    })),
    dataZoom: props.xAxis.length > 12 ? [{ type: 'slider', bottom: 0, height: 22 }] : [],
  }
}

async function initChart() {
  if (!chartEl.value) return
  const ec = await import('echarts')
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
  chartInstance = ec.init(chartEl.value, null, { renderer: 'canvas' })
  chartInstance.setOption(buildOption(), true)
}

watch(() => props.visible, async (val) => {
  if (val) {
    await nextTick()
    await initChart()
  } else {
    if (chartInstance) { chartInstance.dispose(); chartInstance = null }
  }
})

onUnmounted(() => {
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
})
</script>

<style scoped>
.fcm-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center;
  padding: 16px;
}
.fcm-dialog {
  background: white; border-radius: 16px;
  width: min(860px, 100%); max-height: 90vh;
  display: flex; flex-direction: column;
  overflow: hidden; box-shadow: 0 8px 40px rgba(0,0,0,.25);
}
.fcm-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-bottom: 1px solid var(--border);
}
.fcm-title { font-size: 14px; font-weight: 600; color: var(--text); }
.fcm-close {
  background: none; border: none; font-size: 18px; color: var(--muted);
  cursor: pointer; line-height: 1; padding: 4px 8px; border-radius: 6px;
}
.fcm-close:hover { background: var(--surface2); }
.fcm-canvas { flex: 1; min-height: 480px; padding: 8px; }
</style>
