/**
 * C28.4 Final Browser Acceptance Patch — frontend tests.
 *
 * T1–T3: "技能：unknown" must not appear.
 * T4–T6: final_answer.data_quality forcefully clears ALL stale dq thinking items.
 */
import { describe, it, expect } from 'vitest'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'
import { applyChatUiEvent } from '../utils/chatReducer.js'

// ---------------------------------------------------------------------------
// Problem 1 — "技能：unknown" must never reach the UI
// ---------------------------------------------------------------------------

describe('chatEventNormalizer — unknown skill name guard (T1–T3)', () => {
  it('T1: skill_started with name="unknown" → title is "技能路由", detail has no "unknown"', () => {
    const ev = normalizeChatEvent('skill_started', { skill_name: 'unknown' })
    expect(ev.type).toBe('ui_tool_start')
    expect(ev.title).toBe('技能路由')
    expect(ev.title).not.toContain('unknown')
    expect(ev.detail).not.toBe('unknown')
    expect(ev.detail).not.toContain('unknown')
  })

  it('T2: skill_started with no skill_name → "技能路由" (no undefined/unknown in output)', () => {
    const ev = normalizeChatEvent('skill_started', {})  // no skill_name
    expect(ev.type).toBe('ui_tool_start')
    expect(ev.title).toBe('技能路由')
    expect(ev.title).not.toContain('undefined')
    expect(ev.detail).not.toContain('undefined')
    expect(ev.detail).not.toContain('unknown')
  })

  it('T3: normal skills still show Chinese display names', () => {
    const cases = [
      ['general_financial_answer_skill', '智能问答'],
      ['report_explanation_skill',       '报告解读'],
      ['analysis_run_skill',             'AI研报生成'],
    ]
    for (const [name, expected] of cases) {
      const ev = normalizeChatEvent('skill_started', { skill_name: name })
      expect(ev.title).toBe(`技能：${expected}`)
      expect(ev.detail).toBe(expected)
    }
  })

  it('skill_completed with name="unknown" → summary "已完成", not "unknown"', () => {
    const ev = normalizeChatEvent('skill_completed', { skill_name: 'unknown' })
    expect(ev.summary).toBe('已完成')
    expect(ev.summary).not.toBe('unknown')
    expect(ev.title).toBe('技能路由')
  })

  it('skill_completed with no skill_name → "已完成"', () => {
    const ev = normalizeChatEvent('skill_completed', {})
    expect(ev.summary).toBe('已完成')
    expect(ev.title).toBe('技能路由')
  })

  it('unknown skill name stored in stepKey but not displayed', () => {
    const ev = normalizeChatEvent('skill_started', { skill_name: 'unknown' })
    // stepKey used for dedup — may contain 'skill' (generic key)
    // title and detail must be safe
    expect(ev.title).not.toContain('unknown')
    expect(ev.detail).not.toContain('unknown')
  })
})

// ---------------------------------------------------------------------------
// Problem 2 — final_answer.data_quality replaces ALL stale dq thinking items
// ---------------------------------------------------------------------------

describe('chatReducer — broad data_quality thinking override (T4–T6)', () => {
  function makeMsg() {
    return {
      thinkingItems: [],
      finalAnswer:   null,
      answerContent: '',
      content:       '',
    }
  }

  it('T4: stale high-level thinking replaced by final_answer.data_quality=low', () => {
    const msg = makeMsg()

    // Stale optimistic item
    applyChatUiEvent(msg, {
      type:       'ui_thinking_item',
      source:     'data_quality_review',
      stage:      'data_quality',
      title:      '检查数据质量',
      content:    '数据质量：数据完整。已获取多维度数据，信息完整度高。',
      importance: 'medium',
    })
    expect(msg.thinkingItems[0].content).toContain('数据完整')

    // Final answer with level=low
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low', reason: '仅行情数据' } },
    })

    // T4: only 1 item, content says "数据有限"
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].content).toContain('数据有限')
    expect(msg.thinkingItems[0].content).not.toContain('数据完整')
  })

  it('T5: stale item with different stage/source is also cleared', () => {
    const msg = makeMsg()

    // Old item: stage doesn't match exactly
    msg.thinkingItems.push({
      source:     'agent_step',         // different source
      stage:      'data_quality_check', // different stage value
      title:      '检查数据质量',        // title matches heuristic c
      content:    '数据质量：数据完整。',
      importance: 'medium',
      timestamp:  Date.now(),
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    // Stale item should be gone (matched by title heuristic)
    const remaining = msg.thinkingItems.filter(t => t.content?.includes('数据完整'))
    expect(remaining).toHaveLength(0)
    // Final low item should be there
    expect(msg.thinkingItems.some(t => t.content?.includes('数据有限'))).toBe(true)
  })

  it('T5b: stale item matched by content prefix "数据质量：" is cleared', () => {
    const msg = makeMsg()

    // Old item: content starts with "数据质量："
    msg.thinkingItems.push({
      source:     'synthesis',
      stage:      'something_else',
      title:      '合成',
      content:    '数据质量：数据完整。已获取多维度数据。',
      importance: 'medium',
      timestamp:  Date.now(),
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'insufficient' } },
    })

    expect(msg.thinkingItems.some(t => t.content?.includes('数据完整'))).toBe(false)
    expect(msg.thinkingItems.some(t => t.content?.includes('数据不足'))).toBe(true)
  })

  it('T6: DataQualityCard level=low → thinking says "数据有限"', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: {
        data_quality: {
          level:         'low',
          reason:        '仅获取到行情或新闻数据',
          verified_data: ['实时行情'],
          missing_data:  ['财务数据'],
        },
      },
    })
    const dqItem = msg.thinkingItems.find(t => t.source === 'data_quality_review')
    expect(dqItem).toBeTruthy()
    expect(dqItem.content).toContain('数据有限')
    // Card and thinking text are consistent
    expect(dqItem.content).not.toContain('数据完整')
    expect(dqItem.content).not.toContain('数据部分完整')
    expect(dqItem.content).not.toContain('数据不足')
  })

  it('non-dq thinking items are preserved after final_answer override', () => {
    const msg = makeMsg()

    // Non-dq item should survive
    msg.thinkingItems.push({
      source:     'risk_review',
      stage:      'risk_review',
      title:      '风险审查',
      content:    '未发现高风险表述。',
      importance: 'medium',
      timestamp:  Date.now(),
    })
    // Stale dq item
    msg.thinkingItems.push({
      source:     'data_quality_review',
      stage:      'data_quality',
      title:      '检查数据质量',
      content:    '数据质量：数据完整。',
      importance: 'medium',
      timestamp:  Date.now(),
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'medium' } },
    })

    // risk_review item preserved
    expect(msg.thinkingItems.some(t => t.source === 'risk_review')).toBe(true)
    // data_quality updated
    const dq = msg.thinkingItems.find(t => t.source === 'data_quality_review')
    expect(dq?.content).toContain('数据部分完整')
    expect(dq?.content).not.toContain('数据完整。')
  })
})
