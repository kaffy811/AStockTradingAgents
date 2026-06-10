/**
 * dashboardSummary.js — 首屏仪表盘轻量聚合函数，纯函数无副作用。
 * 仅描述当前指标与数据状态，不含任何投资建议。
 *
 * level 枚举：positive | neutral | warning | limited
 */

import { classifyNewsItem } from './newsInsights.js'

// ── 报告 scope 中文映射 ────────────────────────────────────────────────────────
const _SCOPE_LABELS = {
  comprehensive:         '综合分析',
  technical_only:        '技术面',
  fundamental_only:      '基本面',
  peer_only:             '同行对比',
  news_only:             '新闻面',
  technical_fundamental: '技术+基本面',
}

/**
 * 技术面状态聚合。
 *
 * @param {{ trend, volume, macd, rsi, summary: string } | null} technicalInsight
 * @returns {{ level: string, text: string }}
 */
export function buildTechnicalStatus(technicalInsight) {
  if (!technicalInsight) {
    return { level: 'limited', text: '技术指标数据有限' }
  }

  const dims = ['trend', 'volume', 'macd', 'rsi']
  const positiveCount = dims.filter(k => technicalInsight[k]?.level === 'positive').length
  const warningCount  = dims.filter(k => technicalInsight[k]?.level === 'warning').length
  const limitedCount  = dims.filter(k => technicalInsight[k]?.level === 'limited').length

  if (limitedCount >= 3) return { level: 'limited',  text: '技术指标数据有限' }
  if (positiveCount >= 3) return { level: 'positive', text: '多项指标偏强' }
  if (warningCount  >= 3) return { level: 'warning',  text: '多项指标偏弱' }
  if (positiveCount > warningCount) return { level: 'positive', text: '整体偏强，仍需观察' }
  if (warningCount  > positiveCount) return { level: 'warning',  text: '整体偏弱，仍需观察' }
  return { level: 'neutral', text: '信号混合，震荡观察' }
}

/**
 * 新闻面状态聚合。
 *
 * @param {Array<{ title: string, summary?: string }>} newsItems
 * @returns {{ level: string, text: string, riskCount: number }}
 */
export function buildNewsStatus(newsItems) {
  if (!newsItems || newsItems.length === 0) {
    return { level: 'limited', text: '近 72 小时暂无新闻', riskCount: 0 }
  }

  const classified   = newsItems.map(classifyNewsItem)
  const riskCount    = classified.filter(c => c.type === 'risk').length
  const earningsCount = classified.filter(c => c.type === 'earnings').length

  if (riskCount > 0) {
    return {
      level:     'warning',
      text:      `${newsItems.length} 条新闻，${riskCount} 条风险关注，建议核实原文`,
      riskCount,
    }
  }

  if (earningsCount > 0) {
    return {
      level:     'neutral',
      text:      `${newsItems.length} 条新闻，含业绩相关信息`,
      riskCount: 0,
    }
  }

  return {
    level:     'neutral',
    text:      `${newsItems.length} 条新闻，业务/市场动态`,
    riskCount: 0,
  }
}

/**
 * 报告状态聚合。
 *
 * @param {{ analysis_scope?: string, auto_saved?: boolean, created_at?: string } | null} latestReport
 * @returns {{ level: string, text: string, hasReport: boolean }}
 */
export function buildReportStatus(latestReport) {
  if (!latestReport) {
    return { level: 'limited', text: '暂无历史报告', hasReport: false }
  }

  const scopeLabel = _SCOPE_LABELS[latestReport.analysis_scope] || '综合分析'
  const savedLabel = latestReport.auto_saved ? '自动保存' : '手动保存'
  const timeLabel  = _relativeTime(latestReport.created_at)

  return {
    level:     'positive',
    text:      `${scopeLabel} · ${savedLabel}${timeLabel ? ' · ' + timeLabel : ''}`,
    hasReport: true,
  }
}

/**
 * 汇总入口，供 StockDashboardPanel 一次调用获取全部状态。
 *
 * @param {{ technicalInsight, newsItems, latestReport }} params
 * @returns {{ technical, news, report }}
 */
export function buildDashboardSummary({ technicalInsight, newsItems, latestReport }) {
  return {
    technical: buildTechnicalStatus(technicalInsight),
    news:      buildNewsStatus(newsItems),
    report:    buildReportStatus(latestReport),
  }
}

// ── 内部工具 ──────────────────────────────────────────────────────────────────

/**
 * 将 ISO 8601 时间转为简短相对描述（最多 99 小时，超过则显示日期）。
 */
function _relativeTime(ts) {
  if (!ts) return ''
  try {
    const diff = Date.now() - new Date(ts).getTime()
    if (isNaN(diff)) return ''
    const hours = Math.floor(diff / 3600_000)
    if (hours < 1)   return '刚刚'
    if (hours < 24)  return `${hours} 小时前`
    const days = Math.floor(hours / 24)
    if (days < 30)   return `${days} 天前`
    return new Date(ts).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  } catch {
    return ''
  }
}
