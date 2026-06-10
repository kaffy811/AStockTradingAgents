/**
 * reportText.js — shared text extraction / copy utilities for report export.
 * Used by DownloadMenu, ResearchActionPanel, and any future export surface.
 */

/**
 * Extract the "一、核心摘要" section from a markdown report.
 * Returns the section content from "一、核心摘要" up to the next numbered section,
 * or a fallback slice of the first 500 characters.
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

  // ── zh-CN / zh-TW (Chinese numbered headings) ───────────────────────────
  const s1 = _extract('一、摘要')        // single-agent M29+ wrapper
  if (s1) return s1
  const s2 = _extract('一、核心摘要')    // comprehensive / fallback
  if (s2) return s2

  // ── en-US ────────────────────────────────────────────────────────────────
  const s3 = _extract('I. Summary')      // single-agent en-US
  if (s3) return s3
  const s4 = _extract('I. Core Summary') // fallback en-US
  if (s4) return s4

  // ── ja-JP ────────────────────────────────────────────────────────────────
  const s5 = _extract('I. 要約')
  if (s5) return s5

  // ── ko-KR ────────────────────────────────────────────────────────────────
  const s6 = _extract('I. 요약')
  if (s6) return s6
  const s7 = _extract('I. 핵심 요약')    // fallback ko-KR
  if (s7) return s7

  // ── es-ES ────────────────────────────────────────────────────────────────
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
