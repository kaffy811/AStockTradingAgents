/**
 * chatMock.js — Mock responses for Chat Copilot (Phase C2).
 * Simulates intent recognition, tool calls, and agent responses.
 * No real backend calls are made — all data is hardcoded.
 *
 * IMPORTANT: All mock text follows financial safety rules:
 *   - No "买入/卖出/持有/目标价/稳赚/抄底/追涨"
 *   - Uses: "偏强/偏弱/分歧/需验证/观察重点/研究线索"
 */

// ── Utility ──────────────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

let _msgCounter = 0
export function newMsgId() {
  return `msg_${Date.now()}_${++_msgCounter}`
}

// ── Mock Tool Trace ───────────────────────────────────────────────────────────

const TOOL_LABELS = {
  resolve_stock_tool:          '解析股票代码',
  get_quote_tool:              '获取实时行情',
  get_kline_summary_tool:      '分析 K 线走势',
  get_fundamentals_tool:       '读取基本面数据',
  get_latest_news_tool:        '搜索近期新闻',
  get_peer_comparison_tool:    '同行对比查询',
  get_industry_hot_tool:       '查询行业热门股',
  get_watchlist_tool:          '读取自选股列表',
  get_recent_reports_tool:     '查找历史报告',
  get_report_detail_tool:      '读取报告详情',
  create_analysis_run_tool:    '创建报告生成任务',
  add_to_watchlist_tool:       '添加到自选股',
  remove_from_watchlist_tool:  '从自选股移除',
  create_compare_selection_tool: '准备多股对比',
}

// ── Scenario Definitions ──────────────────────────────────────────────────────

