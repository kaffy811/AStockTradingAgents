/**
 * Tests for chatReducer.js — Phase 2E-3.
 *
 * Verifies that applyChatUiEvent correctly mutates message state for each
 * UI event type.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { applyChatUiEvent } from '../utils/chatReducer.js'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'

/** Create a fresh reactive-like message object */
function makeMsg(overrides = {}) {
  return {
    id:              'test-msg-1',
    role:            'assistant',
    content:         '',
    status:          'connecting',
    isStreaming:     true,
    reasoningSteps:  [],
    toolTrace:       [],
    agentTrace:      [],
    thinkingContent: '',
    answerContent:   '',
    finalAnswer:     null,
    error:           null,
    ...overrides,
  }
}

// ── T1: ui_step_start inserts a running step ──────────────────────────────────
describe('ui_step_start', () => {
  it('inserts a new running step into reasoningSteps', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_step_start', stepKey: 'orchestrator', title: '多 Agent 研究开始', summary: '分析: 茅台',
    })
    expect(msg.reasoningSteps).toHaveLength(1)
    expect(msg.reasoningSteps[0].key).toBe('orchestrator')
    expect(msg.reasoningSteps[0].status).toBe('running')
    expect(msg.reasoningSteps[0].title).toBe('多 Agent 研究开始')
  })

  it('does not add duplicate running entry for same stepKey', () => {
    const msg = makeMsg()
    const evt = { type: 'ui_step_start', stepKey: 'agent:market_agent', title: '行情分析 Agent', summary: '' }
    applyChatUiEvent(msg, evt)
    applyChatUiEvent(msg, evt)  // duplicate
    expect(msg.reasoningSteps).toHaveLength(1)
  })

  it('also syncs agentTrace for backward compat', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_step_start', stepKey: 'agent:fundamental_agent', title: '基本面分析 Agent', summary: '',
    })
    expect(msg.agentTrace).toHaveLength(1)
    expect(msg.agentTrace[0].displayName).toBe('基本面分析 Agent')
  })
})

// ── T2: ui_step_done updates the running step ─────────────────────────────────
describe('ui_step_done', () => {
  it('updates status and summary of running step', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_step_start', stepKey: 'agent:market_agent', title: '行情分析 Agent', summary: '',
    })
    applyChatUiEvent(msg, {
      type: 'ui_step_done', stepKey: 'agent:market_agent',
      status: 'success', summary: '行情数据分析完成', riskFlags: [],
    })
    expect(msg.reasoningSteps[0].status).toBe('success')
    expect(msg.reasoningSteps[0].summary).toBe('行情数据分析完成')
    expect(msg.reasoningSteps[0].finishedAt).toBeTypeOf('number')
  })

  it('marks step as partial when status=partial', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_step_start', stepKey: 'agent:fundamental_agent', title: '基本面分析 Agent', summary: '',
    })
    applyChatUiEvent(msg, {
      type: 'ui_step_done', stepKey: 'agent:fundamental_agent',
      status: 'partial', summary: '未找到官方财报', riskFlags: ['数据受限'],
    })
    expect(msg.reasoningSteps[0].status).toBe('partial')
    expect(msg.reasoningSteps[0].riskFlags).toEqual(['数据受限'])
  })

  it('does nothing if no matching running step', () => {
    const msg = makeMsg()
    // No step started — done should not crash
    expect(() => applyChatUiEvent(msg, {
      type: 'ui_step_done', stepKey: 'agent:unknown', status: 'success', summary: '',
    })).not.toThrow()
    expect(msg.reasoningSteps).toHaveLength(0)
  })
})

