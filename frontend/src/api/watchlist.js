import { baseFetch } from './http.js'

/**
 * Fetch the current user's watchlist.
 * @returns {{ total: number, items: WatchlistItem[] }}
 */
export function listWatchlist() {
  return baseFetch('/watchlist/')
}

/**
 * Fetch the current user's watchlist enriched with latest_price, change_pct,
 * industry_code, industry_name, quote_status, and latest_report.
 * @returns {{ total: number, items: WatchlistEnrichedItem[] }}
 */
export function getWatchlistEnriched() {
  return baseFetch('/watchlist/enriched')
}

/**
 * Add a stock to the watchlist.
 * @param {{ market: string, symbol: string, name?: string, note?: string, sort_order?: number }} body
 * @returns {WatchlistItem}
 * @throws {Error} with status 409 if already exists
 */
export function addWatchlist(body) {
  return baseFetch('/watchlist/', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * Update name / note / sort_order of a watchlist item.
 * @param {string} id
 * @param {{ name?: string, note?: string, sort_order?: number }} body
 * @returns {WatchlistItem}
 */
export function patchWatchlist(id, body) {
  return baseFetch(`/watchlist/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/**
 * Delete a watchlist item. Returns null (204 No Content).
 * @param {string} id
 */
export function deleteWatchlist(id) {
  return baseFetch(`/watchlist/${id}`, { method: 'DELETE' })
}
