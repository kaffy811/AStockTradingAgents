/**
 * chatC2512ToolDedup.test.js — Phase C25.12 frontend tests.
 *
 * T6: Same get_recent_reports_tool key fired twice → only one trace entry,
 *     summary is updated to the more specific result.
 * T7: Phase-5 fallback empty-summary second event does not overwrite good summary.
 * T8: Distinct tools still produce separate trace entries.
 */
import { describe, it, expect } from 'vitest'
import { applyChatUiEvent } from '../utils/chatReducer.js'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'

function makeMsg() {
  return {
    id: 'msg-c2512',
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

// ── T6: Same tool fired twice → single trace entry, best summary kept ─────────

describe('get_recent_reports_tool deduplication', () => {
  it('T6a: two tool_call_start + tool_call_result pairs produce ONE trace entry', () => {
    const msg = makeMsg()

    // First pair (unfiltered: 3 reports)
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool',
      status: 'success',
      result_summary: '找到 3 份历史报告',
    }))

    // Second pair simulating Phase-5 or filtered result (2 reports)
    // This is a tool_started + tool_completed (legacy format)
    applyChatUiEvent(msg, {
      type: 'ui_tool_done',
      stepKey: 'tool:get_recent_reports_tool',
      title: '查找历史报告',
      status: 'success',
      summary: '找到 2 份匹配报告',
    })

    const entries = msg.toolTrace.filter(t => t.key === 'tool:get_recent_reports_tool')
    expect(entries).toHaveLength(1)
  })

  it('T6b: second event with non-empty summary updates the existing entry summary', () => {
    const msg = makeMsg()

    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool',
      status: 'success',
      result_summary: '找到 3 份历史报告',
    }))

    // Second done with more specific summary
    applyChatUiEvent(msg, {
      type: 'ui_tool_done',
      stepKey: 'tool:get_recent_reports_tool',
      title: '查找历史报告',
      status: 'success',
      summary: '找到 2 份匹配报告',
    })

    const entry = msg.toolTrace.find(t => t.key === 'tool:get_recent_reports_tool')
    expect(entry?.summary).toBe('找到 2 份匹配报告')
  })

  it('T6c: second event with EMPTY summary does NOT overwrite the existing good summary', () => {
    const msg = makeMsg()

    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool',
      status: 'success',
      result_summary: '找到 3 份历史报告',
    }))

    // Phase-5 re-emission with empty summary (the _result_event puts text in 'detail', not 'summary')
    applyChatUiEvent(msg, {
      type: 'ui_tool_done',
      stepKey: 'tool:get_recent_reports_tool',
      title: '查找历史报告',
      status: 'success',
      summary: '',  // empty from Phase 5 fallback
    })

    const entry = msg.toolTrace.find(t => t.key === 'tool:get_recent_reports_tool')
    // Good summary must be preserved
    expect(entry?.summary).toBe('找到 3 份历史报告')
    expect(entry?.summary).not.toBe('')
  })
})

// ── T7: Orphan done (no prior start) still creates entry ─────────────────────

describe('orphan done entry', () => {
  it('T7: orphan done entry is still created if no prior entry exists', () => {
    const msg = makeMsg()

    // No start event — only done event
    applyChatUiEvent(msg, {
      type: 'ui_tool_done',
      stepKey: 'tool:get_recent_reports_tool',
      title: '查找历史报告',
      status: 'success',
      summary: '找到 3 份历史报告',
    })

    const entry = msg.toolTrace.find(t => t.key === 'tool:get_recent_reports_tool')
    expect(entry).toBeTruthy()
    expect(entry?.summary).toBe('找到 3 份历史报告')
    expect(entry?.status).toBe('success')
  })
})

// ── T8: Two distinct tools produce two entries ─────────────────────────────────

describe('distinct tools produce separate entries', () => {
  it('T8: get_recent_reports_tool and get_report_detail_tool are separate', () => {
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
    expect(recentEntry?.key).not.toBe(detailEntry?.key)
  })
})
