/**
 * Recent searches — localStorage persistence utility.
 *
 * Key:    tradingagents:recent_searches:v1
 * Format: Array<{ market: string, symbol: string, stock_name: string, ts: number }>
 *         newest-first, max 20 items, dedup by market+symbol.
 */

const STORAGE_KEY = 'tradingagents:recent_searches:v1'
const MAX_ITEMS   = 20
const EVENT_NAME  = 'recent-searches-updated'

function _dispatch() {
  window.dispatchEvent(new CustomEvent(EVENT_NAME))
}

/**
 * Read all recent searches from localStorage.
 * @returns {Array<{market: string, symbol: string, stock_name: string, ts: number}>}
 */
export function getRecentSearches() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * Add (or promote) a search entry. Deduplicates by market+symbol.
 * Increments `count` on each call; backwards-compatible with entries that lack `count`.
 * @param {{ market: string, symbol: string, stock_name?: string }} entry
 */
export function addRecentSearch({ market, symbol, stock_name = '' }) {
  if (!market || !symbol) return
  const existing = getRecentSearches()
  const prev  = existing.find(i => i.market === market && i.symbol === symbol)
  const count = (Number(prev?.count) || 0) + 1
  const filtered = existing.filter(i => !(i.market === market && i.symbol === symbol))
  const updated = [
    {
      market,
      symbol,
      stock_name: stock_name || prev?.stock_name || '',
      ts: Date.now(),
      count,
    },
    ...filtered,
  ].slice(0, MAX_ITEMS)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
    _dispatch()
  } catch {
    // localStorage full or unavailable — silently skip
  }
}

/**
 * Return top `limit` searches sorted by count DESC, then ts DESC.
 * Backwards-compatible: entries without `count` are treated as count=1.
 * @param {number} limit
 * @returns {Array<{market: string, symbol: string, stock_name: string, ts: number, count: number}>}
 */
export function getTopSearches(limit = 5) {
  return [...getRecentSearches()]
    .map(i => ({ ...i, count: Number(i.count) || 1, ts: Number(i.ts) || 0 }))
    .sort((a, b) => b.count - a.count || b.ts - a.ts)
    .slice(0, limit)
}

/**
 * Clear all recent searches.
 */
export function clearRecentSearches() {
  try {
    localStorage.removeItem(STORAGE_KEY)
    _dispatch()
  } catch {
    // ignore
  }
}
