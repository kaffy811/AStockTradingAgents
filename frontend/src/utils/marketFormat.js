/**
 * Shared market-data formatting utilities.
 * Used by WatchlistView, IndustryHotView, StockDetailView, etc.
 */

export function formatAmount(val) {
  if (val == null) return '—'
  if (val >= 1e8) return (val / 1e8).toFixed(2) + '亿'
  if (val >= 1e4) return (val / 1e4).toFixed(1) + '万'
  return Number(val).toFixed(0)
}

export function formatPrice(val) {
  if (val == null || !Number.isFinite(Number(val))) return '—'
  return Number(val).toFixed(2)
}

export function formatChangePct(val) {
  if (val == null || !Number.isFinite(Number(val))) return '—'
  const n = Number(val)
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%'
}

export function changePctClass(val) {
  if (val == null || !Number.isFinite(Number(val))) return ''
  const n = Number(val)
  if (n > 0) return 'up'
  if (n < 0) return 'down'
  return ''
}

export function formatMarketSymbol(market, symbol) {
  return `${market}:${symbol}`
}

const SCOPE_LABELS = {
  comprehensive:    '综合分析',
  technical_only:   '技术面',
  fundamental_only: '基本面',
  tech_fundamental: '技 + 基本',
  news_only:        '新闻',
  peer_only:        '同行对比',
}

export function formatScopeLabel(scope) {
  return SCOPE_LABELS[scope] || scope || '—'
}

/**
 * Format a trade volume number (shares / lots).
 * Same scale breakpoints as formatAmount but without currency implication.
 */
export function formatVolume(val) {
  if (val == null) return '—'
  if (val >= 1e8) return (val / 1e8).toFixed(2) + '亿'
  if (val >= 1e4) return (val / 1e4).toFixed(1) + '万'
  return Number(val).toLocaleString()
}
