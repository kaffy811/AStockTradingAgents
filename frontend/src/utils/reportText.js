/**
 * reportText.js — shared text extraction / copy utilities for report export.
 * Used by DownloadMenu, ResearchActionPanel, and any future export surface.
 */

/**
 * Extract the summary section from a markdown report.
 * Priority (highest first):
 *   M51+: ### 摘要结论 (single-agent), ## 一、综合结论卡片 (comprehensive)
 *   M29+: ## 一、摘要 (single-agent wrapper)
 *   Legacy: ## 一、核心摘要
 * Falls back to the first 500 characters.
 *
 * @param {string} markdown
 * @returns {string}
 */
export function extractSummary(markdown) {
  if (!markdown) return ''

  // Helper: extract section starting at `needle`, stopping at the next ## heading.
  function _extract(needle) {
    const idx = markdown.indexOf(needle)
    if (idx === -1) return null
    const rest = markdown.slice(idx)
    // Stop at the next ## (or ###) heading that follows a newline
    const nextMatch = rest.match(/\n#{2,3}\s+/)
    if (!nextMatch) return rest.slice(0, 800).trim()
    return rest.slice(0, nextMatch.index).trim()
  }

  // ── M51+ zh-CN / zh-TW: single-agent 摘要结论 (unnumbered ### heading) ──
  const m1 = _extract('### 摘要结论')
  if (m1) return m1
  const m1tw = _extract('### 摘要結論')
  if (m1tw) return m1tw

  // ── M51+ zh-CN / zh-TW: comprehensive 综合结论卡片 ──────────────────────
  const m2 = _extract('一、综合结论卡片')
  if (m2) return m2
  const m2tw = _extract('一、綜合結論卡片')
  if (m2tw) return m2tw

  // ── M51+ en-US: single-agent / comprehensive ─────────────────────────────
  // LLM may translate ### 摘要结论 as any of these variants:
  const m3 = _extract('### Summary Conclusion')
  if (m3) return m3
  const m3b = _extract('### Summary & Conclusions')
  if (m3b) return m3b
  const m3c = _extract('### Summary & Conclusion')
  if (m3c) return m3c
  const m3d = _extract('### Summary Conclusions')
  if (m3d) return m3d
  // Broad catch: any ### Summary… heading (covers future LLM variants)
  const m3e = _extract('### Summary')
  if (m3e) return m3e
  const m4 = _extract('I. Synthesis Conclusion Card')
  if (m4) return m4

  // ── M51+ ja-JP ───────────────────────────────────────────────────────────
  const m5 = _extract('### 要約結論')
  if (m5) return m5
  const m6 = _extract('I. 総合結論カード')
  if (m6) return m6

  // ── M51+ ko-KR ───────────────────────────────────────────────────────────
  const m7 = _extract('### 요약 결론')
  if (m7) return m7
  const m8 = _extract('I. 종합 결론 카드')
  if (m8) return m8

  // ── M51+ es-ES ───────────────────────────────────────────────────────────
  const m9 = _extract('### Conclusión Resumida')
  if (m9) return m9
  const m10 = _extract('I. Tarjeta de Conclusión Integral')
  if (m10) return m10

  // ── Legacy zh-CN / zh-TW (M29+ single-agent wrapper) ────────────────────
  const s1 = _extract('一、摘要')
  if (s1) return s1

  // ── Legacy zh-CN comprehensive / fallback ────────────────────────────────
  const s2 = _extract('一、核心摘要')
  if (s2) return s2

  // ── Legacy en-US ─────────────────────────────────────────────────────────
  const s3 = _extract('I. Summary')
  if (s3) return s3
  const s4 = _extract('I. Core Summary')
  if (s4) return s4

  // ── Legacy ja-JP ─────────────────────────────────────────────────────────
  const s5 = _extract('I. 要約')
  if (s5) return s5

  // ── Legacy ko-KR ─────────────────────────────────────────────────────────
  const s6 = _extract('I. 요약')
  if (s6) return s6
  const s7 = _extract('I. 핵심 요약')
  if (s7) return s7

  // ── Legacy es-ES ─────────────────────────────────────────────────────────
  const s8 = _extract('I. Resumen')
  if (s8) return s8

  // ── Legacy zh-CN (pre-M29 single-agent) ─────────────────────────────────
  const s9 = _extract('二、核心结论')
  if (s9) return s9

  // Fallback: first 500 chars
  return markdown.slice(0, 500)
}

/**
 * Build the display identity string for a result.
 * e.g. "平安银行（CN/000001）" or "CN/000001"
 *
 * @param {object} result
 * @returns {string}
 */
export function buildReportIdentity(result) {
  const market = result?.market ?? ''
  const symbol = result?.symbol ?? ''
  const name   = result?.stock_name ?? ''
  if (name) return `${name}（${market}/${symbol}）`
  return `${market}/${symbol}`
}

/**
 * Build a short share text suitable for messaging apps (WeChat, Feishu, email).
 * Capped at ~800 characters. No raw markdown syntax included.
 *
 * @param {object} result
 * @returns {string}
 */
export function buildShareText(result) {
  const identity = buildReportIdentity(result)
  const summary  = extractSummary(result?.report ?? '')

  // Strip markdown formatting (headers, bold, bullet dashes)
  const plain = summary
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/^[-*]\s+/gm, '• ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
    .slice(0, 600)

  return [
    `【股票研究摘要】${identity}`,
    '',
    plain,
    '',
    '仅供研究参考，不构成投资建议。',
  ].join('\n')
}

/**
 * Copy text to clipboard.
 * Prefers navigator.clipboard.writeText; falls back to execCommand('copy').
 *
 * @param {string} text
 * @returns {Promise<boolean>}  true = success, false = failure
 */
export async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
    // execCommand fallback
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity  = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}
