/**
 * chatC2513TraceDedup.test.js — Phase C25.13 frontend tests.
 *
 * T5: get_recent_reports_tool fires two tool_started events (second after first
 *     cycle completed) → only ONE trace entry total, and the better summary
 *     (from the second done event) is kept.
 */
import { describe, it, expect } from 'vitest'
import { applyChatUiEvent } from '../utils/chatReducer.js'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'

function makeMsg() {
  return {
    id: 'msg-c2513',
    role: 'assistant',
    content: '',
    status: 'streaming',
    isStreaming: true,
    reasoningSteps: [],
    toolTrace: [],
    agentTrace: [],
    thinkingContent: '',
    answerContent: '',
    finalAnswer: null,
    error: null,
  }
}

// ── T5: Second tool_started after tool_completed → no second entry ─────────────

describe('C25.13 tool trace deduplication — second tool_started blocked', () => {

  it('T5a: second tool_started for already-completed key creates no new entry', () => {
    const msg = makeMsg()

    // First cycle: start → done
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool',
      status: 'success',
      result_summary: '找到 3 份历史报告',
    }))

    // Second tool_started (Phase 5 re-emission or secondary event)
    applyChatUiEvent(msg, {
      type: 'ui_tool_start',
      stepKey: 'tool:get_recent_reports_tool',
      title: '查找历史报告',
    })

    const entries = msg.toolTrace.filter(t => t.key === 'tool:get_recent_reports_tool')
    expect(entries).toHaveLength(1)
  })

  it('T5b: trace entry remains "success" (not reset to "running") after second start', () => {
    const msg = makeMsg()

    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool',
      status: 'success',
      result_summary: '找到 3 份历史报告',
    }))

    // Second tool_started — must NOT create a new running entry
    applyChatUiEvent(msg, {
      type: 'ui_tool_start',
      stepKey: 'tool:get_recent_reports_tool',
      title: '查找历史报告',
    })

    const entry = msg.toolTrace.find(t => t.key === 'tool:get_recent_reports_tool')
    expect(entry?.status).toBe('success')
    expect(entry?.status).not.toBe('running')
  })

  it('T5c: summary from first good done is preserved when second start fires', () => {
    const msg = makeMsg()

    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool',
      status: 'success',
      result_summary: '找到 3 份历史报告',
    }))

    applyChatUiEvent(msg, {
      type: 'ui_tool_start',
      stepKey: 'tool:get_recent_reports_tool',
      title: '查找历史报告',
    })

    const entry = msg.toolTrace.find(t => t.key === 'tool:get_recent_reports_tool')
    expect(entry?.summary).toBe('找到 3 份历史报告')
  })

  it('T5d: two distinct tools are still separate (non-regression)', () => {
    const msg = makeMsg()

    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', { tool_name: 'get_recent_reports_tool' }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool', status: 'success', result_summary: '找到 3 份',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', { tool_name: 'get_report_detail_tool' }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_report_detail_tool', status: 'success', result_summary: '获取报告详情',
    }))

    const recentEntry = msg.toolTrace.find(t => t.key === 'tool:get_recent_reports_tool')
    const detailEntry = msg.toolTrace.find(t => t.key === 'tool:get_report_detail_tool')
    expect(recentEntry).toBeTruthy()
    expect(detailEntry).toBeTruthy()
    expect(msg.toolTrace).toHaveLength(2)
  })

  it('T5e: three start+done cycles still produce only one entry for same key', () => {
    const msg = makeMsg()

    for (let i = 1; i <= 3; i++) {
      applyChatUiEvent(msg, {
        type: 'ui_tool_start',
        stepKey: 'tool:get_recent_reports_tool',
        title: '查找历史报告',
      })
      applyChatUiEvent(msg, {
        type: 'ui_tool_done',
        stepKey: 'tool:get_recent_reports_tool',
        status: 'success',
        summary: `找到 ${i} 份报告`,
      })
    }

    const entries = msg.toolTrace.filter(t => t.key === 'tool:get_recent_reports_tool')
    expect(entries).toHaveLength(1)
  })
})
