/**
 * C28.3 Final Acceptance Fix — frontend tests.
 *
 * T1–T3: toolTrace must not show internal skill names.
 * T4–T6: final_answer.data_quality syncs data_quality_review thinking item.
 */
import { describe, it, expect } from 'vitest'
import { normalizeChatEvent, SKILL_DISPLAY_NAMES } from '../utils/chatEventNormalizer.js'
import { applyChatUiEvent } from '../utils/chatReducer.js'

// ---------------------------------------------------------------------------
// Problem 1 — skill names never reach UI as snake_case
// ---------------------------------------------------------------------------

describe('chatEventNormalizer — skill name mapping (T1–T3)', () => {
  it('T1: skill_started for general_financial_answer_skill has no snake_case in title/detail', () => {
    const ev = normalizeChatEvent('skill_started', { skill_name: 'general_financial_answer_skill' })
    expect(ev.type).toBe('ui_tool_start')
    expect(ev.title).not.toContain('general_financial_answer_skill')
    expect(ev.detail).not.toContain('general_financial_answer_skill')
    expect(ev.title).toContain('智能问答')
    expect(ev.detail).toBe('智能问答')
  })

  it('T2: skill_completed for report_explanation_skill has no snake_case in summary', () => {
    const ev = normalizeChatEvent('skill_completed', { skill_name: 'report_explanation_skill' })
    expect(ev.type).toBe('ui_tool_done')
    expect(ev.summary).not.toContain('report_explanation_skill')
    expect(ev.summary).toBe('报告解读')
    expect(ev.title).toContain('报告解读')
  })

  it('T3: skill title and summary show Chinese display names', () => {
    const skills = [
      ['general_financial_answer_skill', '智能问答'],
      ['report_explanation_skill',       '报告解读'],
      ['industry_hotspot_skill',         '行业热点分析'],
      ['analysis_run_skill',             'AI研报生成'],
    ]
    for (const [name, expected] of skills) {
      const started = normalizeChatEvent('skill_started', { skill_name: name })
      const done    = normalizeChatEvent('skill_completed', { skill_name: name })
      expect(started.detail).toBe(expected)
      expect(done.summary).toBe(expected)
    }
  })

  it('skill_started stepKey still encodes original skill name for dedup', () => {
    const ev = normalizeChatEvent('skill_started', { skill_name: 'general_financial_answer_skill' })
    // stepKey is used for dedup matching, must still contain the skill key
    expect(ev.stepKey).toBe('tool:skill:general_financial_answer_skill')
  })

  it('unknown skill_name falls back gracefully (no crash)', () => {
    const ev = normalizeChatEvent('skill_started', { skill_name: 'my_custom_skill' })
    expect(ev.type).toBe('ui_tool_start')
    // Falls back to raw name since not in map — acceptable (no Chinese mapping available)
    expect(ev.detail).toBe('my_custom_skill')
  })

  it('SKILL_DISPLAY_NAMES export covers key skills', () => {
    expect(SKILL_DISPLAY_NAMES['general_financial_answer_skill']).toBe('智能问答')
    expect(SKILL_DISPLAY_NAMES['report_explanation_skill']).toBe('报告解读')
  })
})

// ---------------------------------------------------------------------------
// Problem 2 — final_answer.data_quality syncs thinking item
// ---------------------------------------------------------------------------

describe('chatReducer — ui_final_answer syncs data_quality_review thinking (T4–T6)', () => {
  it('T4: early high thinking replaced by final_answer.data_quality=low', () => {
    const msg = {
      thinkingItems: [],
      finalAnswer: null,
      answerContent: '',
      content: '',
    }

    // 1. Early optimistic thinking: data_quality high
    applyChatUiEvent(msg, {
      type:       'ui_thinking_item',
      source:     'data_quality_review',
      stage:      'data_quality',
      title:      '检查数据质量',
      content:    '数据质量：数据完整。已获取多维度数据，信息完整度高。',
      importance: 'medium',
    })
    expect(msg.thinkingItems[0].content).toContain('数据完整')

    // 2. final_answer arrives with data_quality.level=low
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: {
        full_text: '贵州茅台财报分析',
        data_quality: {
          level:  'low',
          reason: '仅获取到行情或新闻数据',
          verified_data: ['实时行情'],
          missing_data:  ['财务数据'],
        },
      },
    })

    // T4: thinking item must now reflect "数据有限" (low level)
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].content).toContain('数据有限')
    expect(msg.thinkingItems[0].content).not.toContain('数据完整')
  })

  it('T5: final_answer upserts new item when no prior thinking exists', () => {
    const msg = {
      thinkingItems: [],
      finalAnswer: null,
      answerContent: '',
      content: '',
    }

    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: {
        data_quality: { level: 'medium', reason: '部分数据' },
      },
    })

    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].source).toBe('data_quality_review')
    expect(msg.thinkingItems[0].stage).toBe('data_quality')
    expect(msg.thinkingItems[0].content).toContain('数据部分完整')
  })

  it('T6: data_quality level labels match card labels exactly', () => {
    const LEVEL_MAP = {
      high:         '数据完整',
      medium:       '数据部分完整',
      low:          '数据有限',
      insufficient: '数据不足',
    }
    for (const [level, expectedLabel] of Object.entries(LEVEL_MAP)) {
      const msg = { thinkingItems: [], finalAnswer: null, answerContent: '', content: '' }
      applyChatUiEvent(msg, {
        type: 'ui_final_answer',
        data: { data_quality: { level } },
      })
      expect(msg.thinkingItems[0]?.content).toContain(expectedLabel)
    }
  })

  it('no thinkingItems pushed when data_quality absent from final_answer', () => {
    const msg = { thinkingItems: [], finalAnswer: null, answerContent: '', content: '' }
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { full_text: '分析完成', summary: '茅台稳健' },  // no data_quality
    })
    expect(msg.thinkingItems).toHaveLength(0)
  })

  it('low and insufficient importance is "high" (urgent flag)', () => {
    const msg = { thinkingItems: [], finalAnswer: null, answerContent: '', content: '' }
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'insufficient' } },
    })
    expect(msg.thinkingItems[0].importance).toBe('high')
  })

  it('high importance is "medium" (normal)', () => {
    const msg = { thinkingItems: [], finalAnswer: null, answerContent: '', content: '' }
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { data_quality: { level: 'high' } },
    })
    expect(msg.thinkingItems[0].importance).toBe('medium')
  })
})
