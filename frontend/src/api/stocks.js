import { baseFetch } from './http.js'

/**
 * 获取股票最新行情快照（价格、涨跌幅）。
 *
 * @param {string} market - 'CN' | 'HK'
 * @param {string} symbol - 股票代码
 * @returns {Promise<QuoteResponse>}
 */
export function getStockQuote(market, symbol) {
  return baseFetch(`/stocks/${market}/${symbol.trim()}/quote`)
}

/**
 * 获取股票相关新闻。
 *
 * @param {string} market    - 'CN' | 'HK'
 * @param {string} symbol    - 股票代码
 * @param {object} [options]
 * @param {number} [options.hours_back=72] - 时间窗口（小时）
 * @param {number} [options.limit=20]      - 最多返回条数
 * @returns {Promise<NewsResponse>}
 */
export function getStockNews(market, symbol, options = {}) {
  const { hours_back = 72, limit = 20 } = options
  const params = new URLSearchParams({ hours_back: String(hours_back), limit: String(limit) })
  return baseFetch(`/stocks/${market}/${symbol.trim()}/news?${params}`)
}

/**
 * 股票搜索 / 代码联想。
 * CN 支持 symbol 前缀 + name 关键词；HK 返回 items=[]。
 *
 * @param {string} market  - 'CN' | 'HK'
 * @param {string} q       - 搜索词（原样传入，不 trim，后端处理）
 * @param {number} [limit=10] - 1–20
 * @returns {Promise<StockSearchResponse>}
 */
export function searchStocks(market, q, limit = 10) {
  const params = new URLSearchParams({ market, q, limit: String(limit) })
  return baseFetch(`/stocks/search?${params}`)
}

/**
 * 获取 K 线 OHLCV 数据。
 *
 * @param {string} market   - 'CN' | 'HK'（原样传入，不转换）
 * @param {string} symbol   - 股票代码（保留前导零，只做 trim）
 * @param {object} options
 * @param {string} [options.period='daily']  - 'daily' | 'weekly' | 'monthly'
 * @param {string} [options.adjust='qfq']   - '' | 'qfq' | 'hfq'
 * @param {number} [options.limit=120]       - 1–500
 * @returns {Promise<KlineResponse>}
 */
export function getKline(market, symbol, options = {}) {
  const {
    period = 'daily',
    adjust = 'qfq',
    limit  = 120,
  } = options
  const params = new URLSearchParams({ period, adjust, limit: String(limit) })
  return baseFetch(`/stocks/${market}/${symbol.trim()}/kline?${params}`)
}

/**
 * 股票详情页首屏聚合接口：行情、行业、自选状态、最近报告摘要一次返回。
 * 任一子数据失败不阻塞整体，降级返回 null/failed 状态。
 *
 * @param {string} market - 'CN' | 'HK'
 * @param {string} symbol - 股票代码
 * @returns {Promise<StockProfileResponse>}
 */
export function getStockProfile(market, symbol) {
  return baseFetch(`/stocks/${market}/${symbol.trim()}/profile`)
}
