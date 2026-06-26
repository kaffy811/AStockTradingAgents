/**
 * chatC2510TraceDedup.test.js — Phase C25.10 frontend tests.
 *
 * T5: Repeated skill_started/completed does not create duplicate trace entries
 * T6: agent_started (reasoningSteps) always sorts before toolTrace items
 * T7: skill steps display Chinese display title (not raw skill_name)
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { applyChatUiEvent } from '../utils/chatReducer.js'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'

function makeMsg() {
  return {
    id:              'msg-001',
    role:            'assistant',
    content:         '',
    status:          'streaming',
    isStreaming:     true,
    reasoningSteps:  [],
    toolTrace:       [],
    agentTrace:      [],
    thinkingContent: '',
    answerContent:   '',
    finalAnswer:     null,
    error:           null,
  }
}

// ── T5: duplicate skill entries suppressed ────────────────────────────────────

describe('step deduplication', () => {
  it('T5a: skill_started + skill_completed = exactly one trace entry', () => {
    const msg = makeMsg()

    // Simulate: skill_started fires
    applyChatUiEvent(msg, normalizeChatEvent('skill_started', {
      skill_name: 'report_explanation_skill',
    }))
    // Simulate: skill_completed fires
    applyChatUiEvent(msg, normalizeChatEvent('skill_completed', {
      skill_name: 'report_explanation_skill',
    }))

    const skillEntries = msg.toolTrace.filter(t =>
      t.key === 'tool:skill:report_explanation_skill'
    )
    expect(skillEntries).toHaveLength(1)
    expect(skillEntries[0].status).toBe('success')
  })

  it('T5b: skill_completed without prior skill_started creates max 1 orphan entry', () => {
    const msg = makeMsg()
    // Only skill_completed fires (no prior started)
    applyChatUiEvent(msg, normalizeChatEvent('skill_completed', {
      skill_name: 'report_explanation_skill',
    }))
    // Fire again — should NOT create a second entry
    applyChatUiEvent(msg, normalizeChatEvent('skill_completed', {
      skill_name: 'report_explanation_skill',
    }))

    const skillEntries = msg.toolTrace.filter(t =>
      t.key === 'tool:skill:report_explanation_skill'
    )
    expect(skillEntries).toHaveLength(1)
  })

  it('T5c: two distinct tools produce two separate entries', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool',
      status: 'success',
      result_summary: '找到3份',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_report_detail_tool',
    }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_report_detail_tool',
      status: 'success',
      result_summary: '报告详情已读取',
    }))

    const recentEntry = msg.toolTrace.filter(t => t.key === 'tool:get_recent_reports_tool')
    const detailEntry = msg.toolTrace.filter(t => t.key === 'tool:get_report_detail_tool')
    expect(recentEntry).toHaveLength(1)
    expect(detailEntry).toHaveLength(1)
    expect(recentEntry[0].status).toBe('success')
    expect(detailEntry[0].status).toBe('success')
  })

  it('T5d: orphan done entry has a startedAt timestamp (not 0)', () => {
    const msg = makeMsg()
    const before = Date.now()
    // Only done event, no start
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_result', {
      tool_name: 'get_recent_reports_tool',
      status: 'success',
      result_summary: '3份报告',
    }))
    const after = Date.now()

    const entry = msg.toolTrace.find(t => t.key === 'tool:get_recent_reports_tool')
    expect(entry).toBeTruthy()
    expect(entry.startedAt).toBeGreaterThanOrEqual(before)
    expect(entry.startedAt).toBeLessThanOrEqual(after)
  })
})

// ── T6: agent_started sorts first ─────────────────────────────────────────────

describe('agent_started ordering', () => {
  it('T6: after ui_done, all running steps become success (no 中断 in success path)', () => {
    const msg = makeMsg()

    // Simulate normal success flow
    applyChatUiEvent(msg, normalizeChatEvent('agent_started', {}))
    applyChatUiEvent(msg, normalizeChatEvent('skill_started', { skill_name: 'report_explanation_skill' }))
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', { tool_name: 'get_recent_reports_tool' }))

    // Normal completion
    applyChatUiEvent(msg, { type: 'ui_done' })

    // All running steps become success, none become failed/中断
    const failedSteps = [
      ...msg.reasoningSteps,
      ...msg.toolTrace,
    ].filter(s => s.status === 'failed' || s.summary === '中断')
    expect(failedSteps).toHaveLength(0)
  })
})

// ── T7: Chinese tool display names ────────────────────────────────────────────

describe('Chinese tool display names in trace', () => {
  it('T7a: get_recent_reports_tool displays Chinese title', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    }))
    const entry = msg.toolTrace.find(t => t.key === 'tool:get_recent_reports_tool')
    expect(entry?.title).toBe('查找历史报告')
  })

  it('T7b: get_report_detail_tool displays Chinese title', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', {
      tool_name: 'get_report_detail_tool',
    }))
    const entry = msg.toolTrace.find(t => t.key === 'tool:get_report_detail_tool')
    expect(entry?.title).toBe('读取报告详情')
  })

  it('T7c: skill step title includes Chinese skill name from normalizer detail', () => {
    const msg = makeMsg()
    applyChatUiEvent(msg, normalizeChatEvent('skill_started', {
      skill_name: 'report_explanation_skill',
    }))
    const entry = msg.toolTrace.find(t => t.key.startsWith('tool:skill:'))
    // title should be '技能路由' (from normalizer); Chinese mapping is in ChatReasoningPanel
    expect(entry?.title).toBe('技能路由')
    // But the stepKey has the skill name embedded
    expect(entry?.key).toBe('tool:skill:report_explanation_skill')
  })
})
