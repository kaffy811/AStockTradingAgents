/**
 * chatC259Normalizer.test.js — Phase C25.9 frontend tests.
 *
 * T7: get_recent_reports_tool and get_report_detail_tool have Chinese display names
 * T8: skill_started / skill_completed stepKeys are scoped by skill_name (no duplicate)
 */
import { describe, it, expect } from 'vitest'
import { normalizeChatEvent, TOOL_DISPLAY_NAMES } from '../utils/chatEventNormalizer.js'

// ── T7: Report tool display names ─────────────────────────────────────────────

describe('report tool display names', () => {
  it('T7a: get_recent_reports_tool has Chinese display name', () => {
    expect(TOOL_DISPLAY_NAMES['get_recent_reports_tool']).toBeTruthy()
    expect(typeof TOOL_DISPLAY_NAMES['get_recent_reports_tool']).toBe('string')
    expect(TOOL_DISPLAY_NAMES['get_recent_reports_tool']).toBe('查找历史报告')
  })

  it('T7b: get_report_detail_tool has Chinese display name', () => {
    expect(TOOL_DISPLAY_NAMES['get_report_detail_tool']).toBeTruthy()
    expect(TOOL_DISPLAY_NAMES['get_report_detail_tool']).toBe('读取报告详情')
  })

  it('T7c: tool_call_start uses Chinese name for get_recent_reports_tool', () => {
    const result = normalizeChatEvent('tool_call_start', {
      tool_name: 'get_recent_reports_tool',
    })
    expect(result.type).toBe('ui_tool_start')
    expect(result.title).toBe('查找历史报告')
  })

  it('T7d: tool_call_result uses Chinese name for get_report_detail_tool', () => {
    const result = normalizeChatEvent('tool_call_result', {
      tool_name: 'get_report_detail_tool',
      status: 'success',
      result_summary: '报告详情已获取',
    })
    expect(result.type).toBe('ui_tool_done')
    expect(result.title).toBe('读取报告详情')
    expect(result.status).toBe('success')
  })
})

// ── T8: Skill stepKey deduplication ──────────────────────────────────────────

describe('skill stepKey scoped by skill_name', () => {
  it('T8a: skill_started uses skill_name in stepKey', () => {
    const result = normalizeChatEvent('skill_started', {
      skill_name: 'report_explanation_skill',
      source: 'skill_registry',
    })
    expect(result.type).toBe('ui_tool_start')
    expect(result.stepKey).toBe('tool:skill:report_explanation_skill')
    // detail should include skill name
    expect(result.detail).toBeTruthy()
  })

  it('T8b: skill_completed uses Chinese display name in summary (C28.3: never raw snake_case)', () => {
    const result = normalizeChatEvent('skill_completed', {
      skill_name: 'report_explanation_skill',
    })
    expect(result.type).toBe('ui_tool_done')
    expect(result.stepKey).toBe('tool:skill:report_explanation_skill')
    // C28.3: summary must be Chinese label, not raw snake_case
    expect(result.summary).toBe('报告解读')
    expect(result.summary).not.toContain('report_explanation_skill')
  })

  it('T8c: two different skills produce different stepKeys (no collision)', () => {
    const startA = normalizeChatEvent('skill_started', { skill_name: 'watchlist_skill' })
    const startB = normalizeChatEvent('skill_started', { skill_name: 'report_explanation_skill' })
    expect(startA.stepKey).not.toBe(startB.stepKey)
  })

  it('T8d: skill_started without skill_name falls back gracefully', () => {
    const result = normalizeChatEvent('skill_started', { source: 'skill_registry' })
    expect(result.type).toBe('ui_tool_start')
    // stepKey should still be a string, not crash
    expect(typeof result.stepKey).toBe('string')
    expect(result.stepKey.startsWith('tool:skill:')).toBe(true)
  })
})
