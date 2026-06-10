/**
 * compareStorage.js
 * Manages the local "stocks to compare" list via localStorage.
 * Key: tradingagents:compare_list:v1
 * Format: [{ market, symbol, stock_name, added_at }]
 */

const LS_KEY = 'tradingagents:compare_list:v1'
const MAX_COUNT = 4

/** Returns [{ market, symbol, stock_name, added_at }] — never throws */
export function getCompareList() {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      item =>
        item &&
        typeof item.market  === 'string' &&
        typeof item.symbol  === 'string' &&
        item.market.length > 0 &&
        item.symbol.length > 0
    )
  } catch {
    return []
  }
}

function _save(list) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(list))
  } catch {
    // quota exceeded or unavailable — silently skip
  }
}

/**
 * Add a stock to the compare list.
 * @param {{ market: string, symbol: string, stock_name?: string }} stock
 * @returns {{ ok: boolean, reason: 'added'|'duplicate'|'full', list: Array }}
 */
export function addCompareStock({ market, symbol, stock_name = '' }) {
  const list = getCompareList()
  const key = `${market}:${symbol}`

  if (list.some(i => `${i.market}:${i.symbol}` === key)) {
    return { ok: false, reason: 'duplicate', list }
  }
  if (list.length >= MAX_COUNT) {
    return { ok: false, reason: 'full', list }
  }

  const newList = [...list, { market, symbol, stock_name: stock_name || '', added_at: Date.now() }]
  _save(newList)
  dispatchCompareUpdated()
  return { ok: true, reason: 'added', list: newList }
}

/** Remove one stock by market + symbol */
export function removeCompareStock(market, symbol) {
  const list = getCompareList().filter(
    i => !(i.market === market && i.symbol === symbol)
  )
  _save(list)
  dispatchCompareUpdated()
  return list
}

/** Clear all */
export function clearCompareList() {
  _save([])
  dispatchCompareUpdated()
}

/**
 * Build the URL query param string.
 * @param {Array} list
 * @returns {string}  e.g. "CN:000001,CN:600519,HK:00700"
 */
export function buildCompareQuery(list) {
  return list.map(i => `${i.market}:${i.symbol}`).join(',')
}

/** Fire a cross-component event so other listeners can react */
export function dispatchCompareUpdated() {
  try {
    window.dispatchEvent(new CustomEvent('compare-list-updated'))
  } catch {
    // Non-browser env or blocked
  }
}