// ── T3: ui_tool_start inserts tool entry ─────────────────────────────────────
describe('ui_tool_start', () => {
  it('adds a running tool entry to toolTrace', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_tool_start', stepKey: 'tool:stock_quote', title: '查询实时行情', status: 'running', detail: '',
    })
    expect(msg.toolTrace).toHaveLength(1)
    expect(msg.toolTrace[0].key).toBe('tool:stock_quote')
    expect(msg.toolTrace[0].title).toBe('查询实时行情')
    expect(msg.toolTrace[0].status).toBe('running')
    expect(msg.toolTrace[0].summary).toBe('执行中…')
  })

  it('does not exceed 20 entries', () => {
    const msg = makeMsg()
    for (let i = 0; i < 25; i++) {
      applyChatUiEvent(msg, {
        type: 'ui_tool_start', stepKey: `tool:t${i}`, title: `工具${i}`, status: 'running', detail: '',
      })
    }
    expect(msg.toolTrace.length).toBeLessThanOrEqual(20)
  })
})

// ── T4: ui_tool_done updates tool entry ──────────────────────────────────────
describe('ui_tool_done', () => {
  it('updates running tool entry to success', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_tool_start', stepKey: 'tool:stock_kline', title: '查询 K 线数据', status: 'running', detail: '',
    })
    applyChatUiEvent(msg, {
      type: 'ui_tool_done', stepKey: 'tool:stock_kline',
      title: '查询 K 线数据', status: 'success', summary: '获取 60 日数据成功',
    })
    expect(msg.toolTrace[0].status).toBe('success')
    expect(msg.toolTrace[0].summary).toBe('获取 60 日数据成功')
  })

  it('adds a completed entry if no running entry exists', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_tool_done', stepKey: 'tool:financial_news',
      title: '检索相关新闻', status: 'success', summary: '找到 5 条新闻',
    })
    expect(msg.toolTrace).toHaveLength(1)
    expect(msg.toolTrace[0].status).toBe('success')
  })
})

// ── T5: ui_thinking_delta accumulates ─────────────────────────────────────────
describe('ui_thinking_delta', () => {
  it('appends to thinkingContent', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_thinking_delta', content: '我需要分析' })
    applyChatUiEvent(msg, { type: 'ui_thinking_delta', content: '一下茅台的财报' })
    expect(msg.thinkingContent).toBe('我需要分析一下茅台的财报')
  })
})

// ── T6: ui_answer_delta accumulates and syncs content ─────────────────────────
describe('ui_answer_delta', () => {
  it('appends to answerContent and mirrors to content', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_answer_delta', content: '根据行情数据' })
    applyChatUiEvent(msg, { type: 'ui_answer_delta', content: '，茅台近期' })
    expect(msg.answerContent).toBe('根据行情数据，茅台近期')
    expect(msg.content).toBe('根据行情数据，茅台近期')
  })
})

// ── T7: ui_final_answer ───────────────────────────────────────────────────────
describe('ui_final_answer', () => {
  it('sets finalAnswer', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { summary: '综合结论', analysis: '详细分析', disclaimer: '风险提示', sources: [] },
    })
    expect(msg.finalAnswer.summary).toBe('综合结论')
  })

  it('fills content from finalAnswer when answerContent is empty', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { summary: '综合结论', analysis: '详细分析' },
    })
    expect(msg.content).toContain('综合结论')
    expect(msg.content).toContain('详细分析')
  })

  it('does NOT overwrite content if answerContent already has text', () => {
    const msg = makeMsg({ answerContent: '流式文本', content: '流式文本' })
    applyChatUiEvent(msg, {
      type: 'ui_final_answer',
      data: { summary: '综合结论' },
    })
    // content should remain the streaming text, not be overwritten
    expect(msg.content).toBe('流式文本')
  })
})

// ── T8: ui_done finalizes all running items ────────────────────────────────────
describe('ui_done', () => {
  it('sets status=done, isStreaming=false', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.status).toBe('done')
    expect(msg.isStreaming).toBe(false)
  })

  it('marks remaining running steps as success', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_step_start', stepKey: 'synthesis', title: '综合生成分析结论', summary: '',
    })
    applyChatUiEvent(msg, {
      type: 'ui_tool_start', stepKey: 'tool:stock_quote', title: '查询实时行情', status: 'running', detail: '',
    })
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.reasoningSteps[0].status).toBe('success')
    expect(msg.toolTrace[0].status).toBe('success')
  })
})

