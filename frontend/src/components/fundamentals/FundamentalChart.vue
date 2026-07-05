<template>
  <div class="fc-wrap">
    <div v-if="isEmpty" class="fc-empty">
      <span class="fc-empty-icon">📊</span>
      <span class="fc-empty-text">{{ emptyState || '暂无图表数据' }}</span>
    </div>
    <div v-else ref="chartEl" class="fc-canvas" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

// Dynamic import cache — avoids re-bundling echarts statically in this chunk
let _ecCache = null
async function getEcharts() {
  if (!_ecCache) _ecCache = await import('echarts')
  return _ecCache
}

const props = defineProps({
  chartType:  { type: String, default: 'line' },     // line|bar|stacked_bar|area|pie|donut|radar|none
  xAxis:      { type: Array,  default: () => [] },
  series:     { type: Array,  default: () => [] },    // [{name, type, data, stack?, connectNulls}]
  height:     { type: Number, default: 320 },
  emptyState: { type: String, default: '暂无图表数据' },
  // For radar chart
  radarIndicators: { type: Array, default: () => [] },
  // Colors: use project's up/down colors
  colors: { type: Array, default: () => ['#5470c6','#91cc75','#fac858','#ee6666','#73c0de','#3ba272'] },
})

const chartEl = ref(null)
let chartInstance = null

const isEmpty = computed(() => {
  if (props.chartType === 'none') return true
  if (!props.series.length) return true
  const allEmpty = props.series.every(s => {
    if (Array.isArray(s.data)) return s.data.every(v => v === null || v === undefined)
    return true
  })
  return allEmpty
})

function buildOption() {
  const type = props.chartType
  if (type === 'pie' || type === 'donut') {
    const pieSeries = props.series[0] || {}
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { orient: 'vertical', right: '5%', top: 'center', type: 'scroll', textStyle: { fontSize: 11 } },
      series: [{
        name: pieSeries.name,
        type: 'pie',
        radius: type === 'donut' ? ['40%', '65%'] : '65%',
        center: ['40%', '50%'],
        data: (pieSeries.data || []).filter(d => d.value != null && d.value > 0),
        label: { formatter: '{b}\n{d}%', fontSize: 11 },
        itemStyle: { borderRadius: 4 },
        emphasis: { label: { fontSize: 12, fontWeight: 600 } },
      }],
    }
  }
  if (type === 'radar') {
    return {
      tooltip: { trigger: 'item' },
      radar: {
        indicator: props.radarIndicators.length ? props.radarIndicators : props.xAxis.map(name => ({ name, max: 100 })),
        radius: '65%',
        axisName: { fontSize: 11 },
      },
      series: props.series.map(s => ({
        type: 'radar',
        data: s.data ? [{ value: s.data, name: s.name }] : [],
        areaStyle: { opacity: 0.2 },
      })),
    }
  }
  // Line/Bar/Stacked/Area
  const isBar = type === 'bar' || type === 'stacked_bar'
  const isArea = type === 'area'
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        const lines = [params[0].axisValue]
        params.forEach(p => {
          const val = p.data != null ? p.data : '—'
          lines.push(`${p.marker}${p.seriesName}: ${val}`)
        })
        return lines.join('<br/>')
      },
    },
    legend: {
      type: 'scroll',
      top: 4,
      textStyle: { fontSize: 11 },
      data: props.series.map(s => s.name),
    },
    grid: { left: 12, right: 12, top: 40, bottom: 50, containLabel: true },
    xAxis: {
      type: 'category',
      data: props.xAxis,
      axisLabel: { fontSize: 10, rotate: props.xAxis.length > 6 ? 30 : 0 },
      axisTick: { alignWithLabel: true },
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
    color: props.colors,
    series: props.series.map(s => ({
      name: s.name,
      type: isBar ? 'bar' : 'line',
      data: s.data,
      stack: s.stack,
      connectNulls: false,    // null values create gaps
      smooth: !isBar,
      areaStyle: isArea ? { opacity: 0.2 } : undefined,
      barMaxWidth: 40,
      label: { show: false },
      emphasis: { focus: 'series' },
    })),
    dataZoom: props.xAxis.length > 12 ? [{ type: 'slider', bottom: 0, height: 20 }] : [],
  }
}

async function initChart() {
  if (!chartEl.value || isEmpty.value) return
  const ec = await getEcharts()
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  chartInstance = ec.init(chartEl.value, null, { renderer: 'canvas' })
  chartInstance.setOption(buildOption(), true)
}

// ResizeObserver for automatic resize
let resizeObs = null

function setupResizeObserver() {
  if (!chartEl.value || typeof ResizeObserver === 'undefined') return
  resizeObs = new ResizeObserver(() => {
    if (chartInstance) chartInstance.resize()
  })
  resizeObs.observe(chartEl.value)
}

onMounted(async () => {
  await nextTick()
  if (!isEmpty.value) {
    initChart()
    setupResizeObserver()
  }
})

onUnmounted(() => {
  if (resizeObs) resizeObs.disconnect()
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
})

watch(() => [props.series, props.xAxis, props.chartType], async () => {
  await nextTick()
  if (isEmpty.value) {
    if (chartInstance) { chartInstance.dispose(); chartInstance = null }
    return
  }
  if (!chartInstance) {
    initChart()
    setupResizeObserver()
  } else {
    chartInstance.setOption(buildOption(), true)
  }
}, { deep: true })
</script>

<style scoped>
.fc-wrap { width: 100%; }
.fc-canvas { width: 100%; min-height: 200px; }
.fc-empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 40px 0;
  color: var(--muted); gap: 8px;
}
.fc-empty-icon { font-size: 28px; }
.fc-empty-text { font-size: 13px; }
</style>
