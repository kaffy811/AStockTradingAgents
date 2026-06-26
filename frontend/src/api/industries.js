import { baseFetch } from './http.js'

/**
 * Get the SW (申万) industry classification for a single stock.
 * Returns 404 if no mapping exists.
 */
export function getStockIndustry(market, symbol) {
  return baseFetch(`/industries/stocks/${market}/${symbol.trim()}`)
}

/**
 * Get the top-N hot stocks for a given SW level-1 industry code.
 * Returns items=[] if no snapshot exists (HTTP 200, not an error).
 */
export function getIndustryHotStocks(market, industryCode, options = {}) {
  const { limit = 20 } = options
  const params = new URLSearchParams({ limit: String(limit) })
  return baseFetch(`/industries/${market}/${industryCode}/hot-stocks?${params}`)
}

/**
 * Dynamic peer discovery for a stock.
 * Priority: PEER_MAP manual override > CN industry Hot Top-N.
 * Non-CN stocks without a PEER_MAP entry return peers=[], HTTP 200.
 *
 * Response shape:
 *   { market, symbol, industry, peers, data_quality }
 *   data_quality.peer_source: "dynamic_hot" | "manual_map" | "none"
 */
export function getDynamicPeers(market, symbol, options = {}) {
  const { limit = 5 } = options
  const params = new URLSearchParams({ limit: String(limit) })
  return baseFetch(`/industries/stocks/${market}/${symbol.trim()}/dynamic-peers?${params}`)
}

/**
 * List all SW level-1 industries for a market.
 * Returns list of { market, industry_code, industry_name, industry_level, source }
 */
export function listIndustries(market = 'CN') {
  const params = new URLSearchParams({ market })
  return baseFetch(`/industries/?${params}`)
}
