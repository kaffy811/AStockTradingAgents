/** Agent display name mapping */
export const AGENT_LABELS = {
  technical:       '技术面',
  fundamental:     '基本面',
  peer_comparison: '同行对比',
  news:            '新闻面',
}

/** Warning key → Chinese description */
export const WARNING_MAP = {
  'HK fundamentals coverage is limited.': 'HK 港股基本面数据覆盖有限，财务字段多为缺失。',
  'valuation fields are missing.':         'PE / PB 等估值字段缺失，无法进行估值评价。',
  'peer comparison is unavailable.':       '暂无同行配置，无法进行横向对比。',
  'news data is unavailable.':             '当前时间窗口内无可用新闻数据。',
  'news relevance may be limited.':        '港股新闻通过关键词搜索获取，相关性可能较弱。',
}

/** Sub-report section definitions */
export const SECTION_DEFS = [
  { key: 'technical',       label: '技术面分析',   icon: '📈' },
  { key: 'fundamental',     label: '基本面分析',   icon: '📊' },
  { key: 'peer_comparison', label: '同行对比分析', icon: '🏢' },
  { key: 'news',            label: '新闻面分析',   icon: '📰' },
]

/** Ordered list of agent names (matches SECTION_DEFS order) */
export const AGENT_NAMES = ['technical', 'fundamental', 'peer_comparison', 'news']

/** Quick example stocks */
export const EXAMPLES = [
  { label: 'CN / 贵州茅台 600519', market: 'CN', symbol: '600519' },
  { label: 'CN / 平安银行 000001', market: 'CN', symbol: '000001' },
  { label: 'CN / 宁德时代 300750', market: 'CN', symbol: '300750' },
  { label: 'HK / 腾讯控股 700',    market: 'HK', symbol: '700'    },
  { label: 'HK / 阿里巴巴 9988',   market: 'HK', symbol: '9988'   },
]

/** Translate a warning key to Chinese. Returns original if not in map. */
export function translateWarning(w) {
  return WARNING_MAP[w] || w
}

/** Return CSS class name for an agent status string. */
export function badgeClass(status) {
  return status === 'success' ? 'badge-success'
       : status === 'timeout' ? 'badge-timeout'
       : 'badge-failed'
}

/** Return display label for an agent name key. */
export function agentLabel(name) {
  return AGENT_LABELS[name] || name
}

/** Format ISO 8601 UTC string to zh-CN locale string. */
export function formatTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    })
  } catch {
    return iso
  }
}