const SCENARIOS = [

  // ── Scenario 1: 股票异动分析 ─────────────────────────────────────────────
  {
    id: 'stock_anomaly',
    match: (msg) => (
      /中船特气|688146/.test(msg) ||
      (/为什么|原因|涨|跌|异动/.test(msg) && /股票|股/.test(msg))
    ),
    async respond() {
      return {
        toolTrace: [
          { name: 'resolve_stock_tool', status: 'success', detail: 'CN/688146 → 中船特气' },
          { name: 'get_quote_tool',     status: 'success', detail: '当前价 330.5（+12.3%）' },
          { name: 'get_kline_summary_tool', status: 'success', detail: '近20日涨幅 147.87%，均线多头排列' },
          { name: 'get_latest_news_tool',   status: 'success', detail: '获取6条近72小时新闻' },
        ],
        content: `**中船特气（CN/688146）近期技术面偏强，以下为多维度观察：**

**技术面：**
价格大幅站上所有短期及中期均线，均线呈多头排列，近20日涨幅约 147.87%，价格偏离 MA20 达 87%，短期技术性回调风险较高。

**新闻面：**
近期因"六氟化钨"概念获市场关注，尾盘多次冲击涨停。公司已就股价严重异常波动发布公告，并澄清未公开披露产品价格信息，市场传闻存在不确定性。

**风险提示：**
短期涨幅较大，成交换手率处于高位（14.47%），存在高位分化风险。公司异常波动公告及监管关注信号值得持续跟踪。

仅供研究参考，不构成投资建议。`,
        resultCard: {
          type: 'stock_summary',
          data: {
            name: '中船特气',
            market: 'CN',
            symbol: '688146',
            price: '330.5',
            changePct: '+12.3%',
            changeDir: 'up',
            summary: '技术面偏强 · 新闻催化明显 · 短期存在回调风险',
            links: [
              { label: '查看股票详情', path: '/stocks/CN/688146' },
              { label: '生成综合报告 →', action: 'generate_report', symbol: '688146', market: 'CN', name: '中船特气' },
            ]
          }
        }
      }
    }
  },

  // ── Scenario 2: 生成综合报告 ───────────────────────────────────────────────
  {
    id: 'generate_report',
    match: (msg) => /生成.{0,10}报告|综合报告|分析报告|帮我分析/.test(msg),
    async respond(msg) {
      // extract stock hint
      const stockHint = /688146|600519|中船特气|茅台/.test(msg)
        ? (/688146|中船特气/.test(msg) ? { name: '中船特气', market: 'CN', symbol: '688146' } : { name: '贵州茅台', market: 'CN', symbol: '600519' })
        : { name: '中船特气', market: 'CN', symbol: '688146' }

      return {
        toolTrace: [
          { name: 'resolve_stock_tool', status: 'success', detail: `CN/${stockHint.symbol} → ${stockHint.name}` },
        ],
        content: '',  // empty — show confirmation card instead
        resultCard: null,
        confirmation: {
          id: 'confirm_report_' + Date.now(),
          text: `我将为 **${stockHint.name}（${stockHint.market}/${stockHint.symbol}）** 生成综合分析报告，预计需要 30~60 秒。是否确认？`,
          params: { market: stockHint.market, symbol: stockHint.symbol, name: stockHint.name },
          onConfirm: async () => ({
            toolTrace: [
              { name: 'create_analysis_run_tool', status: 'success', detail: '综合分析任务已创建' },
            ],
            content: `✓ 报告生成任务已提交。\n\n**综合判断：分歧**\n技术面偏强，但基本面数据不完整，无法全面评估当前估值，信号存在分歧。建议结合公司财报数据进一步判断。\n\n仅供研究参考，不构成投资建议。`,
            resultCard: {
              type: 'report_link',
              data: {
                name: stockHint.name,
                market: stockHint.market,
                symbol: stockHint.symbol,
                scope: '综合分析',
                verdict: '分歧',
                links: [
                  { label: '查看历史报告', path: '/history' },
                  { label: '前往综合分析', path: '/' },
                ]
              }
            }
          })
        }
      }
    }
  },

  // ── Scenario 3: 加入自选股 ─────────────────────────────────────────────────
  {
    id: 'add_watchlist',
    match: (msg) => /加入自选|添加到自选|自选股/.test(msg) && !/查看自选股/.test(msg),
    async respond(msg) {
      const stockHint = /688146|中船特气/.test(msg)
        ? { name: '中船特气', market: 'CN', symbol: '688146' }
        : { name: '中船特气', market: 'CN', symbol: '688146' }

      return {
        toolTrace: [
          { name: 'resolve_stock_tool', status: 'success', detail: `CN/${stockHint.symbol} → ${stockHint.name}` },
          { name: 'get_watchlist_tool', status: 'success', detail: '检查自选股列表，未发现重复' },
        ],
        content: '',
        resultCard: null,
        confirmation: {
          id: 'confirm_watchlist_' + Date.now(),
          text: `我将把 **${stockHint.name}（${stockHint.market}/${stockHint.symbol}）** 加入你的自选股，是否确认？`,
          params: { market: stockHint.market, symbol: stockHint.symbol, name: stockHint.name },
          onConfirm: async () => ({
            toolTrace: [
              { name: 'add_to_watchlist_tool', status: 'success', detail: `${stockHint.name} 已加入自选股` },
            ],
            content: `✓ 已成功将 **${stockHint.name}（${stockHint.market}/${stockHint.symbol}）** 加入自选股。`,
            resultCard: {
              type: 'watchlist_success',
              data: {
                name: stockHint.name,
                market: stockHint.market,
                symbol: stockHint.symbol,
                links: [
                  { label: '查看自选股', path: '/watchlist' },
                ]
              }
            }
          })
        }
      }
    }
  },

  // ── Scenario 4: 多股对比 ───────────────────────────────────────────────────
  {
    id: 'compare_stocks',
    match: (msg) => /对比|比较/.test(msg),
    async respond(msg) {
      // Try to extract stock names from message
      const stocks = [
        { name: '宁德时代', market: 'CN', symbol: '300750' },
        { name: '紫金矿业', market: 'CN', symbol: '601899' },
        { name: '华大九天', market: 'CN', symbol: '301269' },
      ]
      if (/600519|茅台/.test(msg)) {
        stocks[0] = { name: '贵州茅台', market: 'CN', symbol: '600519' }
        stocks.splice(2, 1)
      }

      const compareUrl = `/compare?stocks=${stocks.map(s => `${s.market}:${s.symbol}`).join(',')}`
      const stockDesc = stocks.map(s => `${s.name}（${s.symbol}）`).join('、')

      return {
        toolTrace: stocks.map(s => ({
          name: 'resolve_stock_tool',
          status: 'success',
          detail: `${s.market}/${s.symbol} → ${s.name}`,
        })).concat([
          { name: 'create_compare_selection_tool', status: 'success', detail: `已准备 ${stocks.length} 只股票对比` }
        ]),
        content: '',
        resultCard: null,
        confirmation: {
          id: 'confirm_compare_' + Date.now(),
          text: `我将打开对比页，从研究维度对比 **${stockDesc}**，是否确认？`,
          params: { stocks, compareUrl },
          onConfirm: async () => ({
            toolTrace: [],
            content: `已准备好对比页面。以下为 ${stocks.length} 只股票的研究维度概览（点击下方按钮进入完整对比）。\n\n仅供研究参考，不构成投资建议。`,
            resultCard: {
              type: 'compare_link',
              data: {
                stocks,
                compareUrl,
                links: [
                  { label: '进入对比页', path: compareUrl },
                ]
              }
            }
          })
        }
      }
    }
  },

  // ── Scenario 5: 行业热点 ───────────────────────────────────────────────────
  {
    id: 'industry_hot',
    match: (msg) => /行业|热点|板块|哪些值得|热门/.test(msg),
    async respond() {
      return {
        toolTrace: [
          { name: 'get_industry_hot_tool', status: 'success', detail: '电子/医药/电力设备等行业热度快照' },
        ],
        content: `以下为当前申万行业热度排行（基于成交额 × 涨跌幅综合评分），仅作研究线索，不代表投资价值判断。`,
        resultCard: {
          type: 'industry_hot',
          data: {
            items: [
              { name: '电子', code: '801080', hotScore: 4.82, changePct: '+3.5%' },
              { name: '医药生物', code: '801150', hotScore: 4.31, changePct: '+1.8%' },
              { name: '电力设备', code: '801730', hotScore: 3.97, changePct: '+2.1%' },
              { name: '有色金属', code: '801050', hotScore: 3.65, changePct: '+0.9%' },
              { name: '计算机',   code: '801750', hotScore: 3.44, changePct: '-0.3%' },
            ],
            links: [
              { label: '查看行业页', path: '/industries' },
            ]
          }
        }
      }
    }
  },

  // ── Default: 通用股票研究引导 ─────────────────────────────────────────────
  {
    id: 'default',
    match: () => true,
    async respond() {
      return {
        toolTrace: [],
        content: `你好！我是 TradingAgents Chat Copilot，可以帮你完成以下研究任务：

- **股票异动分析**：例如"中船特气最近为什么涨这么多"
- **生成研究报告**：例如"帮我生成 688146 的综合报告"
- **加入自选股**：例如"把中船特气加入自选"
- **多股对比**：例如"对比宁德时代、紫金矿业"
- **行业热点**：例如"今天哪些行业值得关注"

_AI 输出仅供研究参考，不构成投资建议。_`,
        resultCard: null,
      }
    }
  },
]

// ── Main Entry ────────────────────────────────────────────────────────────────

/**
 * Get mock response for a user message.
 * Returns a structured response object.
 *
 * @param {string} userMessage
 * @returns {Promise<object>}
 */
export async function getMockResponse(userMessage) {
  // Simulate initial "thinking" delay
  await sleep(400 + Math.random() * 400)

  const msg = userMessage.trim().toLowerCase()
  const scenario = SCENARIOS.find(s => s.match(msg)) ?? SCENARIOS[SCENARIOS.length - 1]
  return scenario.respond(msg)
}

/**
 * Simulate tool trace streaming — yields items one by one with delay.
 * @param {Array} toolTrace - array of { name, status, detail }
 * @param {Function} onItem - callback called with each item as it "runs"
 */
export async function streamToolTrace(toolTrace, onItem) {
  for (const item of toolTrace) {
    await sleep(280 + Math.random() * 180)
    onItem({ ...item, status: 'running' })
    await sleep(350 + Math.random() * 200)
    onItem({ ...item, status: item.status ?? 'success' })
  }
}
