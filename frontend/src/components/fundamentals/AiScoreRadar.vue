<template>
  <div class="asr-wrap">
    <div v-if="!hasDimensions" class="asr-empty">暂无维度评分</div>
    <div v-else ref="chartEl" class="asr-canvas" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  dimensions: { type: Array, default: () => [] },  // [{name, score, level}]
  height:     { type: Number, default: 260 },
})

const chartEl = ref(null)
let chartInstance = null
let _ecCache = null

async function getEcharts() {
  if (!_ecCache) _ecCache = await import('echarts')
  return _ecCache
}

const hasDimensions = computed(() => props.dimensions.length > 0)

const levelColor = { strong: '#52c41a', neutral: '#1677ff', weak: '#ff4d4f' }

function buildOption() {
  const dims = props.dimensions
  const indicators = dims.map(d => ({ name: d.name, max: 100 }))
  const values = dims.map(d => d.score ?? 0)

  return {
    tooltip: { trigger: 'item' },
    radar: {
      indicator: indicators,
      radius: '62%',
      axisName: { fontSize: 11, color: 'var(--text, #333)' },
      splitNumber: 4,
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: '基本面评分',
        areaStyle: { opacity: 0.2, color: '#4a86e8' },
        lineStyle: { color: '#4a86e8', width: 2 },
        itemStyle: { color: '#4a86e8' },
        label: {
          show: true,
          formatter: p => p.value,
          fontSize: 10,
        },
      }],
    }],
  }
}

async function initChart() {
  if (!chartEl.value || !hasDimensions.value) return
  const ec = await getEcharts()
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
  chartInstance = ec.init(chartEl.value, null, { renderer: 'canvas' })
  chartInstance.setOption(buildOption(), true)
}

let ro = null
onMounted(async () => {
  await nextTick()
  if (hasDimensions.value) {
    await initChart()
    if (chartEl.value && typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => chartInstance?.resize())
      ro.observe(chartEl.value)
    }
  }
})
onUnmounted(() => {
  ro?.disconnect()
  chartInstance?.dispose()
  chartInstance = null
})
watch(() => props.dimensions, async () => {
  await nextTick()
  if (!hasDimensions.value) return
  if (!chartInstance) { await initChart() } else { chartInstance.setOption(buildOption(), true) }
}, { deep: true })
</script>

<style scoped>
.asr-wrap { width: 100%; }
.asr-canvas { width: 100%; }
.asr-empty { text-align: center; padding: 32px 0; color: var(--muted); font-size: 13px; }
</style>
