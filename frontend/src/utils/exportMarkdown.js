import { AGENT_LABELS, SECTION_DEFS, translateWarning } from './warningMap.js'

/**
 * Resolve the best available timestamp from a result object.
 * Priority: result.created_at → result.metadata.generated_at → now
 * @param {object} result
 * @returns {Date}
 */
function resolveDate(result) {
  if (result.created_at) return new Date(result.created_at)
  const gen = result.metadata?.generated_at
  if (gen) return new Date(gen)
  return new Date()
}

/**
 * Format a Date to "YYYY-MM-DD HH:mm:ss" (local time, zh-CN style).
 * @param {Date} d
 * @returns {string}
 */
function formatDateDisplay(d) {
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
         `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/**
 * Format a Date to compact "YYYYMMDD_HHmmss" for filenames.
 * @param {Date} d
 * @returns {string}
 */
function formatDateFile(d) {
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
         `_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

/**
 * Minimal sanitize for market / symbol used in filenames.
 * Replaces any character that is not alphanumeric, underscore, or hyphen with "-".
 * @param {string} s
 * @returns {string}
 */
function sanitize(s) {
  return String(s ?? '').replace(/[^A-Za-z0-9_-]/g, '-')
}

/**
 * Build a complete Markdown string from a result object.
 * Works for both live analysis results and history detail results
 * (they share the same shape after the getReport() remap).
 *
 * @param {object} result
 * @param {string}   result.market
 * @param {string}   result.symbol
 * @param {string}   result.report       - main comprehensive report
 * @param {object}   result.sections     - { technical, fundamental, peer_comparison, news }
 * @param {object}   result.metadata     - { warnings: string[], agents: {[name]: {status,...}} }
 * @param {string}   [result.created_at] - ISO timestamp (history only)
 * @returns {string}
 */
// ── Multilingual label tables ─────────────────────────────────────────────
// Mirrors backend language_utils.py REPORT_SECTION_LABELS (13 keys, 6 langs).
const _EXPORT_LABELS = {
  'zh-CN': {
    scope_comprehensive:         '综合分析报告',
    scope_technical_only:        '技术面分析报告',
    scope_fundamental_only:      '基本面分析报告',
    scope_peer_only:             '同行对比分析报告',
    scope_news_only:             '新闻面分析报告',
    scope_technical_fundamental: '技术面与基本面分析报告',
    section_technical:           '技术面分析',
    section_fundamental:         '基本面分析',
    section_peer_comparison:     '同行对比分析',
    section_news:                '新闻面分析',
    agent_status:                'Agent 执行状态',
    data_quality:                '数据质量提示',
    no_warnings:                 '暂无数据质量提示。',
  },
  'en-US': {
    scope_comprehensive:         'Comprehensive Analysis Report',
    scope_technical_only:        'Technical Analysis Report',
    scope_fundamental_only:      'Fundamental Analysis Report',
    scope_peer_only:             'Peer Comparison Report',
    scope_news_only:             'News Analysis Report',
    scope_technical_fundamental: 'Technical & Fundamental Report',
    section_technical:           'Technical Analysis',
    section_fundamental:         'Fundamental Analysis',
    section_peer_comparison:     'Peer Comparison',
    section_news:                'News Analysis',
    agent_status:                'Agent Execution Status',
    data_quality:                'Data Quality Notes',
    no_warnings:                 'No data quality issues.',
  },
  'zh-TW': {
    scope_comprehensive:         '綜合分析報告',
    scope_technical_only:        '技術面分析報告',
    scope_fundamental_only:      '基本面分析報告',
    scope_peer_only:             '同行對比分析報告',
    scope_news_only:             '新聞面分析報告',
    scope_technical_fundamental: '技術面與基本面分析報告',
    section_technical:           '技術面分析',
    section_fundamental:         '基本面分析',
    section_peer_comparison:     '同行對比分析',
    section_news:                '新聞面分析',
    agent_status:                'Agent 執行狀態',
    data_quality:                '數據質量提示',
    no_warnings:                 '暫無數據質量提示。',
  },
  'ja-JP': {
    scope_comprehensive:         '総合分析レポート',
    scope_technical_only:        'テクニカル分析レポート',
    scope_fundamental_only:      'ファンダメンタル分析レポート',
    scope_peer_only:             '同業比較レポート',
    scope_news_only:             'ニュース分析レポート',
    scope_technical_fundamental: 'テクニカル・ファンダメンタル分析レポート',
    section_technical:           'テクニカル分析',
    section_fundamental:         'ファンダメンタル分析',
    section_peer_comparison:     '同業比較',
    section_news:                'ニュース分析',
    agent_status:                'エージェント実行状況',
    data_quality:                'データ品質メモ',
    no_warnings:                 'データ品質の問題はありません。',
  },
  'ko-KR': {
    scope_comprehensive:         '종합 분석 보고서',
    scope_technical_only:        '기술 분석 보고서',
    scope_fundamental_only:      '기본 분석 보고서',
    scope_peer_only:             '동종 비교 보고서',
    scope_news_only:             '뉴스 분석 보고서',
    scope_technical_fundamental: '기술·기본 분석 보고서',
    section_technical:           '기술 분석',
    section_fundamental:         '기본 분석',
    section_peer_comparison:     '동종 비교',
    section_news:                '뉴스 분석',
    agent_status:                '에이전트 실행 상태',
    data_quality:                '데이터 품질 메모',
    no_warnings:                 '데이터 품질 문제 없음.',
  },
  'es-ES': {
    scope_comprehensive:         'Informe de Análisis Integral',
    scope_technical_only:        'Informe de Análisis Técnico',
    scope_fundamental_only:      'Informe de Análisis Fundamental',
    scope_peer_only:             'Informe de Comparación entre Pares',
    scope_news_only:             'Informe de Análisis de Noticias',
    scope_technical_fundamental: 'Informe Técnico y Fundamental',
    section_technical:           'Análisis Técnico',
    section_fundamental:         'Análisis Fundamental',
    section_peer_comparison:     'Comparación entre Pares',
    section_news:                'Análisis de Noticias',
    agent_status:                'Estado de los Agentes',
    data_quality:                'Notas de Calidad de Datos',
    no_warnings:                 'Sin problemas de calidad de datos.',
  },
}

function _lbl(lang, key) {
  const tbl = _EXPORT_LABELS[lang] ?? _EXPORT_LABELS['zh-CN']
  return tbl[key] ?? (_EXPORT_LABELS['zh-CN'][key] ?? key)
}

const _SECTION_KEY_MAP = {
  technical:       'section_technical',
  fundamental:     'section_fundamental',
  peer_comparison: 'section_peer_comparison',
  news:            'section_news',
}

export function buildReportMarkdown(result) {
  const market   = result.market  ?? ''
  const symbol   = result.symbol  ?? ''
  const warnings = result.metadata?.warnings ?? []
  const agents   = result.metadata?.agents   ?? {}
  const sections = result.sections ?? {}
  const date     = resolveDate(result)
  const scope    = result.metadata?.analysis_scope || result.analysis_scope || 'comprehensive'
  const lang     = result.output_language || result.metadata?.output_language || 'zh-CN'
  const titleLabel = _lbl(lang, `scope_${scope}`) || _lbl('zh-CN', 'scope_comprehensive')

  const lines = []

  // ── Header ──────────────────────────────────────────────────────────────
  lines.push(`# ${titleLabel}：${market} / ${symbol}`)
  lines.push('')
  lines.push(`> 生成时间：${formatDateDisplay(date)}`)
  lines.push('')
  lines.push('---')
  lines.push('')

  // ── Agent status table ───────────────────────────────────────────────────
  lines.push(`## ${_lbl(lang, 'agent_status')}`)
  lines.push('')
  lines.push('| 模块 | 状态 | 说明 |')
  lines.push('|---|---|---|')

  for (const { key } of SECTION_DEFS) {
    const label  = AGENT_LABELS[key] ?? key
    const info   = agents[key]
    const status = info?.status ?? '—'
    const note   = info?.error  ?? '-'
    lines.push(`| ${label} | ${status} | ${note} |`)
  }

  lines.push('')
  lines.push('---')
  lines.push('')

  // ── Warnings ─────────────────────────────────────────────────────────────
  lines.push(`## ${_lbl(lang, 'data_quality')}`)
  lines.push('')

  if (warnings.length === 0) {
    lines.push(_lbl(lang, 'no_warnings'))
  } else {
    for (const w of warnings) {
      lines.push(`- ${translateWarning(w)}`)
    }
  }

  lines.push('')
  lines.push('---')
  lines.push('')

  // ── Main report ───────────────────────────────────────────────────────────
  lines.push(`## ${titleLabel}`)
  lines.push('')
  lines.push(result.report ?? '')
  lines.push('')
  lines.push('---')
  lines.push('')

  // ── Sub-reports (fixed order from SECTION_DEFS) ───────────────────────────
  for (const { key } of SECTION_DEFS) {
    const content = sections[key]
    if (!content) continue   // skip empty / null / undefined sections
    const sectionLabel = _lbl(lang, _SECTION_KEY_MAP[key] ?? key)
    lines.push(`## ${sectionLabel}`)
    lines.push('')
    lines.push(content)
    lines.push('')
    lines.push('---')
    lines.push('')
  }

  return lines.join('\n')
}

/**
 * Build the download filename for a result.
 * Format: analysis_{market}_{symbol}_{YYYYMMDD_HHmmss}.md
 *
 * @param {object} result
 * @returns {string}
 */
export function buildFilename(result) {
  const market = sanitize(result.market  ?? 'UNKNOWN')
  const symbol = sanitize(result.symbol  ?? 'UNKNOWN')
  const ts     = formatDateFile(resolveDate(result))
  return `analysis_${market}_${symbol}_${ts}.md`
}

/**
 * Trigger a browser download of the report as a Markdown file.
 * Pure side-effect: no return value, no async.
 *
 * @param {object} result
 */
export function downloadMarkdown(result) {
  const content  = buildReportMarkdown(result)
  const filename = buildFilename(result)

  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
