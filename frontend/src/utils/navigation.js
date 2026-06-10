/**
 * Shared navigation helpers.
 * Pass the vue-router `router` instance from `useRouter()`.
 */

export function goAnalyze(router, market, symbol) {
  router.push({ path: '/', query: { market, symbol } })
}

export function goStockDetail(router, market, symbol) {
  router.push(`/stocks/${market}/${symbol}`)
}

export function goHistory(router, market, symbol) {
  router.push({ path: '/history', query: { market, symbol } })
}

export function goReportDetail(router, reportId) {
  router.push(`/history/${reportId}`)
}
