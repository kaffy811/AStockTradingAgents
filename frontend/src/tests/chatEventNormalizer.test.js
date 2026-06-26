/**
 * Tests for chatEventNormalizer.js — Phase 2E-3.
 *
 * Verifies that raw SSE event types + payloads are correctly mapped to
 * standardized UI events.
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeChatEvent,
  TOOL_DISPLAY_NAMES,
  AGENT_DISPLAY_NAMES,
} from '../utils/chatEventNormalizer.js'

// ── T1: tool_call_start → ui_tool_start ───────────────────────────────────────
describe('tool_call_start', () => {
  it('maps to ui_tool_start with correct stepKey and title', () => {
    const result = normalizeChatEvent('tool_call_start', {
      tool_name:    'stock_quote',
      display_name: '查询实时行情',
      arguments:    { symbol: 'AAPL' },
    })
    expect(result.type).toBe('ui_tool_start')
    expect(result.stepKey).toBe('tool:stock_quote')
    expect(result.title).toBe('查询实时行情')
    expect(result.status).toBe('running')
  })

  it('uses TOOL_DISPLAY_NAMES for known tools', () => {
    const r = normalizeChatEvent('tool_call_start', { tool_name: 'financial_rag_search' })
    expect(r.title).toBe(TOOL_DISPLAY_NAMES['financial_rag_search'])
  })

  it('falls back to display_name then tool_name when unknown', () => {
    const r1 = normalizeChatEvent('tool_call_start', {
      tool_name: 'unknown_tool', display_name: '自定义工具',
    })
    expect(r1.title).toBe('自定义工具')

    const r2 = normalizeChatEvent('tool_call_start', { tool_name: 'another_tool' })
    expect(r2.title).toBe('another_tool')
  })
})

// ── T2: tool_call_result → ui_tool_done ──────────────────────────────────────
describe('tool_call_result', () => {
  it('maps success result correctly', () => {
    const result = normalizeChatEvent('tool_call_result', {
      tool_name:      'stock_kline',
      status:         'success',
      result_summary: '获取 60 日 K 线数据成功',
    })
    expect(result.type).toBe('ui_tool_done')
    expect(result.stepKey).toBe('tool:stock_kline')
    expect(result.status).toBe('success')
    expect(result.summary).toBe('获取 60 日 K 线数据成功')
  })

  it('maps failure result correctly', () => {
    const result = normalizeChatEvent('tool_call_result', {
      tool_name: 'stock_quote',
      status:    'error',
    })
    expect(result.type).toBe('ui_tool_done')
    expect(result.status).toBe('error')
    expect(result.summary).toBe('失败')
  })
})

// ── T3: subagent_start → ui_step_start ───────────────────────────────────────
describe('subagent_start', () => {
  it('maps fundamental_agent with Chinese display name', () => {
    const result = normalizeChatEvent('subagent_start', {
      agent_name:   'fundamental_agent',
      display_name: 'Fundamental Agent',
    })
    expect(result.type).toBe('ui_step_start')
    expect(result.stepKey).toBe('agent:fundamental_agent')
    expect(result.title).toBe(AGENT_DISPLAY_NAMES['fundamental_agent'])
    expect(result.status).toBe('running')
  })

  it('falls back to display_name for unknown agent names', () => {
    const r = normalizeChatEvent('subagent_start', {
      agent_name:   'custom_agent',
      display_name: '自定义 Agent',
    })
    expect(r.title).toBe('自定义 Agent')
  })
})

// ── T4: subagent_result → ui_step_done ───────────────────────────────────────
describe('subagent_result', () => {
  it('maps success with summary and risk_flags', () => {
    const result = normalizeChatEvent('subagent_result', {
      agent_name:    'market_agent',
      status:        'success',
      summary:       '行情数据分析完成',
      risk_flags:    ['波动较大'],
      sources_count: 3,
    })
    expect(result.type).toBe('ui_step_done')
    expect(result.stepKey).toBe('agent:market_agent')
    expect(result.status).toBe('success')
    expect(result.summary).toBe('行情数据分析完成')
    expect(result.riskFlags).toEqual(['波动较大'])
    expect(result.sourcesCount).toBe(3)
  })

  it('maps partial status', () => {
    const r = normalizeChatEvent('subagent_result', {
      agent_name: 'fundamental_agent',
      status:     'partial',
      summary:    '未找到官方财报',
    })
    expect(r.status).toBe('partial')
  })
})

// ── T5: risk_review_start/result with stage ───────────────────────────────────
describe('risk_review events', () => {
  it('pre_synthesis start has correct title', () => {
    const r = normalizeChatEvent('risk_review_start', { stage: 'pre_synthesis' })
    expect(r.type).toBe('ui_step_start')
    expect(r.stepKey).toBe('risk_review:pre_synthesis')
    expect(r.title).toBe('数据与合规审核')
  })

  it('post_synthesis start has distinct title', () => {
    const r = normalizeChatEvent('risk_review_start', { stage: 'post_synthesis' })
    expect(r.stepKey).toBe('risk_review:post_synthesis')
    expect(r.title).toBe('输出合规复核')
  })

  it('risk_review_result passed → success', () => {
    const r = normalizeChatEvent('risk_review_result', {
      stage:   'pre_synthesis',
      passed:  true,
      blocked: false,
    })
    expect(r.type).toBe('ui_step_done')
    expect(r.status).toBe('success')
    expect(r.summary).toBe('审核通过')
  })

  it('risk_review_result blocked → failed with safe message', () => {
    const r = normalizeChatEvent('risk_review_result', {
      stage:   'post_synthesis',
      passed:  false,
      blocked: true,
      issues:  ['发现违规建议性语言: 必涨'],
    })
    expect(r.status).toBe('failed')
    // Summary must not echo the raw violation phrase
    expect(r.summary).not.toContain('必涨')
    expect(r.summary).toContain('合规问题')
  })
})

// ── T6: thinking / answer_delta ──────────────────────────────────────────────
describe('streaming content events', () => {
  it('thinking → ui_thinking_delta', () => {
    const r = normalizeChatEvent('thinking', { content: '我来分析一下' })
    expect(r.type).toBe('ui_thinking_delta')
    expect(r.content).toBe('我来分析一下')
  })

  it('answer_delta with delta field → ui_answer_delta', () => {
    const r = normalizeChatEvent('answer_delta', { delta: '根据行情数据' })
    expect(r.type).toBe('ui_answer_delta')
    expect(r.content).toBe('根据行情数据')
  })

  it('answer_delta with content field (fallback)', () => {
    const r = normalizeChatEvent('answer_delta', { content: '备用字段' })
    expect(r.content).toBe('备用字段')
  })
})

// ── T7: final_answer ──────────────────────────────────────────────────────────
describe('final_answer', () => {
  it('flat payload → ui_final_answer with data', () => {
    const r = normalizeChatEvent('final_answer', {
      summary: '综合结论', analysis: '详细分析', disclaimer: '风险提示',
    })
    expect(r.type).toBe('ui_final_answer')
    expect(r.data.summary).toBe('综合结论')
  })

  it('nested payload (final_answer key) → unwrapped', () => {
    const r = normalizeChatEvent('final_answer', {
      final_answer: { summary: '嵌套结论', analysis: '嵌套分析' },
    })
    expect(r.data.summary).toBe('嵌套结论')
  })
})

// ── T8: terminal events ───────────────────────────────────────────────────────
describe('terminal events', () => {
  it('agent_completed → ui_done', () => {
    expect(normalizeChatEvent('agent_completed', {})).toEqual({ type: 'ui_done' })
  })

  it('agent_error → ui_error with message', () => {
    const r = normalizeChatEvent('agent_error', { error: '连接超时' })
    expect(r.type).toBe('ui_error')
    expect(r.message).toBe('连接超时')
  })
})

// ── T9: unknown SSE event → null (no crash) ───────────────────────────────────
describe('unknown events', () => {
  it('returns null for unrecognized event types', () => {
    expect(normalizeChatEvent('totally_unknown_event_xyz', { data: 1 })).toBeNull()
    expect(normalizeChatEvent('keepalive', {})).toBeNull()
    expect(normalizeChatEvent('user_message_saved', {})).toBeNull()
  })

  it('handles undefined payload without crashing', () => {
    expect(() => normalizeChatEvent('tool_call_start', undefined)).not.toThrow()
    expect(() => normalizeChatEvent('agent_error', null)).not.toThrow()
  })
})

// ── T10: RAG events ───────────────────────────────────────────────────────────
describe('rag events', () => {
  it('rag_retrieve_started → ui_tool_start', () => {
    const r = normalizeChatEvent('rag_retrieve_started', {})
    expect(r.type).toBe('ui_tool_start')
    expect(r.stepKey).toBe('tool:rag_retrieve')
    expect(r.title).toBe('检索金融知识库')
  })

  it('rag_retrieve_completed success → includes document count', () => {
    const r = normalizeChatEvent('rag_retrieve_completed', {
      ok: true, documents_count: 5, source_types: ['annual_report'],
    })
    expect(r.type).toBe('ui_tool_done')
    expect(r.status).toBe('success')
    expect(r.summary).toContain('5')
  })

  it('rag_retrieve_completed failure', () => {
    const r = normalizeChatEvent('rag_retrieve_completed', { ok: false })
    expect(r.status).toBe('error')
    expect(r.summary).toBe('RAG 检索失败')
  })
})

// ── T11: synthesis_start / orchestrator_start ─────────────────────────────────
describe('orchestrator events', () => {
  it('orchestrator_start → ui_step_start with title', () => {
    const r = normalizeChatEvent('orchestrator_start', { query: '分析茅台' })
    expect(r.type).toBe('ui_step_start')
    expect(r.stepKey).toBe('orchestrator')
    expect(r.summary).toContain('分析茅台')
  })

  it('synthesis_start → ui_step_start synthesis', () => {
    const r = normalizeChatEvent('synthesis_start', {})
    expect(r.type).toBe('ui_step_start')
    expect(r.stepKey).toBe('synthesis')
    expect(r.title).toBe('综合生成分析结论')
  })
})
