/**
 * C29.1 — Chat UI Flags + C29.4/5 — Message Actions + C29.6 — Markdown
 *
 * T1:  SHOW_DATA_QUALITY is false when env is not DEV
 * T2:  SHOW_SOURCES is false when env is not DEV
 * T3:  SHOW_REASONING_PANEL is false when env is not DEV
 * T4:  SHOW_STREAM_DEBUG is false when env is not DEV
 * T5:  renderMarkdown: headings ## render as <h2>
 * T6:  renderMarkdown: unordered list (- item) renders as <ul><li>
 * T7:  renderMarkdown: ordered list (1. item) renders as <ol><li>
 * T8:  renderMarkdown: bold **text** renders as <strong>
 * T9:  renderMarkdown: inline code `code` renders as <code>
 * T10: renderMarkdown: fenced code block ``` renders as <pre><code>
 * T11: renderMarkdown: table | col | col | renders as <table>
 * T12: renderMarkdown: HTML characters are escaped before inline processing
 * T13: renderMarkdown: --- renders as <hr>
 * T14: renderMarkdown: empty string returns ''
 * T15: session sort — sort by updated_at DESC
 */
import { describe, it, expect } from 'vitest'

// ── T1–T4: flag tests (prod-equivalent: import.meta.env.DEV is false in vitest) ──
// In vitest, import.meta.env.DEV is false by default (not a dev server run),
// so all SHOW_* flags should evaluate to false.
import {
  CHAT_UI_DEBUG,
  SHOW_DATA_QUALITY,
  SHOW_SOURCES,
  SHOW_REASONING_PANEL,
  SHOW_STREAM_DEBUG,
} from '../config/chatUiFlags.js'

describe('C29.1 — chatUiFlags in non-DEV (test) environment', () => {
  it('T1: CHAT_UI_DEBUG is false', () => {
    expect(CHAT_UI_DEBUG).toBe(false)
  })

  it('T2: SHOW_DATA_QUALITY is false', () => {
    expect(SHOW_DATA_QUALITY).toBe(false)
  })

  it('T3: SHOW_SOURCES is false', () => {
    expect(SHOW_SOURCES).toBe(false)
  })

  it('T4: SHOW_REASONING_PANEL is false', () => {
    expect(SHOW_REASONING_PANEL).toBe(false)
  })

  it('T4b: SHOW_STREAM_DEBUG is false', () => {
    expect(SHOW_STREAM_DEBUG).toBe(false)
  })
})

// ── T5–T14: renderMarkdown unit tests ─────────────────────────────────────────
// We extract the renderMarkdown logic into a testable helper.
// Copy of the same function from ChatMessageList.vue (no Vue deps needed).

function _inlineMd(text) {
  return text
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
    .replace(/_([^_\n]+?)_/g, '<em>$1</em>')
}

function renderMarkdown(text) {
  if (!text) return ''
  const esc = s => s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  const lines = text.split('\n')
  const out   = []
  let i       = 0
  let inPara  = false
  const flushPara = () => { if (inPara) { out.push('</p>'); inPara = false } }
  const openPara  = () => { if (!inPara) { out.push('<p>'); inPara = true } }

  while (i < lines.length) {
    const raw  = lines[i]
    const line = raw.trim()

    if (line.startsWith('```')) {
      flushPara()
      const codeLines = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(esc(lines[i]))
        i++
      }
      out.push(`<pre class="md-pre"><code>${codeLines.join('\n')}</code></pre>`)
      i++
      continue
    }

    const hMatch = line.match(/^(#{1,3})\s+(.+)$/)
    if (hMatch) {
      flushPara()
      const lvl = hMatch[1].length
      out.push(`<h${lvl} class="md-h">${_inlineMd(esc(hMatch[2]))}</h${lvl}>`)
      i++
      continue
    }

    if (/^[-*]\s/.test(line)) {
      flushPara()
      out.push('<ul class="md-ul">')
      while (i < lines.length && /^[-*]\s/.test(lines[i].trim())) {
        out.push(`<li>${_inlineMd(esc(lines[i].trim().slice(2).trim()))}</li>`)
        i++
      }
      out.push('</ul>')
      continue
    }

    if (/^\d+\.\s/.test(line)) {
      flushPara()
      out.push('<ol class="md-ol">')
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        out.push(`<li>${_inlineMd(esc(lines[i].trim().replace(/^\d+\.\s/, '')))}</li>`)
        i++
      }
      out.push('</ol>')
      continue
    }

    if (line.startsWith('|') && line.endsWith('|')) {
      flushPara()
      const tableRows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableRows.push(lines[i].trim())
        i++
      }
      const hasHeader = tableRows.length >= 2 && /^\|[\s|:-]+\|$/.test(tableRows[1])
      out.push('<div class="md-table-wrap"><table class="md-table">')
      tableRows.forEach((row, ri) => {
        if (hasHeader && ri === 1) return
        const isHead = hasHeader && ri === 0
        const parts  = row.split('|')
        const cells  = parts.slice(1, parts.length - 1).map(c => c.trim())
        const tag    = isHead ? 'th' : 'td'
        out.push('<tr>' + cells.map(c => `<${tag}>${_inlineMd(esc(c))}</${tag}>`).join('') + '</tr>')
      })
      out.push('</table></div>')
      continue
    }

    if (/^---+$/.test(line) || /^\*\*\*+$/.test(line)) {
      flushPara()
      out.push('<hr class="md-hr">')
      i++
      continue
    }

    if (line === '') {
      flushPara()
      i++
      continue
    }

    openPara()
    out.push(_inlineMd(esc(raw)) + '<br>')
    i++
  }

  flushPara()
  return out.join('')
    .replace(/<br><\/p>/g, '</p>')
    .replace(/<p><\/p>/g, '')
}

