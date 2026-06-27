/**
 * C28 — DeepSeek Reasoning Content + Agent Step Thinking.
 *
 * Tests for:
 *   C28.5  chatEventNormalizer: structured thinking → ui_thinking_item vs raw → ui_thinking_delta
 *   C28.5  chatReducer: ui_thinking_item handling + thinkingItems array + backward compat
 */
import { describe, it, expect } from 'vitest'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'
import { applyChatUiEvent } from '../utils/chatReducer.js'

// ── Helper ───────────────────────────────────────────────────────────────────

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

// ── C28.5: normalizeChatEvent — structured vs raw thinking ───────────────────

describe('normalizeChatEvent — C28 thinking routing', () => {

  it('raw thinking (no source) → ui_thinking_delta', () => {
    const ev = normalizeChatEvent('thinking', { content: '推理内容…' })
    expect(ev).not.toBeNull()
    expect(ev.type).toBe('ui_thinking_delta')
    expect(ev.content).toBe('推理内容…')
  })

  it('structured thinking with source → ui_thinking_item', () => {
    const ev = normalizeChatEvent('thinking', {
      content:    '检查数据质量：高。数据完整。',
      source:     'data_quality_review',
      stage:      'data_quality',
      title:      '检查数据质量',
      importance: 'medium',
    })
    expect(ev).not.toBeNull()
    expect(ev.type).toBe('ui_thinking_item')
    expect(ev.source).toBe('data_quality_review')
    expect(ev.stage).toBe('data_quality')
    expect(ev.title).toBe('检查数据质量')
    expect(ev.content).toBe('检查数据质量：高。数据完整。')
    expect(ev.importance).toBe('medium')
  })

  it('deepseek_reasoning source → ui_thinking_item', () => {
    const ev = normalizeChatEvent('thinking', {
      content: '让我分析茅台的财务状况。',
      source:  'deepseek_reasoning',
    })
    expect(ev.type).toBe('ui_thinking_item')
    expect(ev.source).toBe('deepseek_reasoning')
  })

  it('agent_step source → ui_thinking_item', () => {
    const ev = normalizeChatEvent('thinking', {
      content:    '将使用技能处理此问题',
      source:     'agent_step',
      stage:      'skill_routing',
      title:      '分析步骤',
      importance: 'low',
    })
    expect(ev.type).toBe('ui_thinking_item')
    expect(ev.importance).toBe('low')
  })

  it('tool_planning source → ui_thinking_item', () => {
    const ev = normalizeChatEvent('thinking', {
      content: '规划数据检索',
      source:  'tool_planning',
      title:   '规划数据检索',
    })
    expect(ev.type).toBe('ui_thinking_item')
    expect(ev.source).toBe('tool_planning')
    expect(ev.title).toBe('规划数据检索')
  })

  it('risk_review source → ui_thinking_item', () => {
    const ev = normalizeChatEvent('thinking', {
      content: '未发现高风险表述，合规审查通过。',
      source:  'risk_review',
      title:   '风险审查',
    })
    expect(ev.type).toBe('ui_thinking_item')
    expect(ev.source).toBe('risk_review')
  })

  it('synthesis source → ui_thinking_item', () => {
    const ev = normalizeChatEvent('thinking', {
      content: '将基于已验证数据生成最终回答。',
      source:  'synthesis',
      title:   '生成回答',
    })
    expect(ev.type).toBe('ui_thinking_item')
    expect(ev.source).toBe('synthesis')
  })

  it('missing content defaults to empty string', () => {
    const ev = normalizeChatEvent('thinking', { source: 'agent_step' })
    expect(ev.type).toBe('ui_thinking_item')
    expect(ev.content).toBe('')
  })

  it('missing importance defaults to medium', () => {
    const ev = normalizeChatEvent('thinking', { source: 'risk_review', content: 'ok' })
    expect(ev.importance).toBe('medium')
  })

  it('missing stage defaults to empty string', () => {
    const ev = normalizeChatEvent('thinking', { source: 'synthesis', content: 'ok' })
    expect(ev.stage).toBe('')
  })

  it('empty payload → raw thinking (no source)', () => {
    const ev = normalizeChatEvent('thinking', {})
    expect(ev.type).toBe('ui_thinking_delta')
    expect(ev.content).toBe('')
  })
})

// ── C28.5: chatReducer — ui_thinking_item ────────────────────────────────────

