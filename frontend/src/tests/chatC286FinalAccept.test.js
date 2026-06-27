/**
 * C28.6 Final DataQuality Sync — frontend tests.
 *
 * T11–T14: ui_final_answer syncs data_quality to thinkingItems,
 *           reasoningSteps, toolTrace, and agentTrace.
 */
import { describe, it, expect } from 'vitest'
import { applyChatUiEvent } from '../utils/chatReducer.js'

function makeMsg() {
  return {
    thinkingItems:  [],
    reasoningSteps: [],
    toolTrace:      [],
    agentTrace:     [],
    finalAnswer:    null,
    answerContent:  '',
    content:        '',
  }
}

describe('chatReducer — C28.6 DataQuality sync to reasoningSteps/toolTrace (T11–T14)', () => {

  it('T11: stale thinkingItems "数据完整" replaced with "数据有限" after dq=low', () => {
    const msg = makeMsg()
    msg.thinkingItems.push({
      source:  'data_quality_review',
      stage:   'data_quality',
      title:   '检查数据质量',
      content: '数据质量：数据完整。已获取多维度数据，信息完整度高。',
      importance: 'medium', timestamp: Date.now(),
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    expect(msg.thinkingItems.some(t => t.content?.includes('数据完整'))).toBe(false)
    expect(msg.thinkingItems.some(t => t.content?.includes('数据有限'))).toBe(true)
  })

  it('T12: stale reasoningStep "检查数据质量/数据完整" overwritten to "数据有限"', () => {
    const msg = makeMsg()
    msg.reasoningSteps.push({
      key:    'dq_check',
      title:  '检查数据质量',
      status: 'success',
      summary: '数据质量：数据完整。已获取多维度数据。',
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    const step = msg.reasoningSteps.find(s => s.key === 'dq_check')
    expect(step?.summary).toContain('数据有限')
    expect(step?.summary).not.toContain('数据完整')
  })

  it('T12b: reasoningStep matched by summary "数据完整" (not title)', () => {
    const msg = makeMsg()
    msg.reasoningSteps.push({
      key:    'misc_step',
      title:  '数据审核',
      status: 'success',
      summary: '数据完整，已完成审核。',
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'medium' } },
    })

    const step = msg.reasoningSteps.find(s => s.key === 'misc_step')
    expect(step?.summary).toContain('数据部分完整')
    expect(step?.summary).not.toContain('数据完整，')
  })

  it('T13: stale toolTrace "资料质量审查/数据完整" overwritten', () => {
    const msg = makeMsg()
    msg.toolTrace.push({
      key:    'tool:rag_review',
      name:   'rag_review',
      title:  '资料质量审查',
      status: 'success',
      summary: '数据质量：数据完整。',
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    const tool = msg.toolTrace.find(t => t.key === 'tool:rag_review')
    expect(tool?.summary).toContain('数据有限')
    expect(tool?.summary).not.toContain('数据完整')
  })

  it('T13b: toolTrace matched by summary "数据有限" (level change to high)', () => {
    const msg = makeMsg()
    msg.toolTrace.push({
      key:    'tool:dq',
      name:   'dq',
      title:  'DataQuality',
      status: 'success',
      summary: '数据有限，仅行情数据。',
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'high' } },
    })

    const tool = msg.toolTrace.find(t => t.key === 'tool:dq')
    expect(tool?.summary).toContain('数据完整')
    expect(tool?.summary).not.toContain('数据有限')
  })

  it('T14: no simultaneous "数据完整" and "数据有限" across all collections', () => {
    const msg = makeMsg()
    // Plant stale items everywhere
    msg.thinkingItems.push({
      source: 'data_quality_review', stage: 'data_quality',
      title: '检查数据质量', content: '数据质量：数据完整。已获取多维度数据，信息完整度高。',
      importance: 'medium', timestamp: Date.now(),
    })
    msg.reasoningSteps.push({
      key: 's1', title: '检查数据质量', status: 'success',
      summary: '数据质量：数据完整。',
    })
    msg.toolTrace.push({
      key: 't1', name: 'dq', title: '资料质量审查', status: 'success',
      summary: '数据完整，高信心。',
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    // Collect all summaries + content across all collections
    const allText = [
      ...msg.thinkingItems.map(t => t.content ?? ''),
      ...msg.reasoningSteps.map(s => s.summary ?? ''),
      ...msg.toolTrace.map(t => t.summary ?? ''),
    ].join(' ')

    const hasComplete = allText.includes('数据完整')
    const hasLimited  = allText.includes('数据有限')

    // Must not show both simultaneously
    expect(hasComplete && hasLimited).toBe(false)
    // "数据有限" should be present (the authoritative level=low text)
    expect(hasLimited).toBe(true)
  })

  it('agentTrace is also synced when dq step matches', () => {
    const msg = makeMsg()
    msg.agentTrace.push({
      type:        'dq',
      name:        'dq_agent',
      displayName: '检查数据质量',
      status:      'success',
      summary:     '数据完整。',
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'insufficient' } },
    })

    const agent = msg.agentTrace.find(a => a.name === 'dq_agent')
    expect(agent?.summary).toContain('数据不足')
    expect(agent?.summary).not.toContain('数据完整')
  })

  it('non-dq reasoningSteps are not touched', () => {
    const msg = makeMsg()
    msg.reasoningSteps.push({
      key: 'risk', title: '风险审核', status: 'success',
      summary: '未发现高风险，审核通过。',
    })
    msg.reasoningSteps.push({
      key: 'dq', title: '检查数据质量', status: 'success',
      summary: '数据质量：数据完整。',
    })

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'low' } },
    })

    const risk = msg.reasoningSteps.find(s => s.key === 'risk')
    expect(risk?.summary).toBe('未发现高风险，审核通过。')

    const dq = msg.reasoningSteps.find(s => s.key === 'dq')
    expect(dq?.summary).toContain('数据有限')
  })
})