// ── T9: ui_error marks failure state ─────────────────────────────────────────
describe('ui_error', () => {
  it('sets status=error and error field', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_error', message: '连接超时' })
    expect(msg.status).toBe('error')
    expect(msg.isStreaming).toBe(false)
    expect(msg.error).toBe('连接超时')
  })

  it('fills content with error message when content empty', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, { type: 'ui_error', message: '服务暂时不可用' })
    expect(msg.content).toBe('服务暂时不可用')
  })

  it('marks running steps as failed', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, {
      type: 'ui_step_start', stepKey: 'agent:market_agent', title: '行情分析 Agent', summary: '',
    })
    applyChatUiEvent(msg, {
      type: 'ui_tool_start', stepKey: 'tool:stock_quote', title: '查询实时行情', status: 'running', detail: '',
    })
    applyChatUiEvent(msg, { type: 'ui_error', message: '超时' })
    expect(msg.reasoningSteps[0].status).toBe('failed')
    expect(msg.toolTrace[0].status).toBe('error')
  })
})

// ── T10: unknown UI event is silently ignored ─────────────────────────────────
describe('unknown UI events', () => {
  it('does not crash or mutate message on unknown event type', () => {
    const msg = makeMsg()
    const before = JSON.stringify(msg)
    applyChatUiEvent(msg, { type: 'ui_unknown_future_event', data: 'whatever' })
    // Structural fields should be unchanged (timestamps may differ if set)
    expect(msg.status).toBe('connecting')
    expect(msg.reasoningSteps).toHaveLength(0)
  })

  it('handles null event gracefully', () => {
    const msg = makeMsg()
    expect(() => applyChatUiEvent(msg, null)).not.toThrow()
  })
})

// ── T11: combined scenario — orchestrator flow ────────────────────────────────
describe('full orchestrator scenario', () => {
  it('runs orchestrator → subagent → risk_review → synthesis → done', () => {
    const msg = makeMsg()

    // orchestrator start
    applyChatUiEvent(msg, normalizeChatEventProxy('orchestrator_start', { query: '分析茅台' }))
    // subagent start + result
    applyChatUiEvent(msg, normalizeChatEventProxy('subagent_start', { agent_name: 'fundamental_agent' }))
    applyChatUiEvent(msg, normalizeChatEventProxy('subagent_result', {
      agent_name: 'fundamental_agent', status: 'partial', summary: '未找到官方财报',
    }))
    // risk review pre
    applyChatUiEvent(msg, normalizeChatEventProxy('risk_review_start', { stage: 'pre_synthesis' }))
    applyChatUiEvent(msg, normalizeChatEventProxy('risk_review_result', {
      stage: 'pre_synthesis', passed: true, blocked: false,
    }))
    // synthesis
    applyChatUiEvent(msg, normalizeChatEventProxy('synthesis_start', {}))
    // answer delta
    applyChatUiEvent(msg, normalizeChatEventProxy('answer_delta', { delta: '综合分析结论如下' }))
    // done
    applyChatUiEvent(msg, { type: 'ui_done' })

    expect(msg.reasoningSteps.length).toBeGreaterThanOrEqual(4)
    expect(msg.reasoningSteps.find(s => s.key === 'agent:fundamental_agent')?.status).toBe('partial')
    expect(msg.reasoningSteps.find(s => s.key === 'risk_review:pre_synthesis')?.status).toBe('success')
    expect(msg.answerContent).toBe('综合分析结论如下')
    expect(msg.status).toBe('done')
    expect(msg.isStreaming).toBe(false)
  })
})

// Helper: alias for ergonomic use inside this file
function normalizeChatEventProxy(type, payload) {
  return normalizeChatEvent(type, payload)
}