describe('applyChatUiEvent — ui_thinking_item', () => {

  it('pushes item into thinkingItems array', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type:       'ui_thinking_item',
      source:     'data_quality_review',
      stage:      'data_quality',
      title:      '检查数据质量',
      content:    '数据质量：高。数据完整。',
      importance: 'medium',
    })
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].source).toBe('data_quality_review')
    expect(msg.thinkingItems[0].title).toBe('检查数据质量')
    expect(msg.thinkingItems[0].content).toBe('数据质量：高。数据完整。')
    expect(msg.thinkingItems[0].importance).toBe('medium')
    expect(typeof msg.thinkingItems[0].timestamp).toBe('number')
  })

  it('accumulates multiple thinking items', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_thinking_item', source: 'tool_planning',   content: 'p1', title: '', stage: '', importance: 'medium' })
    applyChatUiEvent(msg, { type: 'ui_thinking_item', source: 'data_quality_review', content: 'p2', title: '', stage: '', importance: 'medium' })
    applyChatUiEvent(msg, { type: 'ui_thinking_item', source: 'risk_review',     content: 'p3', title: '', stage: '', importance: 'medium' })
    applyChatUiEvent(msg, { type: 'ui_thinking_item', source: 'synthesis',       content: 'p4', title: '', stage: '', importance: 'low' })
    expect(msg.thinkingItems).toHaveLength(4)
    expect(msg.thinkingItems.map(i => i.source)).toEqual([
      'tool_planning', 'data_quality_review', 'risk_review', 'synthesis',
    ])
  })

  it('deepseek_reasoning also feeds thinkingContent (backward compat)', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type:       'ui_thinking_item',
      source:     'deepseek_reasoning',
      content:    '推理内容A',
      title:      '',
      stage:      '',
      importance: 'medium',
    })
    // goes into thinkingItems
    expect(msg.thinkingItems).toHaveLength(1)
    // AND into thinkingContent for legacy panel
    expect(msg.thinkingContent).toBe('推理内容A')
  })

  it('deepseek_reasoning accumulates thinkingContent across multiple chunks', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_thinking_item', source: 'deepseek_reasoning', content: 'chunk1', title: '', stage: '', importance: 'medium' })
    applyChatUiEvent(msg, { type: 'ui_thinking_item', source: 'deepseek_reasoning', content: 'chunk2', title: '', stage: '', importance: 'medium' })
    expect(msg.thinkingContent).toBe('chunk1chunk2')
    expect(msg.thinkingItems).toHaveLength(2)
  })

  it('non-deepseek sources do NOT feed thinkingContent', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_thinking_item', source: 'risk_review', content: '审查通过', title: '', stage: '', importance: 'medium' })
    expect(msg.thinkingContent).toBe('')
    expect(msg.thinkingItems).toHaveLength(1)
  })

  it('auto-initializes thinkingItems if not present on msg', () => {
    const msg = makeMsg()
    delete msg.thinkingItems
    applyChatUiEvent(msg, { type: 'ui_thinking_item', source: 'synthesis', content: 'ok', title: '', stage: '', importance: 'low' })
    expect(Array.isArray(msg.thinkingItems)).toBe(true)
    expect(msg.thinkingItems).toHaveLength(1)
  })

  it('does not interfere with toolTrace or reasoningSteps', () => {
    const msg = makeMsg()
    // Add a tool step first
    applyChatUiEvent(msg, {
      type: 'ui_tool_start',
      stepKey: 'tool:stock_quote',
      title: '查询行情',
      status: 'running',
    })
    applyChatUiEvent(msg, {
      type: 'ui_thinking_item',
      source: 'tool_planning',
      content: '计划中',
      title: '', stage: '', importance: 'medium',
    })
    expect(msg.toolTrace).toHaveLength(1)
    expect(msg.thinkingItems).toHaveLength(1)
  })

  it('handles empty content gracefully', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_thinking_item', source: 'agent_step', content: '', title: '', stage: '', importance: 'medium',
    })
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].content).toBe('')
    // No thinkingContent added for agent_step
    expect(msg.thinkingContent).toBe('')
  })
})

// ── C28.5: backward compat — raw ui_thinking_delta still works ───────────────

describe('chatReducer backward compat — ui_thinking_delta', () => {
  it('raw delta still accumulates into thinkingContent', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_thinking_delta', content: 'chunk1' })
    applyChatUiEvent(msg, { type: 'ui_thinking_delta', content: ' chunk2' })
    expect(msg.thinkingContent).toBe('chunk1 chunk2')
    // thinkingItems not touched
    expect(msg.thinkingItems ?? []).toHaveLength(0)
  })

  it('mixing delta and item events is safe', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_thinking_delta', content: 'raw' })
    applyChatUiEvent(msg, {
      type: 'ui_thinking_item', source: 'risk_review', content: '审查',
      title: '', stage: '', importance: 'medium',
    })
    expect(msg.thinkingContent).toBe('raw')
    expect(msg.thinkingItems).toHaveLength(1)
  })
})
