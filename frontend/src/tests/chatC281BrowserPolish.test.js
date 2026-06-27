/**
 * C28.1 Browser Polish — frontend Vitest tests T1-T3.
 *
 * T1: ui_thinking_delta does not set message.content
 * T2: deepseek_reasoning ui_thinking_item does not set finalAnswer
 * T3: full_text in ui_final_answer replaces answerContent in message.content
 */
import { describe, it, expect } from 'vitest'
import { applyChatUiEvent } from '../utils/chatReducer.js'

// ── Helper ────────────────────────────────────────────────────────────────────

function makeMsg(overrides = {}) {
  return {
    reasoningSteps:  [],
    toolTrace:       [],
    thinkingContent: '',
    thinkingItems:   [],
    answerContent:   '',
    content:         '',
    finalAnswer:     null,
    agentTrace:      [],
    status:          'streaming',
    isStreaming:     true,
    error:           null,
    ...overrides,
  }
}

// ── T1: ui_thinking_delta does NOT touch message.content ─────────────────────

describe('T1 — ui_thinking_delta does not set message.content', () => {
  it('thinking delta only updates thinkingContent, not content', () => {
    const msg = makeMsg({ content: '' })
    applyChatUiEvent(msg, { type: 'ui_thinking_delta', content: '推理：分析茅台基本面...' })
    // content should remain empty — reasoning must not leak to display
    expect(msg.content).toBe('')
    // thinkingContent should be set
    expect(msg.thinkingContent).toBe('推理：分析茅台基本面...')
  })

  it('multiple thinking deltas accumulate in thinkingContent, not content', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_thinking_delta', content: 'chunk1' })
    applyChatUiEvent(msg, { type: 'ui_thinking_delta', content: ' chunk2' })
    expect(msg.thinkingContent).toBe('chunk1 chunk2')
    expect(msg.content).toBe('')
    expect(msg.answerContent).toBe('')
  })
})

// ── T2: deepseek_reasoning ui_thinking_item does NOT set finalAnswer ──────────

describe('T2 — deepseek_reasoning ui_thinking_item does not set finalAnswer', () => {
  it('deepseek_reasoning item goes to thinkingItems/thinkingContent, not finalAnswer', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type:       'ui_thinking_item',
      source:     'deepseek_reasoning',
      content:    '让我深入分析茅台的财务数据。',
      title:      '',
      stage:      '',
      importance: 'medium',
    })
    // finalAnswer must remain null
    expect(msg.finalAnswer).toBeNull()
    // thinkingItems gets the entry
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].source).toBe('deepseek_reasoning')
    // thinkingContent also updated (backward compat)
    expect(msg.thinkingContent).toBe('让我深入分析茅台的财务数据。')
    // content must NOT be set from reasoning
    expect(msg.content).toBe('')
  })

  it('deepseek_reasoning does not affect answerContent', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type:    'ui_thinking_item',
      source:  'deepseek_reasoning',
      content: '推理过程中...',
      title: '', stage: '', importance: 'medium',
    })
    expect(msg.answerContent).toBe('')
  })
})

// ── T3: full_text in ui_final_answer replaces answerContent in message.content ─

describe('T3 — full_text in ui_final_answer sets answerContent and content', () => {
  it('full_text is set as both answerContent and content', () => {
    const msg = makeMsg()
    const fullText = '### 研究摘要\n\n茅台是A股白酒龙头，基本面稳健。\n\n### 风险提示\n\n注意行业估值偏高。'
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: {
        full_text: fullText,
        summary:   '茅台基本面稳健',
        analysis:  '详细分析内容',
        disclaimer: '仅供研究参考',
      },
    })
    expect(msg.content).toBe(fullText)
    expect(msg.answerContent).toBe(fullText)
    expect(msg.finalAnswer).not.toBeNull()
  })

  it('without full_text, falls back to summary+analysis join', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: {
        summary:  '茅台摘要',
        analysis: '茅台分析',
      },
    })
    expect(msg.content).toBe('茅台摘要\n\n茅台分析')
    // answerContent not set in fallback path
    expect(msg.answerContent).toBe('')
  })

  it('full_text overrides previously streamed answerContent', () => {
    // Simulate: streaming gave partial content, then full_text arrives with clean version
    const msg = makeMsg({ answerContent: '好的，以下是分析结果...\n\n### 研究摘要', content: '好的，以下是分析结果...\n\n### 研究摘要' })
    const cleanText = '### 研究摘要\n\n茅台基本面稳健。'
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: {
        full_text: cleanText,
        summary:   '茅台基本面稳健',
      },
    })
    // full_text wins — preamble stripped
    expect(msg.content).toBe(cleanText)
    expect(msg.answerContent).toBe(cleanText)
  })

  it('when no full_text and answerContent already present, keeps existing content', () => {
    // Streaming path: answerContent already accumulated via answer_delta
    const existingContent = '### 研究摘要\n\n来自流式传输的内容。'
    const msg = makeMsg({ answerContent: existingContent, content: existingContent })
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: {
        summary:   '摘要',
        analysis:  '分析',
        disclaimer: '仅供参考',
      },
    })
    // No full_text AND answerContent is set → content stays as-is
    expect(msg.content).toBe(existingContent)
    expect(msg.answerContent).toBe(existingContent)
  })
})
