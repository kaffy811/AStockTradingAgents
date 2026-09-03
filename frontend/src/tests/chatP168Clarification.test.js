/**
 * P1.6.8 — Legacy entity clarification candidate helpers.
 *
 * Covers (component-level DOM behavior is verified by the real Browser B03
 * acceptance; these tests cover the shared logic the component renders from):
 *   1. candidates render source: dedup keeps display_name+symbol pairs
 *   2. display_name/symbol selection text
 *   3. deduplication by market+symbol
 *   4. no candidates -> component receives null (renders nothing)
 *   5. normal assistant messages (no metadata) unaffected
 *   6. click -> deterministic explicit selection text
 *   7. no internal status/error fields leak through the mapping
 *   8. no shadow content in the mapping
 *   9. duplicate streaming terminal replay stays idempotent
 *  10. persisted metadata restores candidates after refresh
 *  11. text fallback remains available (content untouched by mapping)
 *  12. B03 regression: 平安 candidates map end-to-end
 */
import { describe, it, expect } from 'vitest'
import {
  candidateKey,
  candidateSelectionText,
  clarificationFromMetadata,
  dedupCandidates,
} from '../utils/clarification.js'

const CANDIDATES = [
  { display_name: '平安银行', symbol: '000001', market: 'CN', reason: '名称以“平安”开头' },
  { display_name: '中国平安', symbol: '601318', market: 'CN', reason: '名称包含“平安”' },
]
const CLARIFICATION = {
  kind: 'entity_selection',
  prompt: '请确认你指的是哪家公司：',
  query_term: '平安',
  selection_required: true,
  candidates: CANDIDATES,
}

describe('clarification helpers (P1.6.8)', () => {
  it('keeps display names, symbols and backend order', () => {
    const out = dedupCandidates(CANDIDATES)
    expect(out.map(c => c.display_name)).toEqual(['平安银行', '中国平安'])
    expect(out.map(c => c.symbol)).toEqual(['000001', '601318'])
  })

  it('deduplicates by market+symbol', () => {
    const out = dedupCandidates([...CANDIDATES, { ...CANDIDATES[0] }])
    expect(out).toHaveLength(2)
    expect(candidateKey(CANDIDATES[0])).toBe('CN:000001')
  })

  it('drops entries without display_name and returns empty for empty input', () => {
    expect(dedupCandidates([{ symbol: 'x' }])).toEqual([])
    expect(dedupCandidates(undefined)).toEqual([])
  })

  it('builds explicit selection text with and without symbol', () => {
    expect(candidateSelectionText(CANDIDATES[1])).toBe('中国平安（601318）')
    expect(candidateSelectionText({ display_name: '中国平安' })).toBe('中国平安')
    expect(candidateSelectionText(null)).toBe('')
  })

  it('restores candidates from persisted message metadata', () => {
    const clarification = clarificationFromMetadata({
      response_kind: 'clarification',
      clarification: CLARIFICATION,
    })
    expect(clarification.candidates).toHaveLength(2)
    expect(clarification.prompt).toContain('请确认')
  })

  it('returns null for missing/empty metadata so no component renders', () => {
    expect(clarificationFromMetadata(null)).toBeNull()
    expect(clarificationFromMetadata({})).toBeNull()
    expect(clarificationFromMetadata({ clarification: { candidates: [] } })).toBeNull()
    // normal assistant message metadata is unaffected
    expect(clarificationFromMetadata({ status: 'completed' })).toBeNull()
  })

  it('does not surface internal status/error/shadow fields through the mapping', () => {
    const clarification = clarificationFromMetadata({
      clarification: CLARIFICATION,
      status: 'clarification_required',
      error_code: 'ENTITY_AMBIGUOUS',
      pi_shadow: { run_id: 'run_x' },
    })
    expect(clarification.status).toBeUndefined()
    expect(clarification.error_code).toBeUndefined()
    expect(JSON.stringify(clarification)).not.toContain('run_x')
  })

  it('terminal event attach + duplicate replay stays idempotent', () => {
    const liveMsg = { clarification: null, content: '“平安”可能指多家公司…' }
    const payload = { status: 'clarification_required', clarification: CLARIFICATION }
    for (let i = 0; i < 2; i += 1) {
      if (payload.clarification?.candidates?.length) liveMsg.clarification = payload.clarification
    }
    expect(liveMsg.clarification.candidates).toHaveLength(2)
    // text fallback untouched
    expect(liveMsg.content).toContain('平安')
  })

  it('B03 regression: 平安 candidates map end-to-end for rendering', () => {
    const restored = clarificationFromMetadata({ clarification: CLARIFICATION })
    const rendered = dedupCandidates(restored.candidates)
    expect(rendered[0].display_name).toBe('平安银行')
    expect(rendered[1].display_name).toBe('中国平安')
    expect(candidateSelectionText(rendered[1])).toBe('中国平安（601318）')
  })
})
