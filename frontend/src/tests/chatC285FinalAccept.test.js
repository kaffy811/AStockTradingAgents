/**
 * C28.5 Final Safety/DataQuality Cut-through Patch — frontend tests.
 *
 * T10–T13: broader thinkingItems filter clears ALL stale dq items by content keywords.
 */
import { describe, it, expect } from 'vitest'
import { applyChatUiEvent } from '../utils/chatReducer.js'

function makeMsg() {
  return {
    thinkingItems: [],
    finalAnswer:   null,
    answerContent: '',
    content:       '',
  }
}

describe('chatReducer — C28.5 broad dq thinking content filter (T10–T13)', () => {

  it('T10: stale item with content="数据质量：数据完整…" replaced when final_answer.dq=low', () => {
    const msg = makeMsg()

    // Stale item — exactly the "high" DQ text
    msg.thinkingItems.push({
      source:  'data_quality_review',
      stage:   'data_quality',
      title:   '检查数据质量',
      content: '数据质量：数据完整。已获取多维度数据，信息完整度高。',
      importance: 'medium',
      timestamp: Date.now(),
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    expect(msg.thinkingItems.some(t => t.content?.includes('数据完整'))).toBe(false)
    expect(msg.thinkingItems.some(t => t.content?.includes('数据有限'))).toBe(true)
  })

  it('T11: final item content matches "数据有限" text for level=low', () => {
    const msg = makeMsg()

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low', reason: '仅行情数据' } },
    })

    const dqItem = msg.thinkingItems.find(t => t.source === 'data_quality_review')
    expect(dqItem).toBeTruthy()
    expect(dqItem.content).toContain('数据有限')
    expect(dqItem.content).not.toContain('数据完整')
    expect(dqItem.content).not.toContain('数据不足')
    expect(dqItem.content).not.toContain('数据部分完整')
  })

  it('T12: stale item matched only by content keyword "数据完整" (no standard source/stage) is also cleared', () => {
    const msg = makeMsg()

    // Item with non-standard source/stage but contains "数据完整" in content
    msg.thinkingItems.push({
      source:  'synthesis',
      stage:   'pre_answer',
      title:   '综合判断',
      content: '已获取多维度数据，数据完整，信息质量高。',
      importance: 'medium',
      timestamp: Date.now(),
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    expect(msg.thinkingItems.some(t => t.content?.includes('数据完整'))).toBe(false)
  })

  it('T13: DataQualityCard level and thinking item content are consistent (medium → 数据部分完整)', () => {
    const msg = makeMsg()

    // Stale "high" item
    msg.thinkingItems.push({
      source:  'data_quality_review',
      stage:   'data_quality',
      title:   '检查数据质量',
      content: '数据质量：数据完整。已获取多维度数据，信息完整度高。',
      importance: 'medium',
      timestamp: Date.now(),
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'medium' } },
    })

    const dq = msg.thinkingItems.find(t => t.source === 'data_quality_review')
    // Card would show "中" / "部分完整" — thinking must agree
    expect(dq?.content).toContain('数据部分完整')
    expect(dq?.content).not.toContain('数据完整。')  // old "high" text
    expect(dq?.content).not.toContain('数据有限')
    expect(dq?.content).not.toContain('数据不足')
  })

  it('non-dq items with "数据完整" in content are also cleared (broad filter)', () => {
    const msg = makeMsg()

    msg.thinkingItems.push({
      source:  'agent_step',
      stage:   'market_analysis',
      title:   '行情分析',
      content: '行情数据完整，已获取K线及实时报价。',  // "数据完整" as substring
      importance: 'medium',
      timestamp: Date.now(),
    })
    // non-dq item without "数据完整" — must survive
    msg.thinkingItems.push({
      source:  'risk_review',
      stage:   'risk_review',
      title:   '风险审查',
      content: '未发现高风险表述。',
      importance: 'medium',
      timestamp: Date.now(),
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    // risk_review item should survive
    expect(msg.thinkingItems.some(t => t.source === 'risk_review')).toBe(true)
    // item with "数据完整" in content should be gone
    expect(msg.thinkingItems.some(t => t.content?.includes('行情数据完整'))).toBe(false)
  })

  it('数据有限 / 数据不足 / 数据部分完整 keywords also clear stale items', () => {
    const msg = makeMsg()

    // Items with each level keyword that would be stale
    const keywords = ['数据有限', '数据不足', '数据部分完整']
    for (const kw of keywords) {
      msg.thinkingItems.push({
        source:  'something',
        stage:   'something',
        title:   'something',
        content: `数据质量：${kw}，部分数据缺失。`,
        importance: 'medium',
        timestamp: Date.now(),
      })
    }

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'high' } },
    })

    // All three stale items cleared
    for (const kw of keywords) {
      expect(
        msg.thinkingItems.some(t => t.content?.startsWith(`数据质量：${kw}`))
      ).toBe(false)
    }
    // Only the new "high" authoritative item remains
    const dq = msg.thinkingItems.find(t => t.source === 'data_quality_review')
    expect(dq?.content).toContain('数据完整')
  })
})
