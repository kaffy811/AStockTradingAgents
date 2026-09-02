const STATUS_VIEWS = Object.freeze({
  fulfilled: {
    title: '已完成研究',
    description: '已获得可验证数据与来源',
    tone: 'success',
    completed: true,
    retryable: false,
  },
  partial: {
    title: '部分完成',
    description: '已展示可验证部分，并列出缺失项',
    tone: 'warning',
    completed: false,
    retryable: true,
  },
  unavailable: {
    title: '当前缺少所需数据',
    description: '当前没有足够的已批准数据完成该研究',
    tone: 'neutral',
    completed: false,
    retryable: false,
  },
  failed: {
    title: '研究执行失败',
    description: '本次执行未产生可验证结论，可稍后重试',
    tone: 'danger',
    completed: false,
    retryable: true,
  },
})

const REASON_MESSAGES = Object.freeze({
  NO_APPROVED_NEWS_SOURCE: '当前没有可用的已批准新闻来源。',
  NO_APPROVED_INDUSTRY_NEWS_SOURCE: '当前没有可用的已批准行业新闻来源。',
  PROVIDER_NETWORK_TIMEOUT: '数据服务响应超时，可稍后重试。',
  PROVIDER_PERMISSION_DENIED: '当前账户暂无该数据权限。',
  DATA_NOT_AVAILABLE: '当前数据范围内没有可验证结果。',
  NO_PERSISTED_CNINFO_EVENTS: '当前已持久化数据中没有可用的官方披露事件。',
  NO_MATCHING_PERSISTED_CNINFO_EVENTS: '当前已持久化数据中没有匹配的官方披露事件。',
  REPORT_RAG_EVIDENCE_NOT_RENDERED: '已找到报告元数据，但暂无可展示的报告证据。',
})

const SAFE_SOURCE_LABELS = Object.freeze({
  CNINFO: '巨潮资讯（CNINFO）',
  TUSHARE: '已授权行情数据',
  'TUSHARE EOD': '已授权行情数据',
})

const COVERAGE_LABELS = Object.freeze({
  persisted_cninfo_report_metadata: '已持久化的官方公告与报告元数据',
  persisted_cninfo_events: '已持久化的官方披露事件',
  official_company_events: '公司官方披露事件',
  eod: '个股日线行情',
  market_overview: '市场概览',
})

const SENSITIVE_TEXT = /(token|cookie|password|secret|authorization|chunk[_ -]?id|stack\s*trace|traceback|database|table\b|provider\b|supabase|postgres|sql\b)/i

function safeText(value, maxLength = 240) {
  if (typeof value !== 'string') return ''
  const text = value.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim()
  if (!text || SENSITIVE_TEXT.test(text)) return ''
  return text.slice(0, maxLength)
}

function safeUrl(value) {
  if (typeof value !== 'string') return ''
  try {
    const parsed = new URL(value)
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) return ''
    return parsed.href
  } catch {
    return ''
  }
}

function sourceLabel(raw, url) {
  const normalized = String(raw ?? '').trim().toUpperCase()
  if (SAFE_SOURCE_LABELS[normalized]) return SAFE_SOURCE_LABELS[normalized]
  return url ? '已验证来源' : ''
}

function normalizeSources(metadata) {
  const inputs = [
    ...(Array.isArray(metadata.sources) ? metadata.sources : []),
    ...(Array.isArray(metadata.events) ? metadata.events : []),
  ]
  const seen = new Set()
  return inputs.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const url = safeUrl(item.source_url ?? item.url)
    const name = sourceLabel(item.source_name ?? item.source ?? item.name, url)
    if (!name) return []
    const key = `${name}|${url}`
    if (seen.has(key)) return []
    seen.add(key)
    return [{ name, url }]
  })
}

function coverageLabel(value) {
  if (!value) return ''
  if (typeof value === 'string') return COVERAGE_LABELS[value] ?? '已验证数据范围'
  if (typeof value !== 'object') return ''
  const kind = value.kind ?? value.type ?? value.scope
  const base = COVERAGE_LABELS[kind] ?? '已验证数据范围'
  const rawCount = value.count ?? value.event_count
  const count = Number.isInteger(rawCount) && rawCount >= 0 ? `（${rawCount} 项）` : ''
  return `${base}${count}`
}

function normalizeLimitations(metadata, reasonMessage) {
  const raw = Array.isArray(metadata.limitations)
    ? metadata.limitations
    : (metadata.limitation ? [metadata.limitation] : [])
  const values = raw.map((item) => safeText(item)).filter(Boolean).slice(0, 5)
  if (!values.length && reasonMessage) values.push(reasonMessage)
  if (!values.length && metadata.fulfillment === 'partial') values.push('部分数据或字段当前不可用。')
  return values
}

export function researchReasonMessage(reasonCode) {
  return REASON_MESSAGES[reasonCode] ?? (reasonCode ? REASON_MESSAGES.DATA_NOT_AVAILABLE : '')
}

export function researchFulfillmentView(status, reasonCode = '') {
  const key = Object.hasOwn(STATUS_VIEWS, status) ? status : ''
  if (!key) return null
  const base = STATUS_VIEWS[key]
  const reason = researchReasonMessage(reasonCode)
  const retryable = base.retryable || reasonCode === 'PROVIDER_NETWORK_TIMEOUT'
  return { ...base, status: key, reason, retryable }
}

export function normalizeResearchMetadata(input = {}) {
  const metadata = input && typeof input === 'object' ? input : {}
  const rawStatus = metadata.fulfillment ?? metadata.research_fulfillment
  const status = Object.hasOwn(STATUS_VIEWS, rawStatus) ? rawStatus : ''
  if (!status) return null

  const reasonCode = Object.hasOwn(REASON_MESSAGES, metadata.reason_code)
    ? metadata.reason_code
    : (metadata.reason_code ? 'DATA_NOT_AVAILABLE' : '')
  const view = researchFulfillmentView(status, reasonCode)
  const reason = view.reason
  return {
    ...view,
    reasonCode,
    asOf: safeText(metadata.as_of, 80),
    coverage: coverageLabel(metadata.coverage),
    limitations: normalizeLimitations(metadata, status === 'partial' || status === 'unavailable' ? reason : ''),
    sources: normalizeSources(metadata),
  }
}
