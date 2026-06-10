/**
 * newsInsights.js — 规则型新闻分类与影响摘要工具，纯函数无副作用。
 * 仅描述新闻分类状态，不含任何投资建议。
 *
 * 分类优先级：risk > earnings > policy > market > product > neutral
 */

// ── 分类规则表（优先级从高到低） ──────────────────────────────────────────────
const _CLASSIFY_RULES = [
  {
    type:     'risk',
    label:    '风险关注',
    level:    'risk',
    reason:   '标题或摘要包含风险类关键词',
    keywords: ['处罚', '立案', '调查', '诉讼', '违规', '暴雷', '退市', 'ST ', ' ST', ' *ST', '风险提示',
               '下调评级', '亏损扩大', '爆雷', '债务违约', '违约', '破产', '冻结', '失联', '被查'],
  },
  {
    type:     'earnings',
    label:    '业绩相关',
    level:    'neutral',
    reason:   '标题或摘要包含业绩类关键词',
    keywords: ['业绩', '财报', '净利润', '营收', '收入增', '亏损', '盈利', '同比增', '同比降',
               '季报', '年报', '利润', '增速', '业绩预', '扭亏', '归母', '每股收益'],
  },
  {
    type:     'policy',
    label:    '政策监管',
    level:    'neutral',
    reason:   '标题或摘要包含政策类关键词',
    keywords: ['政策', '监管', '证监会', '央行', '银保监', '金管局', '行业规范', '新规',
               '法规', '规定发布', '通知', '意见稿', '征求意见', '审批', '许可证'],
  },
  {
    type:     'market',
    label:    '市场动态',
    level:    'neutral',
    reason:   '标题或摘要包含市场类关键词',
    keywords: ['回购', '分红', '增持', '减持', '股价', '大宗交易', '融资', '定增',
               '评级', '目标价', '主力资金', '北向资金', '机构持仓', '股东增持'],
  },
  {
    type:     'product',
    label:    '业务动态',
    level:    'neutral',
    reason:   '标题或摘要包含业务类关键词',
    keywords: ['合作', '产品发布', '发布新', '上线', '签约', '订单', '中标', '项目', '战略合作',
               '业务拓展', '新品', '布局', '扩张', '投产', '竣工', '开工'],
  },
]

/**
 * 分类单条新闻（基于标题 + 摘要关键词规则）。
 *
 * @param {{ title?: string, summary?: string }} news
 * @returns {{ type: string, label: string, level: string, reason: string }}
 */
export function classifyNewsItem(news) {
  if (!news || !news.title) {
    return { type: 'neutral', label: '其他', level: 'neutral', reason: '无可分析内容' }
  }

  const text = [news.title || '', news.summary || ''].join(' ')

  for (const rule of _CLASSIFY_RULES) {
    if (rule.keywords.some(kw => text.includes(kw))) {
      return {
        type:   rule.type,
        label:  rule.label,
        level:  rule.level,
        reason: rule.reason,
      }
    }
  }

  return { type: 'neutral', label: '其他', level: 'neutral', reason: '未匹配到特定分类关键词' }
}

/**
 * 将新闻列表分类后按时间倒序，并按日期分组返回时间线数据。
 *
 * @param {Array<{ title: string, summary?: string, publish_time?: string }>} newsItems
 * @returns {Array<{ date: string, items: Array }>}
 */
export function buildNewsTimelineGroups(newsItems) {
  if (!Array.isArray(newsItems) || newsItems.length === 0) return []

  // 分类 + 按时间排序（倒序）
  const classified = newsItems
    .map(item => ({ ...item, _classification: classifyNewsItem(item) }))
    .sort((a, b) => {
      const ta = a.publish_time ? new Date(a.publish_time).getTime() : 0
      const tb = b.publish_time ? new Date(b.publish_time).getTime() : 0
      return tb - ta
    })

  // 按日期分组
  const groups = {}
  for (const item of classified) {
    const date = _extractDate(item.publish_time)
    if (!groups[date]) groups[date] = []
    groups[date].push(item)
  }

  // 返回按日期倒序的分组数组
  return Object.keys(groups)
    .sort((a, b) => b.localeCompare(a))
    .map(date => ({ date, items: groups[date] }))
}

/**
 * 生成新闻影响摘要（不含任何投资建议词）。
 *
 * @param {Array} newsItems
 * @returns {{ summary: string, riskCount: number, earningsCount: number, total: number }}
 */
export function buildNewsImpactSummary(newsItems) {
  if (!Array.isArray(newsItems) || newsItems.length === 0) {
    return {
      summary:       '近 72 小时暂无可展示新闻，新闻面信息有限。',
      riskCount:     0,
      earningsCount: 0,
      total:         0,
    }
  }

  const classified   = newsItems.map(classifyNewsItem)
  const total        = classified.length
  const riskCount    = classified.filter(c => c.type === 'risk').length
  const earningsCount = classified.filter(c => c.type === 'earnings').length

  let summary
  if (riskCount > 0) {
    summary = `近 72 小时新闻中出现 ${riskCount} 条风险关注类信息，建议结合公告原文进一步核实。`
  } else if (earningsCount > 0) {
    summary = `近 72 小时新闻中包含 ${earningsCount} 条业绩相关信息，可结合财报数据进一步观察。`
  } else {
    summary = `近 72 小时新闻主要为业务、市场或行业动态，暂未识别到明显风险类关键词。`
  }

  return { summary, riskCount, earningsCount, total }
}

/**
 * 格式化新闻发布时间，返回可读短串。
 * 无法解析时返回"时间未知"。
 *
 * @param {string|null|undefined} time
 * @returns {string}
 */
export function formatNewsTime(time) {
  if (!time) return '时间未知'
  try {
    const d = new Date(time)
    if (isNaN(d.getTime())) return '时间未知'
    return d.toLocaleString('zh-CN', {
      month:  'numeric',
      day:    'numeric',
      hour:   '2-digit',
      minute: '2-digit',
    })
  } catch {
    return '时间未知'
  }
}

// ── 内部工具 ──────────────────────────────────────────────────────────────────

/**
 * 从 ISO 8601 时间中提取日期字符串，供按日期分组使用。
 *
 * @param {string|null|undefined} publishTime
 * @returns {string}
 */
function _extractDate(publishTime) {
  if (!publishTime) return '日期未知'
  try {
    const d = new Date(publishTime)
    if (isNaN(d.getTime())) return '日期未知'
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric' })
  } catch {
    return '日期未知'
  }
}
