import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Ephemeral store for passing a report result to PrintReportView.
 * Not persisted — intentionally cleared after printing or on page unload.
 */
export const usePrintStore = defineStore('print', () => {
  const result = ref(null)

  function setResult(reportResult) {
    result.value = reportResult
  }

  function clear() {
    result.value = null
  }

  return { result, setResult, clear }
})
