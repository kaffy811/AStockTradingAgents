/**
 * C31 Dynamic Agent Thinking Mode — frontend tests.
 *
 * T20–T22  (C31.5): ChatThinkingMiniPanel PHASE_LABELS + visibleSteps
 * T23      (C31.5): deep_reasoning content flows through to visibleSteps
 * T24      (C31.5): No thinkingEvents → fallback template shown
 * T25      (C31.5): Internal skill snake_case names not shown
 * T26      (C31.6): normalizeChatEvent maps thinking_event → ui_thinking_event
 * T27      (C31.6): chatReducer upserts thinkingEvents into message
 * T28      (C31.6): Same phase running → completed overwrites in-place
 * T29      (C31.6): MiniPanel uses thinkingEvents when present (priority over legacy)
 */

import { describe, it, expect } from 'vitest'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'
import { applyChatUiEvent }   from '../utils/chatReducer.js'

// ── T26–T28 helpers ────────────────────────────────────────────────────────

function freshMessage() {
  return {
    reasoningSteps:  [],
    toolTrace:       [],
    thinkingContent: '',
    thinkingEvents:  [],
    thinkingItems:   [],
    answerContent:   '',
    content:         '',
    finalAnswer:     null,
    agentTrace:      [],
    status:          'connecting',
    isStreaming:     true,
    error:           null,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// T20–T25: C31.5 — ChatThinkingMiniPanel logic (pure JS, no Vue mount)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mirror the filteredThinkingEvents + visibleSteps logic from ChatThinkingMiniPanel.vue
 * so we can test it without a full Vue mount.
 */
const PHASE_LABELS = {
  problem_analysis:   '问题分析',
  intent_decision:    '意图识别',
  planning:           '自主规划',
  task_decomposition: '任务拆解',
  agent_dispatch:     'Agent 调度',
  agent_observation:  '数据观测',
  deep_reasoning:     '深度思考',
  risk_review:        '风险审查',
  synthesis:          '回答生成',
}

function filterThinkingEvents(events) {
  return (events ?? []).filter(ev => {
    if (!ev || !ev.phase) return false
    if (!ev.content && !ev.title) return false
    if (ev.phase === 'intent_decision') return false
    if (!ev.content) return false
    return true
  })
}

function buildVisibleSteps(thinkingEvents) {
  const filtered = filterThinkingEvents(thinkingEvents)
  if (filtered.length > 0) {
    return filtered.map(ev => ({
      phase:   ev.phase,
      title:   PHASE_LABELS[ev.phase] || ev.title || ev.phase,
      content: ev.content,
      agent:   ev.agent || '',
      status:  ev.status || 'completed',
    }))
  }
  // Fallback template (partial)
  return null
}

describe('C31.5 ChatThinkingMiniPanel — event-driven steps', () => {

  it('T20: problem_analysis phase renders as "问题分析"', () => {
    const events = [
      { phase: 'problem_analysis', content: '用户想了解半导体行业热点', status: 'completed', agent: '' },
    ]
    const steps = buildVisibleSteps(events)
    expect(steps).not.toBeNull()
    expect(steps[0].title).toBe('问题分析')
  })

  it('T21: planning phase renders as "自主规划"', () => {
    const events = [
      { phase: 'planning', content: '规划调用IndustryAgent和NewsAgent', status: 'completed', agent: '' },
    ]
    const steps = buildVisibleSteps(events)
    expect(steps[0].title).toBe('自主规划')
  })

  it('T22: agent_dispatch step includes agent badge when agent field is set', () => {
    const events = [
      {
        phase:   'agent_dispatch',
        content: '正在调度IndustryAgent',
        status:  'running',
        agent:   'IndustryAgent',
      },
    ]
    const steps = buildVisibleSteps(events)
    expect(steps[0].agent).toBe('IndustryAgent')
    expect(steps[0].status).toBe('running')
  })

  it('T23: deep_reasoning content flows through to visibleSteps.content', () => {
    const events = [
      {
        phase:   'deep_reasoning',
        content: '正在综合行情和新闻数据，区分短期热度与中长期趋势，不给出确定性判断。',
        status:  'completed',
        agent:   '',
      },
    ]
    const steps = buildVisibleSteps(events)
    expect(steps[0].title).toBe('深度思考')
    expect(steps[0].content).toContain('趋势')
  })

  it('T24: empty thinkingEvents → fallback template returned (null from helper)', () => {
    const steps = buildVisibleSteps([])
    // Our helper returns null for empty → caller uses legacy template
    expect(steps).toBeNull()
  })

  it('T25: intent_decision phase is excluded (too internal for users)', () => {
    const events = [
      { phase: 'intent_decision',  content: '意图: industry_research', status: 'completed', agent: '' },
      { phase: 'problem_analysis', content: '用户询问行业热点',         status: 'completed', agent: '' },
    ]
    const steps = buildVisibleSteps(events)
    const phases = steps.map(s => s.phase)
    expect(phases).not.toContain('intent_decision')
    expect(phases).toContain('problem_analysis')
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T26–T29: C31.6 — normalizeChatEvent + chatReducer
// ─────────────────────────────────────────────────────────────────────────────

describe('C31.6 normalizeChatEvent — thinking_event → ui_thinking_event', () => {

  it('T26: thinking_event raw type maps to ui_thinking_event', () => {
    const payload = {
      phase:      'deep_reasoning',
      title:      '深度思考',
      content:    '正在分析行业趋势',
      status:     'completed',
      agent:      '',
      importance: 'high',
      timestamp:  '2026-06-28T10:00:00Z',
    }
    const result = normalizeChatEvent('thinking_event', payload)
    expect(result).not.toBeNull()
    expect(result.type).toBe('ui_thinking_event')
    expect(result.phase).toBe('deep_reasoning')
    expect(result.content).toBe('正在分析行业趋势')
    expect(result.status).toBe('completed')
  })

  it('T26b: thinking_event with missing fields gets safe defaults', () => {
    const result = normalizeChatEvent('thinking_event', { phase: 'synthesis' })
    expect(result.type).toBe('ui_thinking_event')
    expect(result.phase).toBe('synthesis')
    expect(result.title).toBe('')
    expect(result.content).toBe('')
    expect(result.status).toBe('completed')
    expect(result.agent).toBe('')
  })

})

describe('C31.6 chatReducer — thinkingEvents upsert', () => {

  it('T27: ui_thinking_event pushes new entry into message.thinkingEvents', () => {
    const msg = freshMessage()
    const uiEv = {
      type:      'ui_thinking_event',
      phase:     'problem_analysis',
      title:     '问题分析',
      content:   '用户想了解行业热点',
      status:    'completed',
      agent:     '',
      importance:'medium',
      timestamp: null,
    }
    applyChatUiEvent(msg, uiEv)
    expect(msg.thinkingEvents).toHaveLength(1)
    expect(msg.thinkingEvents[0].phase).toBe('problem_analysis')
    expect(msg.thinkingEvents[0].content).toBe('用户想了解行业热点')
  })

  it('T28: same phase running → completed overwrites the existing slot', () => {
    const msg = freshMessage()

    // First event: running
    applyChatUiEvent(msg, {
      type: 'ui_thinking_event', phase: 'deep_reasoning', title: '深度思考',
      content: '正在分析…', status: 'running', agent: '', importance: 'medium', timestamp: null,
    })
    expect(msg.thinkingEvents).toHaveLength(1)
    expect(msg.thinkingEvents[0].status).toBe('running')

    // Second event: completed — same phase, same agent → overwrites
    applyChatUiEvent(msg, {
      type: 'ui_thinking_event', phase: 'deep_reasoning', title: '深度思考',
      content: '分析完成，区分了短期热度与长期趋势。', status: 'completed', agent: '', importance: 'high', timestamp: null,
    })
    // Must still be length 1 (not 2)
    expect(msg.thinkingEvents).toHaveLength(1)
    expect(msg.thinkingEvents[0].status).toBe('completed')
    expect(msg.thinkingEvents[0].content).toBe('分析完成，区分了短期热度与长期趋势。')
  })

  it('T28b: different agents produce separate slots for same phase', () => {
    const msg = freshMessage()

    applyChatUiEvent(msg, {
      type: 'ui_thinking_event', phase: 'agent_observation', title: '数据观测',
      content: 'IndustryAgent 返回行业数据', status: 'completed',
      agent: 'IndustryAgent', importance: 'medium', timestamp: null,
    })
    applyChatUiEvent(msg, {
      type: 'ui_thinking_event', phase: 'agent_observation', title: '数据观测',
      content: 'NewsAgent 返回新闻数据', status: 'completed',
      agent: 'NewsAgent', importance: 'medium', timestamp: null,
    })
    // Different agents → two separate slots
    expect(msg.thinkingEvents).toHaveLength(2)
  })

  it('T29: thinkingEvents coexist with legacy thinkingItems (no cross-contamination)', () => {
    const msg = freshMessage()

    // Legacy thinkingItem via ui_thinking_item
    applyChatUiEvent(msg, {
      type:       'ui_thinking_item',
      source:     'agent_step',
      stage:      'planning',
      title:      'Planning',
      content:    '选择分析 Agent',
      importance: 'medium',
    })

    // New-style thinkingEvent via ui_thinking_event
    applyChatUiEvent(msg, {
      type:      'ui_thinking_event',
      phase:     'planning',
      title:     '自主规划',
      content:   '规划任务序列',
      status:    'completed',
      agent:     '',
      importance:'medium',
      timestamp: null,
    })

    // Both arrays should be populated independently
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingEvents).toHaveLength(1)
    expect(msg.thinkingItems[0].source).toBe('agent_step')
    expect(msg.thinkingEvents[0].phase).toBe('planning')
  })

})
