/**
 * requestCache.js — In-flight dedup + short-term result cache for API requests.
 *
 * Key design:
 * - Concurrent requests to same key share one Promise (in-flight dedup)
 * - Completed results cached for `ttlMs` (default 5 min)
 * - force_refresh=true bypasses cache
 * - Errors never populate the result cache
 * - clearByPrefix(prefix) for stock-specific cache busting
 */

const _inFlight = new Map()   // key → Promise
const _cache    = new Map()   // key → {data, expiresAt}
const DEFAULT_TTL = 5 * 60 * 1000  // 5 minutes

export function buildKey(endpoint, params = {}) {
  const sorted = Object.entries(params).sort(([a],[b]) => a.localeCompare(b))
  return `${endpoint}?${sorted.map(([k,v]) => `${k}=${v}`).join('&')}`
}

export async function cachedRequest(key, fetcher, { ttlMs = DEFAULT_TTL, forceRefresh = false } = {}) {
  if (!forceRefresh) {
    const cached = _cache.get(key)
    if (cached && cached.expiresAt > Date.now()) return cached.data

    const inflight = _inFlight.get(key)
    if (inflight) return inflight
  }

  const promise = fetcher().then(data => {
    _inFlight.delete(key)
    _cache.set(key, { data, expiresAt: Date.now() + ttlMs })
    return data
  }).catch(err => {
    _inFlight.delete(key)
    throw err
  })

  _inFlight.set(key, promise)
  return promise
}

export function clearByPrefix(prefix) {
  for (const key of [..._cache.keys(), ..._inFlight.keys()]) {
    if (key.startsWith(prefix)) {
      _cache.delete(key)
      _inFlight.delete(key)
    }
  }
}

export function clearFundamentalsCache(stockCode) {
  clearByPrefix(`/api/v1/stock/${stockCode}/`)
}

export function clearAllCache() {
  _cache.clear()
  _inFlight.clear()
}