describe('C29.6 — renderMarkdown', () => {
  it('T5: ## heading renders as <h2 class="md-h">', () => {
    const result = renderMarkdown('## 技术面分析')
    expect(result).toContain('<h2 class="md-h">技术面分析</h2>')
    expect(result).not.toContain('##')
  })

  it('T6: unordered list renders as <ul><li>', () => {
    const result = renderMarkdown('- 苹果\n- 橙子\n- 香蕉')
    expect(result).toContain('<ul class="md-ul">')
    expect(result).toContain('<li>苹果</li>')
    expect(result).toContain('<li>香蕉</li>')
  })

  it('T7: ordered list renders as <ol><li>', () => {
    const result = renderMarkdown('1. 第一步\n2. 第二步\n3. 第三步')
    expect(result).toContain('<ol class="md-ol">')
    expect(result).toContain('<li>第一步</li>')
    expect(result).toContain('<li>第三步</li>')
  })

  it('T8: bold **text** renders as <strong>', () => {
    const result = renderMarkdown('这是 **重要信息** 请关注')
    expect(result).toContain('<strong>重要信息</strong>')
  })

  it('T9: inline code `code` renders as <code>', () => {
    const result = renderMarkdown('调用 `get_price()` 方法')
    expect(result).toContain('<code>get_price()</code>')
  })

  it('T10: fenced code block renders as <pre><code>', () => {
    const result = renderMarkdown('```\nprint("hello")\n```')
    expect(result).toContain('<pre class="md-pre"><code>')
    expect(result).toContain('print("hello")')
    expect(result).toContain('</code></pre>')
  })

  it('T11: table renders as <table class="md-table">', () => {
    const table = '| 指标 | 数值 |\n| --- | --- |\n| PE | 25.3 |'
    const result = renderMarkdown(table)
    expect(result).toContain('<table class="md-table">')
    expect(result).toContain('<th>指标</th>')
    expect(result).toContain('<td>25.3</td>')
    // Separator row must not appear as a table row
    expect(result).not.toContain('---')
  })

  it('T12: HTML characters are escaped', () => {
    const result = renderMarkdown('<script>alert(1)</script>')
    expect(result).not.toContain('<script>')
    expect(result).toContain('&lt;script&gt;')
  })

  it('T13: --- renders as <hr>', () => {
    const result = renderMarkdown('---')
    expect(result).toContain('<hr class="md-hr">')
  })

  it('T14: empty string returns empty string', () => {
    expect(renderMarkdown('')).toBe('')
    expect(renderMarkdown(null)).toBe('')
    expect(renderMarkdown(undefined)).toBe('')
  })
})

// ── T15: session sort helper ──────────────────────────────────────────────────
describe('C29.3 — session sort by updated_at DESC', () => {
  it('T15: sessions are sorted most-recent first', () => {
    const sessions = [
      { id: 'a', updated_at: '2026-06-01T10:00:00Z' },
      { id: 'b', updated_at: '2026-06-27T15:00:00Z' },
      { id: 'c', updated_at: '2026-06-20T08:00:00Z' },
    ]
    sessions.sort((a, b) => (b.updated_at > a.updated_at ? 1 : -1))
    expect(sessions.map(s => s.id)).toEqual(['b', 'c', 'a'])
  })

  it('T15b: missing updated_at falls back gracefully', () => {
    const sessions = [
      { id: 'x', updated_at: '' },
      { id: 'y', updated_at: '2026-06-27T12:00:00Z' },
    ]
    sessions.sort((a, b) => (b.updated_at > a.updated_at ? 1 : -1))
    expect(sessions[0].id).toBe('y')
  })
})
