import { ref, onUnmounted, nextTick } from 'vue'

/**
 * useChartResize — handles ECharts instance lifecycle and resize.
 *
 * Usage:
 *   const { chartRef, initChart, disposeChart } = useChartResize()
 *   // In an async function:
 *   const ec = await import('echarts')
 *   const inst = initChart(ec)
 *   inst.setOption(option)
 */
export function useChartResize() {
  const chartRef = ref(null)
  let _instance = null
  let _ro = null

  function initChart(echarts) {
    if (!chartRef.value) return null
    if (_instance) return _instance
    _instance = echarts.init(chartRef.value, null, { renderer: 'canvas' })
    _ro = new ResizeObserver(() => {
      if (_instance && chartRef.value?.offsetWidth > 0) {
        _instance.resize()
      }
    })
    _ro.observe(chartRef.value)
    return _instance
  }

  function disposeChart() {
    _ro?.disconnect()
    _ro = null
    _instance?.dispose()
    _instance = null
  }

  function resizeChart() {
    nextTick(() => {
      if (_instance && chartRef.value?.offsetWidth > 0) {
        _instance.resize()
      }
    })
  }

  onUnmounted(disposeChart)

  return { chartRef, initChart, disposeChart, resizeChart }
}
