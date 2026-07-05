/**
 * C30.5 Browser Acceptance Fixes — frontend tests.
 *
 * T1–T5   (C30.5.1): Report success error clearing — chatReducer ui_done + pollRunTick
 * T6–T10  (C30.5.2): Compare page dedup — StockCompareView _parseTokens
 * T11–T15 (C30.5.3): StockMiniTrend querySelector bug fix → containerRef
 * T16–T22 (C30.5.4): ChatInputBox IME Enter key fix
 * T23–T29 (C30.5.5): onEditUser removes messages after edited user message
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'
import { applyChatUiEvent } from '../utils/chatReducer.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '../../')

function readSrc(relPath) {
  return readFileSync(path.join(ROOT, relPath), 'utf-8')
}

function freshMessage(overrides = {}) {
  return {
    reasoningSteps:  [],
    toolTrace:       [],
    thinkingContent: '',
    thinkingEvents:  [],
    thinkingItems:   [],
    answerContent:   '',
    content:         '',
    finalAnswer:     null,
    agentTrace:      [],
    status:          'connecting',
    isStreaming:     true,
    error:           null,
    resultCard:      null,
    ...overrides,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// T1–T5: C30.5.1 — ui_done clears transient error when analysis_run completed
// ─────────────────────────────────────────────────────────────────────────────

describe('C30.5.1 — Report success error clearing (chatReducer)', () => {

  it('T1: ui_done clears message.error when analysis_run card has queued status', () => {
    const msg = freshMessage({
      error: '分析启动失败，请稍后重试',
      resultCard: { type: 'analysis_run', data: { status: 'queued', name: '测试股票', links: [] } },
    })
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.status).toBe('done')
    expect(msg.error).toBeNull()
  })

  it('T2: ui_done clears message.error when analysis_run card has running status', () => {
    const msg = freshMessage({
      error: 'agent_error occurred mid-stream',
      resultCard: { type: 'analysis_run', data: { status: 'running', name: '平安银行', links: [] } },
    })
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.error).toBeNull()
  })

  it('T3: ui_done does NOT clear error when analysis_run card has failed status', () => {
    const msg = freshMessage({
      error: '分析失败',
      resultCard: { type: 'analysis_run', data: { status: 'failed', name: '平安银行', links: [] } },
    })
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.error).toBe('分析失败')
  })

  it('T4: ui_done does NOT clear error when resultCard is absent (generic error)', () => {
    const msg = freshMessage({ error: '网络错误', resultCard: null })
    applyChatUiEvent(msg, { type: 'ui_done' })
    // Generic errors unrelated to analysis_run should not be silently cleared
    expect(msg.error).toBe('网络错误')
  })

  it('T5: ui_done does NOT clear error when resultCard type is not analysis_run', () => {
    const msg = freshMessage({
      error: '某种错误',
      resultCard: { type: 'watchlist_update', data: {} },
    })
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.error).toBe('某种错误')
  })

  it('T5b: ChatCopilotView _pollRunTick clears error on completed status', () => {
    // Source inspection: confirm the fix is present
    const src = readSrc('src/views/ChatCopilotView.vue')
    // Must clear liveMsg.error when snap.status === 'completed'
    expect(src).toContain('liveMsg.error = null')
    // Must also reset status from error to done
    expect(src).toContain("liveMsg.status = 'done'")
    // Guard must be inside the completed branch
    const completedIdx = src.indexOf("snap.status === 'completed'")
    const errorClearIdx = src.indexOf('liveMsg.error = null')
    expect(completedIdx).toBeGreaterThan(-1)
    expect(errorClearIdx).toBeGreaterThan(completedIdx)
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T6–T10: C30.5.2 — Compare page _parseTokens dedup
// ─────────────────────────────────────────────────────────────────────────────

// Mirror _parseTokens logic from StockCompareView.vue for pure-logic tests
function _parseTokens(stocksParam) {
  const seen = new Set()
  return String(stocksParam)
    .split(',')
    .map(t => t.trim())
    .filter(Boolean)
    .map(t => {
      const colonIdx = t.indexOf(':')
      if (colonIdx < 1) return null
      const market = t.slice(0, colonIdx).toUpperCase()
      const symbol = t.slice(colonIdx + 1).trim()
      if (!symbol) return null
      if (!['CN', 'HK'].includes(market)) return null
      return { market, symbol, name: '' }
    })
    .filter(Boolean)
    .filter(s => {
      const key = `${s.market}:${s.symbol}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, 4)
}

describe('C30.5.2 — Compare page _parseTokens dedup', () => {

  it('T6: StockCompareView source contains dedup Set logic', () => {
    const src = readSrc('src/views/StockCompareView.vue')
    // Must have a Set for deduplication
    expect(src).toContain('new Set()')
    // Must filter using the Set
    expect(src).toContain('seen.has(key)')
    expect(src).toContain('seen.add(key)')
  })

  it('T7: duplicate market:symbol tokens are deduplicated', () => {
    const result = _parseTokens('CN:300750,CN:300750')
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({ market: 'CN', symbol: '300750' })
  })

  it('T8: 4 unique stocks are all preserved (no over-dedup)', () => {
    const result = _parseTokens('CN:300750,CN:600519,HK:00700,CN:000001')
    expect(result).toHaveLength(4)
    const symbols = result.map(s => s.symbol)
    expect(symbols).toContain('300750')
    expect(symbols).toContain('600519')
    expect(symbols).toContain('00700')
    expect(symbols).toContain('000001')
  })

  it('T9: 5 tokens with one dup → 4 unique after dedup+slice', () => {
    // CN:300750 appears twice; after dedup = 4 unique; slice(0,4) keeps all 4
    const result = _parseTokens('CN:300750,CN:600519,HK:00700,CN:000001,CN:300750')
    expect(result).toHaveLength(4)
  })

  it('T10: all-same token → only 1 result', () => {
    const result = _parseTokens('CN:300750,CN:300750,CN:300750,CN:300750')
    expect(result).toHaveLength(1)
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T11–T15: C30.5.3 — StockMiniTrend querySelector fix
// ─────────────────────────────────────────────────────────────────────────────

describe('C30.5.3 — StockMiniTrend containerRef fix', () => {

  it('T11: StockMiniTrend does NOT use document.querySelector globally', () => {
    const src = readSrc('src/components/StockMiniTrend.vue')
    // The global querySelector bug must be removed
    expect(src).not.toContain("document.querySelector('.smt-wrap')")
  })

  it('T12: StockMiniTrend uses containerRef.value for the ResizeObserver target', () => {
    const src = readSrc('src/components/StockMiniTrend.vue')
    expect(src).toContain('containerRef.value')
  })

  it('T13: StockMiniTrend template attaches ref="containerRef" to the wrapper div', () => {
    const src = readSrc('src/components/StockMiniTrend.vue')
    // The .smt-wrap div must have the ref attribute
    expect(src).toMatch(/class="smt-wrap"[^>]*ref="containerRef"|ref="containerRef"[^>]*class="smt-wrap"/)
  })

  it('T14: StockMiniTrend declares containerRef = ref(null)', () => {
    const src = readSrc('src/components/StockMiniTrend.vue')
    expect(src).toContain('containerRef')
    expect(src).toContain('ref(null)')
  })

  it('T15: StockMiniTrend still contains ResizeObserver wiring (not accidentally removed)', () => {
    const src = readSrc('src/components/StockMiniTrend.vue')
    expect(src).toContain('ResizeObserver')
    expect(src).toContain('ro.observe(el)')
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T16–T22: C30.5.4 — ChatInputBox IME Enter key fix
// ─────────────────────────────────────────────────────────────────────────────

describe('C30.5.4 — ChatInputBox IME composition guard', () => {

  it('T16: ChatInputBox template has @compositionstart handler', () => {
    const src = readSrc('src/components/chat/ChatInputBox.vue')
    expect(src).toContain('@compositionstart')
  })

  it('T17: ChatInputBox template has @compositionend handler', () => {
    const src = readSrc('src/components/chat/ChatInputBox.vue')
    expect(src).toContain('@compositionend')
  })

  it('T18: ChatInputBox declares isComposing ref', () => {
    const src = readSrc('src/components/chat/ChatInputBox.vue')
    expect(src).toContain('isComposing')
    expect(src).toContain('ref(false)')
  })

  it('T19: ChatInputBox onEnter checks isComposing before sending', () => {
    const src = readSrc('src/components/chat/ChatInputBox.vue')
    // Guard must mention both the local ref and event.isComposing
    expect(src).toContain('isComposing.value')
    expect(src).toContain('event?.isComposing')
  })

  it('T20: ChatInputBox does NOT use the old .prevent modifier on enter keydown', () => {
    const src = readSrc('src/components/chat/ChatInputBox.vue')
    // The .prevent modifier caused IME issues — must be removed from the template attr
    expect(src).not.toContain('@keydown.enter.exact.prevent')
  })

  it('T21: ChatInputBox keeps the .exact modifier on Enter (Shift+Enter unaffected)', () => {
    const src = readSrc('src/components/chat/ChatInputBox.vue')
    expect(src).toContain('@keydown.enter.exact')
  })

  it('T22: onEnter pure logic returns early when event.isComposing is true', () => {
    // Simulate the guard logic inline
    let sent = false
    const isComposing = { value: false }
    const canSend = { value: true }

    function simulateOnEnter(eventIsComposing) {
      if (isComposing.value || eventIsComposing) return
      if (canSend.value) sent = true
    }

    // composing — should NOT send
    sent = false
    simulateOnEnter(true)
    expect(sent).toBe(false)

    // not composing — should send
    sent = false
    simulateOnEnter(false)
    expect(sent).toBe(true)

    // local ref composing — should NOT send
    sent = false
    isComposing.value = true
    simulateOnEnter(false)
    expect(sent).toBe(false)
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T23–T29: C30.5.5 — onEditUser removes messages after edited user message
// ─────────────────────────────────────────────────────────────────────────────

describe('C30.5.5 — onEditUser removes stale messages', () => {

  it('T23: ChatCopilotView onEditUser uses findIndex to locate edited message', () => {
    const src = readSrc('src/views/ChatCopilotView.vue')
    const editFnIdx = src.indexOf('function onEditUser')
    const fnBody = src.slice(editFnIdx, editFnIdx + 1500)
    expect(fnBody).toContain('findIndex')
  })

  it('T24: ChatCopilotView onEditUser slices messages array at editIdx', () => {
    const src = readSrc('src/views/ChatCopilotView.vue')
    const editFnIdx = src.indexOf('function onEditUser')
    const fnBody = src.slice(editFnIdx, editFnIdx + 1500)
    expect(fnBody).toContain('slice(0, editIdx)')
  })

  it('T25: ChatCopilotView onEditUser parameter is no longer prefixed _ (is now used)', () => {
    const src = readSrc('src/views/ChatCopilotView.vue')
    // The old signature was: function onEditUser(_msgId, content)
    // After fix, msgId is used
    expect(src).not.toContain('function onEditUser(_msgId')
    expect(src).toContain('function onEditUser(msgId')
  })

  // Pure logic: simulate the messages.value slice behavior
  function simulateOnEditUser(messages, msgId) {
    const editIdx = messages.findIndex(m => m.id === msgId)
    if (editIdx >= 0) {
      return messages.slice(0, editIdx)
    }
    return messages
  }

  it('T26: editing the 2nd user message removes it and the following assistant message', () => {
    const msgs = [
      { id: 'u1', role: 'user',      content: '第一条问题' },
      { id: 'a1', role: 'assistant', content: '第一条回答' },
      { id: 'u2', role: 'user',      content: '第二条问题' },
      { id: 'a2', role: 'assistant', content: '第二条回答' },
    ]
    const result = simulateOnEditUser(msgs, 'u2')
    expect(result).toHaveLength(2)
    expect(result[0].id).toBe('u1')
    expect(result[1].id).toBe('a1')
  })

  it('T27: editing the 1st user message results in an empty messages array', () => {
    const msgs = [
      { id: 'u1', role: 'user',      content: '第一条问题' },
      { id: 'a1', role: 'assistant', content: '第一条回答' },
    ]
    const result = simulateOnEditUser(msgs, 'u1')
    expect(result).toHaveLength(0)
  })

  it('T28: messages before edited user message are preserved intact', () => {
    const msgs = [
      { id: 'u1', role: 'user',      content: 'q1' },
      { id: 'a1', role: 'assistant', content: 'a1' },
      { id: 'u2', role: 'user',      content: 'q2' },
      { id: 'a2', role: 'assistant', content: 'a2' },
      { id: 'u3', role: 'user',      content: 'q3' },
    ]
    const result = simulateOnEditUser(msgs, 'u3')
    expect(result).toHaveLength(4)
    expect(result.map(m => m.id)).toEqual(['u1', 'a1', 'u2', 'a2'])
  })

  it('T29: onEditUser handles unknown msgId gracefully (no truncation)', () => {
    const msgs = [
      { id: 'u1', role: 'user',      content: 'q1' },
      { id: 'a1', role: 'assistant', content: 'a1' },
    ]
    const result = simulateOnEditUser(msgs, 'non-existent-id')
    // Messages unchanged when id not found
    expect(result).toHaveLength(2)
  })

})
